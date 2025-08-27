"""
Connection Optimizer Module

Optimizes network I/O operations for better throughput and scalability.
Includes connection pooling, message batching, and network optimizations.
"""

import socket
import threading
import time
import logging
import zlib
from collections import deque, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Callable
from queue import Queue, Empty
import struct

from chat_app.shared.exceptions import ConnectionOptimizerError


logger = logging.getLogger(__name__)


@dataclass
class ConnectionStats:
    """Statistics for a connection."""
    bytes_sent: int = 0
    bytes_received: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    connection_time: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    
    @property
    def session_duration(self) -> timedelta:
        """Get session duration."""
        return datetime.now() - self.connection_time
    
    @property
    def idle_time(self) -> timedelta:
        """Get idle time since last activity."""
        return datetime.now() - self.last_activity
    
    def update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now()


@dataclass
class MessageBatch:
    """Represents a batch of messages to be sent together."""
    messages: List[bytes] = field(default_factory=list)
    target_socket: Optional[socket.socket] = None
    created_at: datetime = field(default_factory=datetime.now)
    max_size: int = 10
    timeout_seconds: float = 0.1
    
    def add_message(self, message: bytes) -> bool:
        """
        Add a message to the batch.
        
        Args:
            message: Message bytes to add
            
        Returns:
            True if batch is now full and should be sent
        """
        self.messages.append(message)
        return len(self.messages) >= self.max_size
    
    def is_ready_to_send(self) -> bool:
        """Check if batch is ready to send (full or timed out)."""
        if len(self.messages) >= self.max_size:
            return True
        
        age = (datetime.now() - self.created_at).total_seconds()
        return age >= self.timeout_seconds
    
    def get_batched_data(self) -> bytes:
        """Get all messages as a single batched payload."""
        if not self.messages:
            return b''
        
        # Simple batching format: [count][len1][msg1][len2][msg2]...
        batched = struct.pack('!I', len(self.messages))
        
        for message in self.messages:
            batched += struct.pack('!I', len(message))
            batched += message
        
        return batched


class ConnectionPool:
    """
    Connection pool for reusing network connections.
    
    Features:
    - Connection reuse and pooling
    - Automatic connection health checking
    - Connection lifecycle management
    - Statistics tracking
    """
    
    def __init__(
        self,
        max_connections: int = 20,
        connection_timeout: int = 30,
        idle_timeout: int = 300
    ):
        """
        Initialize connection pool.
        
        Args:
            max_connections: Maximum number of pooled connections
            connection_timeout: Timeout for new connections
            idle_timeout: Timeout for idle connections
        """
        self.max_connections = max_connections
        self.connection_timeout = connection_timeout
        self.idle_timeout = idle_timeout
        
        # Connection storage
        self._lock = threading.RLock()
        self._available_connections: Dict[str, List[socket.socket]] = defaultdict(list)
        self._active_connections: Dict[socket.socket, str] = {}
        self._connection_stats: Dict[socket.socket, ConnectionStats] = {}
        
        # Cleanup thread
        self._cleanup_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        
        # Statistics
        self.connections_created = 0
        self.connections_reused = 0
        self.connections_closed = 0
        
        self._start_cleanup_thread()
        
        logger.info(f"ConnectionPool initialized with max_connections={max_connections}")
    
    def get_connection(self, host: str, port: int) -> socket.socket:
        """
        Get a connection from the pool or create a new one.
        
        Args:
            host: Target host
            port: Target port
            
        Returns:
            Socket connection
            
        Raises:
            ConnectionOptimizerError: If connection cannot be established
        """
        pool_key = f"{host}:{port}"
        
        with self._lock:
            # Try to reuse an existing connection
            available = self._available_connections[pool_key]
            
            while available:
                conn = available.pop(0)
                
                # Check if connection is still valid
                if self._is_connection_healthy(conn):
                    self._active_connections[conn] = pool_key
                    stats = self._connection_stats.get(conn)
                    if stats:
                        stats.update_activity()
                    
                    self.connections_reused += 1
                    logger.debug(f"Reused connection to {pool_key}")
                    return conn
                else:
                    # Connection is dead, close it
                    self._close_connection(conn)
        
        # Create new connection
        try:
            conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            conn.settimeout(self.connection_timeout)
            conn.connect((host, port))
            
            # Optimize socket settings
            self._optimize_socket(conn)
            
            with self._lock:
                self._active_connections[conn] = pool_key
                self._connection_stats[conn] = ConnectionStats()
                self.connections_created += 1
            
            logger.debug(f"Created new connection to {pool_key}")
            return conn
            
        except Exception as e:
            raise ConnectionOptimizerError(f"Failed to create connection to {host}:{port}: {e}")
    
    def return_connection(self, conn: socket.socket) -> None:
        """
        Return a connection to the pool.
        
        Args:
            conn: Socket connection to return
        """
        with self._lock:
            pool_key = self._active_connections.pop(conn, None)
            
            if pool_key and self._is_connection_healthy(conn):
                # Return to available pool if under limit
                available = self._available_connections[pool_key]
                
                if len(available) < self.max_connections:
                    available.append(conn)
                    logger.debug(f"Returned connection to pool: {pool_key}")
                    return
            
            # Close connection if not returned to pool
            self._close_connection(conn)
    
    def close_connection(self, conn: socket.socket) -> None:
        """
        Close a connection and remove from pool.
        
        Args:
            conn: Socket connection to close
        """
        with self._lock:
            self._active_connections.pop(conn, None)
            self._close_connection(conn)
    
    def get_pool_statistics(self) -> Dict[str, Any]:
        """
        Get connection pool statistics.
        
        Returns:
            Dictionary with pool statistics
        """
        with self._lock:
            pool_stats = {}
            total_available = 0
            
            for pool_key, connections in self._available_connections.items():
                pool_stats[pool_key] = len(connections)
                total_available += len(connections)
            
            return {
                'max_connections': self.max_connections,
                'total_available': total_available,
                'active_connections': len(self._active_connections),
                'connections_created': self.connections_created,
                'connections_reused': self.connections_reused,
                'connections_closed': self.connections_closed,
                'pool_breakdown': pool_stats
            }
    
    def shutdown(self) -> None:
        """Shutdown the connection pool."""
        logger.info("Shutting down ConnectionPool...")
        
        self._shutdown_event.set()
        
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5.0)
        
        with self._lock:
            # Close all connections
            all_connections = []
            all_connections.extend(self._active_connections.keys())
            
            for connections in self._available_connections.values():
                all_connections.extend(connections)
            
            for conn in all_connections:
                self._close_connection(conn)
            
            self._available_connections.clear()
            self._active_connections.clear()
            self._connection_stats.clear()
        
        logger.info("ConnectionPool shutdown complete")
    
    def _optimize_socket(self, conn: socket.socket) -> None:
        """Apply socket optimizations."""
        try:
            # Enable TCP keepalive
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            
            # Set TCP_NODELAY to disable Nagle's algorithm for low latency
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            
            # Set socket buffer sizes
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
            
            # Platform-specific optimizations
            if hasattr(socket, 'TCP_KEEPIDLE'):
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 300)
            if hasattr(socket, 'TCP_KEEPINTVL'):
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 30)
            if hasattr(socket, 'TCP_KEEPCNT'):
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
                
        except Exception as e:
            logger.warning(f"Failed to optimize socket: {e}")
    
    def _is_connection_healthy(self, conn: socket.socket) -> bool:
        """Check if a connection is still healthy."""
        try:
            # Use MSG_PEEK to check if connection is alive without consuming data
            conn.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT)
            return True
        except socket.error:
            return False
    
    def _close_connection(self, conn: socket.socket) -> None:
        """Close a connection and update statistics."""
        try:
            conn.close()
            self.connections_closed += 1
        except Exception as e:
            logger.error(f"Error closing connection: {e}")
        finally:
            self._connection_stats.pop(conn, None)
    
    def _start_cleanup_thread(self) -> None:
        """Start the cleanup thread for idle connections."""
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            name="ConnectionPool-Cleanup",
            daemon=True
        )
        self._cleanup_thread.start()
    
    def _cleanup_loop(self) -> None:
        """Main cleanup loop for removing idle connections."""
        while not self._shutdown_event.is_set():
            try:
                self._cleanup_idle_connections()
                self._shutdown_event.wait(60)  # Check every minute
            except Exception as e:
                logger.error(f"Connection cleanup error: {e}")
                self._shutdown_event.wait(60)
    
    def _cleanup_idle_connections(self) -> None:
        """Remove idle connections from the pool."""
        current_time = datetime.now()
        connections_to_close = []
        
        with self._lock:
            # Check available connections for idle timeout
            for pool_key, connections in list(self._available_connections.items()):
                for conn in list(connections):
                    stats = self._connection_stats.get(conn)
                    if stats and stats.idle_time.total_seconds() > self.idle_timeout:
                        connections.remove(conn)
                        connections_to_close.append(conn)
        
        # Close idle connections
        for conn in connections_to_close:
            self._close_connection(conn)
            logger.debug("Closed idle connection")


class MessageBatcher:
    """
    Batches messages for efficient network transmission.
    
    Features:
    - Automatic message batching
    - Configurable batch size and timeout
    - Per-connection batching
    - Compression support
    """
    
    def __init__(
        self,
        batch_size: int = 10,
        batch_timeout: float = 0.1,
        enable_compression: bool = False,
        compression_threshold: int = 1024
    ):
        """
        Initialize message batcher.
        
        Args:
            batch_size: Maximum messages per batch
            batch_timeout: Maximum time to wait for batch completion
            enable_compression: Whether to compress batched messages
            compression_threshold: Minimum size for compression
        """
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.enable_compression = enable_compression
        self.compression_threshold = compression_threshold
        
        # Batching state
        self._lock = threading.RLock()
        self._batches: Dict[socket.socket, MessageBatch] = {}
        self._send_queue: Queue = Queue()
        
        # Sender thread
        self._sender_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        
        # Statistics
        self.messages_batched = 0
        self.batches_sent = 0
        self.bytes_saved_by_batching = 0
        self.bytes_saved_by_compression = 0
        
        self._start_sender_thread()
        
        logger.info(f"MessageBatcher initialized with batch_size={batch_size}, timeout={batch_timeout}s")
    
    def queue_message(self, conn: socket.socket, message: bytes) -> None:
        """
        Queue a message for batching and sending.
        
        Args:
            conn: Target socket connection
            message: Message bytes to send
        """
        with self._lock:
            # Get or create batch for this connection
            if conn not in self._batches:
                self._batches[conn] = MessageBatch(
                    target_socket=conn,
                    max_size=self.batch_size,
                    timeout_seconds=self.batch_timeout
                )
            
            batch = self._batches[conn]
            is_full = batch.add_message(message)
            
            self.messages_batched += 1
            
            # Send immediately if batch is full
            if is_full:
                self._send_batch(conn, batch)
                del self._batches[conn]
    
    def flush_connection(self, conn: socket.socket) -> None:
        """
        Flush any pending messages for a connection.
        
        Args:
            conn: Socket connection to flush
        """
        with self._lock:
            if conn in self._batches:
                batch = self._batches[conn]
                if batch.messages:
                    self._send_batch(conn, batch)
                del self._batches[conn]
    
    def flush_all(self) -> None:
        """Flush all pending batches."""
        with self._lock:
            for conn, batch in list(self._batches.items()):
                if batch.messages:
                    self._send_batch(conn, batch)
            self._batches.clear()
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get batching statistics.
        
        Returns:
            Dictionary with batching statistics
        """
        with self._lock:
            return {
                'batch_size': self.batch_size,
                'batch_timeout': self.batch_timeout,
                'enable_compression': self.enable_compression,
                'messages_batched': self.messages_batched,
                'batches_sent': self.batches_sent,
                'pending_batches': len(self._batches),
                'bytes_saved_by_batching': self.bytes_saved_by_batching,
                'bytes_saved_by_compression': self.bytes_saved_by_compression,
                'compression_ratio': (
                    self.bytes_saved_by_compression / max(1, self.messages_batched * 100)
                ) * 100
            }
    
    def shutdown(self) -> None:
        """Shutdown the message batcher."""
        logger.info("Shutting down MessageBatcher...")
        
        # Flush all pending messages
        self.flush_all()
        
        self._shutdown_event.set()
        
        if self._sender_thread and self._sender_thread.is_alive():
            self._sender_thread.join(timeout=5.0)
        
        logger.info("MessageBatcher shutdown complete")
    
    def _send_batch(self, conn: socket.socket, batch: MessageBatch) -> None:
        """Send a batch of messages."""
        try:
            batched_data = batch.get_batched_data()
            
            # Apply compression if enabled and beneficial
            if (self.enable_compression and 
                len(batched_data) >= self.compression_threshold):
                
                compressed_data = zlib.compress(batched_data)
                
                if len(compressed_data) < len(batched_data):
                    # Compression was beneficial
                    self.bytes_saved_by_compression += len(batched_data) - len(compressed_data)
                    
                    # Send compressed data with header
                    header = b'COMP' + struct.pack('!I', len(batched_data))
                    conn.sendall(header + compressed_data)
                else:
                    # Compression not beneficial, send uncompressed
                    header = b'NORM' + struct.pack('!I', len(batched_data))
                    conn.sendall(header + batched_data)
            else:
                # Send uncompressed
                header = b'NORM' + struct.pack('!I', len(batched_data))
                conn.sendall(header + batched_data)
            
            self.batches_sent += 1
            
            # Calculate bytes saved by batching (rough estimate)
            individual_overhead = len(batch.messages) * 8  # Assume 8 bytes overhead per message
            batch_overhead = 8  # Single batch overhead
            self.bytes_saved_by_batching += max(0, individual_overhead - batch_overhead)
            
            logger.debug(f"Sent batch with {len(batch.messages)} messages to {conn.getpeername()}")
            
        except Exception as e:
            logger.error(f"Failed to send batch: {e}")
    
    def _start_sender_thread(self) -> None:
        """Start the sender thread for timeout-based batch sending."""
        self._sender_thread = threading.Thread(
            target=self._sender_loop,
            name="MessageBatcher-Sender",
            daemon=True
        )
        self._sender_thread.start()
    
    def _sender_loop(self) -> None:
        """Main sender loop for handling batch timeouts."""
        while not self._shutdown_event.is_set():
            try:
                # Check for timed-out batches
                current_time = datetime.now()
                batches_to_send = []
                
                with self._lock:
                    for conn, batch in list(self._batches.items()):
                        if batch.is_ready_to_send():
                            batches_to_send.append((conn, batch))
                            del self._batches[conn]
                
                # Send timed-out batches
                for conn, batch in batches_to_send:
                    self._send_batch(conn, batch)
                
                # Sleep for a short interval
                self._shutdown_event.wait(0.05)  # 50ms
                
            except Exception as e:
                logger.error(f"Sender loop error: {e}")
                self._shutdown_event.wait(0.1)


class NetworkOptimizer:
    """
    High-level network optimizer that combines connection pooling,
    message batching, and other optimizations.
    """
    
    def __init__(
        self,
        enable_connection_pooling: bool = True,
        enable_message_batching: bool = True,
        enable_compression: bool = False,
        pool_max_connections: int = 20,
        batch_size: int = 10,
        batch_timeout: float = 0.1
    ):
        """
        Initialize network optimizer.
        
        Args:
            enable_connection_pooling: Enable connection pooling
            enable_message_batching: Enable message batching
            enable_compression: Enable message compression
            pool_max_connections: Maximum pooled connections
            batch_size: Messages per batch
            batch_timeout: Batch timeout in seconds
        """
        self.enable_connection_pooling = enable_connection_pooling
        self.enable_message_batching = enable_message_batching
        self.enable_compression = enable_compression
        
        # Initialize components
        self.connection_pool: Optional[ConnectionPool] = None
        self.message_batcher: Optional[MessageBatcher] = None
        
        if enable_connection_pooling:
            self.connection_pool = ConnectionPool(max_connections=pool_max_connections)
        
        if enable_message_batching:
            self.message_batcher = MessageBatcher(
                batch_size=batch_size,
                batch_timeout=batch_timeout,
                enable_compression=enable_compression
            )
        
        logger.info(f"NetworkOptimizer initialized (pooling={enable_connection_pooling}, batching={enable_message_batching})")
    
    def get_connection(self, host: str, port: int) -> socket.socket:
        """
        Get an optimized connection.
        
        Args:
            host: Target host
            port: Target port
            
        Returns:
            Socket connection
        """
        if self.connection_pool:
            return self.connection_pool.get_connection(host, port)
        else:
            # Create direct connection
            conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            conn.connect((host, port))
            return conn
    
    def send_message(self, conn: socket.socket, message: bytes) -> None:
        """
        Send a message using optimizations.
        
        Args:
            conn: Socket connection
            message: Message bytes to send
        """
        if self.message_batcher:
            self.message_batcher.queue_message(conn, message)
        else:
            conn.sendall(message)
    
    def return_connection(self, conn: socket.socket) -> None:
        """
        Return a connection (to pool if enabled).
        
        Args:
            conn: Socket connection to return
        """
        if self.connection_pool:
            self.connection_pool.return_connection(conn)
        else:
            conn.close()
    
    def flush_connection(self, conn: socket.socket) -> None:
        """
        Flush any pending messages for a connection.
        
        Args:
            conn: Socket connection to flush
        """
        if self.message_batcher:
            self.message_batcher.flush_connection(conn)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get optimizer statistics.
        
        Returns:
            Dictionary with optimization statistics
        """
        stats = {
            'connection_pooling_enabled': self.enable_connection_pooling,
            'message_batching_enabled': self.enable_message_batching,
            'compression_enabled': self.enable_compression
        }
        
        if self.connection_pool:
            stats['connection_pool'] = self.connection_pool.get_pool_statistics()
        
        if self.message_batcher:
            stats['message_batcher'] = self.message_batcher.get_statistics()
        
        return stats
    
    def shutdown(self) -> None:
        """Shutdown the network optimizer."""
        logger.info("Shutting down NetworkOptimizer...")
        
        if self.message_batcher:
            self.message_batcher.shutdown()
        
        if self.connection_pool:
            self.connection_pool.shutdown()
        
        logger.info("NetworkOptimizer shutdown complete")


# Convenience class alias
ConnectionOptimizer = NetworkOptimizer
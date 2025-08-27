"""
Connection Limiter

Provides connection limiting and security controls for managing client connections.
"""

import socket
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, Set, Tuple, Deque, Any
import logging

from chat_app.shared.exceptions import (
    ConnectionLimitExceededError,
    ConnectionTimeoutError,
    SecurityError
)


logger = logging.getLogger(__name__)


@dataclass
class ConnectionInfo:
    """Information about a client connection."""
    ip_address: str
    connection_time: datetime = field(default_factory=datetime.now)
    socket_obj: Optional[socket.socket] = None
    connection_id: Optional[str] = None
    last_activity: datetime = field(default_factory=datetime.now)
    
    def update_activity(self) -> None:
        """Update the last activity timestamp."""
        self.last_activity = datetime.now()
    
    @property
    def connection_duration(self) -> timedelta:
        """Get the duration of this connection."""
        return datetime.now() - self.connection_time
    
    @property
    def idle_duration(self) -> timedelta:
        """Get the idle duration since last activity."""
        return datetime.now() - self.last_activity


@dataclass
class IPConnectionTracker:
    """Tracks connections for a specific IP address."""
    ip_address: str
    active_connections: Set[str] = field(default_factory=set)
    connection_history: Deque[datetime] = field(default_factory=deque)
    total_connections: int = 0
    last_connection_attempt: Optional[datetime] = None
    blocked_until: Optional[datetime] = None
    
    def add_connection(self, connection_id: str) -> None:
        """Add a new connection for this IP."""
        self.active_connections.add(connection_id)
        self.connection_history.append(datetime.now())
        self.total_connections += 1
        self.last_connection_attempt = datetime.now()
        
        # Keep only recent connection history (last hour)
        cutoff_time = datetime.now() - timedelta(hours=1)
        while self.connection_history and self.connection_history[0] < cutoff_time:
            self.connection_history.popleft()
    
    def remove_connection(self, connection_id: str) -> None:
        """Remove a connection for this IP."""
        self.active_connections.discard(connection_id)
    
    def get_connection_count(self) -> int:
        """Get the current number of active connections."""
        return len(self.active_connections)
    
    def get_recent_connection_count(self, minutes: int = 5) -> int:
        """Get the number of connections in the last N minutes."""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        return sum(1 for conn_time in self.connection_history if conn_time >= cutoff_time)
    
    def is_blocked(self) -> bool:
        """Check if this IP is currently blocked."""
        if self.blocked_until is None:
            return False
        return datetime.now() < self.blocked_until
    
    def block_temporarily(self, duration_minutes: int = 5) -> None:
        """Temporarily block this IP."""
        self.blocked_until = datetime.now() + timedelta(minutes=duration_minutes)


class ConnectionLimiter:
    """
    Manages connection limits and security controls for client connections.
    
    Provides functionality to:
    - Limit connections per IP address
    - Implement secure timeout mechanisms
    - Track connection statistics
    - Prevent connection flooding attacks
    """
    
    def __init__(
        self,
        max_connections_per_ip: int = 5,
        max_total_connections: int = 100,
        connection_timeout_seconds: int = 30,
        max_connections_per_minute: int = 10,
        temporary_block_duration_minutes: int = 5
    ):
        """
        Initialize the connection limiter.
        
        Args:
            max_connections_per_ip: Maximum concurrent connections per IP
            max_total_connections: Maximum total concurrent connections
            connection_timeout_seconds: Timeout for connection operations
            max_connections_per_minute: Max new connections per IP per minute
            temporary_block_duration_minutes: Duration to block IPs after violations
        """
        self.max_connections_per_ip = max_connections_per_ip
        self.max_total_connections = max_total_connections
        self.connection_timeout_seconds = connection_timeout_seconds
        self.max_connections_per_minute = max_connections_per_minute
        self.temporary_block_duration_minutes = temporary_block_duration_minutes
        
        # Thread-safe data structures
        self._lock = threading.RLock()
        self._connections: Dict[str, ConnectionInfo] = {}
        self._ip_trackers: Dict[str, IPConnectionTracker] = defaultdict(
            lambda: IPConnectionTracker(ip_address="")
        )
        self._blocked_ips: Set[str] = set()
        
        # Statistics
        self.total_connections_created = 0
        self.total_connections_rejected = 0
        self.total_timeouts = 0
        self.start_time = datetime.now()
        
        logger.info(
            f"ConnectionLimiter initialized: max_per_ip={max_connections_per_ip}, "
            f"max_total={max_total_connections}, timeout={connection_timeout_seconds}s"
        )
    
    def can_accept_connection(self, ip_address: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a new connection from the given IP can be accepted.
        
        Args:
            ip_address: The IP address requesting connection
            
        Returns:
            Tuple of (can_accept, reason_if_rejected)
        """
        with self._lock:
            # Check if IP is temporarily blocked
            tracker = self._ip_trackers[ip_address]
            if tracker.is_blocked():
                return False, f"IP {ip_address} is temporarily blocked"
            
            # Check total connection limit
            if len(self._connections) >= self.max_total_connections:
                return False, "Server at maximum capacity"
            
            # Check per-IP connection limit
            current_connections = tracker.get_connection_count()
            if current_connections >= self.max_connections_per_ip:
                return False, f"Too many connections from IP {ip_address}"
            
            # Check connection rate limit
            recent_connections = tracker.get_recent_connection_count(minutes=1)
            if recent_connections >= self.max_connections_per_minute:
                # Temporarily block this IP
                tracker.block_temporarily(self.temporary_block_duration_minutes)
                self._blocked_ips.add(ip_address)
                logger.warning(
                    f"IP {ip_address} temporarily blocked due to connection rate limit"
                )
                return False, f"Connection rate limit exceeded for IP {ip_address}"
            
            return True, None
    
    def register_connection(
        self,
        connection_id: str,
        ip_address: str,
        socket_obj: Optional[socket.socket] = None
    ) -> ConnectionInfo:
        """
        Register a new connection.
        
        Args:
            connection_id: Unique identifier for the connection
            ip_address: IP address of the client
            socket_obj: Optional socket object
            
        Returns:
            ConnectionInfo object for the registered connection
            
        Raises:
            ConnectionLimitExceededError: If connection limits are exceeded
        """
        with self._lock:
            can_accept, reason = self.can_accept_connection(ip_address)
            if not can_accept:
                self.total_connections_rejected += 1
                logger.warning(f"Connection rejected from {ip_address}: {reason}")
                raise ConnectionLimitExceededError(reason or "Connection limit exceeded")
            
            # Create connection info
            connection_info = ConnectionInfo(
                ip_address=ip_address,
                socket_obj=socket_obj,
                connection_id=connection_id
            )
            
            # Register the connection
            self._connections[connection_id] = connection_info
            self._ip_trackers[ip_address].add_connection(connection_id)
            self.total_connections_created += 1
            
            logger.info(
                f"Connection registered: {connection_id} from {ip_address} "
                f"(total: {len(self._connections)})"
            )
            
            return connection_info
    
    def unregister_connection(self, connection_id: str) -> bool:
        """
        Unregister a connection.
        
        Args:
            connection_id: Unique identifier for the connection
            
        Returns:
            True if connection was found and removed, False otherwise
        """
        with self._lock:
            connection_info = self._connections.pop(connection_id, None)
            if connection_info is None:
                return False
            
            # Update IP tracker
            tracker = self._ip_trackers[connection_info.ip_address]
            tracker.remove_connection(connection_id)
            
            # Clean up empty trackers
            if tracker.get_connection_count() == 0:
                # Keep tracker for rate limiting history, but remove from blocked set
                self._blocked_ips.discard(connection_info.ip_address)
            
            logger.info(
                f"Connection unregistered: {connection_id} from {connection_info.ip_address} "
                f"(total: {len(self._connections)})"
            )
            
            return True
    
    def update_connection_activity(self, connection_id: str) -> bool:
        """
        Update the last activity time for a connection.
        
        Args:
            connection_id: Unique identifier for the connection
            
        Returns:
            True if connection was found and updated, False otherwise
        """
        with self._lock:
            connection_info = self._connections.get(connection_id)
            if connection_info is None:
                return False
            
            connection_info.update_activity()
            return True
    
    def get_connection_info(self, connection_id: str) -> Optional[ConnectionInfo]:
        """
        Get connection information for a specific connection.
        
        Args:
            connection_id: Unique identifier for the connection
            
        Returns:
            ConnectionInfo object if found, None otherwise
        """
        with self._lock:
            return self._connections.get(connection_id)
    
    def get_connections_by_ip(self, ip_address: str) -> Dict[str, ConnectionInfo]:
        """
        Get all connections from a specific IP address.
        
        Args:
            ip_address: IP address to search for
            
        Returns:
            Dictionary of connection_id -> ConnectionInfo for the IP
        """
        with self._lock:
            return {
                conn_id: conn_info
                for conn_id, conn_info in self._connections.items()
                if conn_info.ip_address == ip_address
            }
    
    def get_idle_connections(self, idle_threshold_minutes: int = 30) -> Dict[str, ConnectionInfo]:
        """
        Get connections that have been idle for longer than the threshold.
        
        Args:
            idle_threshold_minutes: Idle time threshold in minutes
            
        Returns:
            Dictionary of connection_id -> ConnectionInfo for idle connections
        """
        threshold = timedelta(minutes=idle_threshold_minutes)
        with self._lock:
            return {
                conn_id: conn_info
                for conn_id, conn_info in self._connections.items()
                if conn_info.idle_duration > threshold
            }
    
    def cleanup_idle_connections(self, idle_threshold_minutes: int = 30) -> int:
        """
        Remove idle connections that exceed the threshold.
        
        Args:
            idle_threshold_minutes: Idle time threshold in minutes
            
        Returns:
            Number of connections cleaned up
        """
        idle_connections = self.get_idle_connections(idle_threshold_minutes)
        cleanup_count = 0
        
        for connection_id, connection_info in idle_connections.items():
            try:
                # Close socket if available
                if connection_info.socket_obj:
                    connection_info.socket_obj.close()
                
                # Unregister the connection
                if self.unregister_connection(connection_id):
                    cleanup_count += 1
                    logger.info(
                        f"Cleaned up idle connection: {connection_id} "
                        f"(idle for {connection_info.idle_duration})"
                    )
            except Exception as e:
                logger.error(f"Error cleaning up connection {connection_id}: {e}")
        
        return cleanup_count
    
    def apply_secure_timeout(self, socket_obj: socket.socket) -> None:
        """
        Apply secure timeout settings to a socket.
        
        Args:
            socket_obj: Socket to configure
            
        Raises:
            ConnectionTimeoutError: If timeout configuration fails
        """
        try:
            socket_obj.settimeout(self.connection_timeout_seconds)
            
            # Set additional socket options for security
            socket_obj.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            
            # Platform-specific keep-alive settings
            if hasattr(socket, 'TCP_KEEPIDLE'):
                socket_obj.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
            if hasattr(socket, 'TCP_KEEPINTVL'):
                socket_obj.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
            if hasattr(socket, 'TCP_KEEPCNT'):
                socket_obj.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
                
        except Exception as e:
            logger.error(f"Failed to apply secure timeout settings: {e}")
            raise ConnectionTimeoutError(f"Failed to configure connection timeout: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get connection limiter statistics.
        
        Returns:
            Dictionary containing various statistics
        """
        with self._lock:
            uptime = datetime.now() - self.start_time
            
            # Calculate per-IP statistics
            ip_stats = {}
            for ip, tracker in self._ip_trackers.items():
                ip_stats[ip] = {
                    'active_connections': tracker.get_connection_count(),
                    'total_connections': tracker.total_connections,
                    'recent_connections': tracker.get_recent_connection_count(),
                    'is_blocked': tracker.is_blocked()
                }
            
            return {
                'uptime_seconds': uptime.total_seconds(),
                'current_connections': len(self._connections),
                'max_connections_per_ip': self.max_connections_per_ip,
                'max_total_connections': self.max_total_connections,
                'total_connections_created': self.total_connections_created,
                'total_connections_rejected': self.total_connections_rejected,
                'total_timeouts': self.total_timeouts,
                'blocked_ips_count': len(self._blocked_ips),
                'tracked_ips_count': len(self._ip_trackers),
                'ip_statistics': ip_stats
            }
    
    def is_ip_blocked(self, ip_address: str) -> bool:
        """
        Check if an IP address is currently blocked.
        
        Args:
            ip_address: IP address to check
            
        Returns:
            True if IP is blocked, False otherwise
        """
        with self._lock:
            tracker = self._ip_trackers.get(ip_address)
            return tracker.is_blocked() if tracker else False
    
    def unblock_ip(self, ip_address: str) -> bool:
        """
        Manually unblock an IP address.
        
        Args:
            ip_address: IP address to unblock
            
        Returns:
            True if IP was blocked and is now unblocked, False otherwise
        """
        with self._lock:
            tracker = self._ip_trackers.get(ip_address)
            if tracker and tracker.is_blocked():
                tracker.blocked_until = None
                self._blocked_ips.discard(ip_address)
                logger.info(f"Manually unblocked IP: {ip_address}")
                return True
            return False
    
    def shutdown(self) -> None:
        """
        Shutdown the connection limiter and clean up resources.
        """
        with self._lock:
            logger.info("Shutting down ConnectionLimiter...")
            
            # Close all tracked sockets
            for connection_info in self._connections.values():
                if connection_info.socket_obj:
                    try:
                        connection_info.socket_obj.close()
                    except Exception as e:
                        logger.error(f"Error closing socket: {e}")
            
            # Clear all data structures
            self._connections.clear()
            self._ip_trackers.clear()
            self._blocked_ips.clear()
            
            logger.info("ConnectionLimiter shutdown complete")


# Convenience class for backward compatibility
ConnectionStatus = ConnectionInfo
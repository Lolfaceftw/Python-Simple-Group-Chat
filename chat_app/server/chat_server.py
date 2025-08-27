"""
Chat Server Module

Main server class that orchestrates all server components with modular dependencies,
graceful shutdown, comprehensive error handling, and integrated security.
"""

import socket
import sys
import threading
import time
import signal
import logging
from typing import Optional, Dict, Tuple, Any
from datetime import datetime

from chat_app.shared.config import ServerConfig
from chat_app.shared.constants import (
    DISCOVERY_MESSAGE,
    DEFAULT_SOCKET_TIMEOUT
)
from chat_app.shared.models import Message, ClientConnection, MessageType
from chat_app.shared.exceptions import (
    ChatServerError,
    SecurityError,
    ConfigurationError
)
from chat_app.shared.logging_config import get_logger
from chat_app.server.client_manager import ClientManager
from chat_app.server.message_broker import MessageBroker
from chat_app.server.security.validator import InputValidator
from chat_app.server.security.rate_limiter import RateLimiter
from chat_app.server.security.connection_limiter import ConnectionLimiter
from chat_app.server.performance.thread_pool import ThreadPoolManager, ThreadPoolConfig
from chat_app.server.performance.memory_manager import MemoryManager, MemoryConfig


logger = get_logger(__name__)


class ChatServer:
    """
    Main chat server class with modular architecture and integrated security.
    
    Orchestrates client connections, message routing, and security controls
    with graceful shutdown and comprehensive error handling.
    """
    
    def __init__(self, config: Optional[ServerConfig] = None):
        """
        Initialize the chat server with modular dependencies.
        
        Args:
            config: Server configuration. If None, loads from environment.
        """
        self.config = config or ServerConfig.from_env()
        self.server_socket: Optional[socket.socket] = None
        self.is_running = False
        self.shutdown_event = threading.Event()
        
        # Initialize security components
        self.validator = InputValidator(
            max_message_length=self.config.max_message_length,
            max_username_length=self.config.max_username_length
        )
        
        self.rate_limiter = RateLimiter(
            default_rate_per_minute=self.config.rate_limit_messages_per_minute
        )
        
        self.connection_limiter = ConnectionLimiter(
            max_connections_per_ip=self.config.max_connections_per_ip,
            max_total_connections=self.config.max_clients
        )
        
        # Initialize performance components
        thread_pool_config = ThreadPoolConfig(
            min_threads=max(2, self.config.max_clients // 10),
            max_threads=min(50, self.config.max_clients),
            enable_monitoring=True
        )
        self.thread_pool = ThreadPoolManager(thread_pool_config)
        
        memory_config = MemoryConfig(
            max_message_history=self.config.message_history_size,
            enable_auto_cleanup=True
        )
        self.memory_manager = MemoryManager(memory_config)
        
        # Initialize core components
        self.client_manager = ClientManager(
            rate_limiter=self.rate_limiter,
            connection_limiter=self.connection_limiter,
            max_message_history=self.config.message_history_size
        )
        
        self.message_broker = MessageBroker(
            validator=self.validator,
            rate_limiter=self.rate_limiter,
            max_message_history=self.config.message_history_size
        )
        
        # Threading components
        self.client_threads: Dict[str, Any] = {}  # Now stores Future objects
        self.discovery_thread: Optional[threading.Thread] = None
        self.cleanup_thread: Optional[threading.Thread] = None
        
        # Statistics
        self.start_time: Optional[datetime] = None
        self.total_connections_accepted = 0
        self.total_connections_rejected = 0
        
        # Set up signal handlers for graceful shutdown
        self._setup_signal_handlers()
        
        logger.info(f"ChatServer initialized with config: {self.config}")
    
    def start(self) -> None:
        """
        Start the chat server and begin accepting connections.
        
        Raises:
            ChatServerError: If server fails to start
            ConfigurationError: If configuration is invalid
        """
        if self.is_running:
            raise ChatServerError("Server is already running")
        
        try:
            self._validate_configuration()
            self._create_server_socket()
            self._bind_and_listen()
            
            self.is_running = True
            self.start_time = datetime.now()
            
            logger.info(f"Chat server started on {self.config.host}:{self.config.port}")
            
            # Start background threads
            self._start_discovery_service()
            self._start_cleanup_service()
            
            # Main server loop
            self._run_server_loop()
            
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            self.shutdown()
            raise ChatServerError(f"Server startup failed: {e}") from e
    
    def shutdown(self) -> None:
        """
        Gracefully shutdown the server and clean up all resources.
        """
        if not self.is_running:
            return
        
        logger.info("Initiating server shutdown...")
        
        # Signal shutdown to all threads
        self.is_running = False
        self.shutdown_event.set()
        
        try:
            # Stop accepting new connections
            if self.server_socket:
                self.server_socket.close()
                logger.info("Server socket closed")
            
            # Shutdown components in reverse order of initialization
            self._shutdown_client_threads()
            self._shutdown_background_threads()
            self._shutdown_components()
            
            logger.info("Server shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        finally:
            self.is_running = False
    
    def get_server_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive server statistics.
        
        Returns:
            Dictionary containing server statistics
        """
        uptime = datetime.now() - self.start_time if self.start_time else None
        
        stats = {
            'server_info': {
                'host': self.config.host,
                'port': self.config.port,
                'is_running': self.is_running,
                'start_time': self.start_time,
                'uptime_seconds': uptime.total_seconds() if uptime else 0,
                'total_connections_accepted': self.total_connections_accepted,
                'total_connections_rejected': self.total_connections_rejected
            },
            'client_manager': self.client_manager.get_client_statistics(),
            'message_broker': self.message_broker.get_statistics(),
            'rate_limiter': self.rate_limiter.get_statistics(),
            'connection_limiter': self.connection_limiter.get_statistics(),
            'thread_pool': self.thread_pool.get_stats().__dict__,
            'memory_manager': self.memory_manager.get_memory_stats().__dict__
        }
        
        return stats
    
    def _validate_configuration(self) -> None:
        """
        Validate server configuration.
        
        Raises:
            ConfigurationError: If configuration is invalid
        """
        if not (self.config.port == 0 or 1024 <= self.config.port <= 65535):
            raise ConfigurationError(f"Invalid port number: {self.config.port}")
        
        if self.config.max_clients <= 0:
            raise ConfigurationError(f"Invalid max_clients: {self.config.max_clients}")
        
        if self.config.rate_limit_messages_per_minute <= 0:
            raise ConfigurationError(f"Invalid rate limit: {self.config.rate_limit_messages_per_minute}")
        
        logger.debug("Configuration validation passed")
    
    def _create_server_socket(self) -> None:
        """
        Create and configure the server socket.
        
        Raises:
            ChatServerError: If socket creation fails
        """
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.settimeout(DEFAULT_SOCKET_TIMEOUT)
            
            logger.debug("Server socket created and configured")
            
        except Exception as e:
            raise ChatServerError(f"Failed to create server socket: {e}") from e
    
    def _bind_and_listen(self) -> None:
        """
        Bind the server socket and start listening.
        
        Raises:
            ChatServerError: If binding or listening fails
        """
        try:
            self.server_socket.bind((self.config.host, self.config.port))
            self.server_socket.listen(self.config.max_clients)
            
            logger.info(f"Server listening on {self.config.host}:{self.config.port}")
            
        except OSError as e:
            if e.errno == 98:  # Address already in use
                raise ChatServerError(f"Port {self.config.port} is already in use") from e
            elif e.errno == 13:  # Permission denied
                raise ChatServerError(f"Permission denied to bind to port {self.config.port}") from e
            else:
                raise ChatServerError(f"Failed to bind to {self.config.host}:{self.config.port}: {e}") from e
    
    def _run_server_loop(self) -> None:
        """
        Main server loop that accepts and handles client connections.
        """
        logger.info("Server loop started, accepting connections...")
        
        try:
            while self.is_running and not self.shutdown_event.is_set():
                try:
                    # Accept new connection with timeout
                    client_socket, address = self.server_socket.accept()
                    self.total_connections_accepted += 1
                    
                    logger.debug(f"New connection attempt from {address}")
                    
                    # Handle the new client in a separate thread
                    self._handle_new_client(client_socket, address)
                    
                except socket.timeout:
                    # Timeout allows checking for shutdown signal
                    continue
                    
                except OSError as e:
                    if self.is_running:  # Only log if not shutting down
                        logger.error(f"Socket error in server loop: {e}")
                    break
                    
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
        except Exception as e:
            logger.error(f"Unexpected error in server loop: {e}")
        finally:
            logger.info("Server loop ended")
    
    def _handle_new_client(self, client_socket: socket.socket, address: Tuple[str, int]) -> None:
        """
        Handle a new client connection with security checks.
        
        Args:
            client_socket: The client's socket
            address: Client's address tuple
        """
        try:
            # Add client to manager (includes security checks)
            client_id = self.client_manager.add_client(client_socket, address)
            
            # Register client with message broker
            connection = self.client_manager.get_client(client_id)
            if connection:
                self.message_broker.register_client(client_id, connection)
                
                # Send welcome message and history
                self.message_broker.send_welcome_message(client_id)
                
                # Broadcast join notification
                join_message = f"{connection.user.username} has joined the chat."
                self.message_broker.broadcast_server_message(join_message, exclude_clients={client_id})
                
                # Broadcast updated user list
                user_list = self.client_manager.get_user_list_string()
                self.message_broker.broadcast_user_list(user_list)
                
                # Start client handler using thread pool
                future = self.thread_pool.submit_client_handler(
                    self._handle_client_communication,
                    client_id
                )
                
                # Store future reference for cleanup
                self.client_threads[client_id] = future
                
                logger.info(f"Client {connection.user.username} connected and handler started")
            
        except SecurityError as e:
            logger.warning(f"Security check failed for {address}: {e}")
            self.total_connections_rejected += 1
            try:
                client_socket.close()
            except Exception:
                pass
                
        except Exception as e:
            logger.error(f"Error handling new client {address}: {e}")
            self.total_connections_rejected += 1
            try:
                client_socket.close()
            except Exception:
                pass
    
    def _handle_client_communication(self, client_id: str) -> None:
        """
        Handle communication with a specific client.
        
        Args:
            client_id: Unique client identifier
        """
        connection = self.client_manager.get_client(client_id)
        if not connection:
            logger.error(f"Client connection not found: {client_id}")
            return
        
        logger.debug(f"Starting communication handler for {connection.user.username}")
        
        try:
            while self.is_running and not self.shutdown_event.is_set():
                try:
                    # Receive data from client
                    data = connection.socket.recv(4096)
                    if not data:
                        logger.debug(f"Client {connection.user.username} disconnected (no data)")
                        break
                    
                    # Process the message
                    message = data.decode('utf-8').strip()
                    if message:
                        self._process_client_message(client_id, message)
                    
                    # Update client activity
                    self.client_manager.update_client_activity(client_id)
                    
                except socket.timeout:
                    continue
                    
                except (ConnectionResetError, BrokenPipeError):
                    logger.debug(f"Connection lost with {connection.user.username}")
                    break
                    
                except Exception as e:
                    logger.error(f"Error handling client {connection.user.username}: {e}")
                    break
        
        finally:
            self._cleanup_client(client_id)
    
    def _process_client_message(self, client_id: str, message: str) -> None:
        """
        Process a message received from a client.
        
        Args:
            client_id: ID of the sending client
            message: Raw message content
        """
        try:
            # Parse message protocol
            parts = message.split('|', 1)
            msg_type = parts[0]
            payload = parts[1] if len(parts) > 1 else ""
            
            connection = self.client_manager.get_client(client_id)
            if not connection:
                return
            
            if msg_type == "CMD_USER":
                # Handle username change
                self._handle_username_change(client_id, payload)
                
            elif msg_type == "MSG":
                # Handle chat message
                self._handle_chat_message(client_id, payload)
                
            else:
                logger.warning(f"Unknown message type from {connection.user.username}: {msg_type}")
        
        except Exception as e:
            logger.error(f"Error processing message from client {client_id}: {e}")
    
    def _handle_username_change(self, client_id: str, new_username: str) -> None:
        """
        Handle a username change request.
        
        Args:
            client_id: ID of the client requesting change
            new_username: Requested new username
        """
        try:
            # Validate the new username
            validation_result = self.validator.validate_username(new_username)
            if not validation_result.is_valid:
                logger.warning(f"Invalid username change request from {client_id}: {validation_result.errors}")
                return
            
            # Update username
            success, old_username = self.client_manager.update_username(client_id, new_username)
            if success:
                connection = self.client_manager.get_client(client_id)
                if connection:
                    # Broadcast username change notification
                    notification = f"{old_username} is now known as {connection.user.username}."
                    self.message_broker.broadcast_server_message(notification)
                    
                    # Broadcast updated user list
                    user_list = self.client_manager.get_user_list_string()
                    self.message_broker.broadcast_user_list(user_list)
                    
                    logger.info(f"Username changed: {old_username} -> {connection.user.username}")
        
        except Exception as e:
            logger.error(f"Error handling username change for client {client_id}: {e}")
    
    def _handle_chat_message(self, client_id: str, message_content: str) -> None:
        """
        Handle a chat message from a client.
        
        Args:
            client_id: ID of the sending client
            message_content: Content of the chat message
        """
        try:
            # Process message through message broker (includes validation and rate limiting)
            result = self.message_broker.process_message(
                sender_id=client_id,
                message_content=message_content,
                message_type=MessageType.CHAT
            )
            
            if not result.success:
                logger.warning(f"Message delivery failed for client {client_id}: {result.errors}")
            
        except Exception as e:
            logger.error(f"Error handling chat message from client {client_id}: {e}")
    
    def _cleanup_client(self, client_id: str) -> None:
        """
        Clean up resources for a disconnected client.
        
        Args:
            client_id: ID of the client to clean up
        """
        try:
            # Get client info before removal
            connection = self.client_manager.get_client(client_id)
            username = connection.user.username if connection else "Unknown"
            
            # Remove from message broker
            self.message_broker.unregister_client(client_id)
            
            # Remove from client manager
            if self.client_manager.remove_client(client_id):
                # Broadcast leave notification
                leave_message = f"{username} has left the chat."
                self.message_broker.broadcast_server_message(leave_message)
                
                # Broadcast updated user list
                user_list = self.client_manager.get_user_list_string()
                self.message_broker.broadcast_user_list(user_list)
                
                logger.info(f"Client {username} cleaned up successfully")
            
            # Remove thread reference
            self.client_threads.pop(client_id, None)
            
        except Exception as e:
            logger.error(f"Error cleaning up client {client_id}: {e}")
    
    def _start_discovery_service(self) -> None:
        """Start the service discovery broadcast thread."""
        if self.discovery_thread and self.discovery_thread.is_alive():
            return
        
        self.discovery_thread = threading.Thread(
            target=self._run_discovery_service,
            name="DiscoveryService"
        )
        self.discovery_thread.daemon = True
        self.discovery_thread.start()
        
        logger.info("Service discovery started")
    
    def _run_discovery_service(self) -> None:
        """Run the service discovery broadcast service."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                broadcast_address = ('<broadcast>', self.config.discovery_port)
                
                logger.debug(f"Discovery service broadcasting on port {self.config.discovery_port}")
                
                while self.is_running and not self.shutdown_event.is_set():
                    try:
                        sock.sendto(DISCOVERY_MESSAGE, broadcast_address)
                        self.shutdown_event.wait(self.config.discovery_broadcast_interval)
                        
                    except Exception as e:
                        logger.error(f"Discovery broadcast failed: {e}")
                        self.shutdown_event.wait(self.config.discovery_broadcast_interval * 2)
                        
        except Exception as e:
            logger.error(f"Discovery service error: {e}")
    
    def _start_cleanup_service(self) -> None:
        """Start the periodic cleanup service."""
        if self.cleanup_thread and self.cleanup_thread.is_alive():
            return
        
        self.cleanup_thread = threading.Thread(
            target=self._run_cleanup_service,
            name="CleanupService"
        )
        self.cleanup_thread.daemon = True
        self.cleanup_thread.start()
        
        logger.debug("Cleanup service started")
    
    def _run_cleanup_service(self) -> None:
        """Run periodic cleanup tasks."""
        cleanup_interval = 300  # 5 minutes
        
        while self.is_running and not self.shutdown_event.is_set():
            try:
                # Clean up inactive clients
                cleaned_count = self.client_manager.cleanup_inactive_clients(30)
                if cleaned_count > 0:
                    logger.info(f"Cleaned up {cleaned_count} inactive clients")
                
                # Clean up rate limiter
                self.rate_limiter._cleanup_old_entries()
                
                # Clean up connection limiter
                self.connection_limiter.cleanup_idle_connections()
                
            except Exception as e:
                logger.error(f"Cleanup service error: {e}")
            
            self.shutdown_event.wait(cleanup_interval)
    
    def _shutdown_client_threads(self) -> None:
        """Shutdown all client handler threads."""
        logger.info(f"Shutting down {len(self.client_threads)} client handlers...")
        
        # Signal all clients to disconnect
        for client_id in list(self.client_threads.keys()):
            try:
                connection = self.client_manager.get_client(client_id)
                if connection:
                    connection.socket.close()
            except Exception as e:
                logger.error(f"Error closing client socket {client_id}: {e}")
        
        # Cancel pending futures and wait for completion
        for client_id, future in list(self.client_threads.items()):
            try:
                if not future.done():
                    future.cancel()
                # Wait for completion with timeout
                try:
                    future.result(timeout=5.0)
                except Exception:
                    pass  # Expected for cancelled futures
            except Exception as e:
                logger.error(f"Error handling client future {client_id}: {e}")
        
        self.client_threads.clear()
        logger.info("Client handlers shutdown complete")
    
    def _shutdown_background_threads(self) -> None:
        """Shutdown background service threads."""
        threads_to_shutdown = [
            ("Discovery", self.discovery_thread),
            ("Cleanup", self.cleanup_thread)
        ]
        
        for name, thread in threads_to_shutdown:
            if thread and thread.is_alive():
                logger.debug(f"Shutting down {name} thread...")
                try:
                    thread.join(timeout=5.0)
                    if thread.is_alive():
                        logger.warning(f"{name} thread did not shutdown gracefully")
                    else:
                        logger.debug(f"{name} thread shutdown complete")
                except Exception as e:
                    logger.error(f"Error shutting down {name} thread: {e}")
    
    def _shutdown_components(self) -> None:
        """Shutdown all server components."""
        logger.debug("Shutting down server components...")
        
        try:
            # Shutdown performance components first
            self.thread_pool.shutdown(wait=True, timeout=10.0)
            self.memory_manager.shutdown()
            
            # Then shutdown core components
            self.message_broker.shutdown()
            self.client_manager.shutdown()
            logger.debug("Components shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down components: {e}")
    
    def get_server_port(self) -> int:
        """
        Get the actual port the server is listening on.
        
        Returns:
            The port number the server is bound to
            
        Raises:
            ChatServerError: If server socket is not initialized
        """
        if not self.server_socket:
            raise ChatServerError("Server socket not initialized")
        
        try:
            return self.server_socket.getsockname()[1]
        except Exception as e:
            raise ChatServerError(f"Failed to get server port: {e}") from e
    
    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating shutdown...")
            self.shutdown()
            sys.exit(0)
        
        # Set up signal handlers (Unix-like systems)
        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        except AttributeError:
            # Windows doesn't have all signals
            signal.signal(signal.SIGINT, signal_handler)
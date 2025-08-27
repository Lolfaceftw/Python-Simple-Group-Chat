"""
Client Manager Module

Manages client connections, user tracking, and user list management
with thread-safe operations and security integration.
"""

import socket
import threading
import uuid
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Set, Deque
import logging

from chat_app.shared.models import User, ClientConnection, Message, MessageType
from chat_app.shared.protocols import RateLimiter, ConnectionLimiter
from chat_app.shared.exceptions import (
    ClientNotFoundError,
    DuplicateClientError,
    SecurityError
)


logger = logging.getLogger(__name__)


class ClientManager:
    """
    Manages client connections with thread-safe operations and security integration.
    
    Provides functionality to:
    - Add and remove client connections
    - Track user information and activity
    - Manage user list updates
    - Integrate with security controls (rate limiting, connection limits)
    - Maintain thread-safe access to client data
    """
    
    def __init__(
        self,
        rate_limiter: Optional[RateLimiter] = None,
        connection_limiter: Optional[ConnectionLimiter] = None,
        max_message_history: int = 50
    ):
        """
        Initialize the client manager.
        
        Args:
            rate_limiter: Rate limiter for message control
            connection_limiter: Connection limiter for security
            max_message_history: Maximum number of messages to keep in history
        """
        self.rate_limiter = rate_limiter
        self.connection_limiter = connection_limiter
        self.max_message_history = max_message_history
        
        # Thread-safe data structures
        self._lock = threading.RLock()
        self._clients: Dict[str, ClientConnection] = {}
        self._socket_to_client_id: Dict[socket.socket, str] = {}
        self._username_to_client_id: Dict[str, str] = {}
        self._message_history: Deque[Message] = deque(maxlen=max_message_history)
        
        # Statistics
        self.total_clients_connected = 0
        self.total_clients_disconnected = 0
        self.start_time = datetime.now()
        
        logger.info(f"ClientManager initialized with max_history={max_message_history}")
    
    def add_client(
        self,
        client_socket: socket.socket,
        address: Tuple[str, int],
        initial_username: Optional[str] = None
    ) -> str:
        """
        Add a new client connection.
        
        Args:
            client_socket: The client's socket connection
            address: Client's address tuple (host, port)
            initial_username: Optional initial username
            
        Returns:
            Unique client ID for the new connection
            
        Raises:
            DuplicateClientError: If client is already registered
            SecurityError: If security checks fail
        """
        with self._lock:
            # Check if socket is already registered
            if client_socket in self._socket_to_client_id:
                raise DuplicateClientError("Client socket already registered")
            
            # Generate unique client ID
            client_id = str(uuid.uuid4())
            addr_str = f"{address[0]}:{address[1]}"
            
            # Create default username if not provided
            if initial_username is None:
                initial_username = f"User_{addr_str}"
            
            # Check for username conflicts and resolve
            username = self._resolve_username_conflict(initial_username)
            
            # Register with connection limiter if available
            if self.connection_limiter:
                try:
                    self.connection_limiter.register_connection(
                        connection_id=client_id,
                        ip_address=address[0],
                        socket_obj=client_socket
                    )
                except Exception as e:
                    logger.error(f"Connection limiter registration failed: {e}")
                    raise SecurityError(f"Connection security check failed: {e}")
            
            # Create user and connection objects
            user = User(
                username=username,
                address=addr_str,
                connection_time=datetime.now(),
                last_activity=datetime.now()
            )
            
            connection = ClientConnection(
                socket=client_socket,
                user=user,
                connection_id=client_id
            )
            
            # Store client data
            self._clients[client_id] = connection
            self._socket_to_client_id[client_socket] = client_id
            self._username_to_client_id[username] = client_id
            
            # Update statistics
            self.total_clients_connected += 1
            
            logger.info(
                f"Client added: {username} ({addr_str}) with ID {client_id} "
                f"(total: {len(self._clients)})"
            )
            
            return client_id
    
    def remove_client(self, client_id: str) -> bool:
        """
        Remove a client connection.
        
        Args:
            client_id: Unique client identifier
            
        Returns:
            True if client was found and removed, False otherwise
        """
        with self._lock:
            connection = self._clients.get(client_id)
            if connection is None:
                return False
            
            # Clean up mappings
            self._socket_to_client_id.pop(connection.socket, None)
            self._username_to_client_id.pop(connection.user.username, None)
            del self._clients[client_id]
            
            # Unregister from connection limiter
            if self.connection_limiter:
                self.connection_limiter.unregister_connection(client_id)
            
            # Update statistics
            self.total_clients_disconnected += 1
            
            logger.info(
                f"Client removed: {connection.user.username} "
                f"({connection.user.address}) with ID {client_id} "
                f"(total: {len(self._clients)})"
            )
            
            return True
    
    def get_client(self, client_id: str) -> Optional[ClientConnection]:
        """
        Get a client connection by ID.
        
        Args:
            client_id: Unique client identifier
            
        Returns:
            ClientConnection object if found, None otherwise
        """
        with self._lock:
            return self._clients.get(client_id)
    
    def get_client_by_socket(self, client_socket: socket.socket) -> Optional[ClientConnection]:
        """
        Get a client connection by socket.
        
        Args:
            client_socket: Client's socket object
            
        Returns:
            ClientConnection object if found, None otherwise
        """
        with self._lock:
            client_id = self._socket_to_client_id.get(client_socket)
            if client_id:
                return self._clients.get(client_id)
            return None
    
    def get_client_by_username(self, username: str) -> Optional[ClientConnection]:
        """
        Get a client connection by username.
        
        Args:
            username: Username to search for
            
        Returns:
            ClientConnection object if found, None otherwise
        """
        with self._lock:
            client_id = self._username_to_client_id.get(username)
            if client_id:
                return self._clients.get(client_id)
            return None
    
    def get_all_clients(self) -> List[ClientConnection]:
        """
        Get all client connections.
        
        Returns:
            List of all ClientConnection objects
        """
        with self._lock:
            return list(self._clients.values())
    
    def get_client_count(self) -> int:
        """
        Get the current number of connected clients.
        
        Returns:
            Number of connected clients
        """
        with self._lock:
            return len(self._clients)
    
    def update_username(self, client_id: str, new_username: str) -> Tuple[bool, Optional[str]]:
        """
        Update a client's username.
        
        Args:
            client_id: Unique client identifier
            new_username: New username to set
            
        Returns:
            Tuple of (success, old_username)
        """
        with self._lock:
            connection = self._clients.get(client_id)
            if connection is None:
                return False, None
            
            old_username = connection.user.username
            
            # Check for username conflicts
            resolved_username = self._resolve_username_conflict(new_username, exclude_client_id=client_id)
            
            # Update mappings
            self._username_to_client_id.pop(old_username, None)
            self._username_to_client_id[resolved_username] = client_id
            
            # Update user object
            connection.user.username = resolved_username
            connection.user.update_activity()
            
            logger.info(f"Username updated: {old_username} -> {resolved_username} for client {client_id}")
            
            return True, old_username
    
    def update_client_activity(self, client_id: str) -> bool:
        """
        Update a client's last activity time.
        
        Args:
            client_id: Unique client identifier
            
        Returns:
            True if client was found and updated, False otherwise
        """
        with self._lock:
            connection = self._clients.get(client_id)
            if connection is None:
                return False
            
            connection.user.update_activity()
            
            # Update connection limiter activity if available
            if self.connection_limiter:
                self.connection_limiter.update_connection_activity(client_id)
            
            return True
    
    def check_rate_limit(self, client_id: str, tokens_needed: int = 1) -> bool:
        """
        Check if a client can perform an action within rate limits.
        
        Args:
            client_id: Unique client identifier
            tokens_needed: Number of rate limit tokens needed
            
        Returns:
            True if action is allowed, False if rate limited
        """
        if self.rate_limiter is None:
            return True
        
        return self.rate_limiter.check_message_rate_limit(client_id, tokens_needed)
    
    def get_user_list(self) -> List[Tuple[str, str]]:
        """
        Get a list of all connected users.
        
        Returns:
            List of (username, address) tuples
        """
        with self._lock:
            return [
                (conn.user.username, conn.user.address)
                for conn in self._clients.values()
            ]
    
    def get_user_list_string(self) -> str:
        """
        Get user list as a formatted string for protocol transmission.
        
        Returns:
            Formatted user list string: "user1(addr1),user2(addr2)"
        """
        user_list = self.get_user_list()
        return ",".join([f"{username}({address})" for username, address in user_list])
    
    def add_message_to_history(self, message: Message) -> None:
        """
        Add a message to the message history.
        
        Args:
            message: Message to add to history
        """
        with self._lock:
            self._message_history.append(message)
            logger.debug(f"Message added to history: {message.content[:50]}...")
    
    def get_message_history(self) -> List[Message]:
        """
        Get the message history.
        
        Returns:
            List of messages in chronological order
        """
        with self._lock:
            return list(self._message_history)
    
    def get_client_statistics(self) -> Dict:
        """
        Get client manager statistics.
        
        Returns:
            Dictionary containing various statistics
        """
        with self._lock:
            uptime = datetime.now() - self.start_time
            
            # Calculate per-client statistics
            client_stats = {}
            for client_id, connection in self._clients.items():
                client_stats[client_id] = {
                    'username': connection.user.username,
                    'address': connection.user.address,
                    'connection_time': connection.user.connection_time,
                    'session_duration': connection.user.session_duration,
                    'message_count': connection.user.message_count,
                    'last_activity': connection.user.last_activity
                }
            
            return {
                'uptime_seconds': uptime.total_seconds(),
                'current_clients': len(self._clients),
                'total_clients_connected': self.total_clients_connected,
                'total_clients_disconnected': self.total_clients_disconnected,
                'message_history_size': len(self._message_history),
                'max_message_history': self.max_message_history,
                'client_details': client_stats
            }
    
    def cleanup_inactive_clients(self, inactive_threshold_minutes: int = 30) -> int:
        """
        Remove clients that have been inactive for too long.
        
        Args:
            inactive_threshold_minutes: Threshold in minutes for considering a client inactive
            
        Returns:
            Number of clients cleaned up
        """
        inactive_clients = []
        cutoff_time = datetime.now()
        
        with self._lock:
            for client_id, connection in self._clients.items():
                inactive_duration = (cutoff_time - connection.user.last_activity).total_seconds() / 60
                if inactive_duration > inactive_threshold_minutes:
                    inactive_clients.append(client_id)
        
        cleanup_count = 0
        for client_id in inactive_clients:
            connection = self.get_client(client_id)
            if connection:
                try:
                    # Close the socket
                    connection.socket.close()
                except Exception as e:
                    logger.error(f"Error closing socket for inactive client {client_id}: {e}")
                
                # Remove the client
                if self.remove_client(client_id):
                    cleanup_count += 1
                    logger.info(f"Cleaned up inactive client: {client_id}")
        
        return cleanup_count
    
    def _resolve_username_conflict(self, desired_username: str, exclude_client_id: Optional[str] = None) -> str:
        """
        Resolve username conflicts by appending a number if necessary.
        
        Args:
            desired_username: The desired username
            exclude_client_id: Client ID to exclude from conflict checking (for username updates)
            
        Returns:
            A unique username
        """
        base_username = desired_username
        counter = 1
        current_username = base_username
        
        while True:
            # Check if username is already taken
            existing_client_id = self._username_to_client_id.get(current_username)
            
            # If no conflict or the conflict is with the excluded client, we're good
            if existing_client_id is None or existing_client_id == exclude_client_id:
                return current_username
            
            # Try next variation
            counter += 1
            current_username = f"{base_username}_{counter}"
            
            # Prevent infinite loops
            if counter > 1000:
                current_username = f"{base_username}_{datetime.now().microsecond}"
                break
        
        return current_username
    
    def shutdown(self) -> None:
        """
        Shutdown the client manager and clean up resources.
        """
        with self._lock:
            logger.info("Shutting down ClientManager...")
            
            # Close all client sockets
            for connection in self._clients.values():
                try:
                    connection.socket.close()
                except Exception as e:
                    logger.error(f"Error closing client socket: {e}")
            
            # Clear all data structures
            self._clients.clear()
            self._socket_to_client_id.clear()
            self._username_to_client_id.clear()
            self._message_history.clear()
            
            logger.info("ClientManager shutdown complete")
"""
TCP Connection Management

Handles TCP socket connections with error handling and reconnection logic.
"""

import socket
import threading
import time
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime

from chat_app.shared.models import ConnectionStatus, NetworkMessage
from chat_app.shared.constants import (
    DEFAULT_BUFFER_SIZE, 
    DEFAULT_SOCKET_TIMEOUT,
    MESSAGE_DELIMITER
)
from chat_app.shared.protocols import NetworkConnection


@dataclass
class ConnectionConfig:
    """Configuration for TCP connections."""
    host: str
    port: int
    timeout: float = DEFAULT_SOCKET_TIMEOUT
    buffer_size: int = DEFAULT_BUFFER_SIZE
    max_reconnect_attempts: int = 5
    reconnect_delay: float = 2.0
    enable_keepalive: bool = True


class Connection(NetworkConnection):
    """
    TCP connection manager with error handling and reconnection logic.
    
    Provides a robust TCP connection with automatic reconnection,
    proper error handling, and thread-safe operations.
    """
    
    def __init__(self, config: ConnectionConfig) -> None:
        """
        Initialize the connection.
        
        Args:
            config: Connection configuration.
        """
        self.config = config
        self._socket: Optional[socket.socket] = None
        self._status = ConnectionStatus.DISCONNECTED
        self._lock = threading.Lock()
        self._reconnect_attempts = 0
        self._last_error: Optional[str] = None
        self._connection_time: Optional[datetime] = None
        
        # Callbacks
        self._on_connected: Optional[Callable[[], None]] = None
        self._on_disconnected: Optional[Callable[[], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None
        self._on_data_received: Optional[Callable[[bytes], None]] = None
        
        # Buffer for incomplete messages
        self._receive_buffer = b""
    
    def set_callbacks(self, 
                     on_connected: Optional[Callable[[], None]] = None,
                     on_disconnected: Optional[Callable[[], None]] = None,
                     on_error: Optional[Callable[[str], None]] = None,
                     on_data_received: Optional[Callable[[bytes], None]] = None) -> None:
        """
        Set event callbacks.
        
        Args:
            on_connected: Called when connection is established.
            on_disconnected: Called when connection is lost.
            on_error: Called when an error occurs.
            on_data_received: Called when data is received.
        """
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected
        self._on_error = on_error
        self._on_data_received = on_data_received
    
    def connect(self) -> bool:
        """
        Establish connection to the server.
        
        Returns:
            True if connection was successful, False otherwise.
        """
        with self._lock:
            if self._status == ConnectionStatus.CONNECTED:
                return True
            
            self._status = ConnectionStatus.CONNECTING
            
            try:
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                
                # Configure socket options
                if self.config.enable_keepalive:
                    self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                
                self._socket.settimeout(self.config.timeout)
                self._socket.connect((self.config.host, self.config.port))
                
                self._status = ConnectionStatus.CONNECTED
                self._connection_time = datetime.now()
                self._reconnect_attempts = 0
                self._last_error = None
                
                if self._on_connected:
                    self._on_connected()
                
                return True
                
            except (ConnectionRefusedError, socket.gaierror, OSError) as e:
                self._last_error = str(e)
                self._status = ConnectionStatus.ERROR
                
                if self._on_error:
                    self._on_error(self._last_error)
                
                self._cleanup_socket()
                return False
    
    def disconnect(self) -> None:
        """Disconnect from the server."""
        with self._lock:
            if self._status != ConnectionStatus.DISCONNECTED:
                self._status = ConnectionStatus.DISCONNECTED
                self._cleanup_socket()
                
                if self._on_disconnected:
                    self._on_disconnected()
    
    def reconnect(self) -> bool:
        """
        Attempt to reconnect to the server.
        
        Returns:
            True if reconnection was successful, False otherwise.
        """
        if self._reconnect_attempts >= self.config.max_reconnect_attempts:
            return False
        
        self._status = ConnectionStatus.RECONNECTING
        self._reconnect_attempts += 1
        
        # Wait before attempting reconnection
        time.sleep(self.config.reconnect_delay)
        
        return self.connect()
    
    def send(self, data: bytes) -> None:
        """
        Send data over the connection.
        
        Args:
            data: The data to send.
            
        Raises:
            ConnectionError: If not connected or send fails.
        """
        with self._lock:
            if not self.is_connected():
                raise ConnectionError("Not connected to server")
            
            try:
                if self._socket:
                    self._socket.send(data)
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                self._last_error = str(e)
                self._status = ConnectionStatus.ERROR
                
                if self._on_error:
                    self._on_error(self._last_error)
                
                raise ConnectionError(f"Failed to send data: {e}")
    
    def send_message(self, message: str) -> None:
        """
        Send a text message with proper encoding and delimiter.
        
        Args:
            message: The message to send.
        """
        data = message.encode('utf-8') + MESSAGE_DELIMITER
        self.send(data)
    
    def receive(self, buffer_size: int = None) -> bytes:
        """
        Receive data from the connection.
        
        Args:
            buffer_size: Maximum number of bytes to receive.
            
        Returns:
            Received data.
            
        Raises:
            ConnectionError: If not connected or receive fails.
        """
        if buffer_size is None:
            buffer_size = self.config.buffer_size
        
        with self._lock:
            if not self.is_connected():
                raise ConnectionError("Not connected to server")
            
            try:
                if self._socket:
                    data = self._socket.recv(buffer_size)
                    if not data:
                        # Connection closed by server - this is a graceful disconnection
                        self._status = ConnectionStatus.DISCONNECTED
                        if self._on_disconnected:
                            self._on_disconnected()
                        raise ConnectionError("Connection closed by server")
                    
                    return data
                else:
                    raise ConnectionError("Socket not available")
                    
            except socket.timeout:
                # Timeout is expected for non-blocking operations
                return b""
            except ConnectionError:
                # Re-raise ConnectionError without changing status (already set above)
                raise
            except (ConnectionResetError, OSError) as e:
                self._last_error = str(e)
                self._status = ConnectionStatus.ERROR
                
                if self._on_error:
                    self._on_error(self._last_error)
                
                raise ConnectionError(f"Failed to receive data: {e}")
    
    def receive_messages(self) -> list[str]:
        """
        Receive and parse complete messages from the buffer.
        
        Returns:
            List of complete messages.
        """
        try:
            data = self.receive()
            if not data:
                return []
            
            self._receive_buffer += data
            messages = []
            
            # Process all complete messages in buffer
            while MESSAGE_DELIMITER in self._receive_buffer:
                message_bytes, self._receive_buffer = self._receive_buffer.split(MESSAGE_DELIMITER, 1)
                try:
                    message = message_bytes.decode('utf-8').strip()
                    if message:
                        messages.append(message)
                except UnicodeDecodeError:
                    # Skip malformed messages
                    continue
            
            return messages
            
        except ConnectionError:
            return []
    
    def close(self) -> None:
        """Close the connection."""
        self.disconnect()
    
    def is_connected(self) -> bool:
        """
        Check if the connection is active.
        
        Returns:
            True if connected, False otherwise.
        """
        return self._status == ConnectionStatus.CONNECTED and self._socket is not None
    
    def get_status(self) -> ConnectionStatus:
        """
        Get the current connection status.
        
        Returns:
            Current connection status.
        """
        return self._status
    
    def get_last_error(self) -> Optional[str]:
        """
        Get the last error message.
        
        Returns:
            Last error message, or None if no error.
        """
        return self._last_error
    
    def get_connection_info(self) -> dict[str, Any]:
        """
        Get connection information.
        
        Returns:
            Dictionary with connection details.
        """
        return {
            "host": self.config.host,
            "port": self.config.port,
            "status": self._status.value,
            "connected_at": self._connection_time,
            "reconnect_attempts": self._reconnect_attempts,
            "last_error": self._last_error
        }
    
    def _cleanup_socket(self) -> None:
        """Clean up the socket connection."""
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass  # Socket already closed
            finally:
                self._socket = None
        
        self._receive_buffer = b""
    
    def __enter__(self) -> "Connection":
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
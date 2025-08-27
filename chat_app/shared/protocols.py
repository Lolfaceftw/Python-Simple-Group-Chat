"""
Type Protocols and Interfaces

Defines protocol interfaces for structural typing throughout the application.
"""

from typing import Protocol, Any, Dict, List, Optional, Tuple, Callable, runtime_checkable
from abc import abstractmethod
import socket
from .models import Message, User, ClientConnection


@runtime_checkable
class MessageHandler(Protocol):
    """Protocol for handling messages."""
    
    @abstractmethod
    def handle_message(self, message: Message, sender: Any) -> None:
        """
        Handle an incoming message.
        
        Args:
            message: The message to handle.
            sender: The sender of the message.
        """
        ...


@runtime_checkable
class NetworkConnection(Protocol):
    """Protocol for network connections."""
    
    @abstractmethod
    def send(self, data: bytes) -> None:
        """
        Send data over the connection.
        
        Args:
            data: The data to send.
        """
        ...
    
    @abstractmethod
    def receive(self, buffer_size: int = 4096) -> bytes:
        """
        Receive data from the connection.
        
        Args:
            buffer_size: Maximum number of bytes to receive.
            
        Returns:
            Received data.
        """
        ...
    
    @abstractmethod
    def close(self) -> None:
        """Close the connection."""
        ...
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the connection is active."""
        ...


@runtime_checkable
class UIComponent(Protocol):
    """Protocol for UI components."""
    
    @abstractmethod
    def update(self) -> None:
        """Update the component state."""
        ...
    
    @abstractmethod
    def render(self) -> Any:
        """
        Render the component.
        
        Returns:
            Rendered component (type depends on UI framework).
        """
        ...


class InputHandler(Protocol):
    """Protocol for handling user input."""
    
    @abstractmethod
    def handle_input(self, input_data: Any) -> Optional[str]:
        """
        Handle user input.
        
        Args:
            input_data: The input data to handle.
            
        Returns:
            Processed input string, or None if no action needed.
        """
        ...


class ClientManager(Protocol):
    """Protocol for managing client connections."""
    
    @abstractmethod
    def add_client(self, connection: ClientConnection) -> None:
        """
        Add a new client connection.
        
        Args:
            connection: The client connection to add.
        """
        ...
    
    @abstractmethod
    def remove_client(self, client_id: str) -> None:
        """
        Remove a client connection.
        
        Args:
            client_id: The ID of the client to remove.
        """
        ...
    
    @abstractmethod
    def get_client(self, client_id: str) -> Optional[ClientConnection]:
        """
        Get a client connection by ID.
        
        Args:
            client_id: The client ID.
            
        Returns:
            The client connection, or None if not found.
        """
        ...
    
    @abstractmethod
    def get_all_clients(self) -> List[ClientConnection]:
        """
        Get all client connections.
        
        Returns:
            List of all client connections.
        """
        ...


class MessageBroker(Protocol):
    """Protocol for message broadcasting and routing."""
    
    @abstractmethod
    def broadcast_message(self, message: Message, exclude_client: Optional[str] = None) -> None:
        """
        Broadcast a message to all clients.
        
        Args:
            message: The message to broadcast.
            exclude_client: Client ID to exclude from broadcast.
        """
        ...
    
    @abstractmethod
    def send_direct_message(self, client_id: str, message: Message) -> bool:
        """
        Send a message directly to a specific client.
        
        Args:
            client_id: The target client ID.
            message: The message to send.
            
        Returns:
            True if message was sent successfully.
        """
        ...


@runtime_checkable
class SecurityValidator(Protocol):
    """Protocol for security validation."""
    
    @abstractmethod
    def validate_input(self, input_data: str, input_type: str) -> Tuple[bool, Optional[str]]:
        """
        Validate user input.
        
        Args:
            input_data: The input to validate.
            input_type: The type of input (e.g., 'username', 'message').
            
        Returns:
            Tuple of (is_valid, error_message).
        """
        ...
    
    @abstractmethod
    def sanitize_input(self, input_data: str) -> str:
        """
        Sanitize user input.
        
        Args:
            input_data: The input to sanitize.
            
        Returns:
            Sanitized input.
        """
        ...


class RateLimiter(Protocol):
    """Protocol for rate limiting."""
    
    @abstractmethod
    def is_allowed(self, client_id: str) -> bool:
        """
        Check if a client is allowed to perform an action.
        
        Args:
            client_id: The client ID.
            
        Returns:
            True if action is allowed.
        """
        ...
    
    @abstractmethod
    def consume_token(self, client_id: str) -> bool:
        """
        Consume a rate limit token for a client.
        
        Args:
            client_id: The client ID.
            
        Returns:
            True if token was consumed successfully.
        """
        ...


class ConnectionLimiter(Protocol):
    """Protocol for connection limiting."""
    
    @abstractmethod
    def can_accept_connection(self, client_address: str) -> bool:
        """
        Check if a new connection can be accepted.
        
        Args:
            client_address: The client's IP address.
            
        Returns:
            True if connection can be accepted.
        """
        ...
    
    @abstractmethod
    def register_connection(self, client_address: str) -> None:
        """
        Register a new connection.
        
        Args:
            client_address: The client's IP address.
        """
        ...
    
    @abstractmethod
    def unregister_connection(self, client_address: str) -> None:
        """
        Unregister a connection.
        
        Args:
            client_address: The client's IP address.
        """
        ...


class ServiceDiscovery(Protocol):
    """Protocol for service discovery."""
    
    @abstractmethod
    def discover_servers(self, timeout: int = 3) -> List[str]:
        """
        Discover available servers on the network.
        
        Args:
            timeout: Discovery timeout in seconds.
            
        Returns:
            List of discovered server addresses.
        """
        ...
    
    @abstractmethod
    def start_broadcasting(self) -> None:
        """Start broadcasting server presence."""
        ...
    
    @abstractmethod
    def stop_broadcasting(self) -> None:
        """Stop broadcasting server presence."""
        ...


@runtime_checkable
class ConfigurationProvider(Protocol):
    """Protocol for configuration management."""
    
    @abstractmethod
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            key: The configuration key.
            default: Default value if key not found.
            
        Returns:
            Configuration value.
        """
        ...
    
    @abstractmethod
    def set_config(self, key: str, value: Any) -> None:
        """
        Set a configuration value.
        
        Args:
            key: The configuration key.
            value: The value to set.
        """
        ...
    
    @abstractmethod
    def reload_config(self) -> None:
        """Reload configuration from source."""
        ...


@runtime_checkable
class Logger(Protocol):
    """Protocol for logging."""
    
    @abstractmethod
    def debug(self, message: str, *args, **kwargs) -> None:
        """Log a debug message."""
        ...
    
    @abstractmethod
    def info(self, message: str, *args, **kwargs) -> None:
        """Log an info message."""
        ...
    
    @abstractmethod
    def warning(self, message: str, *args, **kwargs) -> None:
        """Log a warning message."""
        ...
    
    @abstractmethod
    def error(self, message: str, *args, **kwargs) -> None:
        """Log an error message."""
        ...
    
    @abstractmethod
    def critical(self, message: str, *args, **kwargs) -> None:
        """Log a critical message."""
        ...


class EventEmitter(Protocol):
    """Protocol for event emission."""
    
    @abstractmethod
    def emit(self, event: str, *args, **kwargs) -> None:
        """
        Emit an event.
        
        Args:
            event: The event name.
            *args: Event arguments.
            **kwargs: Event keyword arguments.
        """
        ...
    
    @abstractmethod
    def on(self, event: str, callback: Callable[..., None]) -> None:
        """
        Register an event listener.
        
        Args:
            event: The event name.
            callback: The callback function.
        """
        ...
    
    @abstractmethod
    def off(self, event: str, callback: Callable[..., None]) -> None:
        """
        Unregister an event listener.
        
        Args:
            event: The event name.
            callback: The callback function.
        """
        ...
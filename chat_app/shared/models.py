"""
Data Models

Defines data classes and models used throughout the chat application.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
import socket


class MessageType(Enum):
    """Enumeration of message types in the chat protocol."""
    CHAT = "MSG"
    SERVER = "SRV"
    USER_LIST = "ULIST"
    COMMAND = "CMD"
    USER_COMMAND = "CMD_USER"


class ConnectionStatus(Enum):
    """Enumeration of connection statuses."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class User:
    """Represents a chat user."""
    username: str
    address: str
    connection_time: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    message_count: int = 0
    
    def update_activity(self) -> None:
        """Update the last activity timestamp."""
        self.last_activity = datetime.now()
    
    def increment_message_count(self) -> None:
        """Increment the message count and update activity."""
        self.message_count += 1
        self.update_activity()
    
    @property
    def session_duration(self) -> float:
        """Get the session duration in seconds."""
        return (datetime.now() - self.connection_time).total_seconds()


@dataclass
class Message:
    """Represents a chat message."""
    content: str
    sender: str
    timestamp: datetime = field(default_factory=datetime.now)
    message_type: MessageType = MessageType.CHAT
    recipient: Optional[str] = None  # For direct messages
    
    def to_protocol_string(self, separator: str = '|') -> str:
        """Convert message to protocol string format."""
        return f"{self.message_type.value}{separator}{self.content}"
    
    @classmethod
    def from_protocol_string(cls, protocol_str: str, sender: str = "", 
                           separator: str = '|') -> "Message":
        """Create message from protocol string."""
        parts = protocol_str.split(separator, 1)
        msg_type_str = parts[0]
        content = parts[1] if len(parts) > 1 else ""
        
        # Convert string to MessageType enum
        try:
            msg_type = MessageType(msg_type_str)
        except ValueError:
            msg_type = MessageType.CHAT
        
        return cls(
            content=content,
            sender=sender,
            message_type=msg_type
        )


@dataclass
class ClientConnection:
    """Represents a client connection on the server side."""
    socket: socket.socket
    user: User
    connection_id: str
    rate_limit_tokens: int = 60  # For rate limiting
    last_token_refresh: datetime = field(default_factory=datetime.now)
    
    def refresh_rate_limit_tokens(self, tokens_per_minute: int = 60) -> None:
        """Refresh rate limit tokens based on time elapsed."""
        now = datetime.now()
        time_diff = (now - self.last_token_refresh).total_seconds()
        
        # Add tokens based on time elapsed (tokens per second)
        tokens_to_add = int(time_diff * (tokens_per_minute / 60))
        
        if tokens_to_add > 0:
            self.rate_limit_tokens = min(tokens_per_minute, 
                                       self.rate_limit_tokens + tokens_to_add)
            self.last_token_refresh = now
    
    def consume_token(self) -> bool:
        """Consume a rate limit token. Returns True if successful."""
        if self.rate_limit_tokens > 0:
            self.rate_limit_tokens -= 1
            return True
        return False


@dataclass
class ServerStats:
    """Represents server statistics."""
    start_time: datetime = field(default_factory=datetime.now)
    total_connections: int = 0
    current_connections: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    rate_limit_violations: int = 0
    connection_limit_violations: int = 0
    
    @property
    def uptime_seconds(self) -> float:
        """Get server uptime in seconds."""
        return (datetime.now() - self.start_time).total_seconds()
    
    def increment_connection(self) -> None:
        """Increment connection counters."""
        self.total_connections += 1
        self.current_connections += 1
    
    def decrement_connection(self) -> None:
        """Decrement current connection counter."""
        self.current_connections = max(0, self.current_connections - 1)


@dataclass
class ClientState:
    """Represents client application state."""
    username: str
    connection_status: ConnectionStatus = ConnectionStatus.DISCONNECTED
    server_host: Optional[str] = None
    server_port: Optional[int] = None
    scroll_offset: int = 0
    active_panel: str = "chat"
    unseen_messages_count: int = 0
    is_scrolled_to_bottom: bool = True
    user_panel_scroll_offset: int = 0
    input_buffer: str = ""
    
    def reset_scroll_state(self) -> None:
        """Reset scroll-related state to defaults."""
        self.scroll_offset = 0
        self.is_scrolled_to_bottom = True
        self.unseen_messages_count = 0
        self.user_panel_scroll_offset = 0


@dataclass
class NetworkMessage:
    """Represents a network message with metadata."""
    data: bytes
    source_address: Optional[tuple] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def decode(self, encoding: str = 'utf-8') -> str:
        """Decode the message data to string."""
        return self.data.decode(encoding)
    
    @classmethod
    def from_string(cls, message: str, encoding: str = 'utf-8') -> "NetworkMessage":
        """Create NetworkMessage from string."""
        return cls(data=message.encode(encoding))


@dataclass
class DiscoveryResponse:
    """Represents a service discovery response."""
    server_address: str
    server_port: int
    discovery_time: datetime = field(default_factory=datetime.now)
    response_time_ms: Optional[float] = None
    
    @property
    def server_endpoint(self) -> str:
        """Get server endpoint as host:port string."""
        return f"{self.server_address}:{self.server_port}"


@dataclass
class RateLimitInfo:
    """Information about rate limiting for a client."""
    client_id: str
    tokens_remaining: int
    tokens_per_minute: int
    last_request_time: datetime = field(default_factory=datetime.now)
    violation_count: int = 0
    
    def is_rate_limited(self) -> bool:
        """Check if the client is currently rate limited."""
        return self.tokens_remaining <= 0
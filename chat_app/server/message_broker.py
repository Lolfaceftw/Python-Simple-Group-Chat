"""
Message Broker Module

Handles message routing, broadcasting, and history management with integrated
security features including rate limiting and input validation.
"""

import socket
import threading
import logging
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Set, Deque, Callable, Any
from dataclasses import dataclass

from chat_app.shared.models import Message, MessageType, ClientConnection, User
from chat_app.shared.constants import (
    MAX_MESSAGE_HISTORY,
    DEFAULT_MESSAGE_HISTORY,
    PROTOCOL_SEPARATOR
)
from chat_app.shared.exceptions import (
    MessageBrokerError,
    ValidationError,
    RateLimitExceededError,
    SecurityError
)
from chat_app.server.security.validator import InputValidator, ValidationResult
from chat_app.server.security.rate_limiter import RateLimiter


logger = logging.getLogger(__name__)


@dataclass
class MessageDeliveryResult:
    """Result of message delivery attempt."""
    success: bool
    delivered_count: int
    failed_count: int
    errors: List[str]
    rate_limited_clients: List[str]


@dataclass
class BroadcastFilter:
    """Filter criteria for message broadcasting."""
    exclude_sender: bool = True
    exclude_clients: Optional[Set[str]] = None
    include_only_clients: Optional[Set[str]] = None
    message_type_filter: Optional[MessageType] = None


class MessageBroker:
    """
    Message broker for handling secure message routing and broadcasting.
    
    Provides functionality to:
    - Route messages between clients with validation
    - Broadcast messages to multiple clients
    - Manage message history with memory limits
    - Integrate rate limiting and input validation
    - Handle different message types and routing rules
    """
    
    def __init__(
        self,
        validator: Optional[InputValidator] = None,
        rate_limiter: Optional[RateLimiter] = None,
        max_message_history: int = DEFAULT_MESSAGE_HISTORY,
        enable_message_logging: bool = True
    ):
        """
        Initialize the message broker.
        
        Args:
            validator: Input validator for message security
            rate_limiter: Rate limiter for message control
            max_message_history: Maximum messages to keep in history
            enable_message_logging: Whether to log message activity
        """
        self.validator = validator
        self.rate_limiter = rate_limiter
        self.max_message_history = min(max_message_history, MAX_MESSAGE_HISTORY)
        self.enable_message_logging = enable_message_logging
        
        # Thread-safe data structures
        self._lock = threading.RLock()
        self._message_history: Deque[Message] = deque(maxlen=self.max_message_history)
        self._client_connections: Dict[str, ClientConnection] = {}
        self._message_handlers: Dict[MessageType, Callable] = {}
        
        # Statistics
        self.total_messages_processed = 0
        self.total_messages_broadcast = 0
        self.total_validation_failures = 0
        self.total_rate_limit_violations = 0
        self.start_time = datetime.now()
        
        # Register default message handlers
        self._register_default_handlers()
        
        logger.info(
            f"MessageBroker initialized with max_history={self.max_message_history}, "
            f"validation={'enabled' if validator else 'disabled'}, "
            f"rate_limiting={'enabled' if rate_limiter else 'disabled'}"
        )
    
    def register_client(self, client_id: str, connection: ClientConnection) -> None:
        """
        Register a client connection with the message broker.
        
        Args:
            client_id: Unique client identifier
            connection: Client connection object
        """
        with self._lock:
            self._client_connections[client_id] = connection
            logger.debug(f"Client registered with MessageBroker: {client_id}")
    
    def unregister_client(self, client_id: str) -> bool:
        """
        Unregister a client connection from the message broker.
        
        Args:
            client_id: Unique client identifier
            
        Returns:
            True if client was found and removed, False otherwise
        """
        with self._lock:
            if client_id in self._client_connections:
                del self._client_connections[client_id]
                logger.debug(f"Client unregistered from MessageBroker: {client_id}")
                return True
            return False
    
    def process_message(
        self,
        sender_id: str,
        message_content: str,
        message_type: MessageType = MessageType.CHAT,
        recipient_id: Optional[str] = None
    ) -> MessageDeliveryResult:
        """
        Process and route a message with security validation.
        
        Args:
            sender_id: ID of the sending client
            message_content: Content of the message
            message_type: Type of message
            recipient_id: Optional specific recipient ID
            
        Returns:
            MessageDeliveryResult with delivery status and statistics
            
        Raises:
            MessageBrokerError: If message processing fails
            ValidationError: If message validation fails
            RateLimitExceededError: If rate limit is exceeded
        """
        with self._lock:
            self.total_messages_processed += 1
            
            # Get sender connection
            sender_connection = self._client_connections.get(sender_id)
            if not sender_connection:
                raise MessageBrokerError(f"Sender not found: {sender_id}")
            
            # Check rate limiting
            if self.rate_limiter and not self.rate_limiter.check_message_rate_limit(sender_id):
                self.total_rate_limit_violations += 1
                logger.warning(f"Rate limit exceeded for client {sender_id}")
                raise RateLimitExceededError(f"Rate limit exceeded for client {sender_id}")
            
            # Validate message content
            sanitized_content = message_content
            if self.validator:
                try:
                    validation_result = self.validator.validate_message(message_content)
                    if not validation_result.is_valid:
                        self.total_validation_failures += 1
                        error_msg = f"Message validation failed: {'; '.join(validation_result.errors)}"
                        logger.warning(f"Validation failed for client {sender_id}: {error_msg}")
                        raise ValidationError(error_msg)
                    
                    # Use sanitized content
                    sanitized_content = validation_result.sanitized_value or message_content
                    
                except ValidationError:
                    raise
                except Exception as e:
                    self.total_validation_failures += 1
                    logger.error(f"Unexpected validation error for client {sender_id}: {e}")
                    raise ValidationError(f"Message validation error: {e}")
            
            # Create message object
            message = Message(
                content=sanitized_content,
                sender=sender_connection.user.username,
                timestamp=datetime.now(),
                message_type=message_type,
                recipient=recipient_id
            )
            
            # Add to history
            self._add_to_history(message)
            
            # Route message based on type and recipient
            if recipient_id:
                # Direct message
                result = self._send_direct_message(message, sender_id, recipient_id)
            else:
                # Broadcast message
                result = self._broadcast_message(message, sender_id)
            
            # Update sender activity
            sender_connection.user.increment_message_count()
            
            if self.enable_message_logging:
                logger.info(
                    f"Message processed: {sender_connection.user.username} -> "
                    f"{'broadcast' if not recipient_id else recipient_id} "
                    f"({len(sanitized_content)} chars, {result.delivered_count} delivered)"
                )
            
            return result
    
    def broadcast_server_message(
        self,
        content: str,
        exclude_clients: Optional[Set[str]] = None,
        include_only_clients: Optional[Set[str]] = None
    ) -> MessageDeliveryResult:
        """
        Broadcast a server message to clients.
        
        Args:
            content: Server message content
            exclude_clients: Set of client IDs to exclude
            include_only_clients: Set of client IDs to include (exclusive)
            
        Returns:
            MessageDeliveryResult with delivery status
        """
        message = Message(
            content=content,
            sender="Server",
            timestamp=datetime.now(),
            message_type=MessageType.SERVER
        )
        
        broadcast_filter = BroadcastFilter(
            exclude_sender=False,
            exclude_clients=exclude_clients,
            include_only_clients=include_only_clients,
            message_type_filter=MessageType.SERVER
        )
        
        return self._broadcast_message_with_filter(message, None, broadcast_filter)
    
    def broadcast_user_list(
        self,
        user_list_data: str,
        exclude_clients: Optional[Set[str]] = None
    ) -> MessageDeliveryResult:
        """
        Broadcast user list update to clients.
        
        Args:
            user_list_data: Formatted user list data
            exclude_clients: Set of client IDs to exclude
            
        Returns:
            MessageDeliveryResult with delivery status
        """
        message = Message(
            content=user_list_data,
            sender="Server",
            timestamp=datetime.now(),
            message_type=MessageType.USER_LIST
        )
        
        broadcast_filter = BroadcastFilter(
            exclude_sender=False,
            exclude_clients=exclude_clients,
            message_type_filter=MessageType.USER_LIST
        )
        
        return self._broadcast_message_with_filter(message, None, broadcast_filter)
    
    def send_welcome_message(self, client_id: str, message_history: Optional[List[Message]] = None) -> bool:
        """
        Send welcome message and history to a new client.
        
        Args:
            client_id: ID of the client to send welcome message to
            message_history: Optional custom message history
            
        Returns:
            True if welcome message was sent successfully
        """
        connection = self._client_connections.get(client_id)
        if not connection:
            return False
        
        try:
            # Send welcome message
            welcome_msg = f"Welcome to the chat, {connection.user.username}!"
            welcome_message = Message(
                content=welcome_msg,
                sender="Server",
                timestamp=datetime.now(),
                message_type=MessageType.SERVER
            )
            
            self._send_message_to_client(welcome_message, connection)
            
            # Send message history
            history = message_history or self.get_message_history()
            for msg in history[-20:]:  # Send last 20 messages
                if msg.message_type == MessageType.CHAT:
                    self._send_message_to_client(msg, connection)
            
            logger.info(f"Welcome message sent to {connection.user.username}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send welcome message to {client_id}: {e}")
            return False
    
    def get_message_history(self, message_type: Optional[MessageType] = None) -> List[Message]:
        """
        Get message history, optionally filtered by type.
        
        Args:
            message_type: Optional message type filter
            
        Returns:
            List of messages in chronological order
        """
        with self._lock:
            if message_type is None:
                return list(self._message_history)
            else:
                return [msg for msg in self._message_history if msg.message_type == message_type]
    
    def clear_message_history(self) -> int:
        """
        Clear the message history.
        
        Returns:
            Number of messages that were cleared
        """
        with self._lock:
            count = len(self._message_history)
            self._message_history.clear()
            logger.info(f"Message history cleared: {count} messages removed")
            return count
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get message broker statistics.
        
        Returns:
            Dictionary containing various statistics
        """
        with self._lock:
            uptime = datetime.now() - self.start_time
            
            return {
                'uptime_seconds': uptime.total_seconds(),
                'total_messages_processed': self.total_messages_processed,
                'total_messages_broadcast': self.total_messages_broadcast,
                'total_validation_failures': self.total_validation_failures,
                'total_rate_limit_violations': self.total_rate_limit_violations,
                'current_message_history_size': len(self._message_history),
                'max_message_history': self.max_message_history,
                'registered_clients': len(self._client_connections),
                'message_handlers_registered': len(self._message_handlers),
                'validation_enabled': self.validator is not None,
                'rate_limiting_enabled': self.rate_limiter is not None
            }
    
    def register_message_handler(
        self,
        message_type: MessageType,
        handler: Callable[[Message, str], bool]
    ) -> None:
        """
        Register a custom message handler for a specific message type.
        
        Args:
            message_type: Type of message to handle
            handler: Handler function that takes (message, sender_id) and returns success bool
        """
        with self._lock:
            self._message_handlers[message_type] = handler
            logger.debug(f"Message handler registered for type: {message_type}")
    
    def _broadcast_message(self, message: Message, sender_id: Optional[str]) -> MessageDeliveryResult:
        """
        Broadcast a message to all connected clients.
        
        Args:
            message: Message to broadcast
            sender_id: ID of the sender (to exclude from broadcast)
            
        Returns:
            MessageDeliveryResult with delivery statistics
        """
        broadcast_filter = BroadcastFilter(
            exclude_sender=True,
            exclude_clients={sender_id} if sender_id else None
        )
        
        return self._broadcast_message_with_filter(message, sender_id, broadcast_filter)
    
    def _broadcast_message_with_filter(
        self,
        message: Message,
        sender_id: Optional[str],
        broadcast_filter: BroadcastFilter
    ) -> MessageDeliveryResult:
        """
        Broadcast a message with filtering criteria.
        
        Args:
            message: Message to broadcast
            sender_id: ID of the sender
            broadcast_filter: Filter criteria for broadcasting
            
        Returns:
            MessageDeliveryResult with delivery statistics
        """
        delivered_count = 0
        failed_count = 0
        errors = []
        rate_limited_clients = []
        
        with self._lock:
            for client_id, connection in self._client_connections.items():
                # Apply filters
                if broadcast_filter.exclude_sender and client_id == sender_id:
                    continue
                
                if broadcast_filter.exclude_clients and client_id in broadcast_filter.exclude_clients:
                    continue
                
                if broadcast_filter.include_only_clients and client_id not in broadcast_filter.include_only_clients:
                    continue
                
                # Check rate limiting for the recipient
                if self.rate_limiter and not self.rate_limiter.check_message_rate_limit(client_id, 0):
                    rate_limited_clients.append(client_id)
                    continue
                
                # Send message
                try:
                    if self._send_message_to_client(message, connection):
                        delivered_count += 1
                    else:
                        failed_count += 1
                        errors.append(f"Failed to send to {client_id}")
                except Exception as e:
                    failed_count += 1
                    errors.append(f"Error sending to {client_id}: {e}")
            
            self.total_messages_broadcast += 1
        
        return MessageDeliveryResult(
            success=failed_count == 0,
            delivered_count=delivered_count,
            failed_count=failed_count,
            errors=errors,
            rate_limited_clients=rate_limited_clients
        )
    
    def _send_direct_message(
        self,
        message: Message,
        sender_id: str,
        recipient_id: str
    ) -> MessageDeliveryResult:
        """
        Send a direct message to a specific client.
        
        Args:
            message: Message to send
            sender_id: ID of the sender
            recipient_id: ID of the recipient
            
        Returns:
            MessageDeliveryResult with delivery status
        """
        recipient_connection = self._client_connections.get(recipient_id)
        if not recipient_connection:
            return MessageDeliveryResult(
                success=False,
                delivered_count=0,
                failed_count=1,
                errors=[f"Recipient not found: {recipient_id}"],
                rate_limited_clients=[]
            )
        
        # Check rate limiting for recipient
        if self.rate_limiter and not self.rate_limiter.check_message_rate_limit(recipient_id, 0):
            return MessageDeliveryResult(
                success=False,
                delivered_count=0,
                failed_count=1,
                errors=[],
                rate_limited_clients=[recipient_id]
            )
        
        try:
            success = self._send_message_to_client(message, recipient_connection)
            return MessageDeliveryResult(
                success=success,
                delivered_count=1 if success else 0,
                failed_count=0 if success else 1,
                errors=[] if success else [f"Failed to send to {recipient_id}"],
                rate_limited_clients=[]
            )
        except Exception as e:
            return MessageDeliveryResult(
                success=False,
                delivered_count=0,
                failed_count=1,
                errors=[f"Error sending to {recipient_id}: {e}"],
                rate_limited_clients=[]
            )
    
    def _send_message_to_client(self, message: Message, connection: ClientConnection) -> bool:
        """
        Send a message to a specific client connection.
        
        Args:
            message: Message to send
            connection: Client connection
            
        Returns:
            True if message was sent successfully
        """
        try:
            # Format message for protocol transmission
            protocol_message = message.to_protocol_string(PROTOCOL_SEPARATOR)
            message_bytes = (protocol_message + '\n').encode('utf-8')
            
            # Send message
            connection.socket.sendall(message_bytes)
            
            # Update client activity
            connection.user.update_activity()
            
            return True
            
        except socket.error as e:
            logger.error(f"Socket error sending message to {connection.user.username}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending message to {connection.user.username}: {e}")
            return False
    
    def _add_to_history(self, message: Message) -> None:
        """
        Add a message to the history with memory management.
        
        Args:
            message: Message to add to history
        """
        # Only add chat messages to history (not server messages or user lists)
        if message.message_type == MessageType.CHAT:
            self._message_history.append(message)
            logger.debug(f"Message added to history: {message.content[:50]}...")
    
    def _register_default_handlers(self) -> None:
        """Register default message handlers for different message types."""
        
        def handle_chat_message(message: Message, sender_id: str) -> bool:
            """Default handler for chat messages."""
            return True  # Chat messages are handled by the main processing flow
        
        def handle_server_message(message: Message, sender_id: str) -> bool:
            """Default handler for server messages."""
            return True  # Server messages are handled by the main processing flow
        
        def handle_command_message(message: Message, sender_id: str) -> bool:
            """Default handler for command messages."""
            # Commands are typically handled by the server, not the message broker
            logger.debug(f"Command message received: {message.content}")
            return True
        
        self._message_handlers[MessageType.CHAT] = handle_chat_message
        self._message_handlers[MessageType.SERVER] = handle_server_message
        self._message_handlers[MessageType.COMMAND] = handle_command_message
    
    def shutdown(self) -> None:
        """
        Shutdown the message broker and clean up resources.
        """
        with self._lock:
            logger.info("Shutting down MessageBroker...")
            
            # Clear all data structures
            self._client_connections.clear()
            self._message_history.clear()
            self._message_handlers.clear()
            
            logger.info("MessageBroker shutdown complete")


# Convenience functions for common message broker operations
def create_message_broker(
    enable_validation: bool = True,
    enable_rate_limiting: bool = True,
    max_history: int = DEFAULT_MESSAGE_HISTORY
) -> MessageBroker:
    """
    Create a message broker with standard configuration.
    
    Args:
        enable_validation: Whether to enable input validation
        enable_rate_limiting: Whether to enable rate limiting
        max_history: Maximum message history size
        
    Returns:
        Configured MessageBroker instance
    """
    validator = InputValidator() if enable_validation else None
    rate_limiter = RateLimiter() if enable_rate_limiting else None
    
    return MessageBroker(
        validator=validator,
        rate_limiter=rate_limiter,
        max_message_history=max_history
    )
"""
Unit tests for MessageBroker class.

Tests message routing, broadcasting, security integration, and history management.
"""

import pytest
import socket
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch, call

from chat_app.server.message_broker import (
    MessageBroker,
    MessageDeliveryResult,
    BroadcastFilter,
    create_message_broker
)
from chat_app.shared.models import Message, MessageType, ClientConnection, User
from chat_app.shared.exceptions import (
    MessageBrokerError,
    ValidationError,
    RateLimitExceededError
)
from chat_app.server.security.validator import InputValidator, ValidationResult
from chat_app.server.security.rate_limiter import RateLimiter


class TestMessageBroker:
    """Test cases for MessageBroker class."""
    
    @pytest.fixture
    def mock_validator(self):
        """Create a mock input validator."""
        validator = Mock(spec=InputValidator)
        validator.validate_message.return_value = ValidationResult(
            is_valid=True,
            sanitized_value="test message"
        )
        return validator
    
    @pytest.fixture
    def mock_rate_limiter(self):
        """Create a mock rate limiter."""
        rate_limiter = Mock(spec=RateLimiter)
        rate_limiter.check_message_rate_limit.return_value = True
        return rate_limiter
    
    @pytest.fixture
    def mock_socket(self):
        """Create a mock socket."""
        sock = Mock(spec=socket.socket)
        sock.sendall = Mock()
        return sock
    
    @pytest.fixture
    def sample_user(self):
        """Create a sample user."""
        return User(
            username="testuser",
            address="127.0.0.1:12345",
            connection_time=datetime.now(),
            last_activity=datetime.now()
        )
    
    @pytest.fixture
    def sample_connection(self, mock_socket, sample_user):
        """Create a sample client connection."""
        return ClientConnection(
            socket=mock_socket,
            user=sample_user,
            connection_id="test-client-1"
        )
    
    @pytest.fixture
    def message_broker(self, mock_validator, mock_rate_limiter):
        """Create a MessageBroker instance for testing."""
        return MessageBroker(
            validator=mock_validator,
            rate_limiter=mock_rate_limiter,
            max_message_history=50
        )
    
    def test_initialization(self):
        """Test MessageBroker initialization."""
        broker = MessageBroker()
        
        assert broker.validator is None  # No validator by default
        assert broker.rate_limiter is None
        assert broker.max_message_history == 50  # DEFAULT_MESSAGE_HISTORY
        assert broker.total_messages_processed == 0
        assert broker.total_messages_broadcast == 0
        assert len(broker._client_connections) == 0
        assert len(broker._message_history) == 0
    
    def test_initialization_with_custom_params(self, mock_validator, mock_rate_limiter):
        """Test MessageBroker initialization with custom parameters."""
        broker = MessageBroker(
            validator=mock_validator,
            rate_limiter=mock_rate_limiter,
            max_message_history=100,
            enable_message_logging=False
        )
        
        assert broker.validator == mock_validator
        assert broker.rate_limiter == mock_rate_limiter
        assert broker.max_message_history == 100
        assert broker.enable_message_logging is False
    
    def test_register_client(self, message_broker, sample_connection):
        """Test client registration."""
        client_id = "test-client-1"
        
        message_broker.register_client(client_id, sample_connection)
        
        assert client_id in message_broker._client_connections
        assert message_broker._client_connections[client_id] == sample_connection
    
    def test_unregister_client(self, message_broker, sample_connection):
        """Test client unregistration."""
        client_id = "test-client-1"
        
        # Register first
        message_broker.register_client(client_id, sample_connection)
        assert client_id in message_broker._client_connections
        
        # Unregister
        result = message_broker.unregister_client(client_id)
        
        assert result is True
        assert client_id not in message_broker._client_connections
    
    def test_unregister_nonexistent_client(self, message_broker):
        """Test unregistering a client that doesn't exist."""
        result = message_broker.unregister_client("nonexistent-client")
        assert result is False
    
    def test_process_message_success(self, message_broker, sample_connection):
        """Test successful message processing."""
        client_id = "test-client-1"
        message_broker.register_client(client_id, sample_connection)
        
        result = message_broker.process_message(
            sender_id=client_id,
            message_content="Hello, world!",
            message_type=MessageType.CHAT
        )
        
        assert isinstance(result, MessageDeliveryResult)
        assert result.success is True
        assert result.delivered_count == 0  # No other clients to deliver to
        assert result.failed_count == 0
        assert len(result.errors) == 0
        assert message_broker.total_messages_processed == 1
    
    def test_process_message_sender_not_found(self, message_broker):
        """Test message processing with nonexistent sender."""
        with pytest.raises(MessageBrokerError, match="Sender not found"):
            message_broker.process_message(
                sender_id="nonexistent-sender",
                message_content="Hello, world!"
            )
    
    def test_process_message_rate_limited(self, message_broker, sample_connection):
        """Test message processing when rate limited."""
        client_id = "test-client-1"
        message_broker.register_client(client_id, sample_connection)
        
        # Configure rate limiter to deny requests
        message_broker.rate_limiter.check_message_rate_limit.return_value = False
        
        with pytest.raises(RateLimitExceededError):
            message_broker.process_message(
                sender_id=client_id,
                message_content="Hello, world!"
            )
        
        assert message_broker.total_rate_limit_violations == 1
    
    def test_process_message_validation_failure(self, message_broker, sample_connection):
        """Test message processing with validation failure."""
        client_id = "test-client-1"
        message_broker.register_client(client_id, sample_connection)
        
        # Configure validator to fail
        message_broker.validator.validate_message.return_value = ValidationResult(
            is_valid=False,
            errors=["Message too long"]
        )
        
        with pytest.raises(ValidationError, match="Message validation failed"):
            message_broker.process_message(
                sender_id=client_id,
                message_content="This message is too long"
            )
        
        assert message_broker.total_validation_failures == 1
    
    def test_process_message_with_sanitization(self, message_broker, sample_connection):
        """Test message processing with content sanitization."""
        client_id = "test-client-1"
        message_broker.register_client(client_id, sample_connection)
        
        # Configure validator to sanitize content
        message_broker.validator.validate_message.return_value = ValidationResult(
            is_valid=True,
            sanitized_value="sanitized content"
        )
        
        result = message_broker.process_message(
            sender_id=client_id,
            message_content="<script>alert('xss')</script>"
        )
        
        assert result.success is True
        # Check that sanitized content was used
        history = message_broker.get_message_history()
        assert len(history) == 1
        assert history[0].content == "sanitized content"
    
    def test_broadcast_server_message(self, message_broker, mock_socket):
        """Test broadcasting server messages."""
        # Register multiple clients
        clients = []
        for i in range(3):
            client_id = f"client-{i}"
            user = User(username=f"user{i}", address=f"127.0.0.1:{12345+i}")
            connection = ClientConnection(
                socket=Mock(spec=socket.socket),
                user=user,
                connection_id=client_id
            )
            message_broker.register_client(client_id, connection)
            clients.append((client_id, connection))
        
        result = message_broker.broadcast_server_message("Server announcement")
        
        assert result.success is True
        assert result.delivered_count == 3
        assert result.failed_count == 0
        
        # Verify all clients received the message
        for client_id, connection in clients:
            connection.socket.sendall.assert_called_once()
    
    def test_broadcast_server_message_with_exclusions(self, message_broker):
        """Test broadcasting server messages with client exclusions."""
        # Register multiple clients
        clients = []
        for i in range(3):
            client_id = f"client-{i}"
            user = User(username=f"user{i}", address=f"127.0.0.1:{12345+i}")
            connection = ClientConnection(
                socket=Mock(spec=socket.socket),
                user=user,
                connection_id=client_id
            )
            message_broker.register_client(client_id, connection)
            clients.append((client_id, connection))
        
        # Exclude one client
        exclude_set = {"client-1"}
        result = message_broker.broadcast_server_message(
            "Server announcement",
            exclude_clients=exclude_set
        )
        
        assert result.success is True
        assert result.delivered_count == 2  # 3 - 1 excluded
        assert result.failed_count == 0
        
        # Verify excluded client didn't receive message
        clients[1][1].socket.sendall.assert_not_called()
        
        # Verify other clients received message
        clients[0][1].socket.sendall.assert_called_once()
        clients[2][1].socket.sendall.assert_called_once()
    
    def test_broadcast_user_list(self, message_broker):
        """Test broadcasting user list updates."""
        # Register clients
        for i in range(2):
            client_id = f"client-{i}"
            user = User(username=f"user{i}", address=f"127.0.0.1:{12345+i}")
            connection = ClientConnection(
                socket=Mock(spec=socket.socket),
                user=user,
                connection_id=client_id
            )
            message_broker.register_client(client_id, connection)
        
        user_list_data = "user0(127.0.0.1:12345),user1(127.0.0.1:12346)"
        result = message_broker.broadcast_user_list(user_list_data)
        
        assert result.success is True
        assert result.delivered_count == 2
        assert result.failed_count == 0
    
    def test_send_welcome_message(self, message_broker, sample_connection):
        """Test sending welcome message to new client."""
        client_id = "test-client-1"
        message_broker.register_client(client_id, sample_connection)
        
        # Add some messages to history
        for i in range(3):
            msg = Message(
                content=f"Test message {i}",
                sender=f"user{i}",
                message_type=MessageType.CHAT
            )
            message_broker._add_to_history(msg)
        
        result = message_broker.send_welcome_message(client_id)
        
        assert result is True
        # Should have sent welcome message + history messages
        assert sample_connection.socket.sendall.call_count >= 4
    
    def test_send_welcome_message_client_not_found(self, message_broker):
        """Test sending welcome message to nonexistent client."""
        result = message_broker.send_welcome_message("nonexistent-client")
        assert result is False
    
    def test_message_history_management(self, message_broker):
        """Test message history storage and retrieval."""
        # Add messages to history
        messages = []
        for i in range(5):
            msg = Message(
                content=f"Test message {i}",
                sender=f"user{i}",
                message_type=MessageType.CHAT
            )
            message_broker._add_to_history(msg)
            messages.append(msg)
        
        history = message_broker.get_message_history()
        assert len(history) == 5
        
        # Verify order (should be chronological)
        for i, msg in enumerate(history):
            assert msg.content == f"Test message {i}"
    
    def test_message_history_size_limit(self):
        """Test message history size limiting."""
        broker = MessageBroker(max_message_history=3)
        
        # Add more messages than the limit
        for i in range(5):
            msg = Message(
                content=f"Test message {i}",
                sender=f"user{i}",
                message_type=MessageType.CHAT
            )
            broker._add_to_history(msg)
        
        history = broker.get_message_history()
        assert len(history) == 3
        
        # Should contain the last 3 messages
        assert history[0].content == "Test message 2"
        assert history[1].content == "Test message 3"
        assert history[2].content == "Test message 4"
    
    def test_message_history_filtering(self, message_broker):
        """Test message history filtering by type."""
        # Add different types of messages
        chat_msg = Message(content="Chat", sender="user1", message_type=MessageType.CHAT)
        server_msg = Message(content="Server", sender="Server", message_type=MessageType.SERVER)
        
        message_broker._add_to_history(chat_msg)
        # Server messages are not added to history by default
        
        # Get all messages
        all_history = message_broker.get_message_history()
        assert len(all_history) == 1
        assert all_history[0].message_type == MessageType.CHAT
        
        # Get filtered messages
        chat_history = message_broker.get_message_history(MessageType.CHAT)
        assert len(chat_history) == 1
        assert chat_history[0].message_type == MessageType.CHAT
        
        server_history = message_broker.get_message_history(MessageType.SERVER)
        assert len(server_history) == 0
    
    def test_clear_message_history(self, message_broker):
        """Test clearing message history."""
        # Add messages
        for i in range(3):
            msg = Message(
                content=f"Test message {i}",
                sender=f"user{i}",
                message_type=MessageType.CHAT
            )
            message_broker._add_to_history(msg)
        
        assert len(message_broker.get_message_history()) == 3
        
        cleared_count = message_broker.clear_message_history()
        
        assert cleared_count == 3
        assert len(message_broker.get_message_history()) == 0
    
    def test_statistics(self, message_broker, sample_connection):
        """Test statistics collection."""
        client_id = "test-client-1"
        message_broker.register_client(client_id, sample_connection)
        
        # Process some messages
        message_broker.process_message(client_id, "Test message 1")
        message_broker.process_message(client_id, "Test message 2")
        
        stats = message_broker.get_statistics()
        
        assert stats['total_messages_processed'] == 2
        assert stats['total_messages_broadcast'] == 2
        assert stats['registered_clients'] == 1
        assert stats['current_message_history_size'] == 2
        assert stats['validation_enabled'] is True
        assert stats['rate_limiting_enabled'] is True
        assert 'uptime_seconds' in stats
    
    def test_thread_safety(self, message_broker):
        """Test thread safety of message broker operations."""
        # Register multiple clients
        clients = []
        for i in range(5):
            client_id = f"client-{i}"
            user = User(username=f"user{i}", address=f"127.0.0.1:{12345+i}")
            connection = ClientConnection(
                socket=Mock(spec=socket.socket),
                user=user,
                connection_id=client_id
            )
            message_broker.register_client(client_id, connection)
            clients.append((client_id, connection))
        
        # Function to send messages from multiple threads
        def send_messages(client_id, count):
            for i in range(count):
                try:
                    message_broker.process_message(
                        sender_id=client_id,
                        message_content=f"Message {i} from {client_id}"
                    )
                except Exception:
                    pass  # Ignore errors for this test
        
        # Start multiple threads
        threads = []
        for client_id, _ in clients:
            thread = threading.Thread(target=send_messages, args=(client_id, 10))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify that operations completed without deadlocks
        stats = message_broker.get_statistics()
        assert stats['total_messages_processed'] > 0
    
    def test_socket_error_handling(self, message_broker):
        """Test handling of socket errors during message sending."""
        client_id = "test-client-1"
        
        # Create connection with socket that raises error
        mock_socket = Mock(spec=socket.socket)
        mock_socket.sendall.side_effect = socket.error("Connection broken")
        
        user = User(username="testuser", address="127.0.0.1:12345")
        connection = ClientConnection(
            socket=mock_socket,
            user=user,
            connection_id=client_id
        )
        
        message_broker.register_client(client_id, connection)
        
        # Register another client to receive the broadcast
        client_id_2 = "test-client-2"
        user_2 = User(username="testuser2", address="127.0.0.1:12346")
        connection_2 = ClientConnection(
            socket=Mock(spec=socket.socket),
            user=user_2,
            connection_id=client_id_2
        )
        message_broker.register_client(client_id_2, connection_2)
        
        # Process message - should handle socket error gracefully
        result = message_broker.process_message(
            sender_id=client_id,
            message_content="Test message"
        )
        
        # Should still succeed for the working client
        assert result.delivered_count == 1
        assert result.failed_count == 0  # The broken socket client is excluded from broadcast
    
    def test_register_message_handler(self, message_broker):
        """Test registering custom message handlers."""
        handler_called = False
        
        def custom_handler(message, sender_id):
            nonlocal handler_called
            handler_called = True
            return True
        
        message_broker.register_message_handler(MessageType.COMMAND, custom_handler)
        
        assert MessageType.COMMAND in message_broker._message_handlers
        assert message_broker._message_handlers[MessageType.COMMAND] == custom_handler
    
    def test_shutdown(self, message_broker, sample_connection):
        """Test message broker shutdown."""
        client_id = "test-client-1"
        message_broker.register_client(client_id, sample_connection)
        
        # Add some data
        message_broker._add_to_history(Message(
            content="Test",
            sender="user",
            message_type=MessageType.CHAT
        ))
        
        message_broker.shutdown()
        
        # Verify cleanup
        assert len(message_broker._client_connections) == 0
        assert len(message_broker._message_history) == 0
        assert len(message_broker._message_handlers) == 0


class TestBroadcastFilter:
    """Test cases for BroadcastFilter class."""
    
    def test_default_filter(self):
        """Test default broadcast filter settings."""
        filter_obj = BroadcastFilter()
        
        assert filter_obj.exclude_sender is True
        assert filter_obj.exclude_clients is None
        assert filter_obj.include_only_clients is None
        assert filter_obj.message_type_filter is None
    
    def test_custom_filter(self):
        """Test custom broadcast filter settings."""
        exclude_set = {"client1", "client2"}
        include_set = {"client3", "client4"}
        
        filter_obj = BroadcastFilter(
            exclude_sender=False,
            exclude_clients=exclude_set,
            include_only_clients=include_set,
            message_type_filter=MessageType.SERVER
        )
        
        assert filter_obj.exclude_sender is False
        assert filter_obj.exclude_clients == exclude_set
        assert filter_obj.include_only_clients == include_set
        assert filter_obj.message_type_filter == MessageType.SERVER


class TestMessageDeliveryResult:
    """Test cases for MessageDeliveryResult class."""
    
    def test_successful_delivery(self):
        """Test successful message delivery result."""
        result = MessageDeliveryResult(
            success=True,
            delivered_count=5,
            failed_count=0,
            errors=[],
            rate_limited_clients=[]
        )
        
        assert result.success is True
        assert result.delivered_count == 5
        assert result.failed_count == 0
        assert len(result.errors) == 0
        assert len(result.rate_limited_clients) == 0
    
    def test_failed_delivery(self):
        """Test failed message delivery result."""
        errors = ["Client not found", "Socket error"]
        rate_limited = ["client1", "client2"]
        
        result = MessageDeliveryResult(
            success=False,
            delivered_count=2,
            failed_count=3,
            errors=errors,
            rate_limited_clients=rate_limited
        )
        
        assert result.success is False
        assert result.delivered_count == 2
        assert result.failed_count == 3
        assert result.errors == errors
        assert result.rate_limited_clients == rate_limited


class TestConvenienceFunctions:
    """Test cases for convenience functions."""
    
    def test_create_message_broker_default(self):
        """Test creating message broker with default settings."""
        broker = create_message_broker()
        
        assert broker.validator is not None
        assert broker.rate_limiter is not None
        assert broker.max_message_history == 50
    
    def test_create_message_broker_custom(self):
        """Test creating message broker with custom settings."""
        broker = create_message_broker(
            enable_validation=False,
            enable_rate_limiting=False,
            max_history=100
        )
        
        assert broker.validator is None
        assert broker.rate_limiter is None
        assert broker.max_message_history == 100
    
    def test_create_message_broker_validation_only(self):
        """Test creating message broker with validation only."""
        broker = create_message_broker(
            enable_validation=True,
            enable_rate_limiting=False
        )
        
        assert broker.validator is not None
        assert broker.rate_limiter is None
    
    def test_create_message_broker_rate_limiting_only(self):
        """Test creating message broker with rate limiting only."""
        broker = create_message_broker(
            enable_validation=False,
            enable_rate_limiting=True
        )
        
        assert broker.validator is None
        assert broker.rate_limiter is not None


# Integration tests with real components
class TestMessageBrokerIntegration:
    """Integration tests with real validator and rate limiter."""
    
    def test_integration_with_real_validator(self):
        """Test message broker with real input validator."""
        validator = InputValidator(strict_mode=False)
        broker = MessageBroker(validator=validator)
        
        # Register a client
        client_id = "test-client"
        user = User(username="testuser", address="127.0.0.1:12345")
        connection = ClientConnection(
            socket=Mock(spec=socket.socket),
            user=user,
            connection_id=client_id
        )
        broker.register_client(client_id, connection)
        
        # Test valid message
        result = broker.process_message(client_id, "Hello, world!")
        assert result.success is True
        
        # Test message with potentially dangerous content - should fail with strict validation
        with pytest.raises(ValidationError):
            broker.process_message(client_id, "<script>alert('xss')</script>")
        
        # Test with a message that gets sanitized but doesn't fail
        result = broker.process_message(client_id, "Hello & goodbye")
        assert result.success is True
        
        # Check message history
        history = broker.get_message_history()
        assert len(history) == 2
        assert history[0].content == "Hello, world!"
        assert history[1].content == "Hello &amp; goodbye"  # HTML escaped
    
    def test_integration_with_real_rate_limiter(self):
        """Test message broker with real rate limiter."""
        rate_limiter = RateLimiter(default_rate_per_minute=2, burst_allowance=1)
        broker = MessageBroker(rate_limiter=rate_limiter)
        
        # Register a client
        client_id = "test-client"
        user = User(username="testuser", address="127.0.0.1:12345")
        connection = ClientConnection(
            socket=Mock(spec=socket.socket),
            user=user,
            connection_id=client_id
        )
        broker.register_client(client_id, connection)
        
        # Send messages up to the limit
        for i in range(3):  # 2 per minute + 1 burst
            result = broker.process_message(client_id, f"Message {i}")
            assert result.success is True
        
        # Next message should be rate limited
        with pytest.raises(RateLimitExceededError):
            broker.process_message(client_id, "Rate limited message")
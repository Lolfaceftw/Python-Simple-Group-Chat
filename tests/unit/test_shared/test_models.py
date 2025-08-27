"""
Unit tests for chat_app.shared.models module.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock
import socket

from chat_app.shared.models import (
    User, 
    Message, 
    ClientConnection, 
    MessageType,
    ServerStats
)


class TestMessageType:
    """Test MessageType enum."""
    
    def test_message_types(self):
        """Test all message type values."""
        assert MessageType.CHAT.value == "MSG"
        assert MessageType.SERVER.value == "SRV"
        assert MessageType.USER_LIST.value == "ULIST"
        assert MessageType.COMMAND.value == "CMD"
        assert MessageType.USER_COMMAND.value == "CMD_USER"
    
    def test_message_type_from_string(self):
        """Test creating MessageType from string."""
        assert MessageType("MSG") == MessageType.CHAT
        assert MessageType("SRV") == MessageType.SERVER
        assert MessageType("ULIST") == MessageType.USER_LIST


class TestUser:
    """Test User dataclass."""
    
    def test_user_creation(self):
        """Test creating a User instance."""
        user = User(
            username="testuser",
            address="127.0.0.1:12345"
        )
        
        assert user.username == "testuser"
        assert user.address == "127.0.0.1:12345"
        assert isinstance(user.connection_time, datetime)
        assert isinstance(user.last_activity, datetime)
        assert user.message_count == 0
    
    def test_user_with_custom_times(self):
        """Test creating User with custom timestamps."""
        connection_time = datetime.now() - timedelta(hours=1)
        last_activity = datetime.now() - timedelta(minutes=30)
        
        user = User(
            username="testuser",
            address="127.0.0.1:12345",
            connection_time=connection_time,
            last_activity=last_activity,
            message_count=5
        )
        
        assert user.connection_time == connection_time
        assert user.last_activity == last_activity
        assert user.message_count == 5
    
    def test_user_update_activity(self):
        """Test updating user activity."""
        user = User(username="test", address="127.0.0.1:12345")
        original_activity = user.last_activity
        
        # Simulate some time passing
        import time
        time.sleep(0.01)
        
        user.update_activity()
        
        assert user.last_activity > original_activity
        assert user.message_count == 0  # update_activity doesn't increment message count
    
    def test_user_increment_message_count(self):
        """Test incrementing message count."""
        user = User(username="test", address="127.0.0.1:12345")
        original_activity = user.last_activity
        original_count = user.message_count
        
        # Simulate some time passing
        import time
        time.sleep(0.01)
        
        user.increment_message_count()
        
        assert user.message_count == original_count + 1
        assert user.last_activity > original_activity
    
    def test_user_session_duration(self):
        """Test calculating session duration."""
        connection_time = datetime.now() - timedelta(minutes=30)
        user = User(
            username="test",
            address="127.0.0.1:12345",
            connection_time=connection_time
        )
        
        duration = user.session_duration
        
        # Should be approximately 30 minutes (allowing for small timing differences)
        assert 29 * 60 <= duration <= 31 * 60


class TestMessage:
    """Test Message dataclass."""
    
    def test_message_creation(self):
        """Test creating a Message instance."""
        message = Message(
            content="Hello, world!",
            sender="testuser",
            message_type=MessageType.CHAT
        )
        
        assert message.content == "Hello, world!"
        assert message.sender == "testuser"
        assert message.message_type == MessageType.CHAT
        assert isinstance(message.timestamp, datetime)
    
    def test_message_with_custom_timestamp(self):
        """Test creating Message with custom timestamp."""
        custom_time = datetime.now() - timedelta(hours=1)
        
        message = Message(
            content="Test message",
            sender="user",
            message_type=MessageType.SERVER,
            timestamp=custom_time
        )
        
        assert message.timestamp == custom_time
    
    def test_message_to_protocol_string(self):
        """Test converting message to protocol format."""
        message = Message(
            content="Hello",
            sender="user",
            message_type=MessageType.CHAT
        )
        
        protocol_str = message.to_protocol_string()
        
        assert protocol_str == "MSG|Hello"
    
    def test_server_message_to_protocol_string(self):
        """Test converting server message to protocol format."""
        message = Message(
            content="User joined",
            sender="server",
            message_type=MessageType.SERVER
        )
        
        protocol_str = message.to_protocol_string()
        
        assert protocol_str == "SRV|User joined"
    
    def test_message_from_protocol_string(self):
        """Test creating message from protocol string."""
        protocol_str = "MSG|Hello everyone!"
        
        message = Message.from_protocol_string(protocol_str, sender="testuser")
        
        assert message.message_type == MessageType.CHAT
        assert message.sender == "testuser"
        assert message.content == "Hello everyone!"
    
    def test_server_message_from_protocol_string(self):
        """Test creating server message from protocol string."""
        protocol_str = "SRV|User disconnected"
        
        message = Message.from_protocol_string(protocol_str, sender="server")
        
        assert message.message_type == MessageType.SERVER
        assert message.sender == "server"
        assert message.content == "User disconnected"
    
    def test_invalid_protocol_string_defaults_to_chat(self):
        """Test that invalid protocol string defaults to CHAT type."""
        protocol_str = "INVALID|Some content"
        
        message = Message.from_protocol_string(protocol_str, sender="user")
        
        assert message.message_type == MessageType.CHAT
        assert message.content == "Some content"
    
    def test_message_with_recipient(self):
        """Test message with recipient for direct messages."""
        message = Message(
            content="Private message",
            sender="user1",
            recipient="user2",
            message_type=MessageType.CHAT
        )
        
        assert message.recipient == "user2"
        assert message.sender == "user1"
        assert message.content == "Private message"


class TestClientConnection:
    """Test ClientConnection dataclass."""
    
    def test_client_connection_creation(self):
        """Test creating a ClientConnection instance."""
        mock_socket = Mock(spec=socket.socket)
        user = User(username="test", address="127.0.0.1:12345")
        
        connection = ClientConnection(
            socket=mock_socket,
            user=user,
            connection_id="client_1"
        )
        
        assert connection.socket == mock_socket
        assert connection.user == user
        assert connection.connection_id == "client_1"
        assert connection.rate_limit_tokens == 60  # Default rate limit
        assert isinstance(connection.last_token_refresh, datetime)
    
    def test_client_connection_consume_token(self):
        """Test consuming rate limit tokens."""
        mock_socket = Mock(spec=socket.socket)
        user = User(username="test", address="127.0.0.1:12345")
        connection = ClientConnection(
            socket=mock_socket,
            user=user,
            connection_id="client_1"
        )
        
        # Should have tokens initially
        initial_tokens = connection.rate_limit_tokens
        success = connection.consume_token()
        
        assert success is True
        assert connection.rate_limit_tokens == initial_tokens - 1
    
    def test_client_connection_consume_token_when_empty(self):
        """Test consuming token when no tokens available."""
        mock_socket = Mock(spec=socket.socket)
        user = User(username="test", address="127.0.0.1:12345")
        connection = ClientConnection(
            socket=mock_socket,
            user=user,
            connection_id="client_1",
            rate_limit_tokens=0
        )
        
        success = connection.consume_token()
        
        assert success is False
        assert connection.rate_limit_tokens == 0
    
    def test_client_connection_refresh_rate_limit_tokens(self):
        """Test refreshing rate limit tokens."""
        mock_socket = Mock(spec=socket.socket)
        user = User(username="test", address="127.0.0.1:12345")
        
        # Set last refresh to 1 minute ago
        past_time = datetime.now() - timedelta(minutes=1)
        connection = ClientConnection(
            socket=mock_socket,
            user=user,
            connection_id="client_1",
            rate_limit_tokens=30,
            last_token_refresh=past_time
        )
        
        connection.refresh_rate_limit_tokens(tokens_per_minute=60)
        
        # Should have refreshed tokens (up to the limit)
        assert connection.rate_limit_tokens == 60
        assert connection.last_token_refresh > past_time


class TestServerStats:
    """Test ServerStats dataclass."""
    
    def test_server_stats_creation(self):
        """Test creating ServerStats instance."""
        stats = ServerStats()
        
        assert stats.total_connections == 0
        assert stats.current_connections == 0
        assert stats.messages_sent == 0
        assert stats.messages_received == 0
        assert stats.rate_limit_violations == 0
        assert stats.connection_limit_violations == 0
        assert isinstance(stats.start_time, datetime)
    
    def test_server_stats_increment_connection(self):
        """Test incrementing connection statistics."""
        stats = ServerStats()
        
        stats.increment_connection()
        assert stats.total_connections == 1
        assert stats.current_connections == 1
        
        stats.increment_connection()
        assert stats.total_connections == 2
        assert stats.current_connections == 2
    
    def test_server_stats_decrement_connection(self):
        """Test decrementing connection statistics."""
        stats = ServerStats()
        stats.increment_connection()
        stats.increment_connection()
        
        stats.decrement_connection()
        assert stats.total_connections == 2  # Total doesn't decrease
        assert stats.current_connections == 1
        
        stats.decrement_connection()
        assert stats.current_connections == 0
        
        # Should not go below 0
        stats.decrement_connection()
        assert stats.current_connections == 0
    
    def test_server_stats_uptime_seconds(self):
        """Test calculating server uptime."""
        start_time = datetime.now() - timedelta(minutes=30)
        stats = ServerStats(start_time=start_time)
        
        uptime = stats.uptime_seconds
        
        # Should be approximately 30 minutes
        assert 29 * 60 <= uptime <= 31 * 60
    
    def test_server_stats_with_custom_values(self):
        """Test ServerStats with custom values."""
        stats = ServerStats(
            total_connections=10,
            current_connections=5,
            messages_sent=100,
            messages_received=95,
            rate_limit_violations=2,
            connection_limit_violations=1
        )
        
        assert stats.total_connections == 10
        assert stats.current_connections == 5
        assert stats.messages_sent == 100
        assert stats.messages_received == 95
        assert stats.rate_limit_violations == 2
        assert stats.connection_limit_violations == 1


class TestConnectionStatus:
    """Test ConnectionStatus enum."""
    
    def test_connection_status_values(self):
        """Test ConnectionStatus enum values."""
        from chat_app.shared.models import ConnectionStatus
        
        assert ConnectionStatus.DISCONNECTED.value == "disconnected"
        assert ConnectionStatus.CONNECTING.value == "connecting"
        assert ConnectionStatus.CONNECTED.value == "connected"
        assert ConnectionStatus.RECONNECTING.value == "reconnecting"
        assert ConnectionStatus.ERROR.value == "error"


class TestClientState:
    """Test ClientState dataclass."""
    
    def test_client_state_creation(self):
        """Test creating ClientState instance."""
        from chat_app.shared.models import ClientState, ConnectionStatus
        
        state = ClientState(username="testuser")
        
        assert state.username == "testuser"
        assert state.connection_status == ConnectionStatus.DISCONNECTED
        assert state.server_host is None
        assert state.server_port is None
        assert state.scroll_offset == 0
        assert state.active_panel == "chat"
        assert state.unseen_messages_count == 0
        assert state.is_scrolled_to_bottom is True
    
    def test_client_state_reset_scroll_state(self):
        """Test resetting scroll state."""
        from chat_app.shared.models import ClientState
        
        state = ClientState(
            username="testuser",
            scroll_offset=10,
            unseen_messages_count=5,
            is_scrolled_to_bottom=False,
            user_panel_scroll_offset=3
        )
        
        state.reset_scroll_state()
        
        assert state.scroll_offset == 0
        assert state.is_scrolled_to_bottom is True
        assert state.unseen_messages_count == 0
        assert state.user_panel_scroll_offset == 0


class TestNetworkMessage:
    """Test NetworkMessage dataclass."""
    
    def test_network_message_creation(self):
        """Test creating NetworkMessage instance."""
        from chat_app.shared.models import NetworkMessage
        
        message = NetworkMessage(data=b"Hello World")
        
        assert message.data == b"Hello World"
        assert message.source_address is None
        assert isinstance(message.timestamp, datetime)
    
    def test_network_message_decode(self):
        """Test decoding network message."""
        from chat_app.shared.models import NetworkMessage
        
        message = NetworkMessage(data="Hello World".encode('utf-8'))
        decoded = message.decode()
        
        assert decoded == "Hello World"
    
    def test_network_message_from_string(self):
        """Test creating NetworkMessage from string."""
        from chat_app.shared.models import NetworkMessage
        
        message = NetworkMessage.from_string("Hello World")
        
        assert message.data == b"Hello World"
        assert message.decode() == "Hello World"


class TestDiscoveryResponse:
    """Test DiscoveryResponse dataclass."""
    
    def test_discovery_response_creation(self):
        """Test creating DiscoveryResponse instance."""
        from chat_app.shared.models import DiscoveryResponse
        
        response = DiscoveryResponse(
            server_address="192.168.1.1",
            server_port=8080
        )
        
        assert response.server_address == "192.168.1.1"
        assert response.server_port == 8080
        assert isinstance(response.discovery_time, datetime)
        assert response.response_time_ms is None
    
    def test_discovery_response_server_endpoint(self):
        """Test server endpoint property."""
        from chat_app.shared.models import DiscoveryResponse
        
        response = DiscoveryResponse(
            server_address="192.168.1.1",
            server_port=8080
        )
        
        assert response.server_endpoint == "192.168.1.1:8080"


class TestRateLimitInfo:
    """Test RateLimitInfo dataclass."""
    
    def test_rate_limit_info_creation(self):
        """Test creating RateLimitInfo instance."""
        from chat_app.shared.models import RateLimitInfo
        
        info = RateLimitInfo(
            client_id="client_123",
            tokens_remaining=50,
            tokens_per_minute=60
        )
        
        assert info.client_id == "client_123"
        assert info.tokens_remaining == 50
        assert info.tokens_per_minute == 60
        assert isinstance(info.last_request_time, datetime)
        assert info.violation_count == 0
    
    def test_rate_limit_info_is_rate_limited(self):
        """Test checking if client is rate limited."""
        from chat_app.shared.models import RateLimitInfo
        
        # Not rate limited
        info = RateLimitInfo(
            client_id="client_123",
            tokens_remaining=10,
            tokens_per_minute=60
        )
        assert info.is_rate_limited() is False
        
        # Rate limited
        info.tokens_remaining = 0
        assert info.is_rate_limited() is True
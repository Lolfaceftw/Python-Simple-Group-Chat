"""
Unit Tests for ChatServer

Tests for server lifecycle, error handling, and integration with modular components.
"""

import pytest
import socket
import threading
import time
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime

from chat_app.server.chat_server import ChatServer
from chat_app.shared.config import ServerConfig
from chat_app.shared.exceptions import ChatServerError, ConfigurationError, SecurityError
from chat_app.shared.models import User, ClientConnection, Message, MessageType


class TestChatServerInitialization:
    """Test ChatServer initialization and configuration."""
    
    def test_init_with_default_config(self):
        """Test server initialization with default configuration."""
        server = ChatServer()
        
        assert server.config is not None
        assert isinstance(server.config, ServerConfig)
        assert server.server_socket is None
        assert not server.is_running
        assert server.shutdown_event is not None
        
        # Check that components are initialized
        assert server.validator is not None
        assert server.rate_limiter is not None
        assert server.connection_limiter is not None
        assert server.client_manager is not None
        assert server.message_broker is not None
    
    def test_init_with_custom_config(self):
        """Test server initialization with custom configuration."""
        config = ServerConfig(
            host="127.0.0.1",
            port=9999,
            max_clients=50,
            rate_limit_messages_per_minute=30
        )
        
        server = ChatServer(config)
        
        assert server.config == config
        assert server.config.host == "127.0.0.1"
        assert server.config.port == 9999
        assert server.config.max_clients == 50
        assert server.config.rate_limit_messages_per_minute == 30
    
    def test_signal_handlers_setup(self):
        """Test that signal handlers are set up correctly."""
        with patch('signal.signal') as mock_signal:
            server = ChatServer()
            
            # Verify signal handlers were registered
            assert mock_signal.call_count >= 1


class TestChatServerConfiguration:
    """Test server configuration validation."""
    
    def test_validate_configuration_valid(self):
        """Test configuration validation with valid config."""
        config = ServerConfig(port=8080, max_clients=100, rate_limit_messages_per_minute=60)
        server = ChatServer(config)
        
        # Should not raise any exception
        server._validate_configuration()
    
    def test_validate_configuration_invalid_port(self):
        """Test configuration validation with invalid port."""
        config = ServerConfig(port=80)  # Port too low
        server = ChatServer(config)
        
        with pytest.raises(ConfigurationError, match="Invalid port number"):
            server._validate_configuration()
    
    def test_validate_configuration_invalid_max_clients(self):
        """Test configuration validation with invalid max_clients."""
        config = ServerConfig(max_clients=0)
        server = ChatServer(config)
        
        with pytest.raises(ConfigurationError, match="Invalid max_clients"):
            server._validate_configuration()
    
    def test_validate_configuration_invalid_rate_limit(self):
        """Test configuration validation with invalid rate limit."""
        config = ServerConfig(rate_limit_messages_per_minute=0)
        server = ChatServer(config)
        
        with pytest.raises(ConfigurationError, match="Invalid rate limit"):
            server._validate_configuration()


class TestChatServerSocketOperations:
    """Test server socket creation and binding."""
    
    @patch('socket.socket')
    def test_create_server_socket_success(self, mock_socket_class):
        """Test successful server socket creation."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        
        server = ChatServer()
        server._create_server_socket()
        
        assert server.server_socket == mock_socket
        mock_socket.setsockopt.assert_called_with(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        mock_socket.settimeout.assert_called_once()
    
    @patch('socket.socket')
    def test_create_server_socket_failure(self, mock_socket_class):
        """Test server socket creation failure."""
        mock_socket_class.side_effect = OSError("Socket creation failed")
        
        server = ChatServer()
        
        with pytest.raises(ChatServerError, match="Failed to create server socket"):
            server._create_server_socket()
    
    def test_bind_and_listen_success(self):
        """Test successful socket binding and listening."""
        server = ChatServer()
        server.server_socket = Mock()
        
        server._bind_and_listen()
        
        server.server_socket.bind.assert_called_once_with((server.config.host, server.config.port))
        server.server_socket.listen.assert_called_once_with(server.config.max_clients)
    
    def test_bind_and_listen_address_in_use(self):
        """Test socket binding failure due to address in use."""
        server = ChatServer()
        server.server_socket = Mock()
        
        error = OSError("Address already in use")
        error.errno = 98
        server.server_socket.bind.side_effect = error
        
        with pytest.raises(ChatServerError, match="Port .* is already in use"):
            server._bind_and_listen()
    
    def test_bind_and_listen_permission_denied(self):
        """Test socket binding failure due to permission denied."""
        server = ChatServer()
        server.server_socket = Mock()
        
        error = OSError("Permission denied")
        error.errno = 13
        server.server_socket.bind.side_effect = error
        
        with pytest.raises(ChatServerError, match="Permission denied"):
            server._bind_and_listen()


class TestChatServerLifecycle:
    """Test server lifecycle management."""
    
    @patch.object(ChatServer, '_run_server_loop')
    @patch.object(ChatServer, '_start_cleanup_service')
    @patch.object(ChatServer, '_start_discovery_service')
    @patch.object(ChatServer, '_bind_and_listen')
    @patch.object(ChatServer, '_create_server_socket')
    @patch.object(ChatServer, '_validate_configuration')
    def test_start_success(self, mock_validate, mock_create, mock_bind, 
                          mock_discovery, mock_cleanup, mock_loop):
        """Test successful server start."""
        server = ChatServer()
        
        server.start()
        
        assert server.is_running
        assert server.start_time is not None
        mock_validate.assert_called_once()
        mock_create.assert_called_once()
        mock_bind.assert_called_once()
        mock_discovery.assert_called_once()
        mock_cleanup.assert_called_once()
        mock_loop.assert_called_once()
    
    def test_start_already_running(self):
        """Test starting server when already running."""
        server = ChatServer()
        server.is_running = True
        
        with pytest.raises(ChatServerError, match="Server is already running"):
            server.start()
    
    @patch.object(ChatServer, '_validate_configuration')
    def test_start_validation_failure(self, mock_validate):
        """Test server start failure due to validation error."""
        mock_validate.side_effect = ConfigurationError("Invalid config")
        
        server = ChatServer()
        
        with pytest.raises(ChatServerError, match="Server startup failed"):
            server.start()
        
        assert not server.is_running
    
    @patch.object(ChatServer, '_shutdown_components')
    @patch.object(ChatServer, '_shutdown_background_threads')
    @patch.object(ChatServer, '_shutdown_client_threads')
    def test_shutdown_success(self, mock_client_threads, mock_bg_threads, mock_components):
        """Test successful server shutdown."""
        server = ChatServer()
        server.is_running = True
        server.server_socket = Mock()
        
        server.shutdown()
        
        assert not server.is_running
        assert server.shutdown_event.is_set()
        server.server_socket.close.assert_called_once()
        mock_client_threads.assert_called_once()
        mock_bg_threads.assert_called_once()
        mock_components.assert_called_once()
    
    def test_shutdown_not_running(self):
        """Test shutdown when server is not running."""
        server = ChatServer()
        server.is_running = False
        
        # Should not raise any exception
        server.shutdown()
    
    @patch.object(ChatServer, '_shutdown_components')
    def test_shutdown_with_error(self, mock_components):
        """Test shutdown with component error."""
        mock_components.side_effect = Exception("Shutdown error")
        
        server = ChatServer()
        server.is_running = True
        server.server_socket = Mock()
        
        # Should not raise exception, just log error
        server.shutdown()
        
        assert not server.is_running


class TestChatServerClientHandling:
    """Test client connection handling."""
    
    def test_handle_new_client_success(self):
        """Test successful new client handling."""
        server = ChatServer()
        server.client_manager = Mock()
        server.message_broker = Mock()
        
        # Mock client connection
        mock_socket = Mock()
        address = ("127.0.0.1", 12345)
        client_id = "test-client-id"
        
        # Mock user and connection
        mock_user = User(username="TestUser", address="127.0.0.1:12345", 
                        connection_time=datetime.now(), last_activity=datetime.now())
        mock_connection = ClientConnection(socket=mock_socket, user=mock_user, connection_id=client_id)
        
        server.client_manager.add_client.return_value = client_id
        server.client_manager.get_client.return_value = mock_connection
        server.client_manager.get_user_list_string.return_value = "TestUser(127.0.0.1:12345)"
        
        with patch('threading.Thread') as mock_thread:
            server._handle_new_client(mock_socket, address)
        
        # Verify client was added and registered
        server.client_manager.add_client.assert_called_once_with(mock_socket, address)
        server.message_broker.register_client.assert_called_once_with(client_id, mock_connection)
        server.message_broker.send_welcome_message.assert_called_once_with(client_id)
        
        # Verify thread was started
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
    
    def test_handle_new_client_security_error(self):
        """Test new client handling with security error."""
        server = ChatServer()
        server.client_manager = Mock()
        server.total_connections_rejected = 0
        
        mock_socket = Mock()
        address = ("127.0.0.1", 12345)
        
        server.client_manager.add_client.side_effect = SecurityError("Connection rejected")
        
        server._handle_new_client(mock_socket, address)
        
        # Verify socket was closed and rejection counted
        mock_socket.close.assert_called_once()
        assert server.total_connections_rejected == 1
    
    def test_handle_new_client_general_error(self):
        """Test new client handling with general error."""
        server = ChatServer()
        server.client_manager = Mock()
        server.total_connections_rejected = 0
        
        mock_socket = Mock()
        address = ("127.0.0.1", 12345)
        
        server.client_manager.add_client.side_effect = Exception("General error")
        
        server._handle_new_client(mock_socket, address)
        
        # Verify socket was closed and rejection counted
        mock_socket.close.assert_called_once()
        assert server.total_connections_rejected == 1


class TestChatServerMessageProcessing:
    """Test message processing functionality."""
    
    def test_process_client_message_chat(self):
        """Test processing a chat message."""
        server = ChatServer()
        server.message_broker = Mock()
        server.client_manager = Mock()
        
        client_id = "test-client"
        message = "MSG|Hello, world!"
        
        # Mock connection
        mock_user = User(username="TestUser", address="127.0.0.1:12345",
                        connection_time=datetime.now(), last_activity=datetime.now())
        mock_connection = ClientConnection(socket=Mock(), user=mock_user, connection_id=client_id)
        server.client_manager.get_client.return_value = mock_connection
        
        server._process_client_message(client_id, message)
        
        # Verify the call was made with correct parameters
        server.message_broker.process_message.assert_called_once()
        call_args = server.message_broker.process_message.call_args
        assert call_args.kwargs['sender_id'] == client_id
        assert call_args.kwargs['message_content'] == "Hello, world!"
        assert call_args.kwargs['message_type'] == MessageType.CHAT
    
    def test_process_client_message_username_change(self):
        """Test processing a username change message."""
        server = ChatServer()
        server.validator = Mock()
        server.client_manager = Mock()
        server.message_broker = Mock()
        
        # Mock validation result
        validation_result = Mock()
        validation_result.is_valid = True
        server.validator.validate_username.return_value = validation_result
        
        # Mock username change
        server.client_manager.update_username.return_value = (True, "OldUser")
        
        # Mock connection
        mock_user = User(username="NewUser", address="127.0.0.1:12345",
                        connection_time=datetime.now(), last_activity=datetime.now())
        mock_connection = ClientConnection(socket=Mock(), user=mock_user, connection_id="test-client")
        server.client_manager.get_client.return_value = mock_connection
        server.client_manager.get_user_list_string.return_value = "NewUser(127.0.0.1:12345)"
        
        client_id = "test-client"
        message = "CMD_USER|NewUser"
        
        server._process_client_message(client_id, message)
        
        # Verify username validation and update
        server.validator.validate_username.assert_called_once_with("NewUser")
        server.client_manager.update_username.assert_called_once_with(client_id, "NewUser")
        
        # Verify notifications were sent
        server.message_broker.broadcast_server_message.assert_called()
        server.message_broker.broadcast_user_list.assert_called()
    
    def test_process_client_message_invalid_username(self):
        """Test processing an invalid username change."""
        server = ChatServer()
        server.validator = Mock()
        server.client_manager = Mock()
        
        # Mock validation failure
        validation_result = Mock()
        validation_result.is_valid = False
        validation_result.errors = ["Username too long"]
        server.validator.validate_username.return_value = validation_result
        
        client_id = "test-client"
        message = "CMD_USER|VeryLongInvalidUsername"
        
        server._process_client_message(client_id, message)
        
        # Verify validation was called but update was not
        server.validator.validate_username.assert_called_once()
        server.client_manager.update_username.assert_not_called()
    
    def test_process_client_message_unknown_type(self):
        """Test processing a message with unknown type."""
        server = ChatServer()
        server.client_manager = Mock()
        
        # Mock connection
        mock_user = User(username="TestUser", address="127.0.0.1:12345",
                        connection_time=datetime.now(), last_activity=datetime.now())
        mock_connection = ClientConnection(socket=Mock(), user=mock_user, connection_id="test-client")
        server.client_manager.get_client.return_value = mock_connection
        
        client_id = "test-client"
        message = "UNKNOWN|Some payload"
        
        # Should not raise exception, just log warning
        server._process_client_message(client_id, message)


class TestChatServerClientCleanup:
    """Test client cleanup functionality."""
    
    def test_cleanup_client_success(self):
        """Test successful client cleanup."""
        server = ChatServer()
        server.message_broker = Mock()
        server.client_manager = Mock()
        
        client_id = "test-client"
        
        # Mock connection
        mock_user = User(username="TestUser", address="127.0.0.1:12345",
                        connection_time=datetime.now(), last_activity=datetime.now())
        mock_connection = ClientConnection(socket=Mock(), user=mock_user, connection_id=client_id)
        server.client_manager.get_client.return_value = mock_connection
        server.client_manager.remove_client.return_value = True
        server.client_manager.get_user_list_string.return_value = ""
        
        # Add client thread reference
        server.client_threads[client_id] = Mock()
        
        server._cleanup_client(client_id)
        
        # Verify cleanup sequence
        server.message_broker.unregister_client.assert_called_once_with(client_id)
        server.client_manager.remove_client.assert_called_once_with(client_id)
        server.message_broker.broadcast_server_message.assert_called()
        server.message_broker.broadcast_user_list.assert_called()
        
        # Verify thread reference was removed
        assert client_id not in server.client_threads
    
    def test_cleanup_client_not_found(self):
        """Test cleanup when client is not found."""
        server = ChatServer()
        server.message_broker = Mock()
        server.client_manager = Mock()
        
        client_id = "nonexistent-client"
        
        server.client_manager.get_client.return_value = None
        server.client_manager.remove_client.return_value = False
        
        # Should not raise exception
        server._cleanup_client(client_id)
        
        server.message_broker.unregister_client.assert_called_once_with(client_id)


class TestChatServerStatistics:
    """Test server statistics functionality."""
    
    def test_get_server_statistics(self):
        """Test getting server statistics."""
        server = ChatServer()
        server.is_running = True
        server.start_time = datetime.now()
        server.total_connections_accepted = 10
        server.total_connections_rejected = 2
        
        # Mock component statistics
        server.client_manager.get_client_statistics = Mock(return_value={'clients': 5})
        server.message_broker.get_statistics = Mock(return_value={'messages': 100})
        server.rate_limiter.get_statistics = Mock(return_value={'violations': 3})
        server.connection_limiter.get_statistics = Mock(return_value={'connections': 5})
        
        stats = server.get_server_statistics()
        
        assert 'server_info' in stats
        assert stats['server_info']['is_running'] is True
        assert stats['server_info']['total_connections_accepted'] == 10
        assert stats['server_info']['total_connections_rejected'] == 2
        assert 'client_manager' in stats
        assert 'message_broker' in stats
        assert 'rate_limiter' in stats
        assert 'connection_limiter' in stats


class TestChatServerDiscoveryService:
    """Test service discovery functionality."""
    
    @patch('socket.socket')
    def test_run_discovery_service(self, mock_socket_class):
        """Test discovery service operation."""
        mock_socket = Mock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        
        server = ChatServer()
        server.is_running = True
        
        # Mock shutdown event to stop after one iteration
        server.shutdown_event.is_set = Mock(side_effect=[False, True])
        server.shutdown_event.wait = Mock()
        
        server._run_discovery_service()
        
        # Verify socket configuration
        mock_socket.setsockopt.assert_called_with(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        # Verify broadcast was sent
        mock_socket.sendto.assert_called_with(
            server.config.discovery_message if hasattr(server.config, 'discovery_message') else b"PYTHON_CHAT_SERVER_DISCOVERY_V1",
            ('<broadcast>', server.config.discovery_port)
        )
    
    def test_start_discovery_service(self):
        """Test starting discovery service."""
        server = ChatServer()
        
        with patch('threading.Thread') as mock_thread:
            server._start_discovery_service()
        
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
        assert server.discovery_thread is not None


class TestChatServerCleanupService:
    """Test cleanup service functionality."""
    
    def test_run_cleanup_service(self):
        """Test cleanup service operation."""
        server = ChatServer()
        server.is_running = True
        server.client_manager = Mock()
        server.rate_limiter = Mock()
        server.connection_limiter = Mock()
        
        # Mock shutdown event to stop after one iteration
        server.shutdown_event.is_set = Mock(side_effect=[False, True])
        server.shutdown_event.wait = Mock()
        
        server.client_manager.cleanup_inactive_clients.return_value = 2
        
        server._run_cleanup_service()
        
        # Verify cleanup methods were called
        server.client_manager.cleanup_inactive_clients.assert_called_once_with(30)
        server.rate_limiter.cleanup_expired_entries.assert_called_once()
        server.connection_limiter.cleanup_expired_connections.assert_called_once()
    
    def test_start_cleanup_service(self):
        """Test starting cleanup service."""
        server = ChatServer()
        
        with patch('threading.Thread') as mock_thread:
            server._start_cleanup_service()
        
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
        assert server.cleanup_thread is not None


class TestChatServerErrorHandling:
    """Test error handling scenarios."""
    
    def test_handle_client_communication_connection_reset(self):
        """Test handling connection reset error."""
        server = ChatServer()
        server.client_manager = Mock()
        
        client_id = "test-client"
        mock_socket = Mock()
        mock_socket.recv.side_effect = ConnectionResetError("Connection reset")
        
        mock_user = User(username="TestUser", address="127.0.0.1:12345",
                        connection_time=datetime.now(), last_activity=datetime.now())
        mock_connection = ClientConnection(socket=mock_socket, user=mock_user, connection_id=client_id)
        server.client_manager.get_client.return_value = mock_connection
        
        with patch.object(server, '_cleanup_client') as mock_cleanup:
            server._handle_client_communication(client_id)
        
        mock_cleanup.assert_called_once_with(client_id)
    
    def test_handle_client_communication_broken_pipe(self):
        """Test handling broken pipe error."""
        server = ChatServer()
        server.client_manager = Mock()
        
        client_id = "test-client"
        mock_socket = Mock()
        mock_socket.recv.side_effect = BrokenPipeError("Broken pipe")
        
        mock_user = User(username="TestUser", address="127.0.0.1:12345",
                        connection_time=datetime.now(), last_activity=datetime.now())
        mock_connection = ClientConnection(socket=mock_socket, user=mock_user, connection_id=client_id)
        server.client_manager.get_client.return_value = mock_connection
        
        with patch.object(server, '_cleanup_client') as mock_cleanup:
            server._handle_client_communication(client_id)
        
        mock_cleanup.assert_called_once_with(client_id)
    
    def test_handle_client_communication_no_data(self):
        """Test handling client disconnect (no data)."""
        server = ChatServer()
        server.client_manager = Mock()
        
        client_id = "test-client"
        mock_socket = Mock()
        mock_socket.recv.return_value = b''  # No data indicates disconnect
        
        mock_user = User(username="TestUser", address="127.0.0.1:12345",
                        connection_time=datetime.now(), last_activity=datetime.now())
        mock_connection = ClientConnection(socket=mock_socket, user=mock_user, connection_id=client_id)
        server.client_manager.get_client.return_value = mock_connection
        
        with patch.object(server, '_cleanup_client') as mock_cleanup:
            server._handle_client_communication(client_id)
        
        mock_cleanup.assert_called_once_with(client_id)


@pytest.fixture
def server_config():
    """Fixture providing a test server configuration."""
    return ServerConfig(
        host="127.0.0.1",
        port=8888,
        max_clients=10,
        rate_limit_messages_per_minute=30,
        max_message_length=500,
        max_username_length=20,
        max_connections_per_ip=3,
        message_history_size=25,
        discovery_port=8889,
        discovery_broadcast_interval=3
    )


@pytest.fixture
def chat_server(server_config):
    """Fixture providing a ChatServer instance for testing."""
    return ChatServer(server_config)
"""
Unit tests for the Connection class.
"""

import pytest
import socket
import threading
import time
from unittest.mock import Mock, patch, MagicMock

from chat_app.client.network.connection import Connection, ConnectionConfig
from chat_app.shared.models import ConnectionStatus


class TestConnectionConfig:
    """Test ConnectionConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = ConnectionConfig("localhost", 8080)
        
        assert config.host == "localhost"
        assert config.port == 8080
        assert config.timeout == 1.0
        assert config.buffer_size == 4096
        assert config.max_reconnect_attempts == 5
        assert config.reconnect_delay == 2.0
        assert config.enable_keepalive is True
    
    def test_custom_values(self):
        """Test custom configuration values."""
        config = ConnectionConfig(
            host="192.168.1.1",
            port=9090,
            timeout=5.0,
            buffer_size=8192,
            max_reconnect_attempts=3,
            reconnect_delay=1.0,
            enable_keepalive=False
        )
        
        assert config.host == "192.168.1.1"
        assert config.port == 9090
        assert config.timeout == 5.0
        assert config.buffer_size == 8192
        assert config.max_reconnect_attempts == 3
        assert config.reconnect_delay == 1.0
        assert config.enable_keepalive is False


class TestConnection:
    """Test Connection class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = ConnectionConfig("localhost", 8080, timeout=0.1)
        self.connection = Connection(self.config)
    
    def test_initial_state(self):
        """Test initial connection state."""
        assert self.connection.get_status() == ConnectionStatus.DISCONNECTED
        assert not self.connection.is_connected()
        assert self.connection.get_last_error() is None
    
    def test_set_callbacks(self):
        """Test setting event callbacks."""
        on_connected = Mock()
        on_disconnected = Mock()
        on_error = Mock()
        on_data_received = Mock()
        
        self.connection.set_callbacks(
            on_connected=on_connected,
            on_disconnected=on_disconnected,
            on_error=on_error,
            on_data_received=on_data_received
        )
        
        assert self.connection._on_connected == on_connected
        assert self.connection._on_disconnected == on_disconnected
        assert self.connection._on_error == on_error
        assert self.connection._on_data_received == on_data_received
    
    @patch('socket.socket')
    def test_successful_connection(self, mock_socket_class):
        """Test successful connection establishment."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        
        on_connected = Mock()
        self.connection.set_callbacks(on_connected=on_connected)
        
        result = self.connection.connect()
        
        assert result is True
        assert self.connection.get_status() == ConnectionStatus.CONNECTED
        assert self.connection.is_connected()
        mock_socket.connect.assert_called_once_with(("localhost", 8080))
        mock_socket.settimeout.assert_called_once_with(0.1)
        on_connected.assert_called_once()
    
    @patch('socket.socket')
    def test_connection_failure(self, mock_socket_class):
        """Test connection failure handling."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.connect.side_effect = ConnectionRefusedError("Connection refused")
        
        on_error = Mock()
        self.connection.set_callbacks(on_error=on_error)
        
        result = self.connection.connect()
        
        assert result is False
        assert self.connection.get_status() == ConnectionStatus.ERROR
        assert not self.connection.is_connected()
        assert "Connection refused" in self.connection.get_last_error()
        on_error.assert_called_once()
    
    @patch('socket.socket')
    def test_disconnect(self, mock_socket_class):
        """Test disconnection."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        
        # First connect
        self.connection.connect()
        
        on_disconnected = Mock()
        self.connection.set_callbacks(on_disconnected=on_disconnected)
        
        self.connection.disconnect()
        
        assert self.connection.get_status() == ConnectionStatus.DISCONNECTED
        assert not self.connection.is_connected()
        mock_socket.close.assert_called_once()
        on_disconnected.assert_called_once()
    
    @patch('socket.socket')
    def test_send_message(self, mock_socket_class):
        """Test sending messages."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        
        # Connect first
        self.connection.connect()
        
        self.connection.send_message("Hello, World!")
        
        expected_data = b"Hello, World!\n"
        mock_socket.send.assert_called_once_with(expected_data)
    
    def test_send_when_disconnected(self):
        """Test sending when not connected."""
        with pytest.raises(ConnectionError, match="Not connected"):
            self.connection.send(b"test")
    
    @patch('socket.socket')
    def test_send_failure(self, mock_socket_class):
        """Test send failure handling."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.send.side_effect = BrokenPipeError("Broken pipe")
        
        # Connect first
        self.connection.connect()
        
        on_error = Mock()
        self.connection.set_callbacks(on_error=on_error)
        
        with pytest.raises(ConnectionError, match="Failed to send data"):
            self.connection.send(b"test")
        
        assert self.connection.get_status() == ConnectionStatus.ERROR
        on_error.assert_called_once()
    
    @patch('socket.socket')
    def test_receive_data(self, mock_socket_class):
        """Test receiving data."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.recv.return_value = b"test data"
        
        # Connect first
        self.connection.connect()
        
        data = self.connection.receive()
        
        assert data == b"test data"
        mock_socket.recv.assert_called_once_with(4096)
    
    @patch('socket.socket')
    def test_receive_empty_data(self, mock_socket_class):
        """Test receiving empty data (connection closed)."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.recv.return_value = b""
        
        # Connect first
        self.connection.connect()
        
        on_disconnected = Mock()
        self.connection.set_callbacks(on_disconnected=on_disconnected)
        
        with pytest.raises(ConnectionError, match="Connection closed by server"):
            self.connection.receive()
        
        # Status should be DISCONNECTED after receiving empty data
        assert self.connection.get_status() == ConnectionStatus.DISCONNECTED
        on_disconnected.assert_called_once()
    
    @patch('socket.socket')
    def test_receive_messages(self, mock_socket_class):
        """Test receiving and parsing complete messages."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        
        # Connect first
        self.connection.connect()
        
        # Test receiving complete messages
        mock_socket.recv.return_value = b"MSG|Hello\nSRV|Welcome\n"
        messages = self.connection.receive_messages()
        
        assert len(messages) == 2
        assert messages[0] == "MSG|Hello"
        assert messages[1] == "SRV|Welcome"
    
    @patch('socket.socket')
    def test_receive_partial_messages(self, mock_socket_class):
        """Test receiving partial messages."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        
        # Connect first
        self.connection.connect()
        
        # First receive partial message
        mock_socket.recv.return_value = b"MSG|Hel"
        messages = self.connection.receive_messages()
        assert len(messages) == 0
        
        # Second receive completes the message
        mock_socket.recv.return_value = b"lo\n"
        messages = self.connection.receive_messages()
        assert len(messages) == 1
        assert messages[0] == "MSG|Hello"
    
    def test_receive_when_disconnected(self):
        """Test receiving when not connected."""
        with pytest.raises(ConnectionError, match="Not connected"):
            self.connection.receive()
    
    @patch('socket.socket')
    def test_reconnect_success(self, mock_socket_class):
        """Test successful reconnection."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        
        # First connection fails
        mock_socket.connect.side_effect = [ConnectionRefusedError(), None]
        
        # Initial connection fails
        result = self.connection.connect()
        assert result is False
        
        # Reconnect succeeds
        result = self.connection.reconnect()
        assert result is True
        assert self.connection.get_status() == ConnectionStatus.CONNECTED
    
    @patch('socket.socket')
    @patch('time.sleep')
    def test_reconnect_max_attempts(self, mock_sleep, mock_socket_class):
        """Test reconnection with max attempts exceeded."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.connect.side_effect = ConnectionRefusedError()
        
        # Set max attempts to 2 for faster testing
        self.connection.config.max_reconnect_attempts = 2
        
        # Exhaust reconnection attempts
        for _ in range(2):
            result = self.connection.reconnect()
            assert result is False
        
        # Should not attempt more reconnections
        result = self.connection.reconnect()
        assert result is False
    
    def test_get_connection_info(self):
        """Test getting connection information."""
        info = self.connection.get_connection_info()
        
        assert info["host"] == "localhost"
        assert info["port"] == 8080
        assert info["status"] == "disconnected"
        assert info["reconnect_attempts"] == 0
        assert info["last_error"] is None
    
    @patch('socket.socket')
    def test_context_manager(self, mock_socket_class):
        """Test using connection as context manager."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        
        with self.connection as conn:
            assert conn is self.connection
            assert self.connection.get_status() == ConnectionStatus.CONNECTED
        
        # Should be disconnected after exiting context
        assert self.connection.get_status() == ConnectionStatus.DISCONNECTED
        mock_socket.close.assert_called_once()
    
    @patch('socket.socket')
    def test_keepalive_configuration(self, mock_socket_class):
        """Test keepalive socket configuration."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        
        # Test with keepalive enabled (default)
        self.connection.connect()
        mock_socket.setsockopt.assert_called_with(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        
        # Test with keepalive disabled
        config = ConnectionConfig("localhost", 8080, enable_keepalive=False)
        connection = Connection(config)
        mock_socket.reset_mock()
        
        connection.connect()
        # Should not set keepalive option
        mock_socket.setsockopt.assert_not_called()
    
    def test_thread_safety(self):
        """Test thread safety of connection operations."""
        results = []
        errors = []
        
        def connect_worker():
            try:
                with patch('socket.socket') as mock_socket_class:
                    mock_socket = Mock()
                    mock_socket_class.return_value = mock_socket
                    result = self.connection.connect()
                    results.append(result)
            except Exception as e:
                errors.append(e)
        
        # Start multiple threads trying to connect
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=connect_worker)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Should not have any errors
        assert len(errors) == 0
        # At least one connection should succeed
        assert any(results)
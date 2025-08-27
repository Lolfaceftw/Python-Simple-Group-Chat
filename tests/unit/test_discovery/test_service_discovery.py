"""
Unit tests for service discovery functionality.

Tests the ServiceDiscovery class with mocked network operations.
"""

import socket
import threading
import time
from unittest.mock import Mock, patch, MagicMock, call
import pytest

from chat_app.discovery.service_discovery import ServiceDiscovery, DiscoveryConfig
from chat_app.shared.constants import (
    DISCOVERY_MESSAGE,
    DEFAULT_DISCOVERY_PORT,
    DEFAULT_DISCOVERY_TIMEOUT
)


class TestDiscoveryConfig:
    """Test cases for DiscoveryConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = DiscoveryConfig()
        
        assert config.discovery_port == DEFAULT_DISCOVERY_PORT
        assert config.discovery_message == DISCOVERY_MESSAGE
        assert config.timeout == DEFAULT_DISCOVERY_TIMEOUT
        assert config.bind_address == ""
    
    def test_custom_config(self):
        """Test custom configuration values."""
        custom_message = b"CUSTOM_MESSAGE"
        config = DiscoveryConfig(
            discovery_port=9999,
            discovery_message=custom_message,
            timeout=10,
            bind_address="127.0.0.1"
        )
        
        assert config.discovery_port == 9999
        assert config.discovery_message == custom_message
        assert config.timeout == 10
        assert config.bind_address == "127.0.0.1"


class TestServiceDiscovery:
    """Test cases for ServiceDiscovery class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = DiscoveryConfig()
        self.discovery = ServiceDiscovery(self.config)
    
    def test_init_default_config(self):
        """Test initialization with default config."""
        discovery = ServiceDiscovery()
        
        assert discovery.config is not None
        assert discovery.config.discovery_port == DEFAULT_DISCOVERY_PORT
        assert not discovery._broadcasting
        assert discovery._broadcast_thread is None
        assert discovery._broadcast_socket is None
    
    def test_init_custom_config(self):
        """Test initialization with custom config."""
        custom_config = DiscoveryConfig(discovery_port=9999)
        discovery = ServiceDiscovery(custom_config)
        
        assert discovery.config == custom_config
        assert discovery.config.discovery_port == 9999
    
    @patch('socket.socket')
    def test_discover_servers_success(self, mock_socket_class):
        """Test successful server discovery."""
        # Mock socket instance
        mock_socket = Mock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        
        # Mock received data
        mock_socket.recvfrom.side_effect = [
            (DISCOVERY_MESSAGE, ('192.168.1.100', 8081)),
            (DISCOVERY_MESSAGE, ('192.168.1.101', 8081)),
            (b'INVALID_MESSAGE', ('192.168.1.102', 8081)),  # Should be ignored
            (DISCOVERY_MESSAGE, ('192.168.1.100', 8081)),  # Duplicate, should be deduplicated
            socket.timeout()  # End discovery
        ]
        
        servers = self.discovery.discover_servers(timeout=5)
        
        # Verify socket setup
        mock_socket.setsockopt.assert_called_once_with(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        mock_socket.bind.assert_called_once_with(("", DEFAULT_DISCOVERY_PORT))
        mock_socket.settimeout.assert_called_once_with(5)
        
        # Verify results (sorted and deduplicated)
        assert servers == ['192.168.1.100', '192.168.1.101']
    
    @patch('socket.socket')
    def test_discover_servers_bind_error(self, mock_socket_class):
        """Test discovery when bind fails (port in use)."""
        mock_socket = Mock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        mock_socket.bind.side_effect = OSError("Address already in use")
        
        servers = self.discovery.discover_servers()
        
        assert servers == []
    
    @patch('socket.socket')
    def test_discover_servers_socket_error(self, mock_socket_class):
        """Test discovery with socket creation error."""
        mock_socket_class.side_effect = OSError("Socket creation failed")
        
        servers = self.discovery.discover_servers()
        
        assert servers == []
    
    @patch('socket.socket')
    def test_discover_servers_timeout(self, mock_socket_class):
        """Test discovery with timeout (no servers found)."""
        mock_socket = Mock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        mock_socket.recvfrom.side_effect = socket.timeout()
        
        servers = self.discovery.discover_servers()
        
        assert servers == []
    
    @patch('socket.socket')
    def test_discover_servers_custom_timeout(self, mock_socket_class):
        """Test discovery with custom timeout."""
        mock_socket = Mock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        mock_socket.recvfrom.side_effect = socket.timeout()
        
        self.discovery.discover_servers(timeout=10)
        
        mock_socket.settimeout.assert_called_once_with(10)
    
    @patch('socket.socket')
    @patch('time.time')
    def test_discover_servers_time_based_timeout(self, mock_time, mock_socket_class):
        """Test discovery respects time-based timeout."""
        mock_socket = Mock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        
        # Mock time progression
        mock_time.side_effect = [0, 1, 2, 3, 4]  # 4 seconds elapsed, should stop at 3
        
        mock_socket.recvfrom.side_effect = [
            (DISCOVERY_MESSAGE, ('192.168.1.100', 8081)),
            (DISCOVERY_MESSAGE, ('192.168.1.101', 8081)),
            # Time runs out here
        ]
        
        servers = self.discovery.discover_servers(timeout=3)
        
        assert len(servers) == 2
        assert mock_socket.recvfrom.call_count == 2
    
    @patch('threading.Thread')
    def test_start_broadcasting(self, mock_thread_class):
        """Test starting broadcast functionality."""
        mock_thread = Mock()
        mock_thread_class.return_value = mock_thread
        
        assert not self.discovery.is_broadcasting()
        
        self.discovery.start_broadcasting()
        
        assert self.discovery.is_broadcasting()
        mock_thread_class.assert_called_once_with(target=self.discovery._broadcast_loop, daemon=True)
        mock_thread.start.assert_called_once()
    
    def test_start_broadcasting_already_running(self):
        """Test starting broadcast when already running."""
        self.discovery._broadcasting = True
        
        with patch('threading.Thread') as mock_thread_class:
            self.discovery.start_broadcasting()
            
            # Should not create new thread
            mock_thread_class.assert_not_called()
    
    def test_stop_broadcasting(self):
        """Test stopping broadcast functionality."""
        # Set up mock thread and socket
        mock_thread = Mock()
        mock_socket = Mock()
        
        self.discovery._broadcasting = True
        self.discovery._broadcast_thread = mock_thread
        self.discovery._broadcast_socket = mock_socket
        
        self.discovery.stop_broadcasting()
        
        assert not self.discovery.is_broadcasting()
        mock_socket.close.assert_called_once()
        mock_thread.join.assert_called_once_with(timeout=2.0)
        assert self.discovery._broadcast_socket is None
    
    def test_stop_broadcasting_socket_error(self):
        """Test stopping broadcast with socket close error."""
        mock_socket = Mock()
        mock_socket.close.side_effect = OSError("Socket error")
        
        self.discovery._broadcasting = True
        self.discovery._broadcast_socket = mock_socket
        
        # Should not raise exception
        self.discovery.stop_broadcasting()
        
        assert not self.discovery.is_broadcasting()
        assert self.discovery._broadcast_socket is None
    
    def test_stop_broadcasting_not_running(self):
        """Test stopping broadcast when not running."""
        assert not self.discovery.is_broadcasting()
        
        # Should not raise exception
        self.discovery.stop_broadcasting()
        
        assert not self.discovery.is_broadcasting()
    
    @patch('socket.socket')
    @patch('time.sleep')
    def test_broadcast_loop_success(self, mock_sleep, mock_socket_class):
        """Test successful broadcast loop."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        
        # Mock broadcasting flag to stop after a few iterations
        self.discovery._broadcasting = True
        
        def side_effect(*args):
            # Stop broadcasting after first iteration
            self.discovery._broadcasting = False
        
        mock_sleep.side_effect = side_effect
        
        self.discovery._broadcast_loop()
        
        # Verify socket setup
        mock_socket.setsockopt.assert_called_once_with(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        # Verify broadcast message sent
        mock_socket.sendto.assert_called_once_with(
            DISCOVERY_MESSAGE,
            ('<broadcast>', DEFAULT_DISCOVERY_PORT)
        )
        
        # Verify sleep called
        mock_sleep.assert_called_once_with(5.0)
        
        # Verify socket closed
        mock_socket.close.assert_called_once()
    
    @patch('socket.socket')
    def test_broadcast_loop_socket_creation_error(self, mock_socket_class):
        """Test broadcast loop with socket creation error."""
        mock_socket_class.side_effect = OSError("Socket creation failed")
        
        self.discovery._broadcasting = True
        
        # Should not raise exception
        self.discovery._broadcast_loop()
        
        assert self.discovery._broadcast_socket is None
    
    @patch('socket.socket')
    @patch('time.sleep')
    def test_broadcast_loop_send_error(self, mock_sleep, mock_socket_class):
        """Test broadcast loop with send error (OSError breaks loop)."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.sendto.side_effect = OSError("Send failed")
        
        self.discovery._broadcasting = True
        
        self.discovery._broadcast_loop()
        
        # OSError should break the loop after first attempt
        assert mock_socket.sendto.call_count == 1
        assert mock_sleep.call_count == 0  # Sleep not called due to break
        mock_socket.close.assert_called_once()
    
    @patch('socket.socket')
    def test_broadcast_loop_socket_error_breaks_loop(self, mock_socket_class):
        """Test broadcast loop breaks on socket error."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        mock_socket.sendto.side_effect = OSError("Socket closed")
        
        self.discovery._broadcasting = True
        
        self.discovery._broadcast_loop()
        
        # Should break loop on OSError
        mock_socket.sendto.assert_called_once()
        mock_socket.close.assert_called_once()
    
    @patch('socket.socket')
    @patch('time.sleep')
    def test_broadcast_loop_non_oserror_continues(self, mock_sleep, mock_socket_class):
        """Test broadcast loop continues on non-OSError exceptions."""
        mock_socket = Mock()
        mock_socket_class.return_value = mock_socket
        
        # Set up sendto to raise ValueError first, then succeed twice
        call_count = 0
        def sendto_side_effect(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Some error")
            return None
        
        mock_socket.sendto.side_effect = sendto_side_effect
        
        self.discovery._broadcasting = True
        
        # Set up sleep to stop broadcasting after first successful call
        def sleep_side_effect(*args):
            if mock_sleep.call_count >= 1:
                self.discovery._broadcasting = False
        
        mock_sleep.side_effect = sleep_side_effect
        
        self.discovery._broadcast_loop()
        
        # Should continue despite ValueError: 1 failed call + 1 successful call + 1 more attempt = 3 total
        # But only 1 sleep call because we stop after first successful iteration
        assert mock_socket.sendto.call_count >= 2  # At least 2 calls (1 failed, 1+ successful)
        assert mock_sleep.call_count == 1
    
    def test_is_broadcasting(self):
        """Test broadcasting status check."""
        assert not self.discovery.is_broadcasting()
        
        self.discovery._broadcasting = True
        assert self.discovery.is_broadcasting()
        
        self.discovery._broadcasting = False
        assert not self.discovery.is_broadcasting()
    
    def test_get_config(self):
        """Test getting configuration."""
        config = self.discovery.get_config()
        
        assert config == self.config
        assert config.discovery_port == DEFAULT_DISCOVERY_PORT


class TestServiceDiscoveryIntegration:
    """Integration tests for ServiceDiscovery with mocked network operations."""
    
    @patch('socket.socket')
    def test_discover_servers_with_custom_config(self, mock_socket_class):
        """Test discovery with custom configuration."""
        mock_socket = Mock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        mock_socket.recvfrom.side_effect = socket.timeout()
        
        custom_config = DiscoveryConfig(
            discovery_port=9999,
            discovery_message=b"CUSTOM_TEST_MESSAGE",
            timeout=1
        )
        
        discovery = ServiceDiscovery(custom_config)
        
        # Should return empty list (no servers broadcasting custom message)
        servers = discovery.discover_servers()
        assert servers == []
        
        # Verify custom config was used
        mock_socket.bind.assert_called_once_with(("", 9999))
        mock_socket.settimeout.assert_called_once_with(1)
    
    @patch('threading.Thread')
    def test_broadcast_lifecycle(self, mock_thread_class):
        """Test complete broadcast lifecycle."""
        mock_thread = Mock()
        mock_thread_class.return_value = mock_thread
        
        discovery = ServiceDiscovery()
        
        # Start broadcasting
        discovery.start_broadcasting()
        assert discovery.is_broadcasting()
        
        # Stop broadcasting
        discovery.stop_broadcasting()
        assert not discovery.is_broadcasting()
        
        # Verify thread was created and started
        mock_thread_class.assert_called_once()
        mock_thread.start.assert_called_once()
    
    @patch('threading.Thread')
    def test_multiple_discovery_instances(self, mock_thread_class):
        """Test multiple discovery instances don't interfere."""
        mock_thread1 = Mock()
        mock_thread2 = Mock()
        mock_thread_class.side_effect = [mock_thread1, mock_thread2]
        
        discovery1 = ServiceDiscovery()
        discovery2 = ServiceDiscovery()
        
        # Both should be able to start broadcasting
        discovery1.start_broadcasting()
        discovery2.start_broadcasting()
        
        assert discovery1.is_broadcasting()
        assert discovery2.is_broadcasting()
        
        # Both should be able to stop
        discovery1.stop_broadcasting()
        discovery2.stop_broadcasting()
        
        assert not discovery1.is_broadcasting()
        assert not discovery2.is_broadcasting()
        
        # Verify both threads were created
        assert mock_thread_class.call_count == 2


@pytest.fixture
def mock_discovery_config():
    """Fixture providing a mock discovery configuration."""
    return DiscoveryConfig(
        discovery_port=9999,
        discovery_message=b"TEST_MESSAGE",
        timeout=2,
        bind_address="127.0.0.1"
    )


@pytest.fixture
def service_discovery(mock_discovery_config):
    """Fixture providing a ServiceDiscovery instance with mock config."""
    return ServiceDiscovery(mock_discovery_config)


class TestServiceDiscoveryWithFixtures:
    """Test cases using pytest fixtures."""
    
    def test_fixture_config(self, mock_discovery_config):
        """Test that fixture provides correct config."""
        assert mock_discovery_config.discovery_port == 9999
        assert mock_discovery_config.discovery_message == b"TEST_MESSAGE"
        assert mock_discovery_config.timeout == 2
        assert mock_discovery_config.bind_address == "127.0.0.1"
    
    def test_fixture_service_discovery(self, service_discovery, mock_discovery_config):
        """Test that fixture provides correct ServiceDiscovery instance."""
        assert service_discovery.config == mock_discovery_config
        assert not service_discovery.is_broadcasting()
    
    @patch('socket.socket')
    def test_discover_with_fixture_config(self, mock_socket_class, service_discovery):
        """Test discovery using fixture configuration."""
        mock_socket = Mock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        mock_socket.recvfrom.side_effect = socket.timeout()
        
        service_discovery.discover_servers()
        
        # Verify custom config was used
        mock_socket.bind.assert_called_once_with(("127.0.0.1", 9999))
        mock_socket.settimeout.assert_called_once_with(2)
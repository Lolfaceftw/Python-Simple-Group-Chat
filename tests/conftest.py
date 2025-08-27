"""
Pytest Configuration and Shared Fixtures

Provides common test fixtures and configuration for the test suite.
"""

import pytest
import socket
import threading
import time
from unittest.mock import Mock, MagicMock
from typing import Generator, Dict, Any

from chat_app.shared.config import ServerConfig, ClientConfig
from chat_app.shared.models import User, Message, ClientConnection, MessageType


@pytest.fixture
def server_config() -> ServerConfig:
    """Provide a test server configuration."""
    return ServerConfig(
        host="127.0.0.1",
        port=0,  # Use 0 to get a random available port
        max_clients=10,
        rate_limit_messages_per_minute=100,
        max_message_length=500,
        max_username_length=25,
        max_connections_per_ip=3,
        message_history_size=25
    )


@pytest.fixture
def client_config() -> ClientConfig:
    """Provide a test client configuration."""
    return ClientConfig(
        default_host="127.0.0.1",
        default_port=8080,
        discovery_timeout=1,
        ui_refresh_rate=10,
        reconnect_attempts=1,
        reconnect_delay=1
    )


@pytest.fixture
def mock_socket() -> Mock:
    """Provide a mock socket for testing."""
    mock_sock = Mock(spec=socket.socket)
    mock_sock.recv.return_value = b"test message\n"
    mock_sock.send.return_value = None
    mock_sock.close.return_value = None
    mock_sock.bind.return_value = None
    mock_sock.listen.return_value = None
    mock_sock.accept.return_value = (Mock(spec=socket.socket), ("127.0.0.1", 12345))
    return mock_sock


@pytest.fixture
def sample_user() -> User:
    """Provide a sample user for testing."""
    return User(
        username="testuser",
        address="127.0.0.1:12345"
    )


@pytest.fixture
def sample_message() -> Message:
    """Provide a sample message for testing."""
    return Message(
        content="Hello, world!",
        sender="testuser",
        message_type=MessageType.CHAT
    )


@pytest.fixture
def sample_client_connection(mock_socket: Mock, sample_user: User) -> ClientConnection:
    """Provide a sample client connection for testing."""
    return ClientConnection(
        socket=mock_socket,
        user=sample_user,
        connection_id="test_client_1"
    )


@pytest.fixture
def available_port() -> int:
    """Get an available port for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


@pytest.fixture
def mock_rich_console() -> Mock:
    """Provide a mock Rich console for UI testing."""
    console = Mock()
    console.print = Mock()
    console.log = Mock()
    console.height = 24
    console.width = 80
    return console


@pytest.fixture
def mock_rich_layout() -> Mock:
    """Provide a mock Rich layout for UI testing."""
    layout = Mock()
    layout.split = Mock()
    layout.__getitem__ = Mock()
    return layout


@pytest.fixture
def mock_rich_live() -> Mock:
    """Provide a mock Rich Live context manager for UI testing."""
    live = Mock()
    live.__enter__ = Mock(return_value=live)
    live.__exit__ = Mock(return_value=None)
    return live


class MockThread:
    """Mock thread class for testing."""
    
    def __init__(self, target=None, args=None, kwargs=None, daemon=None):
        self.target = target
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.daemon = daemon
        self._started = False
    
    def start(self):
        """Mock start method."""
        self._started = True
        if self.target:
            # Don't actually run the target in tests
            pass
    
    def join(self, timeout=None):
        """Mock join method."""
        pass
    
    def is_alive(self):
        """Mock is_alive method."""
        return self._started


@pytest.fixture
def mock_threading(monkeypatch) -> None:
    """Mock threading module for testing."""
    monkeypatch.setattr("threading.Thread", MockThread)
    monkeypatch.setattr("threading.Lock", Mock)
    monkeypatch.setattr("threading.RLock", Mock)


@pytest.fixture
def temp_log_file(tmp_path) -> str:
    """Provide a temporary log file path."""
    return str(tmp_path / "test.log")


@pytest.fixture(autouse=True)
def reset_logging():
    """Reset logging configuration between tests."""
    import logging
    # Clear all handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    yield
    
    # Clean up after test
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)


@pytest.fixture
def event_loop_policy():
    """Provide event loop policy for async tests."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


# Test data fixtures
@pytest.fixture
def sample_protocol_messages() -> Dict[str, str]:
    """Provide sample protocol messages for testing."""
    return {
        "chat_message": "MSG|testuser: Hello everyone!",
        "server_message": "SRV|User joined the chat",
        "user_list": "ULIST|user1(127.0.0.1:1234),user2(127.0.0.1:5678)",
        "user_command": "CMD_USER|newusername",
        "invalid_message": "INVALID|malformed message"
    }


@pytest.fixture
def sample_usernames() -> Dict[str, bool]:
    """Provide sample usernames with validity flags."""
    return {
        "validuser": True,
        "user_123": True,
        "user-name": True,
        "user name": True,
        "": False,  # Empty
        "a" * 51: False,  # Too long
        "user@name": False,  # Invalid character
        " leadingspace": False,  # Leading space
        "trailingspace ": False,  # Trailing space
        "user\nnewline": False,  # Control character
    }


@pytest.fixture
def sample_messages_content() -> Dict[str, bool]:
    """Provide sample message content with validity flags."""
    return {
        "Hello world": True,
        "Message with 123 numbers": True,
        "Message with symbols !@#$%": True,
        "": False,  # Empty
        "a" * 1001: False,  # Too long
        "message\x00null": False,  # Null byte
        "message\x01control": False,  # Control character
    }
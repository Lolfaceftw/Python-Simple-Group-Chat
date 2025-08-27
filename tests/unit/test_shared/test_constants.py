"""
Unit tests for chat_app.shared.constants module.
"""

import pytest

from chat_app.shared.constants import (
    # Network constants
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    DEFAULT_DISCOVERY_PORT,
    DEFAULT_CLIENT_HOST,
    DEFAULT_BUFFER_SIZE,
    DEFAULT_SOCKET_TIMEOUT,
    DEFAULT_DISCOVERY_TIMEOUT,
    
    # Protocol constants
    MESSAGE_DELIMITER,
    PROTOCOL_SEPARATOR,
    MessageType,
    DISCOVERY_MESSAGE,
    
    # Security constants
    MAX_USERNAME_LENGTH,
    MAX_MESSAGE_LENGTH,
    DEFAULT_MAX_CONNECTIONS_PER_IP,
    DEFAULT_RATE_LIMIT_MESSAGES_PER_MINUTE,
    
    # UI constants
    DEFAULT_UI_REFRESH_RATE,
    MAX_MESSAGE_HISTORY,
    DEFAULT_MESSAGE_HISTORY,
    DEFAULT_PANEL_HEIGHT_OFFSET,
    
    # Server constants
    DEFAULT_MAX_CLIENTS,
    DEFAULT_BROADCAST_INTERVAL,
    
    # Command constants
    QUIT_COMMAND,
    NICK_COMMAND,
    HELP_COMMAND,
    
    # Logging constants
    LOG_FORMAT,
    LOG_DATE_FORMAT
)


class TestNetworkConstants:
    """Test network-related constants."""
    
    def test_default_server_host(self):
        """Test default server host constant."""
        assert DEFAULT_SERVER_HOST == "0.0.0.0"
        assert isinstance(DEFAULT_SERVER_HOST, str)
    
    def test_default_client_host(self):
        """Test default client host constant."""
        assert DEFAULT_CLIENT_HOST == "127.0.0.1"
        assert isinstance(DEFAULT_CLIENT_HOST, str)
    
    def test_default_server_port(self):
        """Test default server port constant."""
        assert DEFAULT_SERVER_PORT == 8080
        assert isinstance(DEFAULT_SERVER_PORT, int)
        assert 1 <= DEFAULT_SERVER_PORT <= 65535
    
    def test_default_discovery_port(self):
        """Test default discovery port constant."""
        assert DEFAULT_DISCOVERY_PORT == 8081
        assert isinstance(DEFAULT_DISCOVERY_PORT, int)
        assert 1 <= DEFAULT_DISCOVERY_PORT <= 65535
        assert DEFAULT_DISCOVERY_PORT != DEFAULT_SERVER_PORT
    
    def test_default_buffer_size(self):
        """Test default buffer size constant."""
        assert DEFAULT_BUFFER_SIZE == 4096
        assert isinstance(DEFAULT_BUFFER_SIZE, int)
        assert DEFAULT_BUFFER_SIZE > 0
    
    def test_default_socket_timeout(self):
        """Test default socket timeout constant."""
        assert DEFAULT_SOCKET_TIMEOUT == 1.0
        assert isinstance(DEFAULT_SOCKET_TIMEOUT, (int, float))
        assert DEFAULT_SOCKET_TIMEOUT > 0
    
    def test_default_discovery_timeout(self):
        """Test default discovery timeout constant."""
        assert DEFAULT_DISCOVERY_TIMEOUT == 3
        assert isinstance(DEFAULT_DISCOVERY_TIMEOUT, (int, float))
        assert DEFAULT_DISCOVERY_TIMEOUT > 0


class TestProtocolConstants:
    """Test protocol-related constants."""
    
    def test_message_delimiter(self):
        """Test message delimiter constant."""
        assert MESSAGE_DELIMITER == b'\n'
        assert isinstance(MESSAGE_DELIMITER, bytes)
        assert len(MESSAGE_DELIMITER) == 1
    
    def test_protocol_separator(self):
        """Test protocol separator constant."""
        assert PROTOCOL_SEPARATOR == '|'
        assert isinstance(PROTOCOL_SEPARATOR, str)
        assert len(PROTOCOL_SEPARATOR) == 1
    
    def test_discovery_message(self):
        """Test discovery message constant."""
        assert DISCOVERY_MESSAGE == b"PYTHON_CHAT_SERVER_DISCOVERY_V1"
        assert isinstance(DISCOVERY_MESSAGE, bytes)
    
    def test_message_type_class(self):
        """Test MessageType class constants."""
        assert MessageType.CHAT == "MSG"
        assert MessageType.SERVER == "SRV"
        assert MessageType.USER_LIST == "ULIST"
        assert MessageType.COMMAND == "CMD"
        assert MessageType.USER_COMMAND == "CMD_USER"
        
        # All should be strings
        assert isinstance(MessageType.CHAT, str)
        assert isinstance(MessageType.SERVER, str)
        assert isinstance(MessageType.USER_LIST, str)
        assert isinstance(MessageType.COMMAND, str)
        assert isinstance(MessageType.USER_COMMAND, str)


class TestSecurityConstants:
    """Test security-related constants."""
    
    def test_max_username_length(self):
        """Test maximum username length constant."""
        assert MAX_USERNAME_LENGTH == 50
        assert isinstance(MAX_USERNAME_LENGTH, int)
        assert MAX_USERNAME_LENGTH > 0
    
    def test_max_message_length(self):
        """Test maximum message length constant."""
        assert MAX_MESSAGE_LENGTH == 1000
        assert isinstance(MAX_MESSAGE_LENGTH, int)
        assert MAX_MESSAGE_LENGTH > 0
        assert MAX_MESSAGE_LENGTH < DEFAULT_BUFFER_SIZE  # Should fit in network buffer
    
    def test_default_max_connections_per_ip(self):
        """Test default maximum connections per IP constant."""
        assert DEFAULT_MAX_CONNECTIONS_PER_IP == 5
        assert isinstance(DEFAULT_MAX_CONNECTIONS_PER_IP, int)
        assert DEFAULT_MAX_CONNECTIONS_PER_IP > 0
    
    def test_default_rate_limit_messages_per_minute(self):
        """Test default rate limit messages per minute constant."""
        assert DEFAULT_RATE_LIMIT_MESSAGES_PER_MINUTE == 60
        assert isinstance(DEFAULT_RATE_LIMIT_MESSAGES_PER_MINUTE, int)
        assert DEFAULT_RATE_LIMIT_MESSAGES_PER_MINUTE > 0


class TestUIConstants:
    """Test UI-related constants."""
    
    def test_default_ui_refresh_rate(self):
        """Test default UI refresh rate constant."""
        assert DEFAULT_UI_REFRESH_RATE == 20
        assert isinstance(DEFAULT_UI_REFRESH_RATE, int)
        assert DEFAULT_UI_REFRESH_RATE > 0
    
    def test_max_message_history(self):
        """Test maximum message history constant."""
        assert MAX_MESSAGE_HISTORY == 2000
        assert isinstance(MAX_MESSAGE_HISTORY, int)
        assert MAX_MESSAGE_HISTORY > 0
    
    def test_default_message_history(self):
        """Test default message history constant."""
        assert DEFAULT_MESSAGE_HISTORY == 50
        assert isinstance(DEFAULT_MESSAGE_HISTORY, int)
        assert DEFAULT_MESSAGE_HISTORY > 0
    
    def test_default_panel_height_offset(self):
        """Test default panel height offset constant."""
        assert DEFAULT_PANEL_HEIGHT_OFFSET == 8
        assert isinstance(DEFAULT_PANEL_HEIGHT_OFFSET, int)
        assert DEFAULT_PANEL_HEIGHT_OFFSET > 0


class TestServerConstants:
    """Test server-related constants."""
    
    def test_default_max_clients(self):
        """Test default maximum clients constant."""
        assert DEFAULT_MAX_CLIENTS == 100
        assert isinstance(DEFAULT_MAX_CLIENTS, int)
        assert DEFAULT_MAX_CLIENTS > 0
    
    def test_default_broadcast_interval(self):
        """Test default broadcast interval constant."""
        assert DEFAULT_BROADCAST_INTERVAL == 5
        assert isinstance(DEFAULT_BROADCAST_INTERVAL, int)
        assert DEFAULT_BROADCAST_INTERVAL > 0


class TestCommandConstants:
    """Test command-related constants."""
    
    def test_quit_command(self):
        """Test quit command constant."""
        assert QUIT_COMMAND == "/quit"
        assert isinstance(QUIT_COMMAND, str)
        assert QUIT_COMMAND.startswith("/")
    
    def test_nick_command(self):
        """Test nick command constant."""
        assert NICK_COMMAND == "/nick"
        assert isinstance(NICK_COMMAND, str)
        assert NICK_COMMAND.startswith("/")
    
    def test_help_command(self):
        """Test help command constant."""
        assert HELP_COMMAND == "/help"
        assert isinstance(HELP_COMMAND, str)
        assert HELP_COMMAND.startswith("/")


class TestLoggingConstants:
    """Test logging-related constants."""
    
    def test_log_format(self):
        """Test log format constant."""
        expected_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        assert LOG_FORMAT == expected_format
        assert isinstance(LOG_FORMAT, str)
        
        # Should contain standard logging format specifiers
        assert "%(asctime)s" in LOG_FORMAT
        assert "%(name)s" in LOG_FORMAT
        assert "%(levelname)s" in LOG_FORMAT
        assert "%(message)s" in LOG_FORMAT
    
    def test_log_date_format(self):
        """Test log date format constant."""
        expected_format = "%Y-%m-%d %H:%M:%S"
        assert LOG_DATE_FORMAT == expected_format
        assert isinstance(LOG_DATE_FORMAT, str)


class TestConstantRelationships:
    """Test relationships between constants."""
    
    def test_port_relationships(self):
        """Test that ports don't conflict."""
        assert DEFAULT_SERVER_PORT != DEFAULT_DISCOVERY_PORT
        
        # Both should be in valid port range
        assert 1 <= DEFAULT_SERVER_PORT <= 65535
        assert 1 <= DEFAULT_DISCOVERY_PORT <= 65535
    
    def test_size_relationships(self):
        """Test that size limits are logical."""
        assert MAX_MESSAGE_LENGTH < DEFAULT_BUFFER_SIZE
        assert DEFAULT_MESSAGE_HISTORY <= MAX_MESSAGE_HISTORY
        assert MAX_USERNAME_LENGTH < MAX_MESSAGE_LENGTH


class TestConstantTypes:
    """Test that constants have correct types."""
    
    def test_string_constants(self):
        """Test string constants."""
        string_constants = [
            DEFAULT_SERVER_HOST,
            DEFAULT_CLIENT_HOST,
            PROTOCOL_SEPARATOR,
            QUIT_COMMAND,
            NICK_COMMAND,
            HELP_COMMAND,
            LOG_FORMAT,
            LOG_DATE_FORMAT
        ]
        
        for constant in string_constants:
            assert isinstance(constant, str)
            assert len(constant) > 0
    
    def test_bytes_constants(self):
        """Test bytes constants."""
        bytes_constants = [
            MESSAGE_DELIMITER,
            DISCOVERY_MESSAGE
        ]
        
        for constant in bytes_constants:
            assert isinstance(constant, bytes)
            assert len(constant) > 0
    
    def test_integer_constants(self):
        """Test integer constants."""
        integer_constants = [
            DEFAULT_SERVER_PORT,
            DEFAULT_DISCOVERY_PORT,
            DEFAULT_BUFFER_SIZE,
            MAX_USERNAME_LENGTH,
            MAX_MESSAGE_LENGTH,
            DEFAULT_MAX_CONNECTIONS_PER_IP,
            DEFAULT_RATE_LIMIT_MESSAGES_PER_MINUTE,
            DEFAULT_UI_REFRESH_RATE,
            MAX_MESSAGE_HISTORY,
            DEFAULT_MESSAGE_HISTORY,
            DEFAULT_MAX_CLIENTS,
            DEFAULT_BROADCAST_INTERVAL,
            DEFAULT_PANEL_HEIGHT_OFFSET
        ]
        
        for constant in integer_constants:
            assert isinstance(constant, int)
            assert constant > 0
    
    def test_float_constants(self):
        """Test float constants."""
        float_constants = [
            DEFAULT_SOCKET_TIMEOUT
        ]
        
        for constant in float_constants:
            assert isinstance(constant, (int, float))
            assert constant > 0
"""
Unit Tests for Server Main Entry Point

Tests for configuration loading, command line parsing, and error handling.
"""

import pytest
import os
import sys
from unittest.mock import Mock, patch, mock_open
from io import StringIO

from chat_app.server.main import (
    main,
    load_server_config,
    parse_command_line_args,
    validate_server_config,
    print_server_info
)
from chat_app.shared.config import ServerConfig
from chat_app.shared.exceptions import ConfigurationError, ChatServerError


class TestMainFunction:
    """Test the main entry point function."""
    
    @patch('chat_app.server.main.ChatServer')
    @patch('chat_app.server.main.load_server_config')
    @patch('chat_app.server.main.setup_logging')
    def test_main_success(self, mock_setup_logging, mock_load_config, mock_chat_server):
        """Test successful main execution."""
        # Mock configuration
        mock_config = ServerConfig()
        mock_load_config.return_value = mock_config
        
        # Mock server
        mock_server_instance = Mock()
        mock_chat_server.return_value = mock_server_instance
        
        result = main()
        
        assert result == 0
        mock_setup_logging.assert_called_once()
        mock_load_config.assert_called_once()
        mock_chat_server.assert_called_once_with(mock_config)
        mock_server_instance.start.assert_called_once()
    
    @patch('chat_app.server.main.setup_logging')
    def test_main_logging_setup_failure(self, mock_setup_logging):
        """Test main with logging setup failure."""
        mock_setup_logging.side_effect = Exception("Logging setup failed")
        
        result = main()
        
        assert result == 1
    
    @patch('chat_app.server.main.ChatServer')
    @patch('chat_app.server.main.load_server_config')
    @patch('chat_app.server.main.setup_logging')
    def test_main_keyboard_interrupt(self, mock_setup_logging, mock_load_config, mock_chat_server):
        """Test main with keyboard interrupt."""
        mock_config = ServerConfig()
        mock_load_config.return_value = mock_config
        
        mock_server_instance = Mock()
        mock_server_instance.start.side_effect = KeyboardInterrupt()
        mock_chat_server.return_value = mock_server_instance
        
        result = main()
        
        assert result == 0
    
    @patch('chat_app.server.main.ChatServer')
    @patch('chat_app.server.main.load_server_config')
    @patch('chat_app.server.main.setup_logging')
    def test_main_configuration_error(self, mock_setup_logging, mock_load_config, mock_chat_server):
        """Test main with configuration error."""
        mock_load_config.side_effect = ConfigurationError("Invalid configuration")
        
        result = main()
        
        assert result == 2
    
    @patch('chat_app.server.main.ChatServer')
    @patch('chat_app.server.main.load_server_config')
    @patch('chat_app.server.main.setup_logging')
    def test_main_server_error(self, mock_setup_logging, mock_load_config, mock_chat_server):
        """Test main with server error."""
        mock_config = ServerConfig()
        mock_load_config.return_value = mock_config
        
        mock_server_instance = Mock()
        mock_server_instance.start.side_effect = ChatServerError("Server failed to start")
        mock_chat_server.return_value = mock_server_instance
        
        result = main()
        
        assert result == 3
    
    @patch('chat_app.server.main.ChatServer')
    @patch('chat_app.server.main.load_server_config')
    @patch('chat_app.server.main.setup_logging')
    def test_main_unexpected_error(self, mock_setup_logging, mock_load_config, mock_chat_server):
        """Test main with unexpected error."""
        mock_config = ServerConfig()
        mock_load_config.return_value = mock_config
        
        mock_server_instance = Mock()
        mock_server_instance.start.side_effect = Exception("Unexpected error")
        mock_chat_server.return_value = mock_server_instance
        
        result = main()
        
        assert result == 1


class TestConfigurationLoading:
    """Test configuration loading functionality."""
    
    @patch('chat_app.server.main.parse_command_line_args')
    @patch('chat_app.server.main.validate_server_config')
    @patch('chat_app.server.main.load_config_from_file')
    @patch.dict(os.environ, {}, clear=True)
    def test_load_server_config_defaults(self, mock_load_file, mock_validate, mock_parse_args):
        """Test loading configuration with defaults."""
        mock_load_file.return_value = {}
        mock_parse_args.side_effect = lambda config: config
        
        config = load_server_config()
        
        assert isinstance(config, ServerConfig)
        mock_validate.assert_called_once()
    
    @patch('chat_app.server.main.parse_command_line_args')
    @patch('chat_app.server.main.validate_server_config')
    @patch('chat_app.server.main.load_config_from_file')
    @patch.dict(os.environ, {'CHAT_SERVER_PORT': '9999'}, clear=True)
    def test_load_server_config_from_env(self, mock_load_file, mock_validate, mock_parse_args):
        """Test loading configuration from environment variables."""
        mock_load_file.return_value = {}
        mock_parse_args.side_effect = lambda config: config
        
        config = load_server_config()
        
        assert config.port == 9999
        mock_validate.assert_called_once()
    
    @patch('chat_app.server.main.parse_command_line_args')
    @patch('chat_app.server.main.validate_server_config')
    @patch('chat_app.server.main.load_config_from_file')
    @patch.dict(os.environ, {'CHAT_CONFIG_FILE': 'test_config.json'}, clear=True)
    def test_load_server_config_from_file(self, mock_load_file, mock_validate, mock_parse_args):
        """Test loading configuration from file."""
        mock_load_file.return_value = {
            'server': {
                'port': 7777,
                'max_clients': 200
            }
        }
        mock_parse_args.side_effect = lambda config: config
        
        config = load_server_config()
        
        assert config.port == 7777
        assert config.max_clients == 200
        mock_load_file.assert_called_once_with('test_config.json')
        mock_validate.assert_called_once()
    
    @patch('chat_app.server.main.parse_command_line_args')
    @patch('chat_app.server.main.validate_server_config')
    @patch('chat_app.server.main.load_config_from_file')
    @patch('os.path.exists')
    def test_load_server_config_default_file(self, mock_exists, mock_load_file, mock_validate, mock_parse_args):
        """Test loading configuration from default config.json file."""
        mock_exists.return_value = True
        mock_load_file.return_value = {
            'server': {
                'host': '0.0.0.0',
                'port': 8888
            }
        }
        mock_parse_args.side_effect = lambda config: config
        
        config = load_server_config()
        
        assert config.host == '0.0.0.0'
        assert config.port == 8888
        mock_load_file.assert_called_once_with(None)
    
    @patch('chat_app.server.main.parse_command_line_args')
    @patch('chat_app.server.main.validate_server_config')
    @patch('chat_app.server.main.load_config_from_file')
    def test_load_server_config_file_error(self, mock_load_file, mock_validate, mock_parse_args):
        """Test handling file loading error."""
        mock_load_file.side_effect = Exception("File read error")
        mock_parse_args.side_effect = lambda config: config
        
        # Should not raise exception, just log warning and continue
        config = load_server_config()
        
        assert isinstance(config, ServerConfig)
        mock_validate.assert_called_once()
    
    @patch('chat_app.server.main.parse_command_line_args')
    @patch('chat_app.server.main.validate_server_config')
    @patch('chat_app.server.main.load_config_from_file')
    def test_load_server_config_validation_error(self, mock_load_file, mock_validate, mock_parse_args):
        """Test handling validation error."""
        mock_load_file.return_value = {}
        mock_parse_args.side_effect = lambda config: config
        mock_validate.side_effect = ConfigurationError("Invalid port")
        
        with pytest.raises(ConfigurationError, match="Failed to load configuration"):
            load_server_config()


class TestCommandLineArguments:
    """Test command line argument parsing."""
    
    def test_parse_command_line_args_defaults(self):
        """Test parsing with default arguments."""
        config = ServerConfig()
        
        with patch('sys.argv', ['main.py']):
            result_config = parse_command_line_args(config)
        
        assert result_config.host == config.host
        assert result_config.port == config.port
        assert result_config.max_clients == config.max_clients
    
    def test_parse_command_line_args_custom(self):
        """Test parsing with custom arguments."""
        config = ServerConfig()
        
        test_args = [
            'main.py',
            '--host', '192.168.1.100',
            '--port', '9999',
            '--max-clients', '50',
            '--rate-limit', '120',
            '--max-message-length', '2000',
            '--max-username-length', '30',
            '--max-connections-per-ip', '10',
            '--message-history-size', '100',
            '--discovery-port', '9998',
            '--discovery-interval', '10',
            '--log-level', 'DEBUG',
            '--log-file', 'server.log'
        ]
        
        with patch('sys.argv', test_args):
            result_config = parse_command_line_args(config)
        
        assert result_config.host == '192.168.1.100'
        assert result_config.port == 9999
        assert result_config.max_clients == 50
        assert result_config.rate_limit_messages_per_minute == 120
        assert result_config.max_message_length == 2000
        assert result_config.max_username_length == 30
        assert result_config.max_connections_per_ip == 10
        assert result_config.message_history_size == 100
        assert result_config.discovery_port == 9998
        assert result_config.discovery_broadcast_interval == 10
        
        # Check environment variables were set
        assert os.environ.get('CHAT_LOG_LEVEL') == 'DEBUG'
        assert os.environ.get('CHAT_LOG_FILE') == 'server.log'
    
    def test_parse_command_line_args_version(self):
        """Test version argument."""
        config = ServerConfig()
        
        with patch('sys.argv', ['main.py', '--version']):
            with pytest.raises(SystemExit):
                parse_command_line_args(config)
    
    def test_parse_command_line_args_help(self):
        """Test help argument."""
        config = ServerConfig()
        
        with patch('sys.argv', ['main.py', '--help']):
            with pytest.raises(SystemExit):
                parse_command_line_args(config)


class TestConfigurationValidation:
    """Test configuration validation."""
    
    def test_validate_server_config_valid(self):
        """Test validation with valid configuration."""
        config = ServerConfig(
            port=8080,
            discovery_port=8081,
            max_clients=100,
            max_connections_per_ip=5,
            rate_limit_messages_per_minute=60,
            max_message_length=1000,
            max_username_length=50,
            message_history_size=50,
            discovery_broadcast_interval=5,
            host="0.0.0.0"
        )
        
        # Should not raise any exception
        validate_server_config(config)
    
    def test_validate_server_config_invalid_server_port(self):
        """Test validation with invalid server port."""
        config = ServerConfig(port=80)  # Too low
        
        with pytest.raises(ConfigurationError, match="Server port must be between 1024 and 65535"):
            validate_server_config(config)
    
    def test_validate_server_config_invalid_discovery_port(self):
        """Test validation with invalid discovery port."""
        config = ServerConfig(discovery_port=70000)  # Too high
        
        with pytest.raises(ConfigurationError, match="Discovery port must be between 1024 and 65535"):
            validate_server_config(config)
    
    def test_validate_server_config_same_ports(self):
        """Test validation with same server and discovery ports."""
        config = ServerConfig(port=8080, discovery_port=8080)
        
        with pytest.raises(ConfigurationError, match="Server port and discovery port cannot be the same"):
            validate_server_config(config)
    
    def test_validate_server_config_invalid_max_clients(self):
        """Test validation with invalid max clients."""
        config = ServerConfig(max_clients=0)
        
        with pytest.raises(ConfigurationError, match="Max clients must be positive"):
            validate_server_config(config)
    
    def test_validate_server_config_invalid_connections_per_ip(self):
        """Test validation with invalid connections per IP."""
        config = ServerConfig(max_connections_per_ip=-1)
        
        with pytest.raises(ConfigurationError, match="Max connections per IP must be positive"):
            validate_server_config(config)
    
    def test_validate_server_config_invalid_rate_limit(self):
        """Test validation with invalid rate limit."""
        config = ServerConfig(rate_limit_messages_per_minute=0)
        
        with pytest.raises(ConfigurationError, match="Rate limit must be positive"):
            validate_server_config(config)
    
    def test_validate_server_config_invalid_message_length(self):
        """Test validation with invalid message length."""
        config = ServerConfig(max_message_length=-1)
        
        with pytest.raises(ConfigurationError, match="Max message length must be positive"):
            validate_server_config(config)
    
    def test_validate_server_config_invalid_username_length(self):
        """Test validation with invalid username length."""
        config = ServerConfig(max_username_length=0)
        
        with pytest.raises(ConfigurationError, match="Max username length must be positive"):
            validate_server_config(config)
    
    def test_validate_server_config_invalid_history_size(self):
        """Test validation with invalid history size."""
        config = ServerConfig(message_history_size=-1)
        
        with pytest.raises(ConfigurationError, match="Message history size cannot be negative"):
            validate_server_config(config)
    
    def test_validate_server_config_invalid_broadcast_interval(self):
        """Test validation with invalid broadcast interval."""
        config = ServerConfig(discovery_broadcast_interval=0)
        
        with pytest.raises(ConfigurationError, match="Discovery broadcast interval must be positive"):
            validate_server_config(config)
    
    def test_validate_server_config_empty_host(self):
        """Test validation with empty host."""
        config = ServerConfig(host="")
        
        with pytest.raises(ConfigurationError, match="Host cannot be empty"):
            validate_server_config(config)
    
    def test_validate_server_config_multiple_errors(self):
        """Test validation with multiple errors."""
        config = ServerConfig(
            port=80,  # Invalid
            max_clients=0,  # Invalid
            rate_limit_messages_per_minute=-1,  # Invalid
            host=""  # Invalid
        )
        
        with pytest.raises(ConfigurationError) as exc_info:
            validate_server_config(config)
        
        error_message = str(exc_info.value)
        assert "Server port must be between" in error_message
        assert "Max clients must be positive" in error_message
        assert "Rate limit must be positive" in error_message
        assert "Host cannot be empty" in error_message


class TestPrintServerInfo:
    """Test server information printing."""
    
    def test_print_server_info(self, capsys):
        """Test printing server information."""
        config = ServerConfig(
            host="127.0.0.1",
            port=8080,
            discovery_port=8081,
            max_clients=100,
            max_connections_per_ip=5,
            rate_limit_messages_per_minute=60,
            max_message_length=1000,
            max_username_length=50,
            message_history_size=50
        )
        
        print_server_info(config)
        
        captured = capsys.readouterr()
        output = captured.out
        
        assert "Python Chat Server" in output
        assert "127.0.0.1:8080" in output
        assert "Discovery Port: 8081" in output
        assert "Max Clients: 100" in output
        assert "Max Connections per IP: 5" in output
        assert "Rate Limit: 60 messages/minute" in output
        assert "Max Message Length: 1000 characters" in output
        assert "Max Username Length: 50 characters" in output
        assert "Message History: 50 messages" in output
        assert "Press Ctrl+C to stop" in output


class TestEnvironmentIntegration:
    """Test environment variable integration."""
    
    @patch.dict(os.environ, {
        'CHAT_SERVER_HOST': '192.168.1.100',
        'CHAT_SERVER_PORT': '9999',
        'CHAT_MAX_CLIENTS': '200',
        'CHAT_RATE_LIMIT_MSG_PER_MIN': '120',
        'CHAT_MAX_MESSAGE_LENGTH': '2000',
        'CHAT_MAX_USERNAME_LENGTH': '30',
        'CHAT_MAX_CONNECTIONS_PER_IP': '10',
        'CHAT_MESSAGE_HISTORY_SIZE': '100',
        'CHAT_DISCOVERY_PORT': '9998',
        'CHAT_DISCOVERY_BROADCAST_INTERVAL': '10'
    }, clear=True)
    def test_config_from_environment(self):
        """Test configuration loading from environment variables."""
        config = ServerConfig.from_env()
        
        assert config.host == '192.168.1.100'
        assert config.port == 9999
        assert config.max_clients == 200
        assert config.rate_limit_messages_per_minute == 120
        assert config.max_message_length == 2000
        assert config.max_username_length == 30
        assert config.max_connections_per_ip == 10
        assert config.message_history_size == 100
        assert config.discovery_port == 9998
        assert config.discovery_broadcast_interval == 10


@pytest.fixture
def clean_environment():
    """Fixture to provide a clean environment for testing."""
    original_env = os.environ.copy()
    
    # Clear relevant environment variables
    env_vars_to_clear = [
        'CHAT_SERVER_HOST', 'CHAT_SERVER_PORT', 'CHAT_MAX_CLIENTS',
        'CHAT_RATE_LIMIT_MSG_PER_MIN', 'CHAT_MAX_MESSAGE_LENGTH',
        'CHAT_MAX_USERNAME_LENGTH', 'CHAT_MAX_CONNECTIONS_PER_IP',
        'CHAT_MESSAGE_HISTORY_SIZE', 'CHAT_DISCOVERY_PORT',
        'CHAT_DISCOVERY_BROADCAST_INTERVAL', 'CHAT_LOG_LEVEL',
        'CHAT_LOG_FILE', 'CHAT_CONFIG_FILE'
    ]
    
    for var in env_vars_to_clear:
        os.environ.pop(var, None)
    
    yield
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)
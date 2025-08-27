"""
Tests for configuration management.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from chat_app.shared.config import (
    ClientConfig, 
    ConfigurationLoader, 
    ServerConfig, 
    load_config_from_file
)
from chat_app.shared.exceptions import ConfigurationError


class TestServerConfig:
    """Test ServerConfig class."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = ServerConfig()
        assert config.host == "0.0.0.0"
        assert config.port == 8080
        assert config.max_clients == 100
        assert config.rate_limit_messages_per_minute == 60
        assert config.max_message_length == 1000
        assert config.max_username_length == 50
        assert config.max_connections_per_ip == 5
        assert config.message_history_size == 50
        assert config.discovery_port == 8081
        assert config.discovery_broadcast_interval == 5
    
    def test_validation_success(self):
        """Test successful validation."""
        config = ServerConfig()
        config.validate()  # Should not raise
    
    def test_validation_invalid_host(self):
        """Test validation with invalid host."""
        config = ServerConfig(host="")
        with pytest.raises(ConfigurationError, match="host must be a non-empty string"):
            config.validate()
    
    def test_validation_invalid_port(self):
        """Test validation with invalid port."""
        config = ServerConfig(port=0)
        with pytest.raises(ConfigurationError, match="port must be an integer between 1 and 65535"):
            config.validate()
        
        config = ServerConfig(port=70000)
        with pytest.raises(ConfigurationError, match="port must be an integer between 1 and 65535"):
            config.validate()
    
    def test_validation_negative_values(self):
        """Test validation with negative values."""
        config = ServerConfig(max_clients=-1)
        with pytest.raises(ConfigurationError, match="max_clients must be a positive integer"):
            config.validate()
    
    def test_validation_same_ports(self):
        """Test validation with same port and discovery_port."""
        config = ServerConfig(port=8080, discovery_port=8080)
        with pytest.raises(ConfigurationError, match="port and discovery_port cannot be the same"):
            config.validate()
    
    def test_validation_multiple_errors(self):
        """Test validation with multiple errors."""
        config = ServerConfig(host="", port=0, max_clients=-1)
        with pytest.raises(ConfigurationError) as exc_info:
            config.validate()
        
        error_msg = str(exc_info.value)
        assert "host must be a non-empty string" in error_msg
        assert "port must be an integer between 1 and 65535" in error_msg
        assert "max_clients must be a positive integer" in error_msg
    
    def test_from_env_default(self):
        """Test loading from environment with default values."""
        with patch.dict(os.environ, {}, clear=True):
            config = ServerConfig.from_env()
            assert config.host == "0.0.0.0"
            assert config.port == 8080
    
    def test_from_env_custom(self):
        """Test loading from environment with custom values."""
        env_vars = {
            "CHAT_SERVER_HOST": "127.0.0.1",
            "CHAT_SERVER_PORT": "9090",
            "CHAT_MAX_CLIENTS": "50",
            "CHAT_RATE_LIMIT_MSG_PER_MIN": "30",
            "CHAT_MAX_MESSAGE_LENGTH": "500",
            "CHAT_MAX_USERNAME_LENGTH": "25",
            "CHAT_MAX_CONNECTIONS_PER_IP": "3",
            "CHAT_MESSAGE_HISTORY_SIZE": "25",
            "CHAT_DISCOVERY_PORT": "9091",
            "CHAT_DISCOVERY_BROADCAST_INTERVAL": "10",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = ServerConfig.from_env()
            assert config.host == "127.0.0.1"
            assert config.port == 9090
            assert config.max_clients == 50
            assert config.rate_limit_messages_per_minute == 30
            assert config.max_message_length == 500
            assert config.max_username_length == 25
            assert config.max_connections_per_ip == 3
            assert config.message_history_size == 25
            assert config.discovery_port == 9091
            assert config.discovery_broadcast_interval == 10
    
    def test_from_env_invalid_values(self):
        """Test loading from environment with invalid values."""
        env_vars = {
            "CHAT_SERVER_PORT": "invalid",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            with pytest.raises(ConfigurationError, match="Failed to load server configuration from environment"):
                ServerConfig.from_env()
    
    def test_from_dict_success(self):
        """Test creating config from dictionary."""
        data = {
            "host": "192.168.1.1",
            "port": 9090,
            "max_clients": 50
        }
        config = ServerConfig.from_dict(data)
        assert config.host == "192.168.1.1"
        assert config.port == 9090
        assert config.max_clients == 50
        # Other values should be defaults
        assert config.rate_limit_messages_per_minute == 60
    
    def test_from_dict_filters_unknown_fields(self):
        """Test that from_dict filters unknown fields."""
        data = {
            "host": "192.168.1.1",
            "port": 9090,
            "unknown_field": "should_be_ignored"
        }
        config = ServerConfig.from_dict(data)
        assert config.host == "192.168.1.1"
        assert config.port == 9090
        assert not hasattr(config, "unknown_field")
    
    def test_from_dict_invalid_data(self):
        """Test creating config from invalid dictionary."""
        data = {
            "port": "invalid_port"
        }
        with pytest.raises(ConfigurationError, match="Server configuration validation failed"):
            ServerConfig.from_dict(data)


class TestClientConfig:
    """Test ClientConfig class."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = ClientConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 8080
        assert config.username == ""
        assert config.discovery_timeout == 3
        assert config.ui_refresh_rate == 20
        assert config.reconnect_attempts == 3
        assert config.reconnect_delay == 5
    
    def test_validation_success(self):
        """Test successful validation."""
        config = ClientConfig()
        config.validate()  # Should not raise
    
    def test_validation_invalid_host(self):
        """Test validation with invalid host."""
        config = ClientConfig(host="")
        with pytest.raises(ConfigurationError, match="host must be a non-empty string"):
            config.validate()
    
    def test_validation_invalid_port(self):
        """Test validation with invalid port."""
        config = ClientConfig(port=0)
        with pytest.raises(ConfigurationError, match="port must be an integer between 1 and 65535"):
            config.validate()
    
    def test_validation_negative_values(self):
        """Test validation with negative values."""
        config = ClientConfig(discovery_timeout=-1)
        with pytest.raises(ConfigurationError, match="discovery_timeout must be a positive integer"):
            config.validate()
    
    def test_from_env_default(self):
        """Test loading from environment with default values."""
        with patch.dict(os.environ, {}, clear=True):
            config = ClientConfig.from_env()
            assert config.host == "127.0.0.1"
            assert config.port == 8080
    
    def test_from_env_custom(self):
        """Test loading from environment with custom values."""
        env_vars = {
            "CHAT_CLIENT_HOST": "192.168.1.100",
            "CHAT_CLIENT_PORT": "9090",
            "CHAT_DISCOVERY_TIMEOUT": "5",
            "CHAT_UI_REFRESH_RATE": "30",
            "CHAT_RECONNECT_ATTEMPTS": "5",
            "CHAT_RECONNECT_DELAY": "10",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = ClientConfig.from_env()
            assert config.host == "192.168.1.100"
            assert config.port == 9090
            assert config.discovery_timeout == 5
            assert config.ui_refresh_rate == 30
            assert config.reconnect_attempts == 5
            assert config.reconnect_delay == 10
    
    def test_from_dict_success(self):
        """Test creating config from dictionary."""
        data = {
            "host": "192.168.1.1",
            "port": 9090,
            "username": "test_user",
            "discovery_timeout": 5
        }
        config = ClientConfig.from_dict(data)
        assert config.host == "192.168.1.1"
        assert config.port == 9090
        assert config.discovery_timeout == 5


class TestConfigurationLoader:
    """Test ConfigurationLoader class."""
    
    def test_load_from_file_json(self):
        """Test loading JSON configuration file."""
        config_data = {
            "server": {
                "host": "192.168.1.1",
                "port": 9090
            },
            "client": {
                "default_host": "192.168.1.1",
                "default_port": 9090
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            f.flush()
            f.close()  # Close file before reading on Windows
            
            try:
                loaded_config = ConfigurationLoader.load_from_file(f.name)
                assert loaded_config == config_data
            finally:
                try:
                    os.unlink(f.name)
                except (OSError, PermissionError):
                    pass  # Ignore cleanup errors on Windows
    
    def test_load_from_file_yaml(self):
        """Test loading YAML configuration file."""
        yaml_content = """
server:
  host: "192.168.1.1"
  port: 9090
client:
  default_host: "192.168.1.1"
  default_port: 9090
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()
            f.close()  # Close file before reading on Windows
            
            try:
                # Skip if PyYAML not available
                try:
                    import yaml
                    loaded_config = ConfigurationLoader.load_from_file(f.name)
                    assert loaded_config["server"]["host"] == "192.168.1.1"
                    assert loaded_config["server"]["port"] == 9090
                except ImportError:
                    pytest.skip("PyYAML not available")
            finally:
                try:
                    os.unlink(f.name)
                except (OSError, PermissionError):
                    pass  # Ignore cleanup errors on Windows
    
    def test_load_from_file_yaml_without_pyyaml(self):
        """Test loading YAML file without PyYAML installed."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("server:\n  host: test")
            f.flush()
            f.close()  # Close file before reading on Windows
            
            try:
                with patch('builtins.__import__', side_effect=ImportError):
                    with pytest.raises(ConfigurationError, match="PyYAML is required"):
                        ConfigurationLoader.load_from_file(f.name)
            finally:
                try:
                    os.unlink(f.name)
                except (OSError, PermissionError):
                    pass  # Ignore cleanup errors on Windows
    
    def test_load_from_file_nonexistent(self):
        """Test loading non-existent configuration file."""
        with pytest.raises(ConfigurationError, match="Configuration file not found"):
            ConfigurationLoader.load_from_file("nonexistent.json")
    
    def test_load_from_file_none_no_defaults(self):
        """Test loading with None path and no default files."""
        config = ConfigurationLoader.load_from_file(None)
        assert config == {}
    
    def test_load_from_file_invalid_json(self):
        """Test loading invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content")
            f.flush()
            f.close()  # Close file before reading on Windows
            
            try:
                with pytest.raises(ConfigurationError, match="Invalid JSON"):
                    ConfigurationLoader.load_from_file(f.name)
            finally:
                try:
                    os.unlink(f.name)
                except (OSError, PermissionError):
                    pass  # Ignore cleanup errors on Windows
    
    def test_load_from_file_unsupported_format(self):
        """Test loading unsupported file format."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("some content")
            f.flush()
            f.close()  # Close file before reading on Windows
            
            try:
                with pytest.raises(ConfigurationError, match="Unsupported configuration file format"):
                    ConfigurationLoader.load_from_file(f.name)
            finally:
                try:
                    os.unlink(f.name)
                except (OSError, PermissionError):
                    pass  # Ignore cleanup errors on Windows
    
    def test_load_server_config_file_only(self):
        """Test loading server config from file only."""
        config_data = {
            "server": {
                "host": "192.168.1.1",
                "port": 9090,
                "max_clients": 50
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            f.flush()
            f.close()  # Close file before reading on Windows
            
            try:
                config = ConfigurationLoader.load_server_config(f.name, use_env=False)
                assert config.host == "192.168.1.1"
                assert config.port == 9090
                assert config.max_clients == 50
                # Defaults for other values
                assert config.rate_limit_messages_per_minute == 60
            finally:
                try:
                    os.unlink(f.name)
                except (OSError, PermissionError):
                    pass  # Ignore cleanup errors on Windows
    
    def test_load_server_config_env_override(self):
        """Test loading server config with environment override."""
        config_data = {
            "server": {
                "host": "192.168.1.1",
                "port": 9090
            }
        }
        
        env_vars = {
            "CHAT_SERVER_PORT": "8888"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            f.flush()
            f.close()  # Close file before reading on Windows
            
            try:
                with patch.dict(os.environ, env_vars, clear=True):
                    config = ConfigurationLoader.load_server_config(f.name, use_env=True)
                    assert config.host == "192.168.1.1"  # From file
                    assert config.port == 8888  # From environment
            finally:
                try:
                    os.unlink(f.name)
                except (OSError, PermissionError):
                    pass  # Ignore cleanup errors on Windows
    
    def test_load_server_config_defaults_only(self):
        """Test loading server config with defaults only."""
        config = ConfigurationLoader.load_server_config(use_env=False)
        assert config.host == "0.0.0.0"
        assert config.port == 8080
    
    def test_load_client_config_file_only(self):
        """Test loading client config from file only."""
        config_data = {
            "client": {
                "default_host": "192.168.1.1",
                "default_port": 9090,
                "discovery_timeout": 5
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            f.flush()
            f.close()  # Close file before reading on Windows
            
            try:
                config = ConfigurationLoader.load_client_config(f.name, use_env=False)
                assert config.default_host == "192.168.1.1"
                assert config.default_port == 9090
                assert config.discovery_timeout == 5
                # Defaults for other values
                assert config.ui_refresh_rate == 20
            finally:
                try:
                    os.unlink(f.name)
                except (OSError, PermissionError):
                    pass  # Ignore cleanup errors on Windows
    
    def test_load_client_config_env_override(self):
        """Test loading client config with environment override."""
        config_data = {
            "client": {
                "default_host": "192.168.1.1",
                "default_port": 9090
            }
        }
        
        env_vars = {
            "CHAT_CLIENT_PORT": "8888"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            f.flush()
            f.close()  # Close file before reading on Windows
            
            try:
                with patch.dict(os.environ, env_vars, clear=True):
                    config = ConfigurationLoader.load_client_config(f.name, use_env=True)
                    assert config.default_host == "192.168.1.1"  # From file
                    assert config.default_port == 8888  # From environment
            finally:
                try:
                    os.unlink(f.name)
                except (OSError, PermissionError):
                    pass  # Ignore cleanup errors on Windows


class TestConfigFileLoading:
    """Test legacy configuration file loading function."""
    
    def test_load_json_config(self):
        """Test loading JSON configuration file."""
        config_data = {
            "server": {
                "host": "192.168.1.1",
                "port": 9090
            },
            "client": {
                "default_host": "192.168.1.1",
                "default_port": 9090
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            f.flush()
            f.close()  # Close file before reading on Windows
            
            try:
                loaded_config = load_config_from_file(f.name)
                assert loaded_config == config_data
            finally:
                try:
                    os.unlink(f.name)
                except (OSError, PermissionError):
                    pass  # Ignore cleanup errors on Windows
    
    def test_load_nonexistent_file(self):
        """Test loading non-existent configuration file."""
        config = load_config_from_file(None)  # No file specified, should return empty dict
        assert config == {}
    
    def test_load_invalid_json(self):
        """Test loading invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content")
            f.flush()
            f.close()  # Close file before reading on Windows
            
            try:
                with pytest.raises(ConfigurationError):
                    load_config_from_file(f.name)
            finally:
                try:
                    os.unlink(f.name)
                except (OSError, PermissionError):
                    pass  # Ignore cleanup errors on Windows
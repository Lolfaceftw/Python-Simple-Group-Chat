"""
Configuration Management

Provides configuration classes and environment-based configuration loading.
"""

import json
import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .exceptions import ConfigurationError


@dataclass
class ServerConfig:
    """Server configuration settings."""
    
    host: str = "0.0.0.0"
    port: int = 8080
    max_clients: int = 100
    rate_limit_messages_per_minute: int = 60
    max_message_length: int = 1000
    max_username_length: int = 50
    max_connections_per_ip: int = 5
    message_history_size: int = 50
    discovery_port: int = 8081
    discovery_broadcast_interval: int = 5
    
    # Enhanced scalability settings
    max_concurrent_connections: int = 1000
    connection_queue_size: int = 50
    socket_buffer_size: int = 65536
    socket_timeout: int = 30
    keepalive_enabled: bool = True
    keepalive_idle: int = 300
    keepalive_interval: int = 30
    keepalive_count: int = 3
    
    # Load balancing and horizontal scaling
    enable_load_balancing: bool = False
    load_balancer_algorithm: str = "round_robin"  # round_robin, least_connections, weighted
    server_weight: int = 100
    health_check_interval: int = 30
    health_check_timeout: int = 5
    cluster_discovery_enabled: bool = False
    cluster_discovery_port: int = 8082
    
    # Performance optimization
    enable_connection_pooling: bool = True
    connection_pool_size: int = 20
    enable_message_batching: bool = True
    message_batch_size: int = 10
    message_batch_timeout: float = 0.1
    enable_compression: bool = False
    compression_threshold: int = 1024
    
    # Resource management
    max_memory_usage_mb: int = 512
    max_cpu_usage_percent: float = 80.0
    enable_resource_monitoring: bool = True
    resource_check_interval: int = 60
    auto_scale_enabled: bool = False
    scale_up_threshold: float = 0.8
    scale_down_threshold: float = 0.3
    
    def validate(self) -> None:
        """Validate configuration values."""
        errors: List[str] = []
        
        if not isinstance(self.host, str) or not self.host.strip():
            errors.append("host must be a non-empty string")
        
        if not isinstance(self.port, int) or not (1 <= self.port <= 65535):
            errors.append("port must be an integer between 1 and 65535")
        
        if not isinstance(self.max_clients, int) or self.max_clients < 1:
            errors.append("max_clients must be a positive integer")
        
        if not isinstance(self.rate_limit_messages_per_minute, int) or self.rate_limit_messages_per_minute < 1:
            errors.append("rate_limit_messages_per_minute must be a positive integer")
        
        if not isinstance(self.max_message_length, int) or self.max_message_length < 1:
            errors.append("max_message_length must be a positive integer")
        
        if not isinstance(self.max_username_length, int) or self.max_username_length < 1:
            errors.append("max_username_length must be a positive integer")
        
        if not isinstance(self.max_connections_per_ip, int) or self.max_connections_per_ip < 1:
            errors.append("max_connections_per_ip must be a positive integer")
        
        if not isinstance(self.message_history_size, int) or self.message_history_size < 0:
            errors.append("message_history_size must be a non-negative integer")
        
        if not isinstance(self.discovery_port, int) or not (1 <= self.discovery_port <= 65535):
            errors.append("discovery_port must be an integer between 1 and 65535")
        
        if not isinstance(self.discovery_broadcast_interval, int) or self.discovery_broadcast_interval < 1:
            errors.append("discovery_broadcast_interval must be a positive integer")
        
        if self.port == self.discovery_port:
            errors.append("port and discovery_port cannot be the same")
        
        # Validate scalability settings
        if not isinstance(self.max_concurrent_connections, int) or self.max_concurrent_connections < 1:
            errors.append("max_concurrent_connections must be a positive integer")
        
        if not isinstance(self.connection_queue_size, int) or self.connection_queue_size < 1:
            errors.append("connection_queue_size must be a positive integer")
        
        if not isinstance(self.socket_buffer_size, int) or self.socket_buffer_size < 1024:
            errors.append("socket_buffer_size must be at least 1024 bytes")
        
        if not isinstance(self.socket_timeout, int) or self.socket_timeout < 1:
            errors.append("socket_timeout must be a positive integer")
        
        if self.load_balancer_algorithm not in ["round_robin", "least_connections", "weighted"]:
            errors.append("load_balancer_algorithm must be one of: round_robin, least_connections, weighted")
        
        if not isinstance(self.server_weight, int) or self.server_weight < 1:
            errors.append("server_weight must be a positive integer")
        
        if not isinstance(self.max_memory_usage_mb, int) or self.max_memory_usage_mb < 64:
            errors.append("max_memory_usage_mb must be at least 64 MB")
        
        if not isinstance(self.max_cpu_usage_percent, (int, float)) or not (0 < self.max_cpu_usage_percent <= 100):
            errors.append("max_cpu_usage_percent must be between 0 and 100")
        
        if errors:
            raise ConfigurationError(f"Server configuration validation failed: {'; '.join(errors)}")
    
    @classmethod
    def from_env(cls) -> "ServerConfig":
        """Load configuration from environment variables."""
        try:
            config = cls(
                host=os.getenv("CHAT_SERVER_HOST", cls.host),
                port=int(os.getenv("CHAT_SERVER_PORT", str(cls.port))),
                max_clients=int(os.getenv("CHAT_MAX_CLIENTS", str(cls.max_clients))),
                rate_limit_messages_per_minute=int(
                    os.getenv("CHAT_RATE_LIMIT_MSG_PER_MIN", str(cls.rate_limit_messages_per_minute))
                ),
                max_message_length=int(
                    os.getenv("CHAT_MAX_MESSAGE_LENGTH", str(cls.max_message_length))
                ),
                max_username_length=int(
                    os.getenv("CHAT_MAX_USERNAME_LENGTH", str(cls.max_username_length))
                ),
                max_connections_per_ip=int(
                    os.getenv("CHAT_MAX_CONNECTIONS_PER_IP", str(cls.max_connections_per_ip))
                ),
                message_history_size=int(
                    os.getenv("CHAT_MESSAGE_HISTORY_SIZE", str(cls.message_history_size))
                ),
                discovery_port=int(
                    os.getenv("CHAT_DISCOVERY_PORT", str(cls.discovery_port))
                ),
                discovery_broadcast_interval=int(
                    os.getenv("CHAT_DISCOVERY_BROADCAST_INTERVAL", str(cls.discovery_broadcast_interval))
                ),
                # Enhanced scalability settings
                max_concurrent_connections=int(
                    os.getenv("CHAT_MAX_CONCURRENT_CONNECTIONS", str(cls.max_concurrent_connections))
                ),
                connection_queue_size=int(
                    os.getenv("CHAT_CONNECTION_QUEUE_SIZE", str(cls.connection_queue_size))
                ),
                socket_buffer_size=int(
                    os.getenv("CHAT_SOCKET_BUFFER_SIZE", str(cls.socket_buffer_size))
                ),
                socket_timeout=int(
                    os.getenv("CHAT_SOCKET_TIMEOUT", str(cls.socket_timeout))
                ),
                keepalive_enabled=os.getenv("CHAT_KEEPALIVE_ENABLED", "true").lower() == "true",
                keepalive_idle=int(
                    os.getenv("CHAT_KEEPALIVE_IDLE", str(cls.keepalive_idle))
                ),
                keepalive_interval=int(
                    os.getenv("CHAT_KEEPALIVE_INTERVAL", str(cls.keepalive_interval))
                ),
                keepalive_count=int(
                    os.getenv("CHAT_KEEPALIVE_COUNT", str(cls.keepalive_count))
                ),
                enable_load_balancing=os.getenv("CHAT_ENABLE_LOAD_BALANCING", "false").lower() == "true",
                load_balancer_algorithm=os.getenv("CHAT_LOAD_BALANCER_ALGORITHM", cls.load_balancer_algorithm),
                server_weight=int(
                    os.getenv("CHAT_SERVER_WEIGHT", str(cls.server_weight))
                ),
                health_check_interval=int(
                    os.getenv("CHAT_HEALTH_CHECK_INTERVAL", str(cls.health_check_interval))
                ),
                health_check_timeout=int(
                    os.getenv("CHAT_HEALTH_CHECK_TIMEOUT", str(cls.health_check_timeout))
                ),
                cluster_discovery_enabled=os.getenv("CHAT_CLUSTER_DISCOVERY_ENABLED", "false").lower() == "true",
                cluster_discovery_port=int(
                    os.getenv("CHAT_CLUSTER_DISCOVERY_PORT", str(cls.cluster_discovery_port))
                ),
                enable_connection_pooling=os.getenv("CHAT_ENABLE_CONNECTION_POOLING", "true").lower() == "true",
                connection_pool_size=int(
                    os.getenv("CHAT_CONNECTION_POOL_SIZE", str(cls.connection_pool_size))
                ),
                enable_message_batching=os.getenv("CHAT_ENABLE_MESSAGE_BATCHING", "true").lower() == "true",
                message_batch_size=int(
                    os.getenv("CHAT_MESSAGE_BATCH_SIZE", str(cls.message_batch_size))
                ),
                message_batch_timeout=float(
                    os.getenv("CHAT_MESSAGE_BATCH_TIMEOUT", str(cls.message_batch_timeout))
                ),
                enable_compression=os.getenv("CHAT_ENABLE_COMPRESSION", "false").lower() == "true",
                compression_threshold=int(
                    os.getenv("CHAT_COMPRESSION_THRESHOLD", str(cls.compression_threshold))
                ),
                max_memory_usage_mb=int(
                    os.getenv("CHAT_MAX_MEMORY_USAGE_MB", str(cls.max_memory_usage_mb))
                ),
                max_cpu_usage_percent=float(
                    os.getenv("CHAT_MAX_CPU_USAGE_PERCENT", str(cls.max_cpu_usage_percent))
                ),
                enable_resource_monitoring=os.getenv("CHAT_ENABLE_RESOURCE_MONITORING", "true").lower() == "true",
                resource_check_interval=int(
                    os.getenv("CHAT_RESOURCE_CHECK_INTERVAL", str(cls.resource_check_interval))
                ),
                auto_scale_enabled=os.getenv("CHAT_AUTO_SCALE_ENABLED", "false").lower() == "true",
                scale_up_threshold=float(
                    os.getenv("CHAT_SCALE_UP_THRESHOLD", str(cls.scale_up_threshold))
                ),
                scale_down_threshold=float(
                    os.getenv("CHAT_SCALE_DOWN_THRESHOLD", str(cls.scale_down_threshold))
                ),
            )
            config.validate()
            return config
        except ValueError as e:
            raise ConfigurationError(f"Failed to load server configuration from environment: {e}")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServerConfig":
        """Create configuration from dictionary."""
        try:
            # Filter only known fields
            field_names = {f.name for f in fields(cls)}
            filtered_data = {k: v for k, v in data.items() if k in field_names}
            config = cls(**filtered_data)
            config.validate()
            return config
        except (TypeError, ValueError) as e:
            raise ConfigurationError(f"Failed to create server configuration from dictionary: {e}")


@dataclass
class ClientConfig:
    """Client configuration settings."""
    
    host: str = "127.0.0.1"
    port: int = 8080
    username: str = ""
    discovery_timeout: int = 3
    ui_refresh_rate: int = 20
    reconnect_attempts: int = 3
    reconnect_delay: int = 5
    console_height: int = 24
    max_message_history: int = 2000
    
    def validate(self) -> None:
        """Validate configuration values."""
        errors: List[str] = []
        
        if not isinstance(self.host, str) or not self.host.strip():
            errors.append("host must be a non-empty string")
        
        if not isinstance(self.port, int) or not (1 <= self.port <= 65535):
            errors.append("port must be an integer between 1 and 65535")
        
        if not isinstance(self.discovery_timeout, int) or self.discovery_timeout < 1:
            errors.append("discovery_timeout must be a positive integer")
        
        if not isinstance(self.ui_refresh_rate, int) or self.ui_refresh_rate < 1:
            errors.append("ui_refresh_rate must be a positive integer")
        
        if not isinstance(self.reconnect_attempts, int) or self.reconnect_attempts < 0:
            errors.append("reconnect_attempts must be a non-negative integer")
        
        if not isinstance(self.reconnect_delay, int) or self.reconnect_delay < 0:
            errors.append("reconnect_delay must be a non-negative integer")
        
        if errors:
            raise ConfigurationError(f"Client configuration validation failed: {'; '.join(errors)}")
    
    @classmethod
    def from_env(cls) -> "ClientConfig":
        """Load configuration from environment variables."""
        try:
            config = cls(
                host=os.getenv("CHAT_CLIENT_HOST", cls.host),
                port=int(os.getenv("CHAT_CLIENT_PORT", str(cls.port))),
                username=os.getenv("CHAT_CLIENT_USERNAME", cls.username),
                discovery_timeout=int(
                    os.getenv("CHAT_DISCOVERY_TIMEOUT", str(cls.discovery_timeout))
                ),
                ui_refresh_rate=int(
                    os.getenv("CHAT_UI_REFRESH_RATE", str(cls.ui_refresh_rate))
                ),
                reconnect_attempts=int(
                    os.getenv("CHAT_RECONNECT_ATTEMPTS", str(cls.reconnect_attempts))
                ),
                reconnect_delay=int(
                    os.getenv("CHAT_RECONNECT_DELAY", str(cls.reconnect_delay))
                ),
            )
            config.validate()
            return config
        except ValueError as e:
            raise ConfigurationError(f"Failed to load client configuration from environment: {e}")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClientConfig":
        """Create configuration from dictionary."""
        try:
            # Filter only known fields
            field_names = {f.name for f in fields(cls)}
            filtered_data = {k: v for k, v in data.items() if k in field_names}
            config = cls(**filtered_data)
            config.validate()
            return config
        except (TypeError, ValueError) as e:
            raise ConfigurationError(f"Failed to create client configuration from dictionary: {e}")


class ConfigurationLoader:
    """Configuration loader with support for multiple sources."""
    
    DEFAULT_CONFIG_PATHS = [
        "config.json",
        "chat_config.json", 
        ".chat_config.json",
        "config.yaml",
        "chat_config.yaml",
        ".chat_config.yaml",
        "config.yml",
        "chat_config.yml",
        ".chat_config.yml"
    ]
    
    @staticmethod
    def load_from_file(config_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        """
        Load configuration from a JSON or YAML file.
        
        Args:
            config_path: Path to configuration file. If None, looks for default locations.
            
        Returns:
            Dictionary containing configuration values.
            
        Raises:
            ConfigurationError: If file cannot be loaded or parsed.
        """
        if config_path is None:
            # Look for default configuration files
            for path in ConfigurationLoader.DEFAULT_CONFIG_PATHS:
                if os.path.exists(path):
                    config_path = path
                    break
        
        if config_path is None:
            return {}
        
        config_path = Path(config_path)
        
        if not config_path.exists():
            raise ConfigurationError(f"Configuration file not found: {config_path}")
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                if config_path.suffix == '.json':
                    return json.load(f)
                elif config_path.suffix in ('.yml', '.yaml'):
                    try:
                        import yaml
                        return yaml.safe_load(f) or {}
                    except ImportError:
                        raise ConfigurationError("PyYAML is required for YAML configuration files. Install with: pip install PyYAML")
                else:
                    raise ConfigurationError(f"Unsupported configuration file format: {config_path.suffix}")
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in configuration file {config_path}: {e}")
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration from {config_path}: {e}")
    
    @staticmethod
    def load_server_config(
        config_path: Optional[Union[str, Path]] = None,
        use_env: bool = True
    ) -> ServerConfig:
        """
        Load server configuration from file and/or environment.
        
        Args:
            config_path: Path to configuration file.
            use_env: Whether to load from environment variables.
            
        Returns:
            ServerConfig instance.
        """
        config_data = {}
        
        # Load from file first
        if config_path or any(os.path.exists(p) for p in ConfigurationLoader.DEFAULT_CONFIG_PATHS):
            file_config = ConfigurationLoader.load_from_file(config_path)
            server_config = file_config.get('server', {})
            config_data.update(server_config)
        
        # Create base config from file data
        if config_data:
            config = ServerConfig.from_dict(config_data)
        else:
            config = ServerConfig()
        
        # Override with environment variables if requested
        if use_env:
            env_config = ServerConfig.from_env()
            # Only override non-default values from environment
            default_config = ServerConfig()
            for field in fields(ServerConfig):
                env_value = getattr(env_config, field.name)
                default_value = getattr(default_config, field.name)
                if env_value != default_value:
                    setattr(config, field.name, env_value)
        
        config.validate()
        return config
    
    @staticmethod
    def load_client_config(
        config_path: Optional[Union[str, Path]] = None,
        use_env: bool = True
    ) -> ClientConfig:
        """
        Load client configuration from file and/or environment.
        
        Args:
            config_path: Path to configuration file.
            use_env: Whether to load from environment variables.
            
        Returns:
            ClientConfig instance.
        """
        config_data = {}
        
        # Load from file first
        if config_path or any(os.path.exists(p) for p in ConfigurationLoader.DEFAULT_CONFIG_PATHS):
            file_config = ConfigurationLoader.load_from_file(config_path)
            client_config = file_config.get('client', {})
            config_data.update(client_config)
        
        # Create base config from file data
        if config_data:
            config = ClientConfig.from_dict(config_data)
        else:
            config = ClientConfig()
        
        # Override with environment variables if requested
        if use_env:
            env_config = ClientConfig.from_env()
            # Only override non-default values from environment
            default_config = ClientConfig()
            for field in fields(ClientConfig):
                env_value = getattr(env_config, field.name)
                default_value = getattr(default_config, field.name)
                if env_value != default_value:
                    setattr(config, field.name, env_value)
        
        config.validate()
        return config


# Convenience functions for backward compatibility
def load_config_from_file(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from a JSON or YAML file.
    
    Args:
        config_path: Path to configuration file. If None, looks for default locations.
        
    Returns:
        Dictionary containing configuration values.
    """
    return ConfigurationLoader.load_from_file(config_path)
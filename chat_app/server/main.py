"""
Server Main Entry Point

Entry point for the modular chat server with configuration loading,
logging setup, and error handling.
"""

import sys
import os
from typing import Optional

# Add the project root to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from chat_app.shared.config import ServerConfig, load_config_from_file
from chat_app.shared.logging_config import setup_logging, get_logger
from chat_app.shared.exceptions import ChatServerError, ConfigurationError
from chat_app.server.chat_server import ChatServer


def main() -> int:
    """
    Main entry point for the chat server.
    
    Returns:
        Exit code (0 for success, non-zero for error)
    """
    # Set up logging first
    try:
        # Configure logging from environment or use defaults
        log_level = os.getenv("CHAT_LOG_LEVEL", "INFO")
        log_file = os.getenv("CHAT_LOG_FILE")
        
        setup_logging(
            level=log_level,
            log_file=log_file,
            enable_colors=True
        )
        
        logger = get_logger(__name__)
        logger.info("Starting Chat Server...")
        
    except Exception as e:
        print(f"Failed to set up logging: {e}", file=sys.stderr)
        return 1
    
    try:
        # Load configuration
        config = load_server_config()
        logger.info(f"Server configuration loaded: {config.host}:{config.port}")
        
        # Create and start server
        server = ChatServer(config)
        server.start()
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
        return 0
        
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        return 2
        
    except ChatServerError as e:
        logger.error(f"Server error: {e}")
        return 3
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1


def load_server_config() -> ServerConfig:
    """
    Load server configuration from various sources.
    
    Priority order:
    1. Command line arguments
    2. Configuration file
    3. Environment variables
    4. Defaults
    
    Returns:
        ServerConfig instance
        
    Raises:
        ConfigurationError: If configuration is invalid
    """
    logger = get_logger(__name__)
    
    try:
        # Start with environment-based config
        config = ServerConfig.from_env()
        
        # Override with config file if available
        config_file_path = os.getenv("CHAT_CONFIG_FILE")
        if config_file_path or os.path.exists("config.json"):
            try:
                file_config = load_config_from_file(config_file_path)
                if file_config:
                    # Update config with file values
                    for key, value in file_config.get("server", {}).items():
                        if hasattr(config, key):
                            setattr(config, key, value)
                    logger.info(f"Configuration loaded from file: {config_file_path or 'config.json'}")
            except Exception as e:
                logger.warning(f"Failed to load config file: {e}")
        
        # Override with command line arguments
        config = parse_command_line_args(config)
        
        # Validate configuration
        validate_server_config(config)
        
        return config
        
    except Exception as e:
        raise ConfigurationError(f"Failed to load configuration: {e}") from e


def parse_command_line_args(config: ServerConfig) -> ServerConfig:
    """
    Parse command line arguments and update configuration.
    
    Args:
        config: Base configuration to update
        
    Returns:
        Updated configuration
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Python Chat Server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "--host",
        default=config.host,
        help="Host address to bind to"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=config.port,
        help="Port number to listen on"
    )
    
    parser.add_argument(
        "--max-clients",
        type=int,
        default=config.max_clients,
        help="Maximum number of concurrent clients"
    )
    
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=config.rate_limit_messages_per_minute,
        help="Rate limit (messages per minute per client)"
    )
    
    parser.add_argument(
        "--max-message-length",
        type=int,
        default=config.max_message_length,
        help="Maximum message length in characters"
    )
    
    parser.add_argument(
        "--max-username-length",
        type=int,
        default=config.max_username_length,
        help="Maximum username length in characters"
    )
    
    parser.add_argument(
        "--max-connections-per-ip",
        type=int,
        default=config.max_connections_per_ip,
        help="Maximum connections per IP address"
    )
    
    parser.add_argument(
        "--message-history-size",
        type=int,
        default=config.message_history_size,
        help="Number of messages to keep in history"
    )
    
    parser.add_argument(
        "--discovery-port",
        type=int,
        default=config.discovery_port,
        help="UDP port for service discovery"
    )
    
    parser.add_argument(
        "--discovery-interval",
        type=int,
        default=config.discovery_broadcast_interval,
        help="Service discovery broadcast interval in seconds"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level"
    )
    
    parser.add_argument(
        "--log-file",
        help="Log file path"
    )
    
    parser.add_argument(
        "--config-file",
        help="Configuration file path"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="Chat Server 1.0.0"
    )
    
    args = parser.parse_args()
    
    # Update configuration with parsed arguments
    config.host = args.host
    config.port = args.port
    config.max_clients = args.max_clients
    config.rate_limit_messages_per_minute = args.rate_limit
    config.max_message_length = args.max_message_length
    config.max_username_length = args.max_username_length
    config.max_connections_per_ip = args.max_connections_per_ip
    config.message_history_size = args.message_history_size
    config.discovery_port = args.discovery_port
    config.discovery_broadcast_interval = args.discovery_interval
    
    # Update environment variables for logging if specified
    if args.log_level:
        os.environ["CHAT_LOG_LEVEL"] = args.log_level
    if args.log_file:
        os.environ["CHAT_LOG_FILE"] = args.log_file
    if args.config_file:
        os.environ["CHAT_CONFIG_FILE"] = args.config_file
    
    return config


def validate_server_config(config: ServerConfig) -> None:
    """
    Validate server configuration values.
    
    Args:
        config: Configuration to validate
        
    Raises:
        ConfigurationError: If configuration is invalid
    """
    errors = []
    
    # Validate port ranges
    if not 1024 <= config.port <= 65535:
        errors.append(f"Server port must be between 1024 and 65535, got {config.port}")
    
    if not 1024 <= config.discovery_port <= 65535:
        errors.append(f"Discovery port must be between 1024 and 65535, got {config.discovery_port}")
    
    if config.port == config.discovery_port:
        errors.append("Server port and discovery port cannot be the same")
    
    # Validate limits
    if config.max_clients <= 0:
        errors.append(f"Max clients must be positive, got {config.max_clients}")
    
    if config.max_connections_per_ip <= 0:
        errors.append(f"Max connections per IP must be positive, got {config.max_connections_per_ip}")
    
    if config.rate_limit_messages_per_minute <= 0:
        errors.append(f"Rate limit must be positive, got {config.rate_limit_messages_per_minute}")
    
    if config.max_message_length <= 0:
        errors.append(f"Max message length must be positive, got {config.max_message_length}")
    
    if config.max_username_length <= 0:
        errors.append(f"Max username length must be positive, got {config.max_username_length}")
    
    if config.message_history_size < 0:
        errors.append(f"Message history size cannot be negative, got {config.message_history_size}")
    
    if config.discovery_broadcast_interval <= 0:
        errors.append(f"Discovery broadcast interval must be positive, got {config.discovery_broadcast_interval}")
    
    # Validate host
    if not config.host:
        errors.append("Host cannot be empty")
    
    if errors:
        raise ConfigurationError("Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in errors))


def print_server_info(config: ServerConfig) -> None:
    """
    Print server information and configuration.
    
    Args:
        config: Server configuration
    """
    print("=" * 60)
    print("Python Chat Server")
    print("=" * 60)
    print(f"Server Address: {config.host}:{config.port}")
    print(f"Discovery Port: {config.discovery_port}")
    print(f"Max Clients: {config.max_clients}")
    print(f"Max Connections per IP: {config.max_connections_per_ip}")
    print(f"Rate Limit: {config.rate_limit_messages_per_minute} messages/minute")
    print(f"Max Message Length: {config.max_message_length} characters")
    print(f"Max Username Length: {config.max_username_length} characters")
    print(f"Message History: {config.message_history_size} messages")
    print("=" * 60)
    print("Press Ctrl+C to stop the server")
    print("=" * 60)


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
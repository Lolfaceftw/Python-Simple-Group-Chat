# Configuration Guide

The chat application supports multiple configuration methods with the following priority order:

1. Environment variables (highest priority)
2. Configuration files (JSON/YAML)
3. Default values (lowest priority)

## Configuration Files

The application automatically looks for configuration files in the following order:

- `config.json`
- `chat_config.json`
- `.chat_config.json`
- `config.yaml`
- `chat_config.yaml`
- `.chat_config.yaml`
- `config.yml`
- `chat_config.yml`
- `.chat_config.yml`

You can also specify a custom configuration file path when loading configuration programmatically.

### JSON Configuration Format

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8080,
    "max_clients": 100,
    "rate_limit_messages_per_minute": 60,
    "max_message_length": 1000,
    "max_username_length": 50,
    "max_connections_per_ip": 5,
    "message_history_size": 50,
    "discovery_port": 8081,
    "discovery_broadcast_interval": 5
  },
  "client": {
    "default_host": "127.0.0.1",
    "default_port": 8080,
    "discovery_timeout": 3,
    "ui_refresh_rate": 20,
    "reconnect_attempts": 3,
    "reconnect_delay": 5
  }
}
```

### YAML Configuration Format

```yaml
server:
  host: "0.0.0.0"
  port: 8080
  max_clients: 100
  rate_limit_messages_per_minute: 60
  max_message_length: 1000
  max_username_length: 50
  max_connections_per_ip: 5
  message_history_size: 50
  discovery_port: 8081
  discovery_broadcast_interval: 5

client:
  default_host: "127.0.0.1"
  default_port: 8080
  discovery_timeout: 3
  ui_refresh_rate: 20
  reconnect_attempts: 3
  reconnect_delay: 5
```

## Environment Variables

All configuration values can be overridden using environment variables:

### Server Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `CHAT_SERVER_HOST` | Server bind address | `0.0.0.0` |
| `CHAT_SERVER_PORT` | Server port | `8080` |
| `CHAT_MAX_CLIENTS` | Maximum concurrent clients | `100` |
| `CHAT_RATE_LIMIT_MSG_PER_MIN` | Messages per minute per client | `60` |
| `CHAT_MAX_MESSAGE_LENGTH` | Maximum message length | `1000` |
| `CHAT_MAX_USERNAME_LENGTH` | Maximum username length | `50` |
| `CHAT_MAX_CONNECTIONS_PER_IP` | Maximum connections per IP | `5` |
| `CHAT_MESSAGE_HISTORY_SIZE` | Message history size | `50` |
| `CHAT_DISCOVERY_PORT` | Service discovery port | `8081` |
| `CHAT_DISCOVERY_BROADCAST_INTERVAL` | Discovery broadcast interval | `5` |

### Client Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `CHAT_CLIENT_HOST` | Default server host | `127.0.0.1` |
| `CHAT_CLIENT_PORT` | Default server port | `8080` |
| `CHAT_DISCOVERY_TIMEOUT` | Discovery timeout in seconds | `3` |
| `CHAT_UI_REFRESH_RATE` | UI refresh rate in Hz | `20` |
| `CHAT_RECONNECT_ATTEMPTS` | Reconnection attempts | `3` |
| `CHAT_RECONNECT_DELAY` | Delay between reconnections | `5` |

## Configuration Validation

The application validates all configuration values and will raise detailed error messages if invalid values are provided:

### Server Configuration Validation

- `host`: Must be a non-empty string
- `port`: Must be an integer between 1 and 65535
- `max_clients`: Must be a positive integer
- `rate_limit_messages_per_minute`: Must be a positive integer
- `max_message_length`: Must be a positive integer
- `max_username_length`: Must be a positive integer
- `max_connections_per_ip`: Must be a positive integer
- `message_history_size`: Must be a non-negative integer
- `discovery_port`: Must be an integer between 1 and 65535 (and different from `port`)
- `discovery_broadcast_interval`: Must be a positive integer

### Client Configuration Validation

- `default_host`: Must be a non-empty string
- `default_port`: Must be an integer between 1 and 65535
- `discovery_timeout`: Must be a positive integer
- `ui_refresh_rate`: Must be a positive integer
- `reconnect_attempts`: Must be a non-negative integer
- `reconnect_delay`: Must be a non-negative integer

## Usage Examples

### Loading Configuration in Code

```python
from chat_app.shared.config import ConfigurationLoader

# Load server configuration with defaults
server_config = ConfigurationLoader.load_server_config()

# Load from specific file
server_config = ConfigurationLoader.load_server_config("my_config.json")

# Load without environment variable override
server_config = ConfigurationLoader.load_server_config(use_env=False)

# Load client configuration
client_config = ConfigurationLoader.load_client_config()
```

### Environment Variable Examples

```bash
# Set server port
export CHAT_SERVER_PORT=9090

# Set client default host
export CHAT_CLIENT_HOST=192.168.1.100

# Set rate limiting
export CHAT_RATE_LIMIT_MSG_PER_MIN=30

# Run server with environment configuration
python -m chat_app.server.main
```

### Docker Environment

```dockerfile
ENV CHAT_SERVER_HOST=0.0.0.0
ENV CHAT_SERVER_PORT=8080
ENV CHAT_MAX_CLIENTS=50
ENV CHAT_RATE_LIMIT_MSG_PER_MIN=30
```

## Troubleshooting

### Common Configuration Errors

1. **Port conflicts**: Ensure `port` and `discovery_port` are different
2. **Invalid port ranges**: Ports must be between 1 and 65535
3. **YAML syntax errors**: Check indentation and syntax
4. **JSON syntax errors**: Validate JSON format
5. **Missing PyYAML**: Install with `pip install PyYAML` for YAML support

### Error Messages

The application provides detailed error messages for configuration issues:

```
ConfigurationError: Server configuration validation failed: port must be an integer between 1 and 65535; port and discovery_port cannot be the same
```

### Debugging Configuration

Enable debug logging to see which configuration values are being loaded:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Configuration loading will now show debug information
config = ConfigurationLoader.load_server_config()
```
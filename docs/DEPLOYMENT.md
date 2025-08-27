# Deployment Guide

This guide covers various deployment options for the Chat Application.

## Table of Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Docker Deployment](#docker-deployment)
- [Manual Deployment](#manual-deployment)
- [Environment Variables](#environment-variables)
- [Health Checks](#health-checks)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/example/chat-app.git
cd chat-app

# Install dependencies
pip install -r requirements.txt -r requirements-optional.txt

# Install the application
pip install .
```

### From PyPI (when published)

```bash
# Basic installation
pip install chat-app

# With optional dependencies
pip install chat-app[full]

# Development installation
pip install chat-app[dev]
```

### Using setup.py

```bash
# Development installation
python setup.py develop

# Production installation
python setup.py install
```

## Configuration

### Configuration Files

The application supports multiple configuration formats and locations:

1. **JSON Configuration**: `config.json`, `chat_config.json`, `.chat_config.json`
2. **YAML Configuration**: `config.yaml`, `chat_config.yaml`, `.chat_config.yaml`
3. **Environment Variables**: See [Environment Variables](#environment-variables)

### Configuration Priority

1. Environment variables (highest priority)
2. Configuration files
3. Default values (lowest priority)

### Example Configurations

Environment-specific configurations are provided in the `config/` directory:

- `config/development.json` - Development settings
- `config/production.json` - Production settings
- `config/testing.json` - Testing settings

## Docker Deployment

### Quick Start

```bash
# Start the server
docker-compose up -d chat-server

# View logs
docker-compose logs -f chat-server

# Stop the server
docker-compose down
```

### Production Deployment

```bash
# Build and start services
docker-compose -f docker-compose.yml up -d

# Scale the server (if using load balancer)
docker-compose up -d --scale chat-server=3

# Update configuration
docker-compose down
# Edit docker-compose.yml or environment files
docker-compose up -d
```

### Development Deployment

```bash
# Start development environment
docker-compose -f docker-compose.dev.yml up

# Run with demo client
docker-compose --profile demo up
```

### Custom Docker Build

```bash
# Build server image
docker build -f Dockerfile.server -t chat-app-server .

# Build client image
docker build -f Dockerfile.client -t chat-app-client .

# Run server
docker run -d -p 8080:8080 -p 8081:8081 \
  -e CHAT_SERVER_HOST=0.0.0.0 \
  -e CHAT_LOG_LEVEL=INFO \
  --name chat-server \
  chat-app-server

# Run client (interactive)
docker run -it --rm \
  -e CHAT_CLIENT_HOST=chat-server \
  --link chat-server \
  chat-app-client
```

## Manual Deployment

### System Requirements

- Python 3.8 or higher
- 2GB RAM minimum (4GB recommended for production)
- 1GB disk space
- Network access for TCP ports (default: 8080, 8081)

### Server Deployment

```bash
# Create dedicated user
sudo useradd -r -s /bin/false chatapp

# Create directories
sudo mkdir -p /opt/chat-app/{logs,config}
sudo chown -R chatapp:chatapp /opt/chat-app

# Install application
sudo -u chatapp pip install --user chat-app[full]

# Create configuration
sudo -u chatapp cp config/production.json /opt/chat-app/config/config.json

# Create systemd service
sudo cp deployment/chat-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable chat-server
sudo systemctl start chat-server
```

### Systemd Service

Create `/etc/systemd/system/chat-server.service`:

```ini
[Unit]
Description=Chat Application Server
After=network.target

[Service]
Type=simple
User=chatapp
Group=chatapp
WorkingDirectory=/opt/chat-app
Environment=PYTHONPATH=/opt/chat-app
Environment=CHAT_LOG_FILE=/opt/chat-app/logs/server.log
Environment=CHAT_LOG_LEVEL=INFO
Environment=CHAT_LOG_JSON=true
ExecStart=/home/chatapp/.local/bin/chat-server
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Nginx Reverse Proxy (Optional)

For HTTP health checks or metrics endpoints:

```nginx
upstream chat_servers {
    server 127.0.0.1:8080;
    # Add more servers for load balancing
    # server 127.0.0.1:8081;
}

server {
    listen 80;
    server_name chat.example.com;

    location /health {
        proxy_pass http://chat_servers;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /metrics {
        proxy_pass http://chat_servers;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # Restrict access to metrics
        allow 10.0.0.0/8;
        deny all;
    }
}
```

## Environment Variables

### Server Configuration

| Variable | Description | Default |
|----------|-------------|---------|
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

| Variable | Description | Default |
|----------|-------------|---------|
| `CHAT_CLIENT_HOST` | Default server host | `127.0.0.1` |
| `CHAT_CLIENT_PORT` | Default server port | `8080` |
| `CHAT_DISCOVERY_TIMEOUT` | Discovery timeout in seconds | `3` |
| `CHAT_UI_REFRESH_RATE` | UI refresh rate in Hz | `20` |
| `CHAT_RECONNECT_ATTEMPTS` | Reconnection attempts | `3` |
| `CHAT_RECONNECT_DELAY` | Delay between reconnections | `5` |

### Logging Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `CHAT_LOG_LEVEL` | Logging level | `INFO` |
| `CHAT_LOG_FILE` | Log file path | None |
| `CHAT_LOG_COLORS` | Enable colored output | `true` |
| `CHAT_LOG_JSON` | Use JSON format | `false` |
| `CHAT_LOG_MAX_SIZE` | Max file size in bytes | `10485760` |
| `CHAT_LOG_BACKUP_COUNT` | Number of backup files | `5` |
| `CHAT_LOG_INCLUDE_METRICS` | Include metrics in JSON logs | `false` |

## Health Checks

### Built-in Health Checks

The application includes several built-in health checks:

- **Memory Usage**: Monitors memory consumption
- **Disk Space**: Checks available disk space
- **Port Binding**: Verifies port availability
- **Network Connectivity**: Tests network connectivity

### HTTP Health Endpoint

When running with monitoring enabled:

```bash
# Check server health
curl http://localhost:8080/health

# Get detailed metrics
curl http://localhost:8080/metrics
```

### Docker Health Checks

Docker containers include built-in health checks:

```bash
# Check container health
docker ps
docker inspect chat-server | grep Health -A 10
```

## Monitoring

### Metrics Collection

The application collects various metrics:

- **Counters**: Message counts, connection events, errors
- **Gauges**: Active connections, memory usage
- **Histograms**: Message sizes, response times
- **Timers**: Operation durations

### Log Monitoring

Structured logging with JSON format for easy parsing:

```bash
# Follow logs
tail -f /opt/chat-app/logs/server.log

# Parse JSON logs
tail -f /opt/chat-app/logs/server.log | jq '.'

# Filter error logs
tail -f /opt/chat-app/logs/server.log | jq 'select(.level == "ERROR")'
```

### System Monitoring

Monitor system resources:

```bash
# CPU and memory usage
top -p $(pgrep -f chat-server)

# Network connections
netstat -tulpn | grep :8080

# Disk usage
df -h /opt/chat-app
```

## Troubleshooting

### Common Issues

#### Port Already in Use

```bash
# Find process using port
sudo lsof -i :8080
sudo netstat -tulpn | grep :8080

# Kill process
sudo kill -9 <PID>
```

#### Permission Denied

```bash
# Check file permissions
ls -la /opt/chat-app/
sudo chown -R chatapp:chatapp /opt/chat-app/

# Check service user
sudo systemctl status chat-server
```

#### High Memory Usage

```bash
# Check memory usage
ps aux | grep chat-server
free -h

# Restart service
sudo systemctl restart chat-server
```

#### Connection Issues

```bash
# Test connectivity
telnet localhost 8080
nc -zv localhost 8080

# Check firewall
sudo ufw status
sudo iptables -L
```

### Debug Mode

Enable debug logging:

```bash
# Environment variable
export CHAT_LOG_LEVEL=DEBUG

# Configuration file
{
  "server": {
    "log_level": "DEBUG"
  }
}

# Command line
chat-server --log-level DEBUG
```

### Log Analysis

Common log patterns to look for:

```bash
# Connection errors
grep "ConnectionError" /opt/chat-app/logs/server.log

# Rate limiting
grep "RateLimitExceeded" /opt/chat-app/logs/server.log

# Memory warnings
grep "memory" /opt/chat-app/logs/server.log

# Client disconnections
grep "disconnect" /opt/chat-app/logs/server.log
```

### Performance Tuning

#### Server Optimization

```bash
# Increase file descriptor limits
echo "chatapp soft nofile 65536" >> /etc/security/limits.conf
echo "chatapp hard nofile 65536" >> /etc/security/limits.conf

# Optimize TCP settings
echo "net.core.somaxconn = 1024" >> /etc/sysctl.conf
echo "net.ipv4.tcp_max_syn_backlog = 1024" >> /etc/sysctl.conf
sysctl -p
```

#### Application Tuning

Adjust configuration for your environment:

```json
{
  "server": {
    "max_clients": 500,
    "rate_limit_messages_per_minute": 30,
    "message_history_size": 25,
    "max_connections_per_ip": 3
  }
}
```

### Getting Help

1. Check the logs first
2. Verify configuration
3. Test network connectivity
4. Check system resources
5. Review the documentation
6. Open an issue on GitHub

For more detailed troubleshooting, enable debug logging and collect the following information:

- Application version
- Operating system and version
- Python version
- Configuration files
- Log files
- Error messages
- Steps to reproduce the issue
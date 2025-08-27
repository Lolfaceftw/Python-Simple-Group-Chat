# Python Group Chat Application

A real-time TCP-based chat application with rich terminal UI, featuring multi-client support, service discovery, and cross-platform compatibility.

## 🚀 Features

- **Multi-client chat server** with message broadcasting and user management
- **Rich terminal UI client** with scrollable chat history, user list panel, and keyboard navigation
- **Service discovery** via UDP broadcast for automatic server detection
- **Message history** with configurable retention for new client onboarding
- **User management** with nickname changes and connection notifications
- **Security-first design** with input validation, rate limiting, and connection controls
- **Comprehensive testing** including unit, integration, and fuzzing tests
- **Production-ready** with logging, monitoring, and deployment support

## 📁 Project Structure

```
chat_app/                    # Main application package
├── client/                  # Client-side components
│   ├── main.py             # Client entry point
│   ├── chat_client.py      # Main client orchestrator
│   ├── ui/                 # User interface components
│   │   ├── layout_manager.py
│   │   ├── input_handler.py
│   │   └── display_manager.py
│   └── network/            # Client networking
│       ├── connection.py
│       └── message_handler.py
├── server/                 # Server-side components
│   ├── main.py            # Server entry point
│   ├── chat_server.py     # Main server orchestrator
│   ├── client_manager.py  # Client connection management
│   ├── message_broker.py  # Message broadcasting logic
│   └── security/          # Security components
│       ├── rate_limiter.py
│       ├── validator.py
│       └── connection_limiter.py
├── shared/                # Shared components
│   ├── config.py         # Configuration management
│   ├── constants.py      # Application constants
│   ├── exceptions.py     # Custom exceptions
│   ├── models.py         # Data models and types
│   ├── protocols.py      # Type protocols/interfaces
│   └── utils.py          # Utility functions
├── discovery/            # Service discovery
│   └── service_discovery.py
└── tools/               # Development and testing tools
    ├── benchmark_suite.py
    └── load_tester.py

tests/                   # Test suite
├── unit/               # Unit tests
├── integration/        # Integration tests
└── fuzzing/           # Fuzzing and property-based tests

docs/                   # Documentation
config/                 # Configuration files
old/                   # Legacy files (deprecated)
```

## 🛠️ Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package installer)

### Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd chat-app
   ```

2. **Create and activate virtual environment:**
   ```bash
   python -m venv .venv
   
   # On Windows
   .venv\Scripts\activate
   
   # On Linux/macOS
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   
   # For development
   pip install -r requirements-dev.txt
   ```

## 🚀 Quick Start

### Running the Modern Modular Version (Recommended)

**Start the server:**
```bash
python -m chat_app.server.main
```

**Start the client:**
```bash
python -m chat_app.client.main
```

### Running with Custom Configuration

**Using environment variables:**
```bash
export CHAT_HOST=0.0.0.0
export CHAT_PORT=8080
export CHAT_MAX_CLIENTS=50
python -m chat_app.server.main
```

**Using configuration file:**
```bash
python -m chat_app.server.main --config config/production.json
```

### Running the Legacy Version

The legacy monolithic files are preserved in the `old/` directory:

```bash
# Legacy server
python old/server.py

# Legacy client  
python old/client.py
```

## 🎮 Usage

### Client Commands

- **Send message:** Type your message and press Enter
- **Change nickname:** `/nick <new_nickname>`
- **Quit application:** `/quit` or Ctrl+C
- **Navigation:** Use arrow keys to scroll through chat history

### Server Management

The server automatically handles:
- Client connections and disconnections
- Message broadcasting to all connected clients
- User list updates
- Rate limiting and security controls
- Service discovery broadcasting

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAT_HOST` | `0.0.0.0` | Server bind address |
| `CHAT_PORT` | `8080` | Server port |
| `CHAT_MAX_CLIENTS` | `100` | Maximum concurrent clients |
| `CHAT_RATE_LIMIT` | `60` | Messages per minute per client |
| `CHAT_MAX_MESSAGE_LENGTH` | `1000` | Maximum message length |
| `CHAT_MAX_USERNAME_LENGTH` | `50` | Maximum username length |
| `CHAT_LOG_LEVEL` | `INFO` | Logging level |

### Configuration Files

Configuration files are supported in JSON and YAML formats:

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8080,
    "max_clients": 100,
    "rate_limit_messages_per_minute": 60
  },
  "security": {
    "max_message_length": 1000,
    "max_username_length": 50,
    "connection_timeout": 30
  }
}
```

See `config/` directory for examples.

## 🧪 Testing

### Run All Tests

```bash
# Run complete test suite
pytest

# Run with coverage
pytest --cov=chat_app --cov-report=html

# Run specific test categories
pytest tests/unit/          # Unit tests only
pytest tests/integration/   # Integration tests only
pytest tests/fuzzing/       # Fuzzing tests only
```

### Type Checking

```bash
mypy chat_app/
```

### Performance Testing

```bash
python -m chat_app.tools.load_tester
python -m chat_app.tools.benchmark_suite
```

## 🐳 Docker Deployment

### Build and Run

```bash
# Build images
docker-compose build

# Run in development mode
docker-compose -f docker-compose.dev.yml up

# Run in production mode
docker-compose up -d
```

### Individual Containers

```bash
# Server only
docker build -f Dockerfile.server -t chat-server .
docker run -p 8080:8080 chat-server

# Client only
docker build -f Dockerfile.client -t chat-client .
docker run -it chat-client
```

## 🔧 Development

### Code Standards

- **Type hints:** Complete type annotations required
- **Documentation:** Google-style docstrings for all public APIs
- **Testing:** >90% code coverage target
- **Style:** PEP 8 compliance
- **Security:** Input validation and rate limiting

### Development Workflow

1. **Setup development environment:**
   ```bash
   pip install -r requirements-dev.txt
   ```

2. **Run quality checks:**
   ```bash
   # Type checking
   mypy chat_app/
   
   # Tests with coverage
   pytest --cov=chat_app
   
   # Code formatting (if using black)
   black chat_app/
   ```

3. **Run development servers:**
   ```bash
   # Server with debug logging
   CHAT_LOG_LEVEL=DEBUG python -m chat_app.server.main
   
   # Client with debug mode
   CHAT_LOG_LEVEL=DEBUG python -m chat_app.client.main
   ```

### Architecture Overview

The application follows a modular, security-first architecture:

- **Separation of Concerns:** Client, server, and shared components are clearly separated
- **Type Safety:** Complete type hints and protocol-based interfaces
- **Security:** Input validation, rate limiting, and connection controls
- **Testability:** Comprehensive test coverage with mocking and fuzzing
- **Production Ready:** Logging, monitoring, configuration management

## 📚 Documentation

Additional documentation is available in the `docs/` directory:

- [Configuration Guide](docs/CONFIGURATION.md)
- [Deployment Guide](docs/DEPLOYMENT.md)
- [Performance Improvements](docs/PERFORMANCE_IMPROVEMENTS_SUMMARY.md)
- [Scalability Features](docs/SCALABILITY_FEATURES_SUMMARY.md)
- [Test Suite Overview](docs/TEST_SUITE_SUMMARY.md)
- [Fuzzing and Protocol Tests](docs/FUZZING_AND_PROTOCOL_TESTS_FIXED.md)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes following the code standards
4. Add tests for new functionality
5. Ensure all tests pass (`pytest`)
6. Ensure type checking passes (`mypy chat_app/`)
7. Commit your changes (`git commit -m 'Add amazing feature'`)
8. Push to the branch (`git push origin feature/amazing-feature`)
9. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🔍 Troubleshooting

### Common Issues

**Connection refused:**
- Ensure the server is running before starting clients
- Check firewall settings for the configured port
- Verify the host/port configuration

**Service discovery not working:**
- Ensure UDP broadcast is allowed on your network
- Check if port 8081 (discovery port) is available
- Try connecting directly using IP address

**Performance issues:**
- Adjust rate limiting settings in configuration
- Monitor resource usage with the built-in metrics
- Consider scaling horizontally for high load

### Getting Help

- Check the documentation in the `docs/` directory
- Review the test suite for usage examples
- Open an issue for bugs or feature requests

## 🏗️ Architecture Migration

This codebase has been refactored from a monolithic structure to a modular, production-ready architecture. The legacy files are preserved in the `old/` directory for reference, but the new modular structure in `chat_app/` is recommended for all new development and deployment.

### Key Improvements

- **Modular Design:** Clear separation of client, server, and shared components
- **Security:** Comprehensive input validation and rate limiting
- **Type Safety:** Complete type hints and protocol-based interfaces  
- **Testing:** >90% code coverage with unit, integration, and fuzzing tests
- **Production Ready:** Logging, monitoring, configuration, and deployment support
- **Documentation:** Comprehensive documentation and examples

The new architecture maintains full backward compatibility while providing a solid foundation for future development and scaling.
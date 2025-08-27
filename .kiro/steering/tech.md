---
inclusion: always
---

# Technology Stack & Development Standards

## Required Technologies

- **Python 3.8+** - Use modern Python features, full type hints required
- **Rich** - All terminal UI must use Rich components (panels, tables, progress bars)
- **Standard Library Only** - Prefer `socket`, `threading`, `dataclasses` over external deps
- **UDP Broadcasting** - Use for service discovery, TCP for chat communication

## Development Dependencies

- **pytest** - All new code requires corresponding tests
- **mypy** - Code must pass type checking with `--strict` mode
- **hypothesis** - Use for property-based testing of network protocols

## Mandatory Code Standards

### Type Safety

- **Complete type hints** - Every function parameter, return value, and class attribute
- **Protocol interfaces** - Use `typing.Protocol` for structural typing, not inheritance
- **Dataclass models** - All data structures must be `@dataclass` with type hints
- **Generic types** - Use `List[str]`, `Dict[str, int]`, etc. not bare `list`, `dict`

### Error Handling

- **Custom exceptions** - Create specific exception types in `chat_app/shared/exceptions.py`
- **Context managers** - Always use `with` statements for sockets, files, locks
- **Graceful degradation** - Network failures should not crash the application
- **Logging** - Use `logging` module, not `print()` statements

### Threading Safety

- **Lock all shared state** - Use `threading.Lock()` for any data accessed by multiple threads
- **Thread-safe collections** - Use `queue.Queue` for inter-thread communication
- **Daemon threads** - Mark background threads as daemon for clean shutdown

### Documentation

- **Google-style docstrings** - Required for all public functions, methods, and classes
- **Type information** - Include parameter and return types in docstrings
- **Examples** - Include usage examples for complex functions

## Architecture Requirements

### Module Organization

- **Absolute imports only** - `from chat_app.shared.models import User`
- **Circular import prevention** - Shared code goes in `chat_app/shared/`
- **Interface segregation** - Small, focused protocols over large interfaces

### Network Programming

- **Non-blocking I/O** - Use `socket.settimeout()` for network operations
- **Connection pooling** - Reuse connections where possible
- **Protocol versioning** - Include version info in message headers

### Configuration

- **Environment variables** - Use `.env` file with `os.getenv()` for configuration
- **Dataclass config** - Centralize settings in `chat_app/shared/config.py`
- **Validation** - Validate all configuration values at startup

## Development Workflow

### Before Committing

```bash
# Type check (must pass)
mypy chat_app/

# Run tests (must pass)
pytest

# Check coverage (aim for >90%)
pytest --cov=chat_app --cov-report=term-missing
```

### Running Applications

```bash
# Development mode (legacy)
python server.py
python client.py

# Production mode (modular)
python -m chat_app.server.main
python -m chat_app.client.main
```

## Quality Gates

- **No `Any` types** - Use specific types or `Union` types
- **100% test coverage** for new modules
- **Zero mypy errors** with `--strict` mode
- **All threads must be joinable** - No orphaned background threads
- **Resource cleanup** - All sockets, files, and threads must be properly closed

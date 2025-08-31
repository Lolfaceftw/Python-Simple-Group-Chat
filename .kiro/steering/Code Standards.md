---
inclusion: always
---

# Python Group Chat Application - Code Standards

## Documentation & Type Safety

- **All functions and classes must have Google-style docstrings** with complete parameter and return type documentation
- **Complete type hints are mandatory** for all function signatures, class attributes, and variables
- Use `typing` module types (`Dict`, `List`, `Tuple`, `Optional`, etc.) and protocol-based interfaces
- Document complex type unions and generic types clearly

## Architecture Patterns

- **Modular design**: Maintain clear separation between `client/`, `server/`, `shared/`, `discovery/`, and `tools/` packages
- **Protocol-based interfaces**: Use typing protocols for defining contracts between components
- **Dependency injection**: Pass dependencies explicitly rather than using global state
- **Thread-safe operations**: Use proper locking mechanisms (`threading.RLock`) for shared resources
- **Resource management**: Use context managers (`with` statements) for sockets, files, and other resources

## Security Standards

- **Input validation**: Validate all user inputs, network data, and configuration values
- **Rate limiting**: Implement rate limiting for network operations and user actions
- **Connection controls**: Enforce maximum client limits and connection timeouts
- **Error handling**: Never expose internal system details in error messages to clients
- **Privilege separation**: Run with minimal required privileges, especially for network scanning operations

## Network Programming Patterns

- **Socket management**: Always use try/except blocks around socket operations with proper cleanup
- **Non-blocking operations**: Use timeouts and non-blocking patterns where appropriate
- **Protocol design**: Use structured message formats with clear delimiters (e.g., `MSG|payload`)
- **Service discovery**: Implement robust UDP broadcast mechanisms with fallback options
- **Connection resilience**: Handle connection drops, timeouts, and network errors gracefully

## UI/UX Standards (Rich Library)

- **Consistent styling**: Use Rich's styling system with consistent color schemes and formatting
- **Progress indicators**: Show progress for long-running operations (scanning, connecting)
- **Error presentation**: Use Rich panels and styling for clear error communication
- **Layout management**: Use Rich Layout for complex UI structures with proper panel organization
- **User feedback**: Provide immediate visual feedback for user actions

## Testing Requirements

- **Coverage target**: Maintain >90% code coverage across unit, integration, and fuzzing tests
- **Test categories**: Organize tests into `unit/`, `integration/`, and `fuzzing/` directories
- **Mock external dependencies**: Mock network calls, file system operations, and external services
- **Property-based testing**: Use fuzzing for protocol validation and edge case discovery
- **Performance testing**: Include load testing and benchmarking for network components

## Error Handling Conventions

- **Specific exceptions**: Use custom exception classes from `shared/exceptions.py`
- **Graceful degradation**: Provide fallback behavior when optional features fail
- **Logging**: Use structured logging with appropriate levels (DEBUG, INFO, WARNING, ERROR)
- **User-friendly messages**: Present technical errors in user-understandable terms
- **Resource cleanup**: Ensure proper cleanup in finally blocks or context managers

## Code Organization Principles

- **KISS, SOLID, DRY, YAGNI**: Follow these fundamental principles
- **Single responsibility**: Each class and function should have one clear purpose
- **Configuration management**: Use `shared/config.py` for all configuration handling
- **Constants**: Define all magic numbers and strings in `shared/constants.py`
- **Utilities**: Place reusable functions in `shared/utils.py`

## Performance Considerations

- **Concurrent operations**: Use `concurrent.futures.ThreadPoolExecutor` for I/O-bound tasks
- **Memory management**: Implement bounded collections (e.g., `deque(maxlen=N)`) for message history
- **Efficient data structures**: Choose appropriate data structures for the use case
- **Resource monitoring**: Include metrics and monitoring capabilities for production deployment

## Platform Compatibility

- **Cross-platform code**: Handle platform-specific differences (Windows vs Linux/macOS)
- **Conditional imports**: Use try/except for platform-specific modules
- **Path handling**: Use `pathlib` for cross-platform file path operations
- **Environment variables**: Support configuration via environment variables

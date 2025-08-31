# Design Document

## Overview

This design document outlines the refactoring of the Python Group Chat Application from a monolithic structure to a modular architecture. The refactoring will organize code into five main packages (`client/`, `server/`, `shared/`, `discovery/`, and `tools/`) while maintaining all existing functionality and user interface behavior.

The current codebase consists of three main files:
- `main.py` - Entry point with server discovery and client initialization logic
- `server.py` - Contains the `ChatServer` class and all server-side functionality
- `client.py` - Contains the `ChatClient` class and all client-side functionality including discovery functions

## Architecture

### Package Structure

```
project_root/
├── client/
│   ├── __init__.py
│   ├── chat_client.py          # ChatClient class from client.py
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── display_manager.py  # UI layout and rendering methods
│   │   ├── input_handler.py    # Windows keyboard input handling
│   │   └── layout_manager.py   # Rich layout creation and management
│   ├── network/
│   │   ├── __init__.py
│   │   ├── connection.py       # Socket connection and message receiving
│   │   └── message_handler.py  # Message parsing and protocol detection
│   └── main.py                 # Client startup logic from main.py
├── server/
│   ├── __init__.py
│   ├── chat_server.py          # ChatServer class from server.py
│   ├── client_manager.py       # Client connection and user management
│   ├── message_broker.py       # Message broadcasting and history
│   └── main.py                 # Server startup logic
├── shared/
│   ├── __init__.py
│   ├── config.py               # Configuration constants (VERSION, ports, etc.)
│   ├── constants.py            # Discovery protocol constants
│   ├── exceptions.py           # Custom exception classes
│   ├── protocols.py            # Protocol definitions and interfaces
│   ├── models.py               # Data models and types
│   └── utils.py                # Common utility functions
├── discovery/
│   ├── __init__.py
│   ├── service_discovery.py    # discover_servers function from client.py
│   ├── network_scanner.py      # scan_and_probe_ports function
│   ├── host_discovery.py       # discover_lan_hosts and related functions
│   └── os_detection.py         # get_os_from_ip function
├── main.py                     # Main application entry point (current main.py)
├── server.py                   # Server entry point (thin wrapper)
└── client.py                   # Client entry point (thin wrapper)
```

## Components and Interfaces

### Shared Package

**Purpose:** Contains common components used by both client and server.

**Key Components:**
- `protocols.py`: Defines typing protocols for `MessageHandler`, `ConnectionManager`, `UserManager`
- `models.py`: Data classes for `User`, `Message`, `ServerInfo`, `ConnectionInfo`
- `constants.py`: Network ports, message types, timeouts, and configuration defaults
- `exceptions.py`: Custom exceptions like `ConnectionError`, `AuthenticationError`, `ValidationError`
- `config.py`: Configuration management with environment variable support

### Server Package

**Purpose:** Handles all server-side functionality with clear separation of concerns.

**Key Components:**
- `chat_server.py`: Main `ChatServer` class coordinating all server operations
- `client_manager.py`: Manages client connections, authentication, and user lists
- `message_broker.py`: Handles message broadcasting, history management, and message validation

**Interfaces:**
```python
class ClientManager(Protocol):
    def add_client(self, socket: socket.socket, address: Tuple[str, int]) -> None
    def remove_client(self, socket: socket.socket) -> None
    def get_user_list(self) -> Dict[str, str]
    def is_username_taken(self, username: str, requesting_socket: socket.socket) -> bool

class MessageBroker(Protocol):
    def broadcast_message(self, message: str, sender_socket: socket.socket = None) -> None
    def add_to_history(self, message: str) -> None
    def get_message_history(self) -> List[str]
```

### Client Package

**Purpose:** Handles client-side functionality with UI separated from networking.

**Key Components:**
- `chat_client.py`: Main `ChatClient` class coordinating client operations
- `ui/display_manager.py`: Rich UI rendering and layout management
- `ui/input_handler.py`: Keyboard input processing and command handling
- `network/connection.py`: Socket connection management and reconnection logic
- `network/message_handler.py`: Message parsing, protocol handling, and server type detection

**Interfaces:**
```python
class DisplayManager(Protocol):
    def update_chat_panel(self, messages: List[Text]) -> None
    def update_user_panel(self, users: Dict[str, str]) -> None
    def render_layout(self) -> None

class InputHandler(Protocol):
    def handle_keyboard_input(self) -> Optional[str]
    def process_command(self, command: str) -> bool
```



### Discovery Package

**Purpose:** Contains all network discovery and scanning functionality extracted from client.py.

**Key Components:**
- `service_discovery.py`: UDP broadcast discovery (`discover_servers` function)
- `network_scanner.py`: Port scanning and probing (`scan_and_probe_ports` function)  
- `host_discovery.py`: LAN host discovery (`discover_lan_hosts`, `get_local_ipv4_addresses`, `get_lan_scan_target` functions)
- `os_detection.py`: Operating system detection (`get_os_from_ip` function)

## Data Models

### Core Models (shared/models.py)

Based on the existing codebase, the following models represent the current data structures:

```python
# Type aliases for existing data structures
ClientInfo = Tuple[str, str]  # (address, username) as used in server.py
UserListEntry = Tuple[str, str, str]  # (ip, vendor, mac) from discover_lan_hosts
PortScanResult = Dict[int, str]  # port -> status mapping from scan_and_probe_ports
ServerList = List[str]  # IP addresses from discover_servers
```

## Error Handling

### Exception Hierarchy (shared/exceptions.py)

```python
class ChatApplicationError(Exception):
    """Base exception for chat application"""

class NetworkError(ChatApplicationError):
    """Network-related errors"""

class ConnectionError(NetworkError):
    """Connection establishment errors"""

class AuthenticationError(ChatApplicationError):
    """User authentication errors"""

class ValidationError(ChatApplicationError):
    """Data validation errors"""

class ServerError(ChatApplicationError):
    """Server-side errors"""

class ClientError(ChatApplicationError):
    """Client-side errors"""
```

### Error Handling Strategy

1. **Graceful Degradation**: Network failures should not crash the application
2. **User-Friendly Messages**: Technical errors are translated to user-understandable messages
3. **Logging**: All errors are logged with appropriate levels using structured logging
4. **Recovery**: Automatic reconnection attempts for network issues
5. **Resource Cleanup**: Proper cleanup in finally blocks and context managers

## Testing Strategy

### Test Organization

```
tests/
├── unit/
│   ├── test_client/
│   ├── test_server/
│   ├── test_shared/
│   ├── test_discovery/
│   └── test_tools/
├── integration/
│   ├── test_client_server_integration.py
│   ├── test_discovery_integration.py
│   └── test_network_protocols.py
└── fuzzing/
    ├── test_message_protocol_fuzzing.py
    ├── test_network_input_fuzzing.py
    └── test_user_input_fuzzing.py
```

### Testing Approach

1. **Unit Tests**: Test individual modules and classes in isolation
2. **Integration Tests**: Test interactions between components
3. **Protocol Tests**: Verify message protocol compatibility
4. **Performance Tests**: Benchmark network and UI performance
5. **Fuzzing Tests**: Test robustness against malformed inputs
6. **Mock Strategy**: Mock external dependencies (network, file system)

### Coverage Requirements

- Maintain >90% code coverage across all packages
- Critical paths (networking, message handling) require 100% coverage
- UI components tested through integration tests
- Error handling paths explicitly tested

## Migration Strategy

### Phase 1: Shared Package Creation
1. Extract constants, exceptions, and protocols
2. Create data models and utility functions
3. Update imports in existing files

### Phase 2: Server Refactoring
1. Extract client management logic
2. Separate message broadcasting functionality
3. Create server package structure

### Phase 3: Client Refactoring
1. Separate UI components from networking
2. Extract input handling logic
3. Create client package structure

### Phase 4: Discovery Package
1. Extract discovery functions from client.py
2. Organize network scanning functionality
3. Create discovery package structure

### Phase 5: Entry Point Updates
1. Update main.py, server.py, client.py to use new structure
2. Ensure backward compatibility
3. Update documentation and examples
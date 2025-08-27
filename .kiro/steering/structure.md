---
inclusion: always
---

# Project Structure & Organization

## Package Architecture

```
chat_app/
├── client/          # Client UI, networking, input handling
├── server/          # Connection management, security, broadcasting
├── shared/          # Models, protocols, config, utilities
└── discovery/       # UDP service discovery
```

## File Placement Decision Tree

**For new functionality:**
- UI/terminal rendering → `chat_app/client/`
- Connection handling/security → `chat_app/server/`
- Data models/protocols → `chat_app/shared/`
- Service discovery → `chat_app/discovery/`
- Tests → Mirror source structure in `tests/unit/`, `tests/integration/`, `tests/fuzzing/`

**Core shared modules (create if missing):**
- `chat_app/shared/models.py` - Dataclasses (User, Message, ClientConnection)
- `chat_app/shared/protocols.py` - Type protocols for interfaces
- `chat_app/shared/config.py` - Environment-based configuration
- `chat_app/shared/constants.py` - Protocol constants, defaults
- `chat_app/shared/exceptions.py` - Custom exception hierarchy
- `chat_app/shared/utils.py` - Common utilities

## Naming Standards

- **Modules**: `snake_case` (e.g., `message_handler.py`)
- **Classes**: `PascalCase` (e.g., `ChatServer`, `MessageBroker`)
- **Functions/methods**: `snake_case` with descriptive verbs
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_CLIENTS`, `DEFAULT_PORT`)
- **Test files**: `test_<module_name>.py` in mirrored directory structure

## Import Rules

**Order (with blank lines between groups):**
1. Standard library
2. Third-party (Rich, pytest)
3. Local application (`from chat_app.shared import ...`)

**Patterns:**
- Always use absolute imports: `from chat_app.shared.models import User`
- Import specific items, not modules: `from chat_app.server.security import RateLimiter`
- Place shared dependencies in `chat_app/shared/` to prevent circular imports

## Package Structure

- Every package directory must have `__init__.py`
- Export public APIs in `__init__.py` files
- Use `__all__` to control public interface

## Legacy Integration

- `server.py` and `client.py` remain functional during refactoring
- New features go in modular `chat_app/` structure
- Gradually migrate functionality from legacy files to packages

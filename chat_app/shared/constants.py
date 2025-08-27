"""
Application Constants

Defines constants used throughout the chat application.
"""

# Protocol constants
DISCOVERY_MESSAGE = b"PYTHON_CHAT_SERVER_DISCOVERY_V1"
MESSAGE_DELIMITER = b'\n'
PROTOCOL_SEPARATOR = '|'

# Message types
class MessageType:
    """Message type constants for the chat protocol."""
    CHAT = "MSG"
    SERVER = "SRV"
    USER_LIST = "ULIST"
    COMMAND = "CMD"
    USER_COMMAND = "CMD_USER"

# Default network settings
DEFAULT_SERVER_HOST = "0.0.0.0"
DEFAULT_SERVER_PORT = 8080
DEFAULT_DISCOVERY_PORT = 8081
DEFAULT_CLIENT_HOST = "127.0.0.1"

# Buffer and limit constants
DEFAULT_BUFFER_SIZE = 4096
MAX_MESSAGE_HISTORY = 2000
DEFAULT_MESSAGE_HISTORY = 50
MAX_USERNAME_LENGTH = 50
MAX_MESSAGE_LENGTH = 1000

# Timing constants
DEFAULT_DISCOVERY_TIMEOUT = 3
DEFAULT_BROADCAST_INTERVAL = 5
DEFAULT_UI_REFRESH_RATE = 20
DEFAULT_SOCKET_TIMEOUT = 1.0

# Security constants
DEFAULT_MAX_CLIENTS = 100
DEFAULT_MAX_CONNECTIONS_PER_IP = 5
DEFAULT_RATE_LIMIT_MESSAGES_PER_MINUTE = 60

# UI constants
DEFAULT_PANEL_HEIGHT_OFFSET = 8
CURSOR_CHAR = "_"
SCROLL_INDICATOR_FORMAT = "(scrolled up {} lines)"
NEW_MESSAGES_FORMAT = "({} New Messages)"

# Command constants
QUIT_COMMAND = "/quit"
NICK_COMMAND = "/nick"
HELP_COMMAND = "/help"

# Platform constants
WINDOWS_PLATFORM = "win32"

# Special key codes for Windows
WINDOWS_TAB_KEY = b'\t'
WINDOWS_ENTER_KEY = b'\r'
WINDOWS_BACKSPACE_KEY = b'\x08'
WINDOWS_SPECIAL_KEY_PREFIX = [b'\xe0', b'\x00']
WINDOWS_UP_ARROW = b'H'
WINDOWS_DOWN_ARROW = b'P'

# Log format constants
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
"""
Utility Functions

Common utility functions used throughout the chat application.
"""

import re
import socket
import time
from typing import Optional, Tuple, List
from .constants import MAX_USERNAME_LENGTH, MAX_MESSAGE_LENGTH


def validate_username(username: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a username according to application rules.
    
    Args:
        username: The username to validate.
        
    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is None.
    """
    if not username:
        return False, "Username cannot be empty"
    
    if len(username) > MAX_USERNAME_LENGTH:
        return False, f"Username cannot exceed {MAX_USERNAME_LENGTH} characters"
    
    if len(username.strip()) != len(username):
        return False, "Username cannot start or end with whitespace"
    
    # Allow alphanumeric, underscore, hyphen, and space
    if not re.match(r'^[a-zA-Z0-9_\- ]+$', username):
        return False, "Username can only contain letters, numbers, spaces, underscores, and hyphens"
    
    return True, None


def validate_message(message: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a chat message according to application rules.
    
    Args:
        message: The message to validate.
        
    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is None.
    """
    if not message:
        return False, "Message cannot be empty"
    
    if len(message) > MAX_MESSAGE_LENGTH:
        return False, f"Message cannot exceed {MAX_MESSAGE_LENGTH} characters"
    
    # Check for null bytes or other control characters that could cause issues
    if '\x00' in message or any(ord(c) < 32 and c not in '\t\n\r' for c in message):
        return False, "Message contains invalid control characters"
    
    return True, None


def sanitize_input(text: str) -> str:
    """
    Sanitize user input by removing potentially dangerous characters.
    
    Args:
        text: The text to sanitize.
        
    Returns:
        Sanitized text.
    """
    # Remove null bytes and most control characters, but keep tabs and newlines
    sanitized = ''.join(c for c in text if ord(c) >= 32 or c in '\t\n\r')
    
    # Strip leading/trailing whitespace
    return sanitized.strip()


def format_address(address: Tuple[str, int]) -> str:
    """
    Format an address tuple as a string.
    
    Args:
        address: Tuple of (host, port).
        
    Returns:
        Formatted address string.
    """
    return f"{address[0]}:{address[1]}"


def parse_message_protocol(message: str, separator: str = '|') -> Tuple[str, str]:
    """
    Parse a protocol message into type and payload.
    
    Args:
        message: The message to parse.
        separator: The separator character.
        
    Returns:
        Tuple of (message_type, payload).
    """
    parts = message.split(separator, 1)
    msg_type = parts[0]
    payload = parts[1] if len(parts) > 1 else ""
    return msg_type, payload


def format_message_protocol(msg_type: str, payload: str, separator: str = '|') -> str:
    """
    Format a message according to the protocol.
    
    Args:
        msg_type: The message type.
        payload: The message payload.
        separator: The separator character.
        
    Returns:
        Formatted protocol message.
    """
    return f"{msg_type}{separator}{payload}"


def get_local_ip() -> str:
    """
    Get the local IP address of this machine.
    
    Returns:
        Local IP address as a string.
    """
    try:
        # Connect to a remote address to determine local IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def is_port_available(host: str, port: int) -> bool:
    """
    Check if a port is available for binding.
    
    Args:
        host: The host address.
        port: The port number.
        
    Returns:
        True if port is available, False otherwise.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, port))
            return True
    except OSError:
        return False


def retry_with_backoff(func, max_attempts: int = 3, base_delay: float = 1.0, 
                      backoff_factor: float = 2.0, exceptions: Tuple[type[BaseException], ...] = (Exception,)):
    """
    Retry a function with exponential backoff.
    
    Args:
        func: The function to retry.
        max_attempts: Maximum number of attempts.
        base_delay: Base delay in seconds.
        backoff_factor: Multiplier for delay on each retry.
        exceptions: Tuple of exceptions to catch and retry on.
        
    Returns:
        Result of the function call.
        
    Raises:
        The last exception if all attempts fail.
    """
    last_exception: Optional[BaseException] = None
    
    for attempt in range(max_attempts):
        try:
            return func()
        except BaseException as e:
            last_exception = e
            if attempt < max_attempts - 1:
                delay = base_delay * (backoff_factor ** attempt)
                time.sleep(delay)
    
    if last_exception is not None:
        raise last_exception
    else:
        raise RuntimeError("Function failed without raising an exception")


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate text to a maximum length with an optional suffix.
    
    Args:
        text: The text to truncate.
        max_length: Maximum length including suffix.
        suffix: Suffix to add if text is truncated.
        
    Returns:
        Truncated text.
    """
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def parse_user_list(user_list_str: str) -> List[Tuple[str, str]]:
    """
    Parse a user list string into a list of (username, address) tuples.
    
    Args:
        user_list_str: String in format "user1(addr1),user2(addr2)".
        
    Returns:
        List of (username, address) tuples.
    """
    users: List[Tuple[str, str]] = []
    if not user_list_str:
        return users
    
    for entry in user_list_str.split(','):
        entry = entry.strip()
        if '(' in entry and entry.endswith(')'):
            username, address = entry.rsplit('(', 1)
            address = address[:-1]  # Remove trailing ')'
            users.append((username, address))
    
    return users


def format_user_list(users: List[Tuple[str, str]]) -> str:
    """
    Format a list of users into a protocol string.
    
    Args:
        users: List of (username, address) tuples.
        
    Returns:
        Formatted user list string.
    """
    return ",".join(f"{username}({address})" for username, address in users)
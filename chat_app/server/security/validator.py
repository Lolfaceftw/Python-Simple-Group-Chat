"""
Input Validation Module

Provides comprehensive input validation and sanitization for usernames,
messages, and commands to prevent injection attacks and ensure data integrity.
"""

import re
import html
from dataclasses import dataclass
from typing import List, Optional, Set, Union
from enum import Enum

from chat_app.shared.constants import (
    MAX_USERNAME_LENGTH, 
    MAX_MESSAGE_LENGTH,
    QUIT_COMMAND,
    NICK_COMMAND,
    HELP_COMMAND
)
from chat_app.shared.exceptions import (
    ValidationError,
    UsernameValidationError,
    MessageValidationError
)


class ValidationSeverity(Enum):
    """Severity levels for validation results."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ValidationResult:
    """Result of input validation with details about any issues found."""
    is_valid: bool
    sanitized_value: Optional[str] = None
    errors: List[str] = None
    warnings: List[str] = None
    severity: ValidationSeverity = ValidationSeverity.INFO
    
    def __post_init__(self):
        """Initialize empty lists if None."""
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []
    
    def add_error(self, message: str) -> None:
        """Add an error message and mark as invalid."""
        self.errors.append(message)
        self.is_valid = False
        self.severity = ValidationSeverity.ERROR
    
    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)
        if self.severity == ValidationSeverity.INFO:
            self.severity = ValidationSeverity.WARNING


class InputValidator:
    """
    Comprehensive input validator for chat application data.
    
    Provides validation and sanitization for usernames, messages, and commands
    with protection against common injection attacks and malformed input.
    """
    
    # Character sets for validation
    ALLOWED_USERNAME_CHARS = re.compile(r'^[a-zA-Z0-9_\-\.]+$')
    FORBIDDEN_USERNAME_PATTERNS = [
        re.compile(r'^(admin|server|system|bot|null|undefined)$', re.IGNORECASE),
        re.compile(r'^\d+$'),  # All numeric usernames
        re.compile(r'^[_\-\.]+$'),  # Only special characters
    ]
    
    # Dangerous patterns that could indicate injection attempts
    INJECTION_PATTERNS = [
        re.compile(r'<script[^>]*>', re.IGNORECASE),
        re.compile(r'javascript:', re.IGNORECASE),
        re.compile(r'on\w+\s*=', re.IGNORECASE),
        re.compile(r'\\x[0-9a-fA-F]{2}'),  # Hex encoded characters
        re.compile(r'\\u[0-9a-fA-F]{4}'),  # Unicode escape sequences
        re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]'),  # Control characters
    ]
    
    # Valid chat commands
    VALID_COMMANDS: Set[str] = {QUIT_COMMAND, NICK_COMMAND, HELP_COMMAND}
    
    def __init__(self, 
                 max_username_length: int = MAX_USERNAME_LENGTH,
                 max_message_length: int = MAX_MESSAGE_LENGTH,
                 strict_mode: bool = True):
        """
        Initialize the input validator.
        
        Args:
            max_username_length: Maximum allowed username length
            max_message_length: Maximum allowed message length
            strict_mode: Enable strict validation rules
        """
        self.max_username_length = max_username_length
        self.max_message_length = max_message_length
        self.strict_mode = strict_mode
    
    def validate_username(self, username: str) -> ValidationResult:
        """
        Validate and sanitize a username.
        
        Args:
            username: The username to validate
            
        Returns:
            ValidationResult with validation status and sanitized username
            
        Raises:
            UsernameValidationError: If validation fails in strict mode
        """
        result = ValidationResult(is_valid=True)
        
        if not username:
            result.add_error("Username cannot be empty")
            if self.strict_mode:
                raise UsernameValidationError("Username cannot be empty")
            return result
        
        # Check length
        if len(username) > self.max_username_length:
            result.add_error(f"Username too long (max {self.max_username_length} characters)")
            if self.strict_mode:
                raise UsernameValidationError(
                    f"Username too long (max {self.max_username_length} characters)"
                )
        
        # Check for minimum length
        if len(username) < 2:
            result.add_error("Username must be at least 2 characters long")
        
        # Sanitize by removing dangerous characters
        sanitized = self._sanitize_string(username)
        
        # Check character set
        if not self.ALLOWED_USERNAME_CHARS.match(sanitized):
            result.add_error(
                "Username contains invalid characters. Only letters, numbers, "
                "hyphens, underscores, and dots are allowed"
            )
        
        # Check forbidden patterns
        for pattern in self.FORBIDDEN_USERNAME_PATTERNS:
            if pattern.match(sanitized):
                result.add_error("Username uses a reserved or invalid pattern")
                break
        
        # Check for injection attempts
        if self._contains_injection_patterns(username):
            result.add_error("Username contains potentially dangerous content")
        
        # Check for leading/trailing whitespace or special chars
        if sanitized != sanitized.strip():
            result.add_warning("Username has leading or trailing whitespace")
            sanitized = sanitized.strip()
        
        if sanitized.startswith('.'):
            result.add_warning("Username should not start with dots")
        if sanitized.endswith('.'):
            result.add_warning("Username should not end with dots")
        
        result.sanitized_value = sanitized
        
        if not result.is_valid and self.strict_mode:
            raise UsernameValidationError("; ".join(result.errors))
        
        return result
    
    def validate_message(self, message: str) -> ValidationResult:
        """
        Validate and sanitize a chat message.
        
        Args:
            message: The message to validate
            
        Returns:
            ValidationResult with validation status and sanitized message
            
        Raises:
            MessageValidationError: If validation fails in strict mode
        """
        result = ValidationResult(is_valid=True)
        
        if not message:
            result.add_error("Message cannot be empty")
            if self.strict_mode:
                raise MessageValidationError("Message cannot be empty")
            return result
        
        # Check length
        if len(message) > self.max_message_length:
            result.add_error(f"Message too long (max {self.max_message_length} characters)")
            if self.strict_mode:
                raise MessageValidationError(
                    f"Message too long (max {self.max_message_length} characters)"
                )
        
        # Sanitize the message
        sanitized = self._sanitize_string(message)
        
        # Check for injection attempts
        if self._contains_injection_patterns(message):
            result.add_error("Message contains potentially dangerous content")
        
        # Check for excessive whitespace
        if len(sanitized.strip()) == 0:
            result.add_error("Message cannot be only whitespace")
        
        # Normalize whitespace
        sanitized = re.sub(r'\s+', ' ', sanitized.strip())
        
        # Check for protocol separator injection
        if '|' in sanitized:
            result.add_warning("Message contains protocol separator character")
            # Don't remove it, but warn about it
        
        result.sanitized_value = sanitized
        
        if not result.is_valid and self.strict_mode:
            raise MessageValidationError("; ".join(result.errors))
        
        return result
    
    def validate_command(self, command: str) -> ValidationResult:
        """
        Validate a chat command.
        
        Args:
            command: The command to validate (including the / prefix)
            
        Returns:
            ValidationResult with validation status and parsed command
        """
        result = ValidationResult(is_valid=True)
        
        if not command:
            result.add_error("Command cannot be empty")
            return result
        
        # Commands should start with /
        if not command.startswith('/'):
            result.add_error("Commands must start with '/'")
            return result
        
        # Split command and arguments
        parts = command.split(' ', 1)
        cmd_name = parts[0].lower()
        cmd_args = parts[1] if len(parts) > 1 else ""
        
        # Check if it's a valid command
        if cmd_name not in self.VALID_COMMANDS:
            result.add_error(f"Unknown command: {cmd_name}")
        
        # Validate command arguments based on command type
        if cmd_name == NICK_COMMAND:
            if not cmd_args:
                result.add_error("Nick command requires a username argument")
            else:
                # Validate the new username
                username_result = self.validate_username(cmd_args)
                if not username_result.is_valid:
                    result.add_error(f"Invalid username: {'; '.join(username_result.errors)}")
                else:
                    result.sanitized_value = f"{cmd_name} {username_result.sanitized_value}"
        elif cmd_name in [QUIT_COMMAND, HELP_COMMAND]:
            # These commands don't take arguments
            if cmd_args:
                result.add_warning(f"{cmd_name} command ignores arguments")
            result.sanitized_value = cmd_name
        
        if result.sanitized_value is None:
            result.sanitized_value = command
        
        return result
    
    def _sanitize_string(self, text: str) -> str:
        """
        Sanitize a string by removing or escaping dangerous content.
        
        Args:
            text: The text to sanitize
            
        Returns:
            Sanitized text
        """
        if not text:
            return text
        
        # HTML escape to prevent HTML/XML injection
        sanitized = html.escape(text, quote=False)
        
        # Remove null bytes and other control characters
        sanitized = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', sanitized)
        
        # Remove or replace potentially dangerous Unicode characters
        # Remove zero-width characters that could be used for obfuscation
        sanitized = re.sub(r'[\u200B-\u200D\uFEFF]', '', sanitized)
        
        return sanitized
    
    def _contains_injection_patterns(self, text: str) -> bool:
        """
        Check if text contains patterns that might indicate injection attempts.
        
        Args:
            text: The text to check
            
        Returns:
            True if potentially dangerous patterns are found
        """
        for pattern in self.INJECTION_PATTERNS:
            if pattern.search(text):
                return True
        return False
    
    def validate_ip_address(self, ip_address: str) -> ValidationResult:
        """
        Validate an IP address format.
        
        Args:
            ip_address: The IP address to validate
            
        Returns:
            ValidationResult with validation status
        """
        result = ValidationResult(is_valid=True)
        
        if not ip_address:
            result.add_error("IP address cannot be empty")
            return result
        
        # Basic IPv4 validation
        ipv4_pattern = re.compile(
            r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
            r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        )
        
        if not ipv4_pattern.match(ip_address):
            result.add_error("Invalid IPv4 address format")
        
        result.sanitized_value = ip_address
        return result
    
    def validate_port(self, port: Union[str, int]) -> ValidationResult:
        """
        Validate a network port number.
        
        Args:
            port: The port number to validate
            
        Returns:
            ValidationResult with validation status
        """
        result = ValidationResult(is_valid=True)
        
        try:
            port_num = int(port)
        except (ValueError, TypeError):
            result.add_error("Port must be a valid integer")
            return result
        
        if port_num < 1 or port_num > 65535:
            result.add_error("Port must be between 1 and 65535")
        
        if port_num < 1024:
            result.add_warning("Port number is in the reserved range (< 1024)")
        
        result.sanitized_value = str(port_num)
        return result


# Convenience functions for common validation tasks
def validate_username(username: str, strict: bool = False) -> ValidationResult:
    """Convenience function to validate a username."""
    validator = InputValidator(strict_mode=strict)
    return validator.validate_username(username)


def validate_message(message: str, strict: bool = False) -> ValidationResult:
    """Convenience function to validate a message."""
    validator = InputValidator(strict_mode=strict)
    return validator.validate_message(message)


def validate_command(command: str) -> ValidationResult:
    """Convenience function to validate a command."""
    validator = InputValidator(strict_mode=False)
    return validator.validate_command(command)


def sanitize_input(text: str) -> str:
    """Convenience function to sanitize input text."""
    validator = InputValidator()
    return validator._sanitize_string(text)
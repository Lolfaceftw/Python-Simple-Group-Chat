"""
Unit tests for input validation module.

Tests all validation scenarios including edge cases, injection attempts,
and proper sanitization of usernames, messages, and commands.
"""

import pytest
from unittest.mock import patch

from chat_app.server.security.validator import (
    InputValidator,
    ValidationResult,
    ValidationSeverity,
    validate_username,
    validate_message,
    validate_command,
    sanitize_input
)
from chat_app.shared.exceptions import (
    UsernameValidationError,
    MessageValidationError
)


class TestValidationResult:
    """Test ValidationResult class functionality."""
    
    def test_initialization_with_defaults(self):
        """Test ValidationResult initialization with default values."""
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.sanitized_value is None
        assert result.errors == []
        assert result.warnings == []
        assert result.severity == ValidationSeverity.INFO
    
    def test_add_error(self):
        """Test adding error messages."""
        result = ValidationResult(is_valid=True)
        result.add_error("Test error")
        
        assert result.is_valid is False
        assert "Test error" in result.errors
        assert result.severity == ValidationSeverity.ERROR
    
    def test_add_warning(self):
        """Test adding warning messages."""
        result = ValidationResult(is_valid=True)
        result.add_warning("Test warning")
        
        assert result.is_valid is True
        assert "Test warning" in result.warnings
        assert result.severity == ValidationSeverity.WARNING


class TestInputValidator:
    """Test InputValidator class functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = InputValidator()
        self.strict_validator = InputValidator(strict_mode=True)
        self.lenient_validator = InputValidator(strict_mode=False)
    
    def test_initialization(self):
        """Test validator initialization with custom parameters."""
        validator = InputValidator(
            max_username_length=20,
            max_message_length=500,
            strict_mode=False
        )
        
        assert validator.max_username_length == 20
        assert validator.max_message_length == 500
        assert validator.strict_mode is False


class TestUsernameValidation:
    """Test username validation functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = InputValidator(strict_mode=False)
        self.strict_validator = InputValidator(strict_mode=True)
    
    def test_valid_usernames(self):
        """Test validation of valid usernames."""
        valid_usernames = [
            "alice",
            "bob123",
            "user_name",
            "test-user",
            "user.name",
            "Alice_Bob-123",
            "a1",  # minimum length
        ]
        
        for username in valid_usernames:
            result = self.validator.validate_username(username)
            assert result.is_valid, f"Username '{username}' should be valid"
            assert result.sanitized_value == username
    
    def test_empty_username(self):
        """Test validation of empty username."""
        result = self.validator.validate_username("")
        assert not result.is_valid
        assert "cannot be empty" in result.errors[0]
        
        # Test strict mode raises exception
        with pytest.raises(UsernameValidationError):
            self.strict_validator.validate_username("")
    
    def test_username_too_long(self):
        """Test validation of overly long usernames."""
        long_username = "a" * 51  # Exceeds default max length of 50
        result = self.validator.validate_username(long_username)
        
        assert not result.is_valid
        assert "too long" in result.errors[0]
        
        with pytest.raises(UsernameValidationError):
            self.strict_validator.validate_username(long_username)
    
    def test_username_too_short(self):
        """Test validation of too short usernames."""
        result = self.validator.validate_username("a")
        assert not result.is_valid
        assert "at least 2 characters" in result.errors[0]
    
    def test_invalid_characters(self):
        """Test usernames with invalid characters."""
        invalid_usernames = [
            "user@name",
            "user name",  # space
            "user#name",
            "user$name",
            "user%name",
            "user&name",
            "user*name",
            "user+name",
            "user=name",
            "user?name",
            "user[name]",
            "user{name}",
            "user|name",
            "user\\name",
            "user/name",
            "user<name>",
            "user\"name",
            "user'name",
        ]
        
        for username in invalid_usernames:
            result = self.validator.validate_username(username)
            assert not result.is_valid, f"Username '{username}' should be invalid"
            assert "invalid characters" in result.errors[0]
    
    def test_forbidden_patterns(self):
        """Test usernames matching forbidden patterns."""
        forbidden_usernames = [
            "admin",
            "ADMIN",
            "Admin",
            "server",
            "SERVER",
            "system",
            "bot",
            "null",
            "undefined",
            "123456",  # all numeric
            "___",     # only special chars
            "---",
            "...",
        ]
        
        for username in forbidden_usernames:
            result = self.validator.validate_username(username)
            assert not result.is_valid, f"Username '{username}' should be forbidden"
    
    def test_injection_patterns(self):
        """Test usernames with potential injection patterns."""
        injection_usernames = [
            "<script>alert('xss')</script>",
            "javascript:alert(1)",
            "onclick=alert(1)",
            "user\\x41",  # hex encoded
            "user\\u0041",  # unicode escape
            "user\x00name",  # null byte
            "user\x01name",  # control character
        ]
        
        for username in injection_usernames:
            result = self.validator.validate_username(username)
            assert not result.is_valid, f"Username '{username}' should be rejected for injection"
    
    def test_whitespace_handling(self):
        """Test handling of usernames with whitespace."""
        result = self.validator.validate_username("  username  ")
        # Should have warnings about whitespace but still be valid after sanitization
        assert "whitespace" in result.warnings[0]
        assert result.sanitized_value == "username"
    
    def test_dot_edge_cases(self):
        """Test usernames starting or ending with dots."""
        result = self.validator.validate_username(".username")
        assert any("should not start" in warning for warning in result.warnings)
        
        result = self.validator.validate_username("username.")
        assert any("should not end" in warning for warning in result.warnings)


class TestMessageValidation:
    """Test message validation functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = InputValidator(strict_mode=False)
        self.strict_validator = InputValidator(strict_mode=True)
    
    def test_valid_messages(self):
        """Test validation of valid messages."""
        valid_messages = [
            "Hello, world!",
            "This is a test message.",
            "Message with numbers 123 and symbols !@#",
            "Multi-line\nmessage",
            "Message with émojis 😀🎉",
            "a" * 999,  # Just under max length
        ]
        
        for message in valid_messages:
            result = self.validator.validate_message(message)
            assert result.is_valid, f"Message '{message[:50]}...' should be valid"
    
    def test_empty_message(self):
        """Test validation of empty message."""
        result = self.validator.validate_message("")
        assert not result.is_valid
        assert "cannot be empty" in result.errors[0]
        
        with pytest.raises(MessageValidationError):
            self.strict_validator.validate_message("")
    
    def test_message_too_long(self):
        """Test validation of overly long messages."""
        long_message = "a" * 1001  # Exceeds default max length of 1000
        result = self.validator.validate_message(long_message)
        
        assert not result.is_valid
        assert "too long" in result.errors[0]
        
        with pytest.raises(MessageValidationError):
            self.strict_validator.validate_message(long_message)
    
    def test_whitespace_only_message(self):
        """Test messages that are only whitespace."""
        whitespace_messages = [
            "   ",
            "\t\t\t",
            "\n\n\n",
            "   \t  \n  ",
        ]
        
        for message in whitespace_messages:
            result = self.validator.validate_message(message)
            assert not result.is_valid
            assert "only whitespace" in result.errors[0]
    
    def test_injection_patterns_in_messages(self):
        """Test messages with potential injection patterns."""
        injection_messages = [
            "<script>alert('xss')</script>",
            "javascript:alert(1)",
            "onclick=alert(1)",
            "Message with \\x41 hex",
            "Message with \\u0041 unicode",
            "Message with \x00 null byte",
            "Message with \x01 control char",
        ]
        
        for message in injection_messages:
            result = self.validator.validate_message(message)
            assert not result.is_valid, f"Message with injection should be rejected"
            assert "dangerous content" in result.errors[0]
    
    def test_protocol_separator_warning(self):
        """Test messages containing protocol separator character."""
        result = self.validator.validate_message("Message with | separator")
        assert result.is_valid  # Should still be valid
        assert any("protocol separator" in warning for warning in result.warnings)
    
    def test_whitespace_normalization(self):
        """Test normalization of excessive whitespace."""
        result = self.validator.validate_message("  Multiple    spaces   between   words  ")
        assert result.is_valid
        assert result.sanitized_value == "Multiple spaces between words"


class TestCommandValidation:
    """Test command validation functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = InputValidator(strict_mode=False)
    
    def test_valid_commands(self):
        """Test validation of valid commands."""
        valid_commands = [
            "/quit",
            "/help",
            "/nick alice",
            "/nick bob123",
            "/QUIT",  # Case insensitive
            "/HELP",
            "/NICK Alice",
        ]
        
        for command in valid_commands:
            result = self.validator.validate_command(command)
            assert result.is_valid, f"Command '{command}' should be valid"
    
    def test_empty_command(self):
        """Test validation of empty command."""
        result = self.validator.validate_command("")
        assert not result.is_valid
        assert "cannot be empty" in result.errors[0]
    
    def test_command_without_slash(self):
        """Test commands that don't start with slash."""
        result = self.validator.validate_command("quit")
        assert not result.is_valid
        assert "must start with '/'" in result.errors[0]
    
    def test_unknown_command(self):
        """Test unknown commands."""
        result = self.validator.validate_command("/unknown")
        assert not result.is_valid
        assert "Unknown command" in result.errors[0]
    
    def test_nick_command_validation(self):
        """Test nick command with various arguments."""
        # Valid nick command
        result = self.validator.validate_command("/nick alice")
        assert result.is_valid
        assert result.sanitized_value == "/nick alice"
        
        # Nick without argument
        result = self.validator.validate_command("/nick")
        assert not result.is_valid
        assert "requires a username argument" in result.errors[0]
        
        # Nick with invalid username
        result = self.validator.validate_command("/nick invalid@user")
        assert not result.is_valid
        assert "Invalid username" in result.errors[0]
    
    def test_commands_with_ignored_arguments(self):
        """Test commands that ignore arguments."""
        result = self.validator.validate_command("/quit now")
        assert result.is_valid
        assert "ignores arguments" in result.warnings[0]
        assert result.sanitized_value == "/quit"
        
        result = self.validator.validate_command("/help me")
        assert result.is_valid
        assert "ignores arguments" in result.warnings[0]
        assert result.sanitized_value == "/help"


class TestIPAddressValidation:
    """Test IP address validation functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = InputValidator(strict_mode=False)
    
    def test_valid_ip_addresses(self):
        """Test validation of valid IP addresses."""
        valid_ips = [
            "127.0.0.1",
            "192.168.1.1",
            "10.0.0.1",
            "255.255.255.255",
            "0.0.0.0",
        ]
        
        for ip in valid_ips:
            result = self.validator.validate_ip_address(ip)
            assert result.is_valid, f"IP '{ip}' should be valid"
            assert result.sanitized_value == ip
    
    def test_invalid_ip_addresses(self):
        """Test validation of invalid IP addresses."""
        invalid_ips = [
            "",
            "256.1.1.1",
            "1.1.1",
            "1.1.1.1.1",
            "abc.def.ghi.jkl",
            "192.168.1",
            "192.168.1.256",
            "not.an.ip.address",
        ]
        
        for ip in invalid_ips:
            result = self.validator.validate_ip_address(ip)
            assert not result.is_valid, f"IP '{ip}' should be invalid"


class TestPortValidation:
    """Test port number validation functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = InputValidator(strict_mode=False)
    
    def test_valid_ports(self):
        """Test validation of valid port numbers."""
        valid_ports = [1, 80, 443, 8080, 65535, "1234", "8080"]
        
        for port in valid_ports:
            result = self.validator.validate_port(port)
            assert result.is_valid, f"Port '{port}' should be valid"
            assert result.sanitized_value == str(port)
    
    def test_invalid_ports(self):
        """Test validation of invalid port numbers."""
        invalid_ports = [0, -1, 65536, 100000, "abc", "", None, "8080.5"]
        
        for port in invalid_ports:
            result = self.validator.validate_port(port)
            assert not result.is_valid, f"Port '{port}' should be invalid"
    
    def test_reserved_port_warning(self):
        """Test warning for reserved ports."""
        result = self.validator.validate_port(80)
        assert result.is_valid
        assert any("reserved range" in warning for warning in result.warnings)


class TestSanitization:
    """Test string sanitization functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = InputValidator(strict_mode=False)
    
    def test_html_escaping(self):
        """Test HTML character escaping."""
        text = "<script>alert('test')</script>"
        sanitized = self.validator._sanitize_string(text)
        assert "&lt;" in sanitized
        assert "&gt;" in sanitized
        assert "<script>" not in sanitized
    
    def test_control_character_removal(self):
        """Test removal of control characters."""
        text = "test\x00\x01\x02string"
        sanitized = self.validator._sanitize_string(text)
        assert sanitized == "teststring"
    
    def test_zero_width_character_removal(self):
        """Test removal of zero-width characters."""
        text = "test\u200Bstring\u200C"
        sanitized = self.validator._sanitize_string(text)
        assert sanitized == "teststring"
    
    def test_injection_pattern_detection(self):
        """Test detection of injection patterns."""
        injection_texts = [
            "<script>alert(1)</script>",
            "javascript:void(0)",
            "onclick=alert(1)",
            "\\x41\\x42",
            "\\u0041\\u0042",
            "\x00\x01\x02",
        ]
        
        for text in injection_texts:
            assert self.validator._contains_injection_patterns(text)
        
        # Safe text should not trigger detection
        safe_texts = [
            "Hello, world!",
            "This is a normal message",
            "Numbers 123 and symbols !@#",
        ]
        
        for text in safe_texts:
            assert not self.validator._contains_injection_patterns(text)


class TestConvenienceFunctions:
    """Test convenience functions for validation."""
    
    def test_validate_username_function(self):
        """Test standalone username validation function."""
        result = validate_username("alice")
        assert result.is_valid
        
        result = validate_username("invalid@user")
        assert not result.is_valid
    
    def test_validate_message_function(self):
        """Test standalone message validation function."""
        result = validate_message("Hello, world!")
        assert result.is_valid
        
        result = validate_message("")
        assert not result.is_valid
    
    def test_validate_command_function(self):
        """Test standalone command validation function."""
        result = validate_command("/quit")
        assert result.is_valid
        
        result = validate_command("quit")
        assert not result.is_valid
    
    def test_sanitize_input_function(self):
        """Test standalone sanitization function."""
        sanitized = sanitize_input("<script>alert('test')</script>")
        assert "&lt;" in sanitized
        assert "<script>" not in sanitized


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = InputValidator(strict_mode=False)
    
    def test_unicode_handling(self):
        """Test handling of Unicode characters."""
        unicode_texts = [
            "café",
            "naïve",
            "résumé",
            "🎉🎊😀",
            "中文测试",
            "العربية",
            "русский",
        ]
        
        for text in unicode_texts:
            # Should handle Unicode gracefully
            result = self.validator.validate_message(text)
            # Unicode should be preserved in sanitized output
            assert text in result.sanitized_value or result.sanitized_value == text
    
    def test_boundary_lengths(self):
        """Test boundary conditions for length validation."""
        # Test exactly at max length
        max_username = "a" * 50
        result = self.validator.validate_username(max_username)
        assert result.is_valid
        
        max_message = "a" * 1000
        result = self.validator.validate_message(max_message)
        assert result.is_valid
        
        # Test one character over max length
        over_username = "a" * 51
        result = self.validator.validate_username(over_username)
        assert not result.is_valid
        
        over_message = "a" * 1001
        result = self.validator.validate_message(over_message)
        assert not result.is_valid
    
    def test_none_input_handling(self):
        """Test handling of None inputs."""
        # Should handle None gracefully without crashing
        result = self.validator._sanitize_string(None)
        assert result is None
    
    def test_mixed_case_commands(self):
        """Test case insensitive command handling."""
        commands = ["/QUIT", "/Quit", "/quit", "/NICK", "/Nick", "/nick"]
        
        for cmd in commands:
            if cmd.lower().startswith("/quit") or cmd.lower().startswith("/nick"):
                result = self.validator.validate_command(cmd)
                # Commands should be case insensitive
                assert result.is_valid or "requires a username" in str(result.errors)


# Integration tests for validator combinations
class TestValidatorIntegration:
    """Test integration scenarios with multiple validation types."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.validator = InputValidator(strict_mode=False)
    
    def test_complete_user_registration_flow(self):
        """Test complete user registration validation flow."""
        # Simulate user registration with username validation
        username = "alice_123"
        username_result = self.validator.validate_username(username)
        assert username_result.is_valid
        
        # Simulate first message validation
        message = "Hello everyone!"
        message_result = self.validator.validate_message(message)
        assert message_result.is_valid
        
        # Simulate command validation
        command = "/nick alice_new"
        command_result = self.validator.validate_command(command)
        assert command_result.is_valid
    
    def test_security_attack_simulation(self):
        """Test validation against simulated security attacks."""
        # Simulate various attack vectors
        attack_vectors = [
            ("username", "<script>alert('xss')</script>"),
            ("message", "javascript:alert(document.cookie)"),
            ("command", "/nick <img src=x onerror=alert(1)>"),
        ]
        
        for input_type, attack_input in attack_vectors:
            if input_type == "username":
                result = self.validator.validate_username(attack_input)
            elif input_type == "message":
                result = self.validator.validate_message(attack_input)
            elif input_type == "command":
                result = self.validator.validate_command(attack_input)
            
            # All attack vectors should be rejected
            assert not result.is_valid, f"Attack vector '{attack_input}' should be rejected"
"""
Unit tests for chat_app.shared.utils module.
"""

import pytest
from unittest.mock import patch, Mock
import socket

from chat_app.shared.utils import (
    validate_username,
    validate_message,
    sanitize_input,
    format_address,
    parse_message_protocol,
    format_message_protocol,
    get_local_ip,
    is_port_available,
    retry_with_backoff,
    truncate_text,
    parse_user_list,
    format_user_list
)


class TestValidateUsername:
    """Test validate_username function."""
    
    def test_valid_username(self):
        """Test valid username validation."""
        is_valid, error = validate_username("testuser")
        
        assert is_valid is True
        assert error is None
    
    def test_valid_username_with_spaces(self):
        """Test valid username with spaces."""
        is_valid, error = validate_username("test user")
        
        assert is_valid is True
        assert error is None
    
    def test_valid_username_with_underscore(self):
        """Test valid username with underscore."""
        is_valid, error = validate_username("test_user")
        
        assert is_valid is True
        assert error is None
    
    def test_valid_username_with_hyphen(self):
        """Test valid username with hyphen."""
        is_valid, error = validate_username("test-user")
        
        assert is_valid is True
        assert error is None
    
    def test_empty_username_invalid(self):
        """Test that empty username is invalid."""
        is_valid, error = validate_username("")
        
        assert is_valid is False
        assert "cannot be empty" in error
    
    def test_username_too_long_invalid(self):
        """Test that username exceeding max length is invalid."""
        long_username = "a" * 51  # Exceeds MAX_USERNAME_LENGTH (50)
        is_valid, error = validate_username(long_username)
        
        assert is_valid is False
        assert "cannot exceed" in error
    
    def test_username_with_leading_whitespace_invalid(self):
        """Test that username with leading whitespace is invalid."""
        is_valid, error = validate_username(" testuser")
        
        assert is_valid is False
        assert "cannot start or end with whitespace" in error
    
    def test_username_with_trailing_whitespace_invalid(self):
        """Test that username with trailing whitespace is invalid."""
        is_valid, error = validate_username("testuser ")
        
        assert is_valid is False
        assert "cannot start or end with whitespace" in error
    
    def test_username_with_invalid_characters(self):
        """Test that username with invalid characters is invalid."""
        is_valid, error = validate_username("test@user")
        
        assert is_valid is False
        assert "can only contain" in error


class TestValidateMessage:
    """Test validate_message function."""
    
    def test_valid_message(self):
        """Test valid message validation."""
        is_valid, error = validate_message("Hello, world!")
        
        assert is_valid is True
        assert error is None
    
    def test_empty_message_invalid(self):
        """Test that empty message is invalid."""
        is_valid, error = validate_message("")
        
        assert is_valid is False
        assert "cannot be empty" in error
    
    def test_message_too_long_invalid(self):
        """Test that message exceeding max length is invalid."""
        long_message = "a" * 1001  # Exceeds MAX_MESSAGE_LENGTH (1000)
        is_valid, error = validate_message(long_message)
        
        assert is_valid is False
        assert "cannot exceed" in error
    
    def test_message_with_null_byte_invalid(self):
        """Test that message with null byte is invalid."""
        is_valid, error = validate_message("Hello\x00World")
        
        assert is_valid is False
        assert "invalid control characters" in error
    
    def test_message_with_control_characters_invalid(self):
        """Test that message with control characters is invalid."""
        is_valid, error = validate_message("Hello\x01World")
        
        assert is_valid is False
        assert "invalid control characters" in error
    
    def test_message_with_allowed_whitespace_valid(self):
        """Test that message with allowed whitespace is valid."""
        is_valid, error = validate_message("Hello\tWorld\nTest\r")
        
        assert is_valid is True
        assert error is None


class TestSanitizeInput:
    """Test sanitize_input function."""
    
    def test_sanitize_normal_string(self):
        """Test sanitizing normal string."""
        result = sanitize_input("Hello World")
        
        assert result == "Hello World"
    
    def test_sanitize_removes_control_characters(self):
        """Test that control characters are removed."""
        result = sanitize_input("Hello\x00\x01World")
        
        assert result == "HelloWorld"
    
    def test_sanitize_preserves_allowed_whitespace(self):
        """Test that allowed whitespace is preserved."""
        result = sanitize_input("Hello\tWorld\nTest")
        
        assert result == "Hello\tWorld\nTest"
    
    def test_sanitize_strips_leading_trailing_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        result = sanitize_input("  Hello World  ")
        
        assert result == "Hello World"
    
    def test_sanitize_empty_string(self):
        """Test sanitizing empty string."""
        result = sanitize_input("")
        
        assert result == ""


class TestFormatAddress:
    """Test format_address function."""
    
    def test_format_ipv4_address(self):
        """Test formatting IPv4 address."""
        result = format_address(("127.0.0.1", 8080))
        
        assert result == "127.0.0.1:8080"
    
    def test_format_ipv6_address(self):
        """Test formatting IPv6 address."""
        result = format_address(("::1", 8080))
        
        assert result == "::1:8080"
    
    def test_format_hostname_address(self):
        """Test formatting hostname address."""
        result = format_address(("localhost", 9000))
        
        assert result == "localhost:9000"


class TestParseMessageProtocol:
    """Test parse_message_protocol function."""
    
    def test_parse_message_with_payload(self):
        """Test parsing message with payload."""
        msg_type, payload = parse_message_protocol("MSG|Hello World")
        
        assert msg_type == "MSG"
        assert payload == "Hello World"
    
    def test_parse_message_without_payload(self):
        """Test parsing message without payload."""
        msg_type, payload = parse_message_protocol("SRV")
        
        assert msg_type == "SRV"
        assert payload == ""
    
    def test_parse_message_with_custom_separator(self):
        """Test parsing message with custom separator."""
        msg_type, payload = parse_message_protocol("MSG:Hello World", separator=":")
        
        assert msg_type == "MSG"
        assert payload == "Hello World"
    
    def test_parse_message_with_multiple_separators(self):
        """Test parsing message with multiple separators in payload."""
        msg_type, payload = parse_message_protocol("MSG|Hello|World|Test")
        
        assert msg_type == "MSG"
        assert payload == "Hello|World|Test"


class TestFormatMessageProtocol:
    """Test format_message_protocol function."""
    
    def test_format_message_with_payload(self):
        """Test formatting message with payload."""
        result = format_message_protocol("MSG", "Hello World")
        
        assert result == "MSG|Hello World"
    
    def test_format_message_without_payload(self):
        """Test formatting message without payload."""
        result = format_message_protocol("SRV", "")
        
        assert result == "SRV|"
    
    def test_format_message_with_custom_separator(self):
        """Test formatting message with custom separator."""
        result = format_message_protocol("MSG", "Hello World", separator=":")
        
        assert result == "MSG:Hello World"


class TestGetLocalIp:
    """Test get_local_ip function."""
    
    @patch('socket.socket')
    def test_get_local_ip_success(self, mock_socket_class):
        """Test successful local IP retrieval."""
        mock_socket = Mock()
        mock_socket.getsockname.return_value = ("192.168.1.100", 12345)
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        
        ip = get_local_ip()
        
        assert ip == "192.168.1.100"
    
    @patch('socket.socket')
    def test_get_local_ip_failure_returns_localhost(self, mock_socket_class):
        """Test that failure returns localhost."""
        mock_socket_class.side_effect = Exception("Network error")
        
        ip = get_local_ip()
        
        assert ip == "127.0.0.1"


class TestIsPortAvailable:
    """Test is_port_available function."""
    
    @patch('socket.socket')
    def test_port_available(self, mock_socket_class):
        """Test that available port returns True."""
        mock_socket = Mock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        
        result = is_port_available("127.0.0.1", 8080)
        
        assert result is True
        mock_socket.bind.assert_called_once_with(("127.0.0.1", 8080))
    
    @patch('socket.socket')
    def test_port_unavailable(self, mock_socket_class):
        """Test that unavailable port returns False."""
        mock_socket = Mock()
        mock_socket.bind.side_effect = OSError("Address already in use")
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        
        result = is_port_available("127.0.0.1", 8080)
        
        assert result is False


class TestRetryWithBackoff:
    """Test retry_with_backoff function."""
    
    def test_successful_operation_no_retry(self):
        """Test that successful operation doesn't retry."""
        mock_operation = Mock(return_value="success")
        
        result = retry_with_backoff(mock_operation, max_attempts=3)
        
        assert result == "success"
        assert mock_operation.call_count == 1
    
    def test_operation_succeeds_after_retries(self):
        """Test operation that succeeds after some failures."""
        mock_operation = Mock(side_effect=[Exception("fail"), Exception("fail"), "success"])
        
        result = retry_with_backoff(mock_operation, max_attempts=3)
        
        assert result == "success"
        assert mock_operation.call_count == 3
    
    def test_operation_fails_all_attempts(self):
        """Test operation that fails all attempts."""
        mock_operation = Mock(side_effect=Exception("always fails"))
        
        with pytest.raises(Exception, match="always fails"):
            retry_with_backoff(mock_operation, max_attempts=2)
        
        assert mock_operation.call_count == 2
    
    @patch('time.sleep')
    def test_retry_with_backoff_delay(self, mock_sleep):
        """Test retry operation with backoff delay."""
        mock_operation = Mock(side_effect=[Exception("fail"), "success"])
        
        result = retry_with_backoff(mock_operation, max_attempts=2, base_delay=1.0)
        
        assert result == "success"
        mock_sleep.assert_called_once_with(1.0)


class TestTruncateText:
    """Test truncate_text function."""
    
    def test_truncate_long_text(self):
        """Test truncating text longer than max length."""
        result = truncate_text("Hello World", max_length=5)
        
        assert result == "He..."
        assert len(result) == 5
    
    def test_truncate_short_text_unchanged(self):
        """Test that short text remains unchanged."""
        result = truncate_text("Hi", max_length=10)
        
        assert result == "Hi"
    
    def test_truncate_exact_length_unchanged(self):
        """Test that text of exact length remains unchanged."""
        result = truncate_text("Hello", max_length=5)
        
        assert result == "Hello"
    
    def test_truncate_with_custom_suffix(self):
        """Test truncating with custom suffix."""
        result = truncate_text("Hello World", max_length=8, suffix=">>")
        
        assert result == "Hello >>"
        assert len(result) == 8
    
    def test_truncate_empty_text(self):
        """Test truncating empty text."""
        result = truncate_text("", max_length=5)
        
        assert result == ""


class TestParseUserList:
    """Test parse_user_list function."""
    
    def test_parse_single_user(self):
        """Test parsing single user."""
        result = parse_user_list("user1(127.0.0.1:8080)")
        
        assert result == [("user1", "127.0.0.1:8080")]
    
    def test_parse_multiple_users(self):
        """Test parsing multiple users."""
        result = parse_user_list("user1(127.0.0.1:8080),user2(192.168.1.1:8080)")
        
        expected = [
            ("user1", "127.0.0.1:8080"),
            ("user2", "192.168.1.1:8080")
        ]
        assert result == expected
    
    def test_parse_empty_string(self):
        """Test parsing empty string."""
        result = parse_user_list("")
        
        assert result == []
    
    def test_parse_malformed_entry_ignored(self):
        """Test that malformed entries are ignored."""
        result = parse_user_list("user1(127.0.0.1:8080),malformed,user2(192.168.1.1:8080)")
        
        expected = [
            ("user1", "127.0.0.1:8080"),
            ("user2", "192.168.1.1:8080")
        ]
        assert result == expected


class TestFormatUserList:
    """Test format_user_list function."""
    
    def test_format_single_user(self):
        """Test formatting single user."""
        users = [("user1", "127.0.0.1:8080")]
        result = format_user_list(users)
        
        assert result == "user1(127.0.0.1:8080)"
    
    def test_format_multiple_users(self):
        """Test formatting multiple users."""
        users = [
            ("user1", "127.0.0.1:8080"),
            ("user2", "192.168.1.1:8080")
        ]
        result = format_user_list(users)
        
        assert result == "user1(127.0.0.1:8080),user2(192.168.1.1:8080)"
    
    def test_format_empty_list(self):
        """Test formatting empty user list."""
        result = format_user_list([])
        
        assert result == ""
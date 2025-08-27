"""
Unit tests for chat_app.shared.exceptions module.
"""

import pytest

from chat_app.shared.exceptions import (
    ChatAppError,
    ConfigurationError,
    ValidationError,
    RateLimitExceededError,
    ConnectionError,
    AuthenticationError,
    NetworkError,
    ProtocolError,
    SecurityError,
    UIError,
    ServerError
)


class TestChatAppError:
    """Test base ChatAppError exception."""
    
    def test_basic_exception(self):
        """Test basic exception creation."""
        error = ChatAppError("Test error")
        
        assert str(error) == "Test error"
        assert isinstance(error, Exception)
    
    def test_exception_with_cause(self):
        """Test exception with underlying cause."""
        cause = ValueError("Original error")
        
        try:
            raise ChatAppError("Wrapper error") from cause
        except ChatAppError as error:
            assert str(error) == "Wrapper error"
            assert error.__cause__ == cause
    
    def test_exception_inheritance(self):
        """Test that all custom exceptions inherit from ChatAppError."""
        assert issubclass(ConfigurationError, ChatAppError)
        assert issubclass(ValidationError, ChatAppError)
        assert issubclass(RateLimitExceededError, ChatAppError)
        assert issubclass(ConnectionError, ChatAppError)
        assert issubclass(AuthenticationError, ChatAppError)
        assert issubclass(NetworkError, ChatAppError)
        assert issubclass(ProtocolError, ChatAppError)
        assert issubclass(SecurityError, ChatAppError)
        assert issubclass(UIError, ChatAppError)
        assert issubclass(ServerError, ChatAppError)


class TestConfigurationError:
    """Test ConfigurationError exception."""
    
    def test_configuration_error(self):
        """Test ConfigurationError creation."""
        error = ConfigurationError("Invalid configuration")
        
        assert str(error) == "Invalid configuration"
        assert isinstance(error, ChatAppError)
    
    def test_configuration_error_with_details(self):
        """Test ConfigurationError with additional details."""
        error = ConfigurationError("Invalid port", details={"port": 70000})
        
        assert str(error) == "Invalid port"
        assert error.details == {"port": 70000}


class TestValidationError:
    """Test ValidationError exception."""
    
    def test_validation_error(self):
        """Test ValidationError creation."""
        error = ValidationError("Invalid input")
        
        assert str(error) == "Invalid input"
        assert isinstance(error, ChatAppError)
    
    def test_validation_error_with_field(self):
        """Test ValidationError with field information."""
        error = ValidationError("Username too long", field="username", value="verylongusername")
        
        assert str(error) == "Username too long"
        assert error.field == "username"
        assert error.value == "verylongusername"
    
    def test_validation_error_without_optional_params(self):
        """Test ValidationError without optional parameters."""
        error = ValidationError("Generic validation error")
        
        assert str(error) == "Generic validation error"
        assert not hasattr(error, 'field')
        assert not hasattr(error, 'value')


class TestRateLimitExceededError:
    """Test RateLimitExceededError exception."""
    
    def test_rate_limit_exceeded_error(self):
        """Test RateLimitExceededError creation."""
        error = RateLimitExceededError("Rate limit exceeded")
        
        assert str(error) == "Rate limit exceeded"
        assert isinstance(error, SecurityError)
        assert isinstance(error, ChatAppError)
    
    def test_rate_limit_exceeded_error_with_retry_after(self):
        """Test RateLimitExceededError with retry_after."""
        error = RateLimitExceededError("Too many messages", retry_after=60)
        
        assert str(error) == "Too many messages"
        assert error.retry_after == 60


class TestConnectionError:
    """Test ConnectionError exception."""
    
    def test_connection_error(self):
        """Test ConnectionError creation."""
        error = ConnectionError("Connection failed")
        
        assert str(error) == "Connection failed"
        assert isinstance(error, ChatAppError)
    
    def test_connection_error_with_address(self):
        """Test ConnectionError with address information."""
        error = ConnectionError("Cannot connect", address="127.0.0.1:8080")
        
        assert str(error) == "Cannot connect"
        assert error.address == "127.0.0.1:8080"


class TestAuthenticationError:
    """Test AuthenticationError exception."""
    
    def test_authentication_error(self):
        """Test AuthenticationError creation."""
        error = AuthenticationError("Authentication failed")
        
        assert str(error) == "Authentication failed"
        assert isinstance(error, ChatAppError)
    
    def test_authentication_error_with_username(self):
        """Test AuthenticationError with username."""
        error = AuthenticationError("Invalid username", username="invalid@user")
        
        assert str(error) == "Invalid username"
        assert error.username == "invalid@user"


class TestNetworkError:
    """Test NetworkError exception."""
    
    def test_network_error(self):
        """Test NetworkError creation."""
        error = NetworkError("Network timeout")
        
        assert str(error) == "Network timeout"
        assert isinstance(error, ChatAppError)
    
    def test_network_error_with_operation(self):
        """Test NetworkError with operation details."""
        error = NetworkError("Operation failed", operation="send", address="127.0.0.1:8080")
        
        assert str(error) == "Operation failed"
        assert error.operation == "send"
        assert error.address == "127.0.0.1:8080"


class TestProtocolError:
    """Test ProtocolError exception."""
    
    def test_protocol_error(self):
        """Test ProtocolError creation."""
        error = ProtocolError("Invalid message format")
        
        assert str(error) == "Invalid message format"
        assert isinstance(error, ChatAppError)
    
    def test_protocol_error_with_message(self):
        """Test ProtocolError with message details."""
        error = ProtocolError("Malformed message", message_data="INVALID|format", expected_format="TYPE|payload")
        
        assert str(error) == "Malformed message"
        assert error.message_data == "INVALID|format"
        assert error.expected_format == "TYPE|payload"


class TestExceptionHandling:
    """Test exception handling patterns."""
    
    def test_catch_base_exception(self):
        """Test catching base ChatAppError."""
        with pytest.raises(ChatAppError):
            raise ValidationError("Test validation error")
    
    def test_catch_specific_exception(self):
        """Test catching specific exception type."""
        with pytest.raises(ValidationError):
            raise ValidationError("Test validation error")
    
    def test_exception_chaining(self):
        """Test exception chaining."""
        try:
            try:
                raise ValueError("Original error")
            except ValueError as e:
                raise ConfigurationError("Configuration failed") from e
        except ConfigurationError as config_error:
            assert str(config_error) == "Configuration failed"
            assert isinstance(config_error.__cause__, ValueError)
            assert str(config_error.__cause__) == "Original error"
    
    def test_multiple_exception_types(self):
        """Test handling multiple exception types."""
        def raise_different_errors(error_type: str):
            if error_type == "validation":
                raise ValidationError("Validation failed")
            elif error_type == "rate_limit":
                raise RateLimitExceededError("Rate limit exceeded")
            elif error_type == "network":
                raise NetworkError("Network error")
        
        # Test ValidationError
        with pytest.raises(ValidationError):
            raise_different_errors("validation")
        
        # Test RateLimitExceededError
        with pytest.raises(RateLimitExceededError):
            raise_different_errors("rate_limit")
        
        # Test NetworkError
        with pytest.raises(NetworkError):
            raise_different_errors("network")
        
        # Test catching all as base type
        with pytest.raises(ChatAppError):
            raise_different_errors("validation")
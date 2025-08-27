"""
Unit tests for chat_app.shared.protocols module.
"""

import pytest
from typing import Any
from unittest.mock import Mock

from chat_app.shared.protocols import (
    MessageHandler,
    NetworkConnection,
    UIComponent,
    SecurityValidator,
    ConfigurationProvider,
    Logger
)


class TestMessageHandlerProtocol:
    """Test MessageHandler protocol."""
    
    def test_message_handler_protocol_structure(self):
        """Test that MessageHandler protocol has required methods."""
        # Check that protocol has the expected method
        assert hasattr(MessageHandler, 'handle_message')
    
    def test_concrete_message_handler_implementation(self):
        """Test concrete implementation of MessageHandler."""
        
        class ConcreteMessageHandler:
            def __init__(self):
                self.handled_messages = []
            
            def handle_message(self, message: str, sender: Any) -> None:
                self.handled_messages.append((message, sender))
        
        handler = ConcreteMessageHandler()
        
        # Should be compatible with protocol
        assert isinstance(handler, MessageHandler)
        
        # Test functionality
        handler.handle_message("Hello", "user1")
        assert len(handler.handled_messages) == 1
        assert handler.handled_messages[0] == ("Hello", "user1")
    
    def test_mock_message_handler(self):
        """Test using mock as MessageHandler."""
        mock_handler = Mock(spec=MessageHandler)
        
        # Should have the required method
        assert hasattr(mock_handler, 'handle_message')
        
        # Test calling the method
        mock_handler.handle_message("test", "sender")
        mock_handler.handle_message.assert_called_once_with("test", "sender")


class TestNetworkConnectionProtocol:
    """Test NetworkConnection protocol."""
    
    def test_network_connection_protocol_structure(self):
        """Test that NetworkConnection protocol has required methods."""
        assert hasattr(NetworkConnection, 'send')
        assert hasattr(NetworkConnection, 'receive')
        assert hasattr(NetworkConnection, 'close')
    
    def test_concrete_network_connection_implementation(self):
        """Test concrete implementation of NetworkConnection."""
        
        class ConcreteNetworkConnection:
            def __init__(self):
                self.sent_data = []
                self.is_closed = False
                self.receive_data = b"test data"
            
            def send(self, data: bytes) -> None:
                if self.is_closed:
                    raise ConnectionError("Connection closed")
                self.sent_data.append(data)
            
            def receive(self, buffer_size: int = 4096) -> bytes:
                if self.is_closed:
                    raise ConnectionError("Connection closed")
                return self.receive_data
            
            def close(self) -> None:
                self.is_closed = True
            
            def is_connected(self) -> bool:
                return not self.is_closed
        
        connection = ConcreteNetworkConnection()
        
        # Should be compatible with protocol
        assert isinstance(connection, NetworkConnection)
        
        # Test functionality
        connection.send(b"hello")
        assert connection.sent_data == [b"hello"]
        
        data = connection.receive()
        assert data == b"test data"
        
        connection.close()
        assert connection.is_closed
    
    def test_mock_network_connection(self):
        """Test using mock as NetworkConnection."""
        mock_connection = Mock(spec=NetworkConnection)
        mock_connection.receive.return_value = b"mock data"
        
        # Test calling methods
        mock_connection.send(b"test")
        mock_connection.send.assert_called_once_with(b"test")
        
        data = mock_connection.receive()
        assert data == b"mock data"
        
        mock_connection.close()
        mock_connection.close.assert_called_once()


class TestUIComponentProtocol:
    """Test UIComponent protocol."""
    
    def test_ui_component_protocol_structure(self):
        """Test that UIComponent protocol has required methods."""
        assert hasattr(UIComponent, 'update')
        assert hasattr(UIComponent, 'render')
    
    def test_concrete_ui_component_implementation(self):
        """Test concrete implementation of UIComponent."""
        
        class ConcreteUIComponent:
            def __init__(self):
                self.update_count = 0
                self.render_count = 0
            
            def update(self) -> None:
                self.update_count += 1
            
            def render(self) -> Any:
                self.render_count += 1
                return f"Rendered {self.render_count} times"
        
        component = ConcreteUIComponent()
        
        # Should be compatible with protocol
        assert isinstance(component, UIComponent)
        
        # Test functionality
        component.update()
        assert component.update_count == 1
        
        result = component.render()
        assert result == "Rendered 1 times"
        assert component.render_count == 1
    
    def test_mock_ui_component(self):
        """Test using mock as UIComponent."""
        mock_component = Mock(spec=UIComponent)
        mock_component.render.return_value = "mock render"
        
        # Test calling methods
        mock_component.update()
        mock_component.update.assert_called_once()
        
        result = mock_component.render()
        assert result == "mock render"


class TestSecurityValidatorProtocol:
    """Test SecurityValidator protocol."""
    
    def test_security_validator_protocol_structure(self):
        """Test that SecurityValidator protocol has required methods."""
        assert hasattr(SecurityValidator, 'validate_input')
        assert hasattr(SecurityValidator, 'sanitize_input')
    
    def test_concrete_security_validator_implementation(self):
        """Test concrete implementation of SecurityValidator."""
        
        class ConcreteSecurityValidator:
            def validate_input(self, input_data: str, input_type: str):
                return (len(input_data) <= 100 and not any(c in input_data for c in ['<', '>', '&']), None)
            
            def sanitize_input(self, input_data: str) -> str:
                # HTML escape in the correct order to avoid double-escaping
                return input_data.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        
        validator = ConcreteSecurityValidator()
        
        # Should be compatible with protocol
        assert isinstance(validator, SecurityValidator)
        
        # Test functionality
        is_valid, error = validator.validate_input("safe input", "message")
        assert is_valid is True
        assert error is None
        
        is_valid, error = validator.validate_input("unsafe <script>", "message")
        assert is_valid is False
        
        sanitized = validator.sanitize_input("test <tag>")
        assert sanitized == "test &lt;tag&gt;"
    
    def test_mock_security_validator(self):
        """Test using mock as SecurityValidator."""
        mock_validator = Mock(spec=SecurityValidator)
        mock_validator.validate_input.return_value = (True, None)
        mock_validator.sanitize_input.return_value = "sanitized"
        
        # Test calling methods
        is_valid, error = mock_validator.validate_input("test", "message")
        assert is_valid is True
        assert error is None
        
        sanitized = mock_validator.sanitize_input("test")
        assert sanitized == "sanitized"


class TestConfigurationProviderProtocol:
    """Test ConfigurationProvider protocol."""
    
    def test_configuration_provider_protocol_structure(self):
        """Test that ConfigurationProvider protocol has required methods."""
        assert hasattr(ConfigurationProvider, 'get_config')
        assert hasattr(ConfigurationProvider, 'set_config')
        assert hasattr(ConfigurationProvider, 'reload_config')
    
    def test_concrete_configuration_provider_implementation(self):
        """Test concrete implementation of ConfigurationProvider."""
        
        class ConcreteConfigurationProvider:
            def __init__(self):
                self.config = {"host": "localhost", "port": 8080}
                self.reload_count = 0
            
            def get_config(self, key: str, default=None):
                return self.config.get(key, default)
            
            def set_config(self, key: str, value) -> None:
                self.config[key] = value
            
            def reload_config(self) -> None:
                self.reload_count += 1
                # Simulate config reload
                self.config["reload_count"] = self.reload_count
        
        provider = ConcreteConfigurationProvider()
        
        # Should be compatible with protocol
        assert isinstance(provider, ConfigurationProvider)
        
        # Test functionality
        host = provider.get_config("host")
        assert host == "localhost"
        
        provider.set_config("new_key", "new_value")
        assert provider.get_config("new_key") == "new_value"
        
        provider.reload_config()
        assert provider.get_config("reload_count") == 1
    
    def test_mock_configuration_provider(self):
        """Test using mock as ConfigurationProvider."""
        mock_provider = Mock(spec=ConfigurationProvider)
        mock_provider.get_config.return_value = "test_value"
        
        # Test calling methods
        value = mock_provider.get_config("test_key")
        assert value == "test_value"
        
        mock_provider.set_config("key", "value")
        mock_provider.set_config.assert_called_once_with("key", "value")
        
        mock_provider.reload_config()
        mock_provider.reload_config.assert_called_once()


class TestLoggerProtocol:
    """Test Logger protocol."""
    
    def test_logger_protocol_structure(self):
        """Test that Logger protocol has required methods."""
        assert hasattr(Logger, 'debug')
        assert hasattr(Logger, 'info')
        assert hasattr(Logger, 'warning')
        assert hasattr(Logger, 'error')
        assert hasattr(Logger, 'critical')
    
    def test_concrete_logger_implementation(self):
        """Test concrete implementation of Logger."""
        
        class ConcreteLogger:
            def __init__(self):
                self.logs = []
            
            def debug(self, message: str, *args, **kwargs) -> None:
                self.logs.append(("DEBUG", message, args, kwargs))
            
            def info(self, message: str, *args, **kwargs) -> None:
                self.logs.append(("INFO", message, args, kwargs))
            
            def warning(self, message: str, *args, **kwargs) -> None:
                self.logs.append(("WARNING", message, args, kwargs))
            
            def error(self, message: str, *args, **kwargs) -> None:
                self.logs.append(("ERROR", message, args, kwargs))
            
            def critical(self, message: str, *args, **kwargs) -> None:
                self.logs.append(("CRITICAL", message, args, kwargs))
        
        logger = ConcreteLogger()
        
        # Should be compatible with protocol
        assert isinstance(logger, Logger)
        
        # Test functionality
        logger.info("Test message")
        logger.error("Error message", extra="data")
        
        assert len(logger.logs) == 2
        assert logger.logs[0] == ("INFO", "Test message", (), {})
        assert logger.logs[1] == ("ERROR", "Error message", (), {"extra": "data"})
    
    def test_mock_logger(self):
        """Test using mock as Logger."""
        mock_logger = Mock(spec=Logger)
        
        # Test calling methods
        mock_logger.info("test message")
        mock_logger.info.assert_called_once_with("test message")
        
        mock_logger.error("error message", exc_info=True)
        mock_logger.error.assert_called_once_with("error message", exc_info=True)


class TestProtocolCompatibility:
    """Test protocol compatibility and type checking."""
    
    def test_protocol_duck_typing(self):
        """Test that protocols work with duck typing."""
        
        class DuckTypedHandler:
            def handle_message(self, message: str, sender: Any) -> None:
                pass
        
        handler = DuckTypedHandler()
        
        # Should be compatible even without explicit inheritance
        def process_with_handler(h: MessageHandler):
            h.handle_message("test", "sender")
        
        # This should work without type errors
        process_with_handler(handler)
    
    def test_protocol_method_signatures(self):
        """Test that protocol methods have correct signatures."""
        
        class TestImplementation:
            def handle_message(self, message: str, sender: Any) -> None:
                pass
            
            def send(self, data: bytes) -> None:
                pass
            
            def receive(self, buffer_size: int = 4096) -> bytes:
                return b""
            
            def close(self) -> None:
                pass
            
            def is_connected(self) -> bool:
                return True
            
            def update(self) -> None:
                pass
            
            def render(self) -> Any:
                return None
        
        impl = TestImplementation()
        
        # Should be compatible with multiple protocols
        assert isinstance(impl, MessageHandler)
        assert isinstance(impl, NetworkConnection)
        assert isinstance(impl, UIComponent)
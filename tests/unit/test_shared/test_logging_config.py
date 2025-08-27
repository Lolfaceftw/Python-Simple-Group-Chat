"""
Unit tests for chat_app.shared.logging_config module.
"""

import pytest
import logging
import tempfile
import os
from unittest.mock import patch, Mock
from pathlib import Path

from chat_app.shared.logging_config import (
    setup_logging,
    get_logger,
    ColoredFormatter,
    JsonFormatter,
    configure_from_env,
    setup_basic_logging,
    LogLevel
)


class TestColoredFormatter:
    """Test ColoredFormatter class."""
    
    def test_colored_formatter_creation(self):
        """Test creating ColoredFormatter."""
        formatter = ColoredFormatter()
        
        assert isinstance(formatter, logging.Formatter)
        assert hasattr(formatter, 'COLORS')
    
    def test_colored_formatter_colors(self):
        """Test that ColoredFormatter has expected colors."""
        formatter = ColoredFormatter()
        
        assert 'DEBUG' in formatter.COLORS
        assert 'INFO' in formatter.COLORS
        assert 'WARNING' in formatter.COLORS
        assert 'ERROR' in formatter.COLORS
        assert 'CRITICAL' in formatter.COLORS
        assert 'RESET' in formatter.COLORS


class TestSetupLogging:
    """Test setup_logging function."""
    
    def setUp(self):
        """Set up test environment."""
        # Clear any existing handlers
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
    
    def tearDown(self):
        """Clean up test environment."""
        # Clear handlers after test
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
    
    def test_setup_logging_console_only(self):
        """Test setting up logging with console handler only."""
        self.setUp()
        
        logger = setup_logging(level="INFO")
        
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) >= 1
        assert root_logger.level == logging.INFO
        
        self.tearDown()
    
    def test_setup_logging_with_file(self):
        """Test setting up logging with file handler."""
        self.setUp()
        
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            log_file = tmp_file.name
        
        try:
            logger = setup_logging(level="DEBUG", log_file=log_file)
            
            root_logger = logging.getLogger()
            assert len(root_logger.handlers) >= 1
            assert root_logger.level == logging.DEBUG
            
            # Check that file handler was added
            file_handlers = [h for h in root_logger.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
            assert len(file_handlers) >= 1
        finally:
            os.unlink(log_file)
            self.tearDown()
    
    def test_setup_logging_with_json_format(self):
        """Test setting up logging with JSON format."""
        self.setUp()
        
        logger = setup_logging(level="INFO", json_format=True)
        
        root_logger = logging.getLogger()
        handler = root_logger.handlers[0]
        assert isinstance(handler.formatter, JsonFormatter)
        
        self.tearDown()
    
    def test_setup_logging_with_colors_disabled(self):
        """Test setting up logging with colors disabled."""
        self.setUp()
        
        logger = setup_logging(level="INFO", enable_colors=False)
        
        root_logger = logging.getLogger()
        handler = root_logger.handlers[0]
        assert not isinstance(handler.formatter, ColoredFormatter)
        
        self.tearDown()


class TestGetLogger:
    """Test get_logger function."""
    
    def test_get_logger_with_name(self):
        """Test getting logger with specific name."""
        logger = get_logger("test_module")
        
        assert logger.name == "test_module"
        assert isinstance(logger, logging.Logger)
    
    def test_get_logger_without_name(self):
        """Test getting logger without name uses caller's module."""
        logger = get_logger()
        
        # Should use the current module name
        assert "test_logging_config" in logger.name
    
    def test_get_logger_same_name_returns_same_instance(self):
        """Test that getting logger with same name returns same instance."""
        logger1 = get_logger("same_name")
        logger2 = get_logger("same_name")
        
        assert logger1 is logger2


class TestJsonFormatter:
    """Test JsonFormatter class."""
    
    def test_json_formatter_creation(self):
        """Test creating JsonFormatter."""
        formatter = JsonFormatter()
        
        assert isinstance(formatter, logging.Formatter)
    
    def test_json_formatter_format(self):
        """Test JsonFormatter format method."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None
        )
        
        formatted = formatter.format(record)
        
        # Should be valid JSON
        import json
        parsed = json.loads(formatted)
        assert parsed["message"] == "Test message"
        assert parsed["level"] == "INFO"


class TestConfigureFromEnv:
    """Test configure_from_env function."""
    
    def setUp(self):
        """Set up test environment."""
        # Clear any existing handlers
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
    
    def tearDown(self):
        """Clean up test environment."""
        # Clear handlers after test
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
    
    @patch.dict(os.environ, {"CHAT_LOG_LEVEL": "ERROR"})
    def test_configure_from_env_with_level(self):
        """Test configuring from environment with log level."""
        self.setUp()
        
        logger = configure_from_env()
        
        root_logger = logging.getLogger()
        assert root_logger.level == logging.ERROR
        
        self.tearDown()
    
    @patch.dict(os.environ, {}, clear=True)
    def test_configure_from_env_defaults(self):
        """Test configuring from environment with defaults."""
        self.setUp()
        
        logger = configure_from_env()
        
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO  # Default level
        
        self.tearDown()


class TestSetupBasicLogging:
    """Test setup_basic_logging function."""
    
    def setUp(self):
        """Set up test environment."""
        # Clear any existing handlers
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
    
    def tearDown(self):
        """Clean up test environment."""
        # Clear handlers after test
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
    
    def test_setup_basic_logging(self):
        """Test setting up basic logging."""
        self.setUp()
        
        logger = setup_basic_logging("test_component")
        
        assert logger.name == "test_component"
        assert isinstance(logger, logging.Logger)
        
        self.tearDown()


class TestLoggingIntegration:
    """Test logging integration scenarios."""
    
    def setUp(self):
        """Set up test environment."""
        # Clear any existing handlers
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
    
    def tearDown(self):
        """Clean up test environment."""
        # Clear handlers after test
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
    
    def test_logging_output_to_file(self):
        """Test that logging actually writes to file."""
        self.setUp()
        
        with tempfile.NamedTemporaryFile(mode='w+', delete=False) as tmp_file:
            log_file = tmp_file.name
        
        try:
            setup_logging(
                level=LogLevel.INFO,
                enable_console=False,
                enable_file=True,
                log_file=log_file
            )
            
            logger = get_logger("test_logger")
            logger.info("Test message")
            
            # Force flush
            for handler in logging.getLogger().handlers:
                handler.flush()
            
            # Read the log file
            with open(log_file, 'r') as f:
                content = f.read()
            
            assert "Test message" in content
            assert "test_logger" in content
        finally:
            os.unlink(log_file)
            self.tearDown()
    
    def test_logging_level_filtering(self):
        """Test that logging level filtering works."""
        self.setUp()
        
        with tempfile.NamedTemporaryFile(mode='w+', delete=False) as tmp_file:
            log_file = tmp_file.name
        
        try:
            setup_logging(
                level=LogLevel.WARNING,
                enable_console=False,
                enable_file=True,
                log_file=log_file
            )
            
            logger = get_logger("test_logger")
            logger.debug("Debug message")  # Should not appear
            logger.info("Info message")    # Should not appear
            logger.warning("Warning message")  # Should appear
            logger.error("Error message")      # Should appear
            
            # Force flush
            for handler in logging.getLogger().handlers:
                handler.flush()
            
            # Read the log file
            with open(log_file, 'r') as f:
                content = f.read()
            
            assert "Debug message" not in content
            assert "Info message" not in content
            assert "Warning message" in content
            assert "Error message" in content
        finally:
            os.unlink(log_file)
            self.tearDown()
    
    def test_multiple_loggers(self):
        """Test multiple loggers with different names."""
        self.setUp()
        
        setup_logging(level=LogLevel.INFO, enable_console=True)
        
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")
        
        assert logger1.name == "module1"
        assert logger2.name == "module2"
        assert logger1 is not logger2
        
        # Both should use the same root configuration
        assert logger1.level == logging.NOTSET  # Inherits from root
        assert logger2.level == logging.NOTSET  # Inherits from root
        
        self.tearDown()
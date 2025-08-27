"""
Logging Configuration

Provides centralized logging configuration for the chat application.
"""

import json
import logging
import logging.handlers
import os
import sys
import threading
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, Union

from .constants import LOG_FORMAT, LOG_DATE_FORMAT


class LogLevel(Enum):
    """Enumeration of logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log levels."""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with colors."""
        # Add color to the level name
        level_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        record.levelname = f"{level_color}{record.levelname}{self.COLORS['RESET']}"
        
        return super().format(record)


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    enable_colors: bool = True,
    json_format: bool = False,
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    include_metrics: bool = False
) -> logging.Logger:
    """
    Set up logging configuration for the application.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Path to log file. If None, logs only to console.
        enable_colors: Whether to enable colored output for console logging.
        json_format: Whether to use JSON format for structured logging.
        max_file_size: Maximum size of log file before rotation.
        backup_count: Number of backup files to keep.
        include_metrics: Whether to include metrics in JSON log entries.
        
    Returns:
        Configured logger instance.
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create root logger
    logger = logging.getLogger()
    logger.setLevel(numeric_level)
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    
    if json_format:
        console_formatter: logging.Formatter = JsonFormatter(include_metrics=include_metrics)
    elif enable_colors and sys.stdout.isatty():
        console_formatter = ColoredFormatter(LOG_FORMAT, LOG_DATE_FORMAT)
    else:
        console_formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
    
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        # Create directory if it doesn't exist
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # Use rotating file handler to prevent log files from growing too large
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(numeric_level)
        
        if json_format:
            file_formatter: logging.Formatter = JsonFormatter(include_metrics=include_metrics)
        else:
            file_formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
        
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def __init__(self, include_metrics: bool = False):
        """
        Initialize JSON formatter.
        
        Args:
            include_metrics: Whether to include metrics in log entries.
        """
        super().__init__()
        self.include_metrics = include_metrics
    
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON."""
        log_entry = {
            'timestamp': self.formatTime(record, self.datefmt or '%Y-%m-%d %H:%M:%S'),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'thread': record.thread,
            'thread_name': record.threadName,
            'process': record.process,
            'process_name': record.processName
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        # Add stack info if present
        if record.stack_info:
            log_entry['stack_info'] = record.stack_info
        
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in ('name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                          'filename', 'module', 'lineno', 'funcName', 'created',
                          'msecs', 'relativeCreated', 'thread', 'threadName',
                          'processName', 'process', 'getMessage', 'exc_info',
                          'exc_text', 'stack_info'):
                log_entry[key] = value
        
        # Add metrics if enabled
        if self.include_metrics:
            try:
                from .metrics import get_metrics_collector
                collector = get_metrics_collector()
                log_entry['metrics'] = {
                    'active_connections': collector.get_gauge('active_connections') or 0,
                    'total_messages': collector.get_counter('messages_sent') or 0,
                    'errors_count': collector.get_counter('errors') or 0
                }
            except Exception:
                # Don't fail logging if metrics collection fails
                pass
        
        return json.dumps(log_entry, default=str, ensure_ascii=False)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance with the specified name.
    
    Args:
        name: Logger name (typically __name__). If None, uses caller's module name.
        
    Returns:
        Logger instance.
    """
    if name is None:
        import inspect
        frame = inspect.currentframe()
        try:
            caller_frame = frame.f_back
            name = caller_frame.f_globals.get('__name__', 'unknown')
        finally:
            del frame
    
    return logging.getLogger(name)


def configure_from_env() -> logging.Logger:
    """
    Configure logging from environment variables.
    
    Environment variables:
        CHAT_LOG_LEVEL: Logging level (default: INFO)
        CHAT_LOG_FILE: Log file path (optional)
        CHAT_LOG_COLORS: Enable colors (default: true)
        CHAT_LOG_JSON: Use JSON format (default: false)
        CHAT_LOG_MAX_SIZE: Max file size in bytes (default: 10MB)
        CHAT_LOG_BACKUP_COUNT: Number of backup files (default: 5)
        CHAT_LOG_INCLUDE_METRICS: Include metrics in JSON logs (default: false)
    
    Returns:
        Configured logger instance.
    """
    level = os.getenv("CHAT_LOG_LEVEL", "INFO")
    log_file = os.getenv("CHAT_LOG_FILE")
    enable_colors = os.getenv("CHAT_LOG_COLORS", "true").lower() == "true"
    json_format = os.getenv("CHAT_LOG_JSON", "false").lower() == "true"
    max_file_size = int(os.getenv("CHAT_LOG_MAX_SIZE", str(10 * 1024 * 1024)))
    backup_count = int(os.getenv("CHAT_LOG_BACKUP_COUNT", "5"))
    include_metrics = os.getenv("CHAT_LOG_INCLUDE_METRICS", "false").lower() == "true"
    
    return setup_logging(
        level=level,
        log_file=log_file,
        enable_colors=enable_colors,
        json_format=json_format,
        max_file_size=max_file_size,
        backup_count=backup_count,
        include_metrics=include_metrics
    )


class MetricsHandler(logging.Handler):
    """Logging handler that collects metrics from log records."""
    
    def __init__(self):
        """Initialize metrics handler."""
        super().__init__()
        self._metrics_collector = None
    
    def emit(self, record: logging.LogRecord) -> None:
        """Process log record and update metrics."""
        try:
            if self._metrics_collector is None:
                from .metrics import get_metrics_collector
                self._metrics_collector = get_metrics_collector()
            
            # Count log messages by level
            self._metrics_collector.increment_counter(
                "log_messages", 
                labels={"level": record.levelname.lower()}
            )
            
            # Count errors and warnings
            if record.levelno >= logging.ERROR:
                self._metrics_collector.increment_counter("errors")
            elif record.levelno >= logging.WARNING:
                self._metrics_collector.increment_counter("warnings")
            
            # Track logger usage
            self._metrics_collector.increment_counter(
                "logger_usage",
                labels={"logger": record.name}
            )
            
        except Exception:
            # Don't fail logging if metrics collection fails
            pass


class PerformanceLogger:
    """Logger wrapper that adds performance monitoring."""
    
    def __init__(self, logger: logging.Logger):
        """
        Initialize performance logger.
        
        Args:
            logger: Base logger instance.
        """
        self.logger = logger
        self._metrics_collector = None
    
    def _get_metrics_collector(self):
        """Get metrics collector instance."""
        if self._metrics_collector is None:
            from .metrics import get_metrics_collector
            self._metrics_collector = get_metrics_collector()
        return self._metrics_collector
    
    def log_operation(self, operation: str, duration: float, success: bool = True, **kwargs) -> None:
        """
        Log an operation with performance metrics.
        
        Args:
            operation: Operation name.
            duration: Operation duration in seconds.
            success: Whether the operation was successful.
            **kwargs: Additional context to log.
        """
        level = logging.INFO if success else logging.ERROR
        status = "success" if success else "failure"
        
        # Log the operation
        self.logger.log(
            level,
            f"Operation {operation} completed in {duration:.3f}s ({status})",
            extra={
                "operation": operation,
                "duration": duration,
                "success": success,
                **kwargs
            }
        )
        
        # Record metrics
        try:
            collector = self._get_metrics_collector()
            collector.record_timer(f"operation_{operation}", duration, {"status": status})
            collector.increment_counter(f"operations_{operation}", labels={"status": status})
        except Exception:
            pass
    
    def log_connection_event(self, event: str, client_id: str, **kwargs) -> None:
        """
        Log a connection event.
        
        Args:
            event: Event type (connect, disconnect, error).
            client_id: Client identifier.
            **kwargs: Additional context.
        """
        self.logger.info(
            f"Connection {event}: {client_id}",
            extra={
                "event": event,
                "client_id": client_id,
                **kwargs
            }
        )
        
        # Record metrics
        try:
            collector = self._get_metrics_collector()
            collector.increment_counter("connection_events", labels={"event": event})
        except Exception:
            pass
    
    def log_message_event(self, event: str, message_size: int, **kwargs) -> None:
        """
        Log a message event.
        
        Args:
            event: Event type (sent, received, broadcast).
            message_size: Message size in bytes.
            **kwargs: Additional context.
        """
        self.logger.debug(
            f"Message {event}: {message_size} bytes",
            extra={
                "event": event,
                "message_size": message_size,
                **kwargs
            }
        )
        
        # Record metrics
        try:
            collector = self._get_metrics_collector()
            collector.increment_counter("messages", labels={"event": event})
            collector.record_histogram("message_size", message_size, {"event": event})
        except Exception:
            pass


def setup_metrics_logging() -> None:
    """Set up metrics collection from log messages."""
    root_logger = logging.getLogger()
    
    # Check if metrics handler is already added
    for handler in root_logger.handlers:
        if isinstance(handler, MetricsHandler):
            return
    
    # Add metrics handler
    metrics_handler = MetricsHandler()
    metrics_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(metrics_handler)


def get_performance_logger(name: str) -> PerformanceLogger:
    """
    Get a performance logger instance.
    
    Args:
        name: Logger name.
        
    Returns:
        Performance logger instance.
    """
    base_logger = get_logger(name)
    return PerformanceLogger(base_logger)


# Convenience function to set up basic logging
def setup_basic_logging(component_name: str = "chat_app") -> logging.Logger:
    """
    Set up basic logging for a component.
    
    Args:
        component_name: Name of the component for the logger.
        
    Returns:
        Configured logger instance.
    """
    # Try to configure from environment first
    try:
        configure_from_env()
    except Exception:
        # Fall back to basic configuration
        setup_logging()
    
    # Set up metrics logging
    setup_metrics_logging()
    
    return get_logger(component_name)
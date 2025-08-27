"""
Custom Exceptions

Defines custom exception classes for the chat application.
"""

from typing import Optional


class ChatAppError(Exception):
    """Base exception class for all chat application errors."""
    pass


class NetworkError(ChatAppError):
    """Raised when network-related errors occur."""
    
    def __init__(self, message: str, operation: Optional[str] = None, address: Optional[str] = None):
        super().__init__(message)
        self.operation = operation
        self.address = address


class ConnectionError(NetworkError):
    """Raised when connection-related errors occur."""
    
    def __init__(self, message: str, address: Optional[str] = None):
        super().__init__(message)
        self.address = address


class ConnectionTimeoutError(ConnectionError):
    """Raised when a connection times out."""
    pass


class ConnectionRefusedError(ConnectionError):
    """Raised when a connection is refused."""
    pass


class ValidationError(ChatAppError):
    """Raised when input validation fails."""
    
    def __init__(self, message: str, field: Optional[str] = None, value: Optional[str] = None):
        super().__init__(message)
        if field is not None:
            self.field = field
        if value is not None:
            self.value = value


class UsernameValidationError(ValidationError):
    """Raised when username validation fails."""
    pass


class MessageValidationError(ValidationError):
    """Raised when message validation fails."""
    pass


class SecurityError(ChatAppError):
    """Base class for security-related errors."""
    pass


class RateLimitExceededError(SecurityError):
    """Raised when rate limits are exceeded."""
    
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class ConnectionLimitExceededError(SecurityError):
    """Raised when connection limits are exceeded."""
    pass


class AuthenticationError(SecurityError):
    """Raised when authentication fails."""
    
    def __init__(self, message: str, username: Optional[str] = None):
        super().__init__(message)
        self.username = username


class AuthorizationError(SecurityError):
    """Raised when authorization fails."""
    pass


class ConfigurationError(ChatAppError):
    """Raised when configuration-related errors occur."""
    
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.details = details


class InvalidConfigurationError(ConfigurationError):
    """Raised when configuration is invalid."""
    pass


class MissingConfigurationError(ConfigurationError):
    """Raised when required configuration is missing."""
    pass


class UIError(ChatAppError):
    """Base class for UI-related errors."""
    pass


class UnsupportedPlatformError(UIError):
    """Raised when the platform is not supported."""
    pass


class InputHandlingError(UIError):
    """Raised when input handling fails."""
    pass


class DisplayError(UIError):
    """Raised when display operations fail."""
    pass


class ProtocolError(ChatAppError):
    """Raised when protocol-related errors occur."""
    
    def __init__(self, message: str, message_data: Optional[str] = None, expected_format: Optional[str] = None):
        super().__init__(message)
        self.message_data = message_data
        self.expected_format = expected_format


class InvalidMessageFormatError(ProtocolError):
    """Raised when message format is invalid."""
    pass


class UnsupportedMessageTypeError(ProtocolError):
    """Raised when an unsupported message type is encountered."""
    pass


class ServerError(ChatAppError):
    """Base class for server-related errors."""
    pass


class ChatServerError(ServerError):
    """Raised when chat server operations fail."""
    pass


class ClientManagerError(ServerError):
    """Raised when client management operations fail."""
    pass


class ClientNotFoundError(ClientManagerError):
    """Raised when a client is not found."""
    pass


class DuplicateClientError(ClientManagerError):
    """Raised when attempting to add a duplicate client."""
    pass


class MessageBrokerError(ServerError):
    """Raised when message broker operations fail."""
    pass


class ServiceDiscoveryError(ChatAppError):
    """Raised when service discovery operations fail."""
    pass


class BroadcastError(ServiceDiscoveryError):
    """Raised when broadcasting fails."""
    pass


class DiscoveryTimeoutError(ServiceDiscoveryError):
    """Raised when service discovery times out."""
    pass


# Performance-related exceptions

class PerformanceError(ChatAppError):
    """Base class for performance-related errors."""
    pass


class ThreadPoolError(PerformanceError):
    """Raised when thread pool operations fail."""
    pass


class MessageQueueError(PerformanceError):
    """Raised when message queue operations fail."""
    pass


class MemoryManagerError(PerformanceError):
    """Raised when memory manager operations fail."""
    pass


class UIOptimizerError(PerformanceError):
    """Raised when UI optimizer operations fail."""
    pass


class SchedulerError(PerformanceError):
    """Raised when scheduler operations fail."""
    pass


# Scalability-related exceptions

class ScalabilityError(ChatAppError):
    """Base class for scalability-related errors."""
    pass


class LoadBalancerError(ScalabilityError):
    """Raised when load balancer operations fail."""
    pass


class ClusterError(ScalabilityError):
    """Raised when cluster management operations fail."""
    pass


class ResourceMonitorError(ScalabilityError):
    """Raised when resource monitoring operations fail."""
    pass


class ConnectionOptimizerError(ScalabilityError):
    """Raised when connection optimizer operations fail."""
    pass


# Load testing exceptions

class LoadTestError(ChatAppError):
    """Raised when load testing operations fail."""
    pass


class BenchmarkError(ChatAppError):
    """Raised when benchmark operations fail."""
    pass
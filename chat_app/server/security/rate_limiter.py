"""
Rate Limiting Module

Implements rate limiting functionality using token bucket algorithm
to control message rates and connection rates per client and IP address.
"""

import time
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

from chat_app.shared.constants import (
    DEFAULT_RATE_LIMIT_MESSAGES_PER_MINUTE,
    DEFAULT_MAX_CONNECTIONS_PER_IP
)
from chat_app.shared.exceptions import RateLimitExceededError


@dataclass
class TokenBucket:
    """
    Token bucket implementation for rate limiting.
    
    The token bucket algorithm allows for burst traffic while maintaining
    an average rate limit over time.
    """
    capacity: int  # Maximum number of tokens
    tokens: float  # Current number of tokens
    refill_rate: float  # Tokens per second
    last_refill: Optional[float] = None
    
    def __post_init__(self):
        """Initialize tokens to full capacity."""
        if self.tokens is None:
            self.tokens = float(self.capacity)
        # Ensure last_refill is set properly
        if self.last_refill is None:
            self.last_refill = time.time()
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        
        # Add tokens based on elapsed time
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now
    
    def consume(self, tokens: int = 1) -> bool:
        """
        Attempt to consume tokens from the bucket.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if tokens were successfully consumed, False otherwise
        """
        self._refill()
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def peek(self) -> float:
        """
        Get current token count without consuming.
        
        Returns:
            Current number of tokens available
        """
        self._refill()
        return self.tokens
    
    def time_until_available(self, tokens: int = 1) -> float:
        """
        Calculate time until specified tokens are available.
        
        Args:
            tokens: Number of tokens needed
            
        Returns:
            Time in seconds until tokens are available, 0 if already available
        """
        self._refill()
        
        if self.tokens >= tokens:
            return 0.0
        
        tokens_needed = tokens - self.tokens
        return tokens_needed / self.refill_rate


@dataclass
class RateLimitInfo:
    """Information about a client's rate limiting status."""
    client_id: str
    bucket: TokenBucket
    violation_count: int = 0
    last_violation: Optional[datetime] = None
    total_requests: int = 0
    
    def record_violation(self) -> None:
        """Record a rate limit violation."""
        self.violation_count += 1
        self.last_violation = datetime.now()
    
    def record_request(self) -> None:
        """Record a successful request."""
        self.total_requests += 1


class RateLimiter:
    """
    Rate limiter using token bucket algorithm.
    
    Provides per-client rate limiting for messages and per-IP rate limiting
    for connections with configurable limits and burst allowances.
    """
    
    def __init__(self, 
                 default_rate_per_minute: int = DEFAULT_RATE_LIMIT_MESSAGES_PER_MINUTE,
                 burst_allowance: int = 10,
                 cleanup_interval: int = 300):  # 5 minutes
        """
        Initialize the rate limiter.
        
        Args:
            default_rate_per_minute: Default rate limit per minute
            burst_allowance: Additional tokens for burst traffic
            cleanup_interval: Interval in seconds to clean up old entries
        """
        self.default_rate_per_minute = default_rate_per_minute
        self.burst_allowance = burst_allowance
        self.cleanup_interval = cleanup_interval
        
        # Convert rate per minute to rate per second
        self.default_rate_per_second = default_rate_per_minute / 60.0
        
        # Storage for rate limit info per client
        self._client_limits: Dict[str, RateLimitInfo] = {}
        self._ip_connection_counts: Dict[str, int] = defaultdict(int)
        self._ip_connection_times: Dict[str, datetime] = {}
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Cleanup tracking
        self._last_cleanup = time.time()
    
    def check_message_rate_limit(self, client_id: str, 
                                tokens_needed: int = 1,
                                custom_rate_per_minute: Optional[int] = None) -> bool:
        """
        Check if a client can send a message within rate limits.
        
        Args:
            client_id: Unique identifier for the client
            tokens_needed: Number of tokens needed for this request
            custom_rate_per_minute: Custom rate limit for this client
            
        Returns:
            True if request is allowed, False if rate limited
            
        Raises:
            RateLimitExceededError: If rate limit is exceeded and strict mode is enabled
        """
        with self._lock:
            self._maybe_cleanup()
            
            # Get or create rate limit info for client
            if client_id not in self._client_limits:
                rate_per_minute = custom_rate_per_minute or self.default_rate_per_minute
                rate_per_second = rate_per_minute / 60.0
                capacity = rate_per_minute + self.burst_allowance
                
                bucket = TokenBucket(
                    capacity=capacity,
                    tokens=float(capacity),
                    refill_rate=rate_per_second
                )
                
                self._client_limits[client_id] = RateLimitInfo(
                    client_id=client_id,
                    bucket=bucket
                )
            
            rate_info = self._client_limits[client_id]
            
            # Try to consume tokens
            if rate_info.bucket.consume(tokens_needed):
                rate_info.record_request()
                return True
            else:
                rate_info.record_violation()
                return False
    
    def check_connection_rate_limit(self, ip_address: str,
                                  max_connections: int = DEFAULT_MAX_CONNECTIONS_PER_IP) -> bool:
        """
        Check if an IP address can establish a new connection.
        
        Args:
            ip_address: IP address to check
            max_connections: Maximum connections allowed for this IP
            
        Returns:
            True if connection is allowed, False if rate limited
        """
        with self._lock:
            current_connections = self._ip_connection_counts[ip_address]
            return current_connections < max_connections
    
    def register_connection(self, ip_address: str) -> None:
        """
        Register a new connection from an IP address.
        
        Args:
            ip_address: IP address of the new connection
        """
        with self._lock:
            self._ip_connection_counts[ip_address] += 1
            self._ip_connection_times[ip_address] = datetime.now()
    
    def unregister_connection(self, ip_address: str) -> None:
        """
        Unregister a connection from an IP address.
        
        Args:
            ip_address: IP address of the disconnected client
        """
        with self._lock:
            if ip_address in self._ip_connection_counts:
                self._ip_connection_counts[ip_address] = max(
                    0, self._ip_connection_counts[ip_address] - 1
                )
                
                # Clean up if no connections remain
                if self._ip_connection_counts[ip_address] == 0:
                    del self._ip_connection_counts[ip_address]
                    if ip_address in self._ip_connection_times:
                        del self._ip_connection_times[ip_address]
    
    def get_rate_limit_status(self, client_id: str) -> Optional[Dict]:
        """
        Get current rate limit status for a client.
        
        Args:
            client_id: Client identifier
            
        Returns:
            Dictionary with rate limit status or None if client not found
        """
        with self._lock:
            if client_id not in self._client_limits:
                return None
            
            rate_info = self._client_limits[client_id]
            bucket = rate_info.bucket
            
            return {
                'client_id': client_id,
                'tokens_available': bucket.peek(),
                'tokens_capacity': bucket.capacity,
                'refill_rate_per_second': bucket.refill_rate,
                'violation_count': rate_info.violation_count,
                'total_requests': rate_info.total_requests,
                'last_violation': rate_info.last_violation,
                'time_until_next_token': bucket.time_until_available(1)
            }
    
    def get_connection_status(self, ip_address: str) -> Dict:
        """
        Get current connection status for an IP address.
        
        Args:
            ip_address: IP address to check
            
        Returns:
            Dictionary with connection status
        """
        with self._lock:
            return {
                'ip_address': ip_address,
                'current_connections': self._ip_connection_counts.get(ip_address, 0),
                'first_connection_time': self._ip_connection_times.get(ip_address)
            }
    
    def reset_client_rate_limit(self, client_id: str) -> bool:
        """
        Reset rate limit for a specific client.
        
        Args:
            client_id: Client identifier
            
        Returns:
            True if client was found and reset, False otherwise
        """
        with self._lock:
            if client_id in self._client_limits:
                rate_info = self._client_limits[client_id]
                rate_info.bucket.tokens = float(rate_info.bucket.capacity)
                rate_info.violation_count = 0
                rate_info.last_violation = None
                return True
            return False
    
    def update_client_rate_limit(self, client_id: str, 
                               new_rate_per_minute: int) -> bool:
        """
        Update rate limit for a specific client.
        
        Args:
            client_id: Client identifier
            new_rate_per_minute: New rate limit per minute
            
        Returns:
            True if client was found and updated, False otherwise
        """
        with self._lock:
            if client_id in self._client_limits:
                rate_info = self._client_limits[client_id]
                
                # Create new bucket with updated rate
                new_rate_per_second = new_rate_per_minute / 60.0
                new_capacity = new_rate_per_minute + self.burst_allowance
                
                # Preserve current token ratio
                current_ratio = rate_info.bucket.peek() / rate_info.bucket.capacity
                new_tokens = new_capacity * current_ratio
                
                rate_info.bucket = TokenBucket(
                    capacity=new_capacity,
                    tokens=new_tokens,
                    refill_rate=new_rate_per_second
                )
                return True
            return False
    
    def get_all_clients(self) -> Dict[str, Dict]:
        """
        Get rate limit status for all clients.
        
        Returns:
            Dictionary mapping client IDs to their status
        """
        with self._lock:
            return {
                client_id: self.get_rate_limit_status(client_id)
                for client_id in self._client_limits.keys()
            }
    
    def get_all_connections(self) -> Dict[str, Dict]:
        """
        Get connection status for all IP addresses.
        
        Returns:
            Dictionary mapping IP addresses to their status
        """
        with self._lock:
            return {
                ip: self.get_connection_status(ip)
                for ip in self._ip_connection_counts.keys()
            }
    
    def _maybe_cleanup(self) -> None:
        """Clean up old entries if cleanup interval has passed."""
        now = time.time()
        if now - self._last_cleanup > self.cleanup_interval:
            self._cleanup_old_entries()
            self._last_cleanup = now
    
    def cleanup_expired_entries(self) -> None:
        """Public method to clean up expired entries."""
        self._cleanup_old_entries()
    
    def get_statistics(self) -> Dict:
        """
        Get rate limiter statistics.
        
        Returns:
            Dictionary containing rate limiter statistics
        """
        with self._lock:
            total_violations = sum(info.violation_count for info in self._client_limits.values())
            total_requests = sum(info.total_requests for info in self._client_limits.values())
            active_clients = len(self._client_limits)
            active_ips = len(self._ip_connection_counts)
            
            return {
                'total_violations': total_violations,
                'total_requests': total_requests,
                'active_clients': active_clients,
                'active_ips': active_ips,
                'default_rate_per_minute': self._default_rate_per_minute,
                'burst_allowance': self._burst_allowance
            }
    
    def _cleanup_old_entries(self) -> None:
        """Remove old rate limit entries to prevent memory leaks."""
        cutoff_time = datetime.now() - timedelta(hours=1)
        
        # Clean up clients with no recent activity
        clients_to_remove = []
        for client_id, rate_info in self._client_limits.items():
            # Remove if no violations and bucket is full (indicating no recent activity)
            if (rate_info.violation_count == 0 and 
                rate_info.bucket.peek() >= rate_info.bucket.capacity * 0.9):
                clients_to_remove.append(client_id)
            # Remove if last violation was too long ago
            elif (rate_info.last_violation and 
                  rate_info.last_violation < cutoff_time):
                clients_to_remove.append(client_id)
        
        for client_id in clients_to_remove:
            del self._client_limits[client_id]
        
        # Clean up old IP connection times
        ips_to_remove = []
        for ip, connection_time in self._ip_connection_times.items():
            if connection_time < cutoff_time and self._ip_connection_counts.get(ip, 0) == 0:
                ips_to_remove.append(ip)
        
        for ip in ips_to_remove:
            if ip in self._ip_connection_times:
                del self._ip_connection_times[ip]
            if ip in self._ip_connection_counts:
                del self._ip_connection_counts[ip]


# Convenience functions for common rate limiting operations
def create_message_rate_limiter(rate_per_minute: int = DEFAULT_RATE_LIMIT_MESSAGES_PER_MINUTE,
                              burst_allowance: int = 10) -> RateLimiter:
    """Create a rate limiter configured for message rate limiting."""
    return RateLimiter(
        default_rate_per_minute=rate_per_minute,
        burst_allowance=burst_allowance
    )


def create_connection_rate_limiter() -> RateLimiter:
    """Create a rate limiter configured for connection rate limiting."""
    return RateLimiter(
        default_rate_per_minute=60,  # Not used for connections
        burst_allowance=0  # No burst for connections
    )
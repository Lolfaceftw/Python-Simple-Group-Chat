"""
Unit tests for rate limiting module.

Tests token bucket algorithm, rate limiting behavior, connection limits,
and edge cases for the rate limiting system.
"""

import time
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from chat_app.server.security.rate_limiter import (
    TokenBucket,
    RateLimiter,
    RateLimitInfo,
    create_message_rate_limiter,
    create_connection_rate_limiter
)
from chat_app.shared.exceptions import RateLimitExceededError


class TestTokenBucket:
    """Test TokenBucket implementation."""
    
    def test_initialization(self):
        """Test token bucket initialization."""
        bucket = TokenBucket(capacity=10, tokens=5.0, refill_rate=1.0)
        
        assert bucket.capacity == 10
        assert bucket.tokens == 5.0
        assert bucket.refill_rate == 1.0
        assert bucket.last_refill > 0
    
    def test_initialization_with_defaults(self):
        """Test token bucket initialization with default tokens."""
        bucket = TokenBucket(capacity=10, tokens=None, refill_rate=1.0)
        
        assert bucket.tokens == 10.0  # Should default to capacity
    
    @patch('time.time')
    def test_consume_success(self, mock_time):
        """Test successful token consumption."""
        mock_time.return_value = 0.0
        bucket = TokenBucket(capacity=10, tokens=5.0, refill_rate=1.0, last_refill=0.0)
        
        assert bucket.consume(3) is True
        assert abs(bucket.tokens - 2.0) < 0.001
    
    @patch('time.time')
    def test_consume_failure(self, mock_time):
        """Test failed token consumption when insufficient tokens."""
        mock_time.return_value = 0.0
        bucket = TokenBucket(capacity=10, tokens=2.0, refill_rate=1.0, last_refill=0.0)
        
        assert bucket.consume(5) is False
        assert abs(bucket.tokens - 2.0) < 0.001  # Should remain unchanged
    
    @patch('time.time')
    def test_consume_exact_amount(self, mock_time):
        """Test consuming exact number of available tokens."""
        mock_time.return_value = 0.0
        bucket = TokenBucket(capacity=10, tokens=5.0, refill_rate=1.0, last_refill=0.0)
        
        assert bucket.consume(5) is True
        assert abs(bucket.tokens - 0.0) < 0.001
    
    @patch('time.time')
    def test_peek(self, mock_time):
        """Test peeking at current token count."""
        mock_time.return_value = 0.0
        bucket = TokenBucket(capacity=10, tokens=7.5, refill_rate=1.0, last_refill=0.0)
        
        # Peek should not change token count
        tokens = bucket.peek()
        assert abs(tokens - 7.5) < 0.001
        assert abs(bucket.tokens - 7.5) < 0.001
    
    @patch('time.time')
    def test_refill_over_time(self, mock_time):
        """Test token refill over time."""
        # Start at time 0
        mock_time.return_value = 0.0
        bucket = TokenBucket(capacity=10, tokens=2.0, refill_rate=2.0)
        bucket.last_refill = 0.0  # Ensure consistent starting point
        
        # Advance time by 3 seconds
        mock_time.return_value = 3.0
        bucket._refill()
        
        # Should have added 6 tokens (3 seconds * 2 tokens/second)
        assert abs(bucket.tokens - 8.0) < 0.001
        assert bucket.last_refill == 3.0
    
    @patch('time.time')
    def test_refill_cap_at_capacity(self, mock_time):
        """Test that refill doesn't exceed capacity."""
        mock_time.return_value = 0.0
        bucket = TokenBucket(capacity=10, tokens=8.0, refill_rate=2.0)
        bucket.last_refill = 0.0  # Ensure consistent starting point
        
        # Advance time by 5 seconds (would add 10 tokens)
        mock_time.return_value = 5.0
        bucket._refill()
        
        # Should be capped at capacity
        assert abs(bucket.tokens - 10.0) < 0.001
    
    @patch('time.time')
    def test_time_until_available(self, mock_time):
        """Test calculation of time until tokens are available."""
        mock_time.return_value = 0.0
        bucket = TokenBucket(capacity=10, tokens=2.0, refill_rate=2.0)
        bucket.last_refill = 0.0  # Ensure consistent starting point
        
        # Need 5 tokens, have 2, need 3 more at rate of 2/second = 1.5 seconds
        time_needed = bucket.time_until_available(5)
        assert abs(time_needed - 1.5) < 0.001
    
    @patch('time.time')
    def test_time_until_available_already_available(self, mock_time):
        """Test time until available when tokens are already available."""
        mock_time.return_value = 0.0
        bucket = TokenBucket(capacity=10, tokens=5.0, refill_rate=2.0)
        bucket.last_refill = 0.0  # Ensure consistent starting point
        
        # Already have enough tokens
        time_needed = bucket.time_until_available(3)
        assert abs(time_needed - 0.0) < 0.001


class TestRateLimitInfo:
    """Test RateLimitInfo functionality."""
    
    def test_initialization(self):
        """Test rate limit info initialization."""
        bucket = TokenBucket(capacity=10, tokens=10.0, refill_rate=1.0)
        info = RateLimitInfo(client_id="test_client", bucket=bucket)
        
        assert info.client_id == "test_client"
        assert info.bucket == bucket
        assert info.violation_count == 0
        assert info.last_violation is None
        assert info.total_requests == 0
    
    def test_record_violation(self):
        """Test recording rate limit violations."""
        bucket = TokenBucket(capacity=10, tokens=10.0, refill_rate=1.0)
        info = RateLimitInfo(client_id="test_client", bucket=bucket)
        
        info.record_violation()
        
        assert info.violation_count == 1
        assert info.last_violation is not None
        assert isinstance(info.last_violation, datetime)
    
    def test_record_request(self):
        """Test recording successful requests."""
        bucket = TokenBucket(capacity=10, tokens=10.0, refill_rate=1.0)
        info = RateLimitInfo(client_id="test_client", bucket=bucket)
        
        info.record_request()
        
        assert info.total_requests == 1


class TestRateLimiter:
    """Test RateLimiter functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rate_limiter = RateLimiter(
            default_rate_per_minute=60,  # 1 per second
            burst_allowance=10,
            cleanup_interval=300
        )
    
    def test_initialization(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter(
            default_rate_per_minute=120,
            burst_allowance=20,
            cleanup_interval=600
        )
        
        assert limiter.default_rate_per_minute == 120
        assert limiter.burst_allowance == 20
        assert limiter.cleanup_interval == 600
        assert limiter.default_rate_per_second == 2.0
    
    def test_check_message_rate_limit_new_client(self):
        """Test rate limit check for new client."""
        result = self.rate_limiter.check_message_rate_limit("client1")
        
        assert result is True
        assert "client1" in self.rate_limiter._client_limits
    
    def test_check_message_rate_limit_within_limits(self):
        """Test multiple requests within rate limits."""
        client_id = "client1"
        
        # Should allow multiple requests within burst allowance
        for i in range(10):
            result = self.rate_limiter.check_message_rate_limit(client_id)
            assert result is True
    
    def test_check_message_rate_limit_exceeds_burst(self):
        """Test requests exceeding burst allowance."""
        client_id = "client1"
        
        # Use up burst allowance (60 + 10 = 70 tokens)
        for i in range(70):
            result = self.rate_limiter.check_message_rate_limit(client_id)
            assert result is True
        
        # Next request should be rate limited
        result = self.rate_limiter.check_message_rate_limit(client_id)
        assert result is False
    
    def test_check_message_rate_limit_custom_rate(self):
        """Test rate limiting with custom rate."""
        client_id = "client1"
        custom_rate = 30  # 0.5 per second
        
        result = self.rate_limiter.check_message_rate_limit(
            client_id, 
            custom_rate_per_minute=custom_rate
        )
        assert result is True
        
        # Check that custom rate was applied
        status = self.rate_limiter.get_rate_limit_status(client_id)
        assert status['tokens_capacity'] == custom_rate + self.rate_limiter.burst_allowance
    
    def test_check_connection_rate_limit_new_ip(self):
        """Test connection rate limit for new IP."""
        result = self.rate_limiter.check_connection_rate_limit("192.168.1.1")
        assert result is True
    
    def test_check_connection_rate_limit_within_limits(self):
        """Test multiple connections within limits."""
        ip = "192.168.1.1"
        max_connections = 5
        
        # Register connections up to limit
        for i in range(max_connections):
            self.rate_limiter.register_connection(ip)
            result = self.rate_limiter.check_connection_rate_limit(ip, max_connections)
            if i < max_connections - 1:
                assert result is True
            else:
                assert result is False  # At limit
    
    def test_check_connection_rate_limit_exceeds_limit(self):
        """Test connections exceeding limit."""
        ip = "192.168.1.1"
        max_connections = 3
        
        # Register connections up to limit
        for i in range(max_connections):
            self.rate_limiter.register_connection(ip)
        
        # Should not allow more connections
        result = self.rate_limiter.check_connection_rate_limit(ip, max_connections)
        assert result is False
    
    def test_register_and_unregister_connection(self):
        """Test connection registration and unregistration."""
        ip = "192.168.1.1"
        
        # Register connection
        self.rate_limiter.register_connection(ip)
        status = self.rate_limiter.get_connection_status(ip)
        assert status['current_connections'] == 1
        
        # Unregister connection
        self.rate_limiter.unregister_connection(ip)
        status = self.rate_limiter.get_connection_status(ip)
        assert status['current_connections'] == 0
    
    def test_unregister_connection_cleanup(self):
        """Test that unregistering all connections cleans up IP entry."""
        ip = "192.168.1.1"
        
        # Register and unregister connection
        self.rate_limiter.register_connection(ip)
        self.rate_limiter.unregister_connection(ip)
        
        # IP should be cleaned up
        assert ip not in self.rate_limiter._ip_connection_counts
    
    def test_unregister_connection_nonexistent(self):
        """Test unregistering connection for non-existent IP."""
        # Should not raise error
        self.rate_limiter.unregister_connection("192.168.1.1")
    
    def test_get_rate_limit_status_existing_client(self):
        """Test getting rate limit status for existing client."""
        client_id = "client1"
        
        # Make a request to create the client
        self.rate_limiter.check_message_rate_limit(client_id)
        
        status = self.rate_limiter.get_rate_limit_status(client_id)
        
        assert status is not None
        assert status['client_id'] == client_id
        assert 'tokens_available' in status
        assert 'tokens_capacity' in status
        assert 'refill_rate_per_second' in status
        assert 'violation_count' in status
        assert 'total_requests' in status
    
    def test_get_rate_limit_status_nonexistent_client(self):
        """Test getting rate limit status for non-existent client."""
        status = self.rate_limiter.get_rate_limit_status("nonexistent")
        assert status is None
    
    def test_get_connection_status(self):
        """Test getting connection status for IP."""
        ip = "192.168.1.1"
        
        # Register connection
        self.rate_limiter.register_connection(ip)
        
        status = self.rate_limiter.get_connection_status(ip)
        
        assert status['ip_address'] == ip
        assert status['current_connections'] == 1
        assert status['first_connection_time'] is not None
    
    def test_reset_client_rate_limit(self):
        """Test resetting client rate limit."""
        client_id = "client1"
        
        # Create client and use some tokens
        for i in range(5):
            self.rate_limiter.check_message_rate_limit(client_id)
        
        # Reset rate limit
        result = self.rate_limiter.reset_client_rate_limit(client_id)
        assert result is True
        
        # Check that tokens are restored
        status = self.rate_limiter.get_rate_limit_status(client_id)
        assert status['tokens_available'] == status['tokens_capacity']
        assert status['violation_count'] == 0
    
    def test_reset_client_rate_limit_nonexistent(self):
        """Test resetting rate limit for non-existent client."""
        result = self.rate_limiter.reset_client_rate_limit("nonexistent")
        assert result is False
    
    def test_update_client_rate_limit(self):
        """Test updating client rate limit."""
        client_id = "client1"
        
        # Create client
        self.rate_limiter.check_message_rate_limit(client_id)
        
        # Update rate limit
        new_rate = 120  # 2 per second
        result = self.rate_limiter.update_client_rate_limit(client_id, new_rate)
        assert result is True
        
        # Check that rate was updated
        status = self.rate_limiter.get_rate_limit_status(client_id)
        expected_capacity = new_rate + self.rate_limiter.burst_allowance
        assert status['tokens_capacity'] == expected_capacity
        assert status['refill_rate_per_second'] == 2.0
    
    def test_update_client_rate_limit_nonexistent(self):
        """Test updating rate limit for non-existent client."""
        result = self.rate_limiter.update_client_rate_limit("nonexistent", 120)
        assert result is False
    
    def test_get_all_clients(self):
        """Test getting status for all clients."""
        # Create multiple clients
        clients = ["client1", "client2", "client3"]
        for client in clients:
            self.rate_limiter.check_message_rate_limit(client)
        
        all_status = self.rate_limiter.get_all_clients()
        
        assert len(all_status) == 3
        for client in clients:
            assert client in all_status
            assert all_status[client]['client_id'] == client
    
    def test_get_all_connections(self):
        """Test getting status for all connections."""
        # Register connections from multiple IPs
        ips = ["192.168.1.1", "192.168.1.2", "10.0.0.1"]
        for ip in ips:
            self.rate_limiter.register_connection(ip)
        
        all_status = self.rate_limiter.get_all_connections()
        
        assert len(all_status) == 3
        for ip in ips:
            assert ip in all_status
            assert all_status[ip]['ip_address'] == ip
    
    def test_cleanup_old_entries(self):
        """Test cleanup of old rate limit entries."""
        client_id = "old_client"
        
        # Create client
        self.rate_limiter.check_message_rate_limit(client_id)
        
        # Manually set old violation time
        rate_info = self.rate_limiter._client_limits[client_id]
        rate_info.last_violation = datetime.now() - timedelta(hours=2)
        
        # Trigger cleanup
        self.rate_limiter._cleanup_old_entries()
        
        # Client should be cleaned up due to old violation
        assert client_id not in self.rate_limiter._client_limits
    
    @patch('time.time')
    def test_maybe_cleanup_interval(self, mock_time):
        """Test that cleanup only runs after interval."""
        mock_time.return_value = 0.0
        
        # Create limiter with short cleanup interval
        limiter = RateLimiter(cleanup_interval=10)
        
        # Should not cleanup immediately
        limiter._maybe_cleanup()
        
        # Advance time past interval
        mock_time.return_value = 15.0
        
        # Should trigger cleanup now
        with patch.object(limiter, '_cleanup_old_entries') as mock_cleanup:
            limiter._maybe_cleanup()
            mock_cleanup.assert_called_once()


class TestRateLimiterIntegration:
    """Test rate limiter integration scenarios."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rate_limiter = RateLimiter(
            default_rate_per_minute=60,
            burst_allowance=5
        )
    
    def test_rate_limiting_with_time_progression(self):
        """Test rate limiting behavior over time."""
        client_id = "client1"
        
        # Use up all tokens (60 + 5 = 65)
        success_count = 0
        for i in range(70):  # Try more than capacity to ensure we hit the limit
            result = self.rate_limiter.check_message_rate_limit(client_id)
            if result:
                success_count += 1
            else:
                break
        
        # Should have used up all tokens
        assert success_count == 65
        
        # Should be rate limited now
        result = self.rate_limiter.check_message_rate_limit(client_id)
        assert result is False
        
        # Wait a bit for tokens to refill (1 token per second)
        time.sleep(1.1)  # Wait for at least 1 token to be added
        
        # Should allow more requests after time passes
        result = self.rate_limiter.check_message_rate_limit(client_id)
        assert result is True
    
    def test_multiple_clients_independent_limits(self):
        """Test that multiple clients have independent rate limits."""
        client1 = "client1"
        client2 = "client2"
        
        # Use up client1's tokens
        for i in range(65):  # 60 + 5 burst
            result = self.rate_limiter.check_message_rate_limit(client1)
            assert result is True
        
        # Client1 should be rate limited
        result = self.rate_limiter.check_message_rate_limit(client1)
        assert result is False
        
        # Client2 should still have tokens
        result = self.rate_limiter.check_message_rate_limit(client2)
        assert result is True
    
    def test_connection_and_message_limits_independent(self):
        """Test that connection and message limits are independent."""
        ip = "192.168.1.1"
        client_id = "client1"
        
        # Register max connections
        for i in range(5):
            self.rate_limiter.register_connection(ip)
        
        # Should not allow more connections
        result = self.rate_limiter.check_connection_rate_limit(ip, 5)
        assert result is False
        
        # But message rate limiting should still work
        result = self.rate_limiter.check_message_rate_limit(client_id)
        assert result is True


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_create_message_rate_limiter(self):
        """Test creating message rate limiter."""
        limiter = create_message_rate_limiter(rate_per_minute=120, burst_allowance=20)
        
        assert limiter.default_rate_per_minute == 120
        assert limiter.burst_allowance == 20
    
    def test_create_connection_rate_limiter(self):
        """Test creating connection rate limiter."""
        limiter = create_connection_rate_limiter()
        
        assert limiter.default_rate_per_minute == 60
        assert limiter.burst_allowance == 0


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rate_limiter = RateLimiter()
    
    @patch('time.time')
    def test_zero_tokens_consumption(self, mock_time):
        """Test consuming zero tokens."""
        mock_time.return_value = 0.0
        bucket = TokenBucket(capacity=10, tokens=5.0, refill_rate=1.0, last_refill=0.0)
        
        result = bucket.consume(0)
        assert result is True
        assert abs(bucket.tokens - 5.0) < 0.001  # Should remain unchanged
    
    def test_negative_tokens_consumption(self):
        """Test consuming negative tokens (should be treated as 0)."""
        bucket = TokenBucket(capacity=10, tokens=5.0, refill_rate=1.0)
        
        result = bucket.consume(-1)
        assert result is True  # Should succeed (consuming 0 or less)
    
    @patch('time.time')
    def test_fractional_tokens(self, mock_time):
        """Test consuming fractional tokens."""
        mock_time.return_value = 0.0
        bucket = TokenBucket(capacity=10, tokens=5.5, refill_rate=1.0, last_refill=0.0)
        
        result = bucket.consume(2.5)
        assert result is True
        assert abs(bucket.tokens - 3.0) < 0.001
    
    def test_very_high_refill_rate(self):
        """Test with very high refill rate."""
        bucket = TokenBucket(capacity=1000, tokens=0.0, refill_rate=1000.0)
        
        # Even with high refill rate, should be capped at capacity
        time.sleep(0.01)  # Small delay to allow refill
        tokens = bucket.peek()
        assert tokens <= 1000.0
    
    def test_zero_capacity_bucket(self):
        """Test bucket with zero capacity."""
        bucket = TokenBucket(capacity=0, tokens=0.0, refill_rate=1.0)
        
        result = bucket.consume(1)
        assert result is False
        
        # Should remain at 0 even after refill
        time.sleep(0.01)
        tokens = bucket.peek()
        assert tokens == 0.0
    
    def test_thread_safety_simulation(self):
        """Test thread safety by simulating concurrent access."""
        import threading
        
        rate_limiter = RateLimiter(default_rate_per_minute=600)  # High rate for testing
        client_id = "concurrent_client"
        results = []
        
        def make_requests():
            for _ in range(10):
                result = rate_limiter.check_message_rate_limit(client_id)
                results.append(result)
        
        # Create multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=make_requests)
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Should have some successful requests
        assert any(results)
        # Should not crash or have inconsistent state
        status = rate_limiter.get_rate_limit_status(client_id)
        assert status is not None


class TestPerformance:
    """Test performance characteristics."""
    
    def test_large_number_of_clients(self):
        """Test performance with large number of clients."""
        rate_limiter = RateLimiter()
        
        # Create many clients
        num_clients = 1000
        for i in range(num_clients):
            client_id = f"client_{i}"
            result = rate_limiter.check_message_rate_limit(client_id)
            assert result is True
        
        # Should handle large number of clients efficiently
        all_status = rate_limiter.get_all_clients()
        assert len(all_status) == num_clients
    
    def test_rapid_requests(self):
        """Test handling rapid requests."""
        rate_limiter = RateLimiter(default_rate_per_minute=6000)  # High rate
        client_id = "rapid_client"
        
        # Make many rapid requests
        success_count = 0
        for i in range(1000):
            if rate_limiter.check_message_rate_limit(client_id):
                success_count += 1
        
        # Should handle rapid requests without errors
        assert success_count > 0
        
        # Status should be consistent
        status = rate_limiter.get_rate_limit_status(client_id)
        assert status is not None
        assert status['total_requests'] == success_count
"""
Unit tests for ConnectionLimiter class.
"""

import socket
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import pytest

from chat_app.server.security.connection_limiter import (
    ConnectionLimiter,
    ConnectionInfo,
    IPConnectionTracker,
    ConnectionStatus
)
from chat_app.shared.exceptions import (
    ConnectionLimitExceededError,
    ConnectionTimeoutError
)


class TestConnectionInfo:
    """Test cases for ConnectionInfo class."""
    
    def test_connection_info_creation(self):
        """Test creating a ConnectionInfo instance."""
        conn_info = ConnectionInfo(ip_address="192.168.1.1")
        
        assert conn_info.ip_address == "192.168.1.1"
        assert isinstance(conn_info.connection_time, datetime)
        assert isinstance(conn_info.last_activity, datetime)
        assert conn_info.socket_obj is None
        assert conn_info.connection_id is None
    
    def test_connection_info_with_socket(self):
        """Test creating ConnectionInfo with socket object."""
        mock_socket = Mock(spec=socket.socket)
        conn_info = ConnectionInfo(
            ip_address="192.168.1.1",
            socket_obj=mock_socket,
            connection_id="test-conn-1"
        )
        
        assert conn_info.socket_obj == mock_socket
        assert conn_info.connection_id == "test-conn-1"
    
    def test_update_activity(self):
        """Test updating connection activity."""
        conn_info = ConnectionInfo(ip_address="192.168.1.1")
        original_activity = conn_info.last_activity
        
        time.sleep(0.01)  # Small delay to ensure time difference
        conn_info.update_activity()
        
        assert conn_info.last_activity > original_activity
    
    def test_connection_duration(self):
        """Test connection duration calculation."""
        conn_info = ConnectionInfo(ip_address="192.168.1.1")
        
        # Duration should be very small for new connection
        duration = conn_info.connection_duration
        assert isinstance(duration, timedelta)
        assert duration.total_seconds() < 1.0
    
    def test_idle_duration(self):
        """Test idle duration calculation."""
        conn_info = ConnectionInfo(ip_address="192.168.1.1")
        
        # Initially, idle duration should be very small
        idle_duration = conn_info.idle_duration
        assert isinstance(idle_duration, timedelta)
        assert idle_duration.total_seconds() < 1.0


class TestIPConnectionTracker:
    """Test cases for IPConnectionTracker class."""
    
    def test_tracker_creation(self):
        """Test creating an IPConnectionTracker instance."""
        tracker = IPConnectionTracker(ip_address="192.168.1.1")
        
        assert tracker.ip_address == "192.168.1.1"
        assert len(tracker.active_connections) == 0
        assert len(tracker.connection_history) == 0
        assert tracker.total_connections == 0
        assert tracker.last_connection_attempt is None
        assert tracker.blocked_until is None
    
    def test_add_connection(self):
        """Test adding a connection to tracker."""
        tracker = IPConnectionTracker(ip_address="192.168.1.1")
        
        tracker.add_connection("conn-1")
        
        assert "conn-1" in tracker.active_connections
        assert len(tracker.connection_history) == 1
        assert tracker.total_connections == 1
        assert tracker.last_connection_attempt is not None
    
    def test_remove_connection(self):
        """Test removing a connection from tracker."""
        tracker = IPConnectionTracker(ip_address="192.168.1.1")
        tracker.add_connection("conn-1")
        tracker.add_connection("conn-2")
        
        tracker.remove_connection("conn-1")
        
        assert "conn-1" not in tracker.active_connections
        assert "conn-2" in tracker.active_connections
        assert tracker.get_connection_count() == 1
    
    def test_get_connection_count(self):
        """Test getting active connection count."""
        tracker = IPConnectionTracker(ip_address="192.168.1.1")
        
        assert tracker.get_connection_count() == 0
        
        tracker.add_connection("conn-1")
        assert tracker.get_connection_count() == 1
        
        tracker.add_connection("conn-2")
        assert tracker.get_connection_count() == 2
        
        tracker.remove_connection("conn-1")
        assert tracker.get_connection_count() == 1
    
    def test_get_recent_connection_count(self):
        """Test getting recent connection count."""
        tracker = IPConnectionTracker(ip_address="192.168.1.1")
        
        # Add some connections
        tracker.add_connection("conn-1")
        tracker.add_connection("conn-2")
        
        # All connections should be recent
        assert tracker.get_recent_connection_count(minutes=5) == 2
        assert tracker.get_recent_connection_count(minutes=1) == 2
    
    def test_blocking_functionality(self):
        """Test IP blocking functionality."""
        tracker = IPConnectionTracker(ip_address="192.168.1.1")
        
        # Initially not blocked
        assert not tracker.is_blocked()
        
        # Block temporarily
        tracker.block_temporarily(duration_minutes=1)
        assert tracker.is_blocked()
        assert tracker.blocked_until is not None
        
        # Test with past time (should not be blocked)
        tracker.blocked_until = datetime.now() - timedelta(minutes=1)
        assert not tracker.is_blocked()


class TestConnectionLimiter:
    """Test cases for ConnectionLimiter class."""
    
    def test_connection_limiter_creation(self):
        """Test creating a ConnectionLimiter instance."""
        limiter = ConnectionLimiter(
            max_connections_per_ip=3,
            max_total_connections=50,
            connection_timeout_seconds=20
        )
        
        assert limiter.max_connections_per_ip == 3
        assert limiter.max_total_connections == 50
        assert limiter.connection_timeout_seconds == 20
        assert limiter.total_connections_created == 0
        assert limiter.total_connections_rejected == 0
    
    def test_can_accept_connection_success(self):
        """Test successful connection acceptance check."""
        limiter = ConnectionLimiter(max_connections_per_ip=5)
        
        can_accept, reason = limiter.can_accept_connection("192.168.1.1")
        
        assert can_accept is True
        assert reason is None
    
    def test_can_accept_connection_per_ip_limit(self):
        """Test connection rejection due to per-IP limit."""
        limiter = ConnectionLimiter(max_connections_per_ip=2)
        
        # Register maximum connections for IP
        limiter.register_connection("conn-1", "192.168.1.1")
        limiter.register_connection("conn-2", "192.168.1.1")
        
        # Next connection should be rejected
        can_accept, reason = limiter.can_accept_connection("192.168.1.1")
        
        assert can_accept is False
        assert "Too many connections from IP" in reason
    
    def test_can_accept_connection_total_limit(self):
        """Test connection rejection due to total connection limit."""
        limiter = ConnectionLimiter(max_total_connections=2)
        
        # Register maximum total connections
        limiter.register_connection("conn-1", "192.168.1.1")
        limiter.register_connection("conn-2", "192.168.1.2")
        
        # Next connection should be rejected
        can_accept, reason = limiter.can_accept_connection("192.168.1.3")
        
        assert can_accept is False
        assert "Server at maximum capacity" in reason
    
    def test_can_accept_connection_rate_limit(self):
        """Test connection rejection due to rate limiting."""
        limiter = ConnectionLimiter(max_connections_per_minute=2)
        
        # Simulate rapid connections from same IP
        for i in range(2):
            limiter.register_connection(f"conn-{i}", "192.168.1.1")
            limiter.unregister_connection(f"conn-{i}")
        
        # Next connection should trigger rate limit
        can_accept, reason = limiter.can_accept_connection("192.168.1.1")
        
        assert can_accept is False
        assert "Connection rate limit exceeded" in reason
    
    def test_register_connection_success(self):
        """Test successful connection registration."""
        limiter = ConnectionLimiter()
        mock_socket = Mock(spec=socket.socket)
        
        conn_info = limiter.register_connection("conn-1", "192.168.1.1", mock_socket)
        
        assert conn_info.connection_id == "conn-1"
        assert conn_info.ip_address == "192.168.1.1"
        assert conn_info.socket_obj == mock_socket
        assert limiter.total_connections_created == 1
    
    def test_register_connection_limit_exceeded(self):
        """Test connection registration when limits are exceeded."""
        limiter = ConnectionLimiter(max_connections_per_ip=1)
        
        # Register first connection
        limiter.register_connection("conn-1", "192.168.1.1")
        
        # Second connection should raise exception
        with pytest.raises(ConnectionLimitExceededError):
            limiter.register_connection("conn-2", "192.168.1.1")
        
        assert limiter.total_connections_rejected == 1
    
    def test_unregister_connection_success(self):
        """Test successful connection unregistration."""
        limiter = ConnectionLimiter()
        
        # Register and then unregister connection
        limiter.register_connection("conn-1", "192.168.1.1")
        result = limiter.unregister_connection("conn-1")
        
        assert result is True
        assert limiter.get_connection_info("conn-1") is None
    
    def test_unregister_connection_not_found(self):
        """Test unregistering non-existent connection."""
        limiter = ConnectionLimiter()
        
        result = limiter.unregister_connection("non-existent")
        
        assert result is False
    
    def test_update_connection_activity(self):
        """Test updating connection activity."""
        limiter = ConnectionLimiter()
        
        # Register connection
        conn_info = limiter.register_connection("conn-1", "192.168.1.1")
        original_activity = conn_info.last_activity
        
        time.sleep(0.01)  # Small delay
        result = limiter.update_connection_activity("conn-1")
        
        assert result is True
        assert conn_info.last_activity > original_activity
    
    def test_update_connection_activity_not_found(self):
        """Test updating activity for non-existent connection."""
        limiter = ConnectionLimiter()
        
        result = limiter.update_connection_activity("non-existent")
        
        assert result is False
    
    def test_get_connection_info(self):
        """Test getting connection information."""
        limiter = ConnectionLimiter()
        
        # Register connection
        original_info = limiter.register_connection("conn-1", "192.168.1.1")
        retrieved_info = limiter.get_connection_info("conn-1")
        
        assert retrieved_info == original_info
        assert retrieved_info.connection_id == "conn-1"
        assert retrieved_info.ip_address == "192.168.1.1"
    
    def test_get_connections_by_ip(self):
        """Test getting connections by IP address."""
        limiter = ConnectionLimiter()
        
        # Register connections from different IPs
        limiter.register_connection("conn-1", "192.168.1.1")
        limiter.register_connection("conn-2", "192.168.1.1")
        limiter.register_connection("conn-3", "192.168.1.2")
        
        connections_ip1 = limiter.get_connections_by_ip("192.168.1.1")
        connections_ip2 = limiter.get_connections_by_ip("192.168.1.2")
        
        assert len(connections_ip1) == 2
        assert len(connections_ip2) == 1
        assert "conn-1" in connections_ip1
        assert "conn-2" in connections_ip1
        assert "conn-3" in connections_ip2
    
    def test_get_idle_connections(self):
        """Test getting idle connections."""
        limiter = ConnectionLimiter()
        
        # Register connection and make it appear idle
        conn_info = limiter.register_connection("conn-1", "192.168.1.1")
        conn_info.last_activity = datetime.now() - timedelta(minutes=35)
        
        idle_connections = limiter.get_idle_connections(idle_threshold_minutes=30)
        
        assert len(idle_connections) == 1
        assert "conn-1" in idle_connections
    
    def test_cleanup_idle_connections(self):
        """Test cleaning up idle connections."""
        limiter = ConnectionLimiter()
        mock_socket = Mock(spec=socket.socket)
        
        # Register connection and make it appear idle
        conn_info = limiter.register_connection("conn-1", "192.168.1.1", mock_socket)
        conn_info.last_activity = datetime.now() - timedelta(minutes=35)
        
        cleanup_count = limiter.cleanup_idle_connections(idle_threshold_minutes=30)
        
        assert cleanup_count == 1
        assert limiter.get_connection_info("conn-1") is None
        mock_socket.close.assert_called_once()
    
    def test_apply_secure_timeout(self):
        """Test applying secure timeout to socket."""
        limiter = ConnectionLimiter(connection_timeout_seconds=25)
        mock_socket = Mock(spec=socket.socket)
        
        limiter.apply_secure_timeout(mock_socket)
        
        mock_socket.settimeout.assert_called_once_with(25)
        mock_socket.setsockopt.assert_called()
    
    def test_apply_secure_timeout_error(self):
        """Test error handling in secure timeout application."""
        limiter = ConnectionLimiter()
        mock_socket = Mock(spec=socket.socket)
        mock_socket.settimeout.side_effect = OSError("Socket error")
        
        with pytest.raises(ConnectionTimeoutError):
            limiter.apply_secure_timeout(mock_socket)
    
    def test_get_statistics(self):
        """Test getting connection limiter statistics."""
        limiter = ConnectionLimiter()
        
        # Register some connections
        limiter.register_connection("conn-1", "192.168.1.1")
        limiter.register_connection("conn-2", "192.168.1.2")
        
        stats = limiter.get_statistics()
        
        assert stats['current_connections'] == 2
        assert stats['total_connections_created'] == 2
        assert stats['total_connections_rejected'] == 0
        assert 'uptime_seconds' in stats
        assert 'ip_statistics' in stats
        assert len(stats['ip_statistics']) == 2
    
    def test_is_ip_blocked(self):
        """Test checking if IP is blocked."""
        limiter = ConnectionLimiter()
        
        # Initially not blocked
        assert not limiter.is_ip_blocked("192.168.1.1")
        
        # Block IP by exceeding rate limit
        limiter._ip_trackers["192.168.1.1"].block_temporarily(5)
        
        assert limiter.is_ip_blocked("192.168.1.1")
    
    def test_unblock_ip(self):
        """Test manually unblocking an IP."""
        limiter = ConnectionLimiter()
        
        # Block IP
        limiter._ip_trackers["192.168.1.1"].block_temporarily(5)
        assert limiter.is_ip_blocked("192.168.1.1")
        
        # Unblock IP
        result = limiter.unblock_ip("192.168.1.1")
        
        assert result is True
        assert not limiter.is_ip_blocked("192.168.1.1")
    
    def test_unblock_ip_not_blocked(self):
        """Test unblocking an IP that wasn't blocked."""
        limiter = ConnectionLimiter()
        
        result = limiter.unblock_ip("192.168.1.1")
        
        assert result is False
    
    def test_shutdown(self):
        """Test connection limiter shutdown."""
        limiter = ConnectionLimiter()
        mock_socket = Mock(spec=socket.socket)
        
        # Register connection with socket
        limiter.register_connection("conn-1", "192.168.1.1", mock_socket)
        
        limiter.shutdown()
        
        # Socket should be closed
        mock_socket.close.assert_called_once()
        
        # Data structures should be cleared
        assert len(limiter._connections) == 0
        assert len(limiter._ip_trackers) == 0
        assert len(limiter._blocked_ips) == 0
    
    def test_thread_safety(self):
        """Test thread safety of connection limiter operations."""
        limiter = ConnectionLimiter(max_connections_per_ip=20)  # Increase limit for test
        results = []
        errors = []
        
        def register_connections(start_id: int, count: int):
            """Register multiple connections in a thread."""
            try:
                for i in range(count):
                    conn_id = f"conn-{start_id}-{i}"
                    # Use unique IP for each connection to avoid per-IP limits
                    ip = f"192.168.{(start_id % 254) + 1}.{(i % 254) + 1}"
                    limiter.register_connection(conn_id, ip)
                    results.append(conn_id)
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=register_connections, args=(i, 10))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0  # No errors should occur
        assert len(results) == 50  # All connections should be registered
        assert len(set(results)) == 50  # All connection IDs should be unique
    
    def test_blocked_ip_cleanup(self):
        """Test that blocked IPs are cleaned up when connections are removed."""
        limiter = ConnectionLimiter(max_connections_per_minute=2)
        
        # Manually trigger rate limit block by adding connections to history
        tracker = limiter._ip_trackers["192.168.1.1"]
        # Add enough connections to trigger rate limit
        for _ in range(3):
            tracker.connection_history.append(datetime.now())
        
        # This should trigger blocking
        can_accept, _ = limiter.can_accept_connection("192.168.1.1")
        assert not can_accept
        
        # IP should be in blocked set
        assert "192.168.1.1" in limiter._blocked_ips
        
        # Manually unblock to test cleanup functionality
        result = limiter.unblock_ip("192.168.1.1")
        assert result is True
        assert "192.168.1.1" not in limiter._blocked_ips


class TestConnectionLimiterIntegration:
    """Integration tests for ConnectionLimiter with real socket operations."""
    
    def test_real_socket_timeout_configuration(self):
        """Test timeout configuration with real socket."""
        limiter = ConnectionLimiter(connection_timeout_seconds=5)
        
        # Create a real socket
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        try:
            limiter.apply_secure_timeout(test_socket)
            
            # Verify timeout was set
            timeout = test_socket.gettimeout()
            assert timeout == 5.0
            
        finally:
            test_socket.close()
    
    def test_connection_lifecycle_with_socket(self):
        """Test complete connection lifecycle with socket object."""
        limiter = ConnectionLimiter()
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        try:
            # Register connection
            conn_info = limiter.register_connection("test-conn", "127.0.0.1", test_socket)
            assert conn_info.socket_obj == test_socket
            
            # Update activity
            assert limiter.update_connection_activity("test-conn")
            
            # Get connection info
            retrieved_info = limiter.get_connection_info("test-conn")
            assert retrieved_info.socket_obj == test_socket
            
            # Unregister connection
            assert limiter.unregister_connection("test-conn")
            
        finally:
            test_socket.close()


# Test fixtures and utilities
@pytest.fixture
def connection_limiter():
    """Fixture providing a fresh ConnectionLimiter instance."""
    return ConnectionLimiter(
        max_connections_per_ip=5,
        max_total_connections=100,
        connection_timeout_seconds=30
    )


@pytest.fixture
def mock_socket():
    """Fixture providing a mock socket object."""
    return Mock(spec=socket.socket)


# Backward compatibility test
def test_connection_status_alias():
    """Test that ConnectionStatus is an alias for ConnectionInfo."""
    assert ConnectionStatus is ConnectionInfo
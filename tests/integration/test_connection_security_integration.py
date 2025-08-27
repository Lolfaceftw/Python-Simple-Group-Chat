"""
Integration tests for connection security controls.
"""

import socket
import threading
import time
from unittest.mock import Mock
import pytest

from chat_app.server.security.connection_limiter import ConnectionLimiter
from chat_app.shared.exceptions import ConnectionLimitExceededError, ConnectionTimeoutError


class TestConnectionSecurityIntegration:
    """Integration tests for connection security controls."""
    
    def test_connection_limiter_with_real_sockets(self):
        """Test connection limiter with real socket objects."""
        limiter = ConnectionLimiter(
            max_connections_per_ip=2,
            connection_timeout_seconds=5
        )
        
        sockets = []
        try:
            # Create real sockets
            for i in range(2):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sockets.append(sock)
                
                # Apply secure timeout
                limiter.apply_secure_timeout(sock)
                
                # Register connection
                conn_info = limiter.register_connection(
                    f"conn-{i}", "127.0.0.1", sock
                )
                
                assert conn_info.socket_obj == sock
                assert sock.gettimeout() == 5.0
            
            # Third connection should be rejected
            with pytest.raises(ConnectionLimitExceededError):
                sock3 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sockets.append(sock3)
                limiter.register_connection("conn-3", "127.0.0.1", sock3)
            
            # Verify statistics
            stats = limiter.get_statistics()
            assert stats['current_connections'] == 2
            assert stats['total_connections_created'] == 2
            assert stats['total_connections_rejected'] == 1
            
        finally:
            # Clean up sockets
            for sock in sockets:
                try:
                    sock.close()
                except:
                    pass
            limiter.shutdown()
    
    def test_concurrent_connection_management(self):
        """Test concurrent connection registration and cleanup."""
        limiter = ConnectionLimiter(
            max_connections_per_ip=10,
            max_total_connections=50
        )
        
        successful_connections = []
        failed_connections = []
        
        def worker_thread(thread_id: int):
            """Worker thread that registers and unregisters connections."""
            try:
                connections = []
                
                # Register multiple connections
                for i in range(5):
                    conn_id = f"thread-{thread_id}-conn-{i}"
                    ip = f"192.168.{thread_id}.{i + 1}"
                    
                    conn_info = limiter.register_connection(conn_id, ip)
                    connections.append(conn_id)
                    successful_connections.append(conn_id)
                    
                    # Update activity
                    limiter.update_connection_activity(conn_id)
                
                # Wait a bit
                time.sleep(0.1)
                
                # Unregister connections
                for conn_id in connections:
                    limiter.unregister_connection(conn_id)
                    
            except Exception as e:
                failed_connections.append(str(e))
        
        # Start multiple worker threads
        threads = []
        for i in range(8):
            thread = threading.Thread(target=worker_thread, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify results
        assert len(failed_connections) == 0, f"Failed connections: {failed_connections}"
        assert len(successful_connections) == 40  # 8 threads * 5 connections each
        
        # Verify final state
        stats = limiter.get_statistics()
        assert stats['current_connections'] == 0  # All should be unregistered
        assert stats['total_connections_created'] == 40
        
        limiter.shutdown()
    
    def test_rate_limiting_and_blocking_integration(self):
        """Test rate limiting and IP blocking integration."""
        limiter = ConnectionLimiter(
            max_connections_per_minute=3,
            temporary_block_duration_minutes=1
        )
        
        ip_address = "192.168.1.100"
        
        # Register and unregister connections rapidly to trigger rate limit
        for i in range(3):
            conn_id = f"rapid-conn-{i}"
            limiter.register_connection(conn_id, ip_address)
            limiter.unregister_connection(conn_id)
        
        # Next connection should trigger rate limit and blocking
        can_accept, reason = limiter.can_accept_connection(ip_address)
        assert not can_accept
        assert "rate limit exceeded" in reason.lower()
        assert limiter.is_ip_blocked(ip_address)
        
        # Verify connection is rejected
        with pytest.raises(ConnectionLimitExceededError):
            limiter.register_connection("blocked-conn", ip_address)
        
        # Manually unblock IP
        assert limiter.unblock_ip(ip_address) is True
        assert not limiter.is_ip_blocked(ip_address)
        
        # Clear the connection history to allow new connections
        limiter._ip_trackers[ip_address].connection_history.clear()
        
        # Should be able to connect again
        can_accept, reason = limiter.can_accept_connection(ip_address)
        assert can_accept
        assert reason is None
        
        limiter.shutdown()
    
    def test_idle_connection_cleanup_integration(self):
        """Test idle connection cleanup with real socket objects."""
        limiter = ConnectionLimiter()
        
        sockets = []
        connection_ids = []
        
        try:
            # Create connections with sockets
            for i in range(3):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sockets.append(sock)
                
                conn_id = f"idle-conn-{i}"
                connection_ids.append(conn_id)
                
                conn_info = limiter.register_connection(conn_id, f"192.168.1.{i+1}", sock)
                
                # Make first connection appear idle
                if i == 0:
                    from datetime import datetime, timedelta
                    conn_info.last_activity = datetime.now() - timedelta(minutes=35)
            
            # Verify initial state
            assert len(limiter._connections) == 3
            
            # Get idle connections
            idle_connections = limiter.get_idle_connections(idle_threshold_minutes=30)
            assert len(idle_connections) == 1
            assert "idle-conn-0" in idle_connections
            
            # Cleanup idle connections
            cleanup_count = limiter.cleanup_idle_connections(idle_threshold_minutes=30)
            assert cleanup_count == 1
            
            # Verify cleanup
            assert len(limiter._connections) == 2
            assert limiter.get_connection_info("idle-conn-0") is None
            assert limiter.get_connection_info("idle-conn-1") is not None
            assert limiter.get_connection_info("idle-conn-2") is not None
            
        finally:
            # Clean up remaining sockets
            for sock in sockets:
                try:
                    sock.close()
                except:
                    pass
            limiter.shutdown()
    
    def test_error_handling_and_information_leakage_prevention(self):
        """Test error handling prevents information leakage."""
        limiter = ConnectionLimiter(max_total_connections=1)
        
        # Register one connection to reach limit
        limiter.register_connection("conn-1", "192.168.1.1")
        
        # Try to register another connection
        try:
            limiter.register_connection("conn-2", "192.168.1.2")
            assert False, "Should have raised ConnectionLimitExceededError"
        except ConnectionLimitExceededError as e:
            # Error message should be generic, not revealing internal details
            error_msg = str(e).lower()
            assert "server at maximum capacity" in error_msg
            # Should not contain internal implementation details
            assert "dict" not in error_msg
            assert "thread" not in error_msg
            assert "lock" not in error_msg
        
        # Test socket timeout error handling
        mock_socket = Mock()
        mock_socket.settimeout.side_effect = OSError("Network error")
        
        try:
            limiter.apply_secure_timeout(mock_socket)
            assert False, "Should have raised ConnectionTimeoutError"
        except ConnectionTimeoutError as e:
            # Error should be wrapped and sanitized
            error_msg = str(e)
            assert "Failed to configure connection timeout" in error_msg
            # Should not expose raw system error details that could leak info
            assert len(error_msg) < 200  # Reasonable length limit
        
        limiter.shutdown()
    
    def test_statistics_and_monitoring_integration(self):
        """Test statistics collection for monitoring purposes."""
        limiter = ConnectionLimiter(
            max_connections_per_ip=3,
            max_total_connections=10
        )
        
        # Create various connection scenarios
        limiter.register_connection("conn-1", "192.168.1.1")
        limiter.register_connection("conn-2", "192.168.1.1")
        limiter.register_connection("conn-3", "192.168.1.2")
        
        # Try to exceed per-IP limit
        try:
            limiter.register_connection("conn-4", "192.168.1.1")
            limiter.register_connection("conn-5", "192.168.1.1")  # This should fail
        except ConnectionLimitExceededError:
            pass  # Expected
        
        # Get comprehensive statistics
        stats = limiter.get_statistics()
        
        # Verify statistics structure and content
        assert 'uptime_seconds' in stats
        assert 'current_connections' in stats
        assert 'total_connections_created' in stats
        assert 'total_connections_rejected' in stats
        assert 'ip_statistics' in stats
        
        assert stats['current_connections'] == 4  # 3 successful + 1 that succeeded before limit
        assert stats['total_connections_created'] == 4
        assert stats['total_connections_rejected'] == 1
        
        # Verify per-IP statistics
        ip_stats = stats['ip_statistics']
        assert '192.168.1.1' in ip_stats
        assert '192.168.1.2' in ip_stats
        
        ip1_stats = ip_stats['192.168.1.1']
        assert ip1_stats['active_connections'] == 3
        assert ip1_stats['total_connections'] == 3  # Only successful connections are tracked in total
        
        ip2_stats = ip_stats['192.168.1.2']
        assert ip2_stats['active_connections'] == 1
        assert ip2_stats['total_connections'] == 1
        
        limiter.shutdown()


if __name__ == "__main__":
    # Run a simple test if executed directly
    test = TestConnectionSecurityIntegration()
    test.test_connection_limiter_with_real_sockets()
    print("Integration test passed!")
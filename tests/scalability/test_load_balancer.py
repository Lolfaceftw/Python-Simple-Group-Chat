"""
Load Balancer Tests

Tests for the load balancing functionality including different algorithms,
health checking, and server management.
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from chat_app.server.scalability.load_balancer import (
    LoadBalancer,
    LoadBalancingStrategy,
    ServerNode,
    RoundRobinAlgorithm,
    LeastConnectionsAlgorithm,
    WeightedAlgorithm,
    RandomAlgorithm,
    LeastResponseTimeAlgorithm
)
from chat_app.shared.exceptions import LoadBalancerError


class TestServerNode:
    """Test ServerNode functionality."""
    
    def test_server_node_creation(self):
        """Test server node creation."""
        node = ServerNode(
            host="127.0.0.1",
            port=8080,
            weight=100,
            max_connections=1000
        )
        
        assert node.host == "127.0.0.1"
        assert node.port == 8080
        assert node.weight == 100
        assert node.max_connections == 1000
        assert node.current_connections == 0
        assert node.is_healthy is True
        assert node.connection_ratio == 0.0
        assert node.failure_rate == 0.0
    
    def test_connection_management(self):
        """Test connection increment/decrement."""
        node = ServerNode("127.0.0.1", 8080, max_connections=2)
        
        # Test increment
        assert node.increment_connections() is True
        assert node.current_connections == 1
        assert node.total_requests == 1
        
        assert node.increment_connections() is True
        assert node.current_connections == 2
        
        # Test at capacity
        assert node.increment_connections() is False
        assert node.current_connections == 2
        
        # Test decrement
        node.decrement_connections()
        assert node.current_connections == 1
        
        node.decrement_connections()
        assert node.current_connections == 0
        
        # Test decrement at zero
        node.decrement_connections()
        assert node.current_connections == 0
    
    def test_health_update(self):
        """Test health status updates."""
        node = ServerNode("127.0.0.1", 8080)
        
        # Test health update
        node.update_health(False, 100.0)
        assert node.is_healthy is False
        assert node.response_time_ms == 100.0
        assert node.last_health_check is not None
        
        # Test response time averaging
        node.update_health(True, 200.0)
        assert node.is_healthy is True
        # Should be exponential moving average: 100 * 0.8 + 200 * 0.2 = 120
        assert node.response_time_ms == 120.0
    
    def test_failure_tracking(self):
        """Test failure rate tracking."""
        node = ServerNode("127.0.0.1", 8080)
        
        # Add some requests
        node.increment_connections()
        node.decrement_connections()
        node.increment_connections()
        node.decrement_connections()
        
        assert node.total_requests == 2
        assert node.failed_requests == 0
        assert node.failure_rate == 0.0
        
        # Record failures
        node.record_failure()
        assert node.failed_requests == 1
        assert node.failure_rate == 50.0
        
        node.record_failure()
        assert node.failed_requests == 2
        assert node.failure_rate == 100.0


class TestLoadBalancingAlgorithms:
    """Test load balancing algorithms."""
    
    def test_round_robin_algorithm(self):
        """Test round-robin algorithm."""
        algorithm = RoundRobinAlgorithm()
        
        servers = [
            ServerNode("host1", 8080),
            ServerNode("host2", 8080),
            ServerNode("host3", 8080)
        ]
        
        # Test round-robin selection
        selected = []
        for _ in range(6):
            server = algorithm.select_server(servers)
            selected.append(server.host)
        
        expected = ["host1", "host2", "host3", "host1", "host2", "host3"]
        assert selected == expected
    
    def test_least_connections_algorithm(self):
        """Test least connections algorithm."""
        algorithm = LeastConnectionsAlgorithm()
        
        servers = [
            ServerNode("host1", 8080),
            ServerNode("host2", 8080),
            ServerNode("host3", 8080)
        ]
        
        # Set different connection counts
        servers[0].current_connections = 5
        servers[1].current_connections = 2
        servers[2].current_connections = 8
        
        # Should select server with least connections (host2)
        selected = algorithm.select_server(servers)
        assert selected.host == "host2"
    
    def test_weighted_algorithm(self):
        """Test weighted algorithm."""
        algorithm = WeightedAlgorithm()
        
        servers = [
            ServerNode("host1", 8080, weight=100),
            ServerNode("host2", 8080, weight=200),  # Higher weight
            ServerNode("host3", 8080, weight=50)
        ]
        
        # Set same connection ratios
        for server in servers:
            server.current_connections = 1
            server.max_connections = 10
        
        # Should prefer higher weight server
        selected = algorithm.select_server(servers)
        assert selected.host == "host2"
    
    def test_random_algorithm(self):
        """Test random algorithm."""
        algorithm = RandomAlgorithm()
        
        servers = [
            ServerNode("host1", 8080),
            ServerNode("host2", 8080),
            ServerNode("host3", 8080)
        ]
        
        # Test that it returns one of the servers
        selected = algorithm.select_server(servers)
        assert selected in servers
        
        # Test with empty list
        assert algorithm.select_server([]) is None
    
    def test_least_response_time_algorithm(self):
        """Test least response time algorithm."""
        algorithm = LeastResponseTimeAlgorithm()
        
        servers = [
            ServerNode("host1", 8080),
            ServerNode("host2", 8080),
            ServerNode("host3", 8080)
        ]
        
        # Set different response times
        servers[0].response_time_ms = 100.0
        servers[1].response_time_ms = 50.0   # Fastest
        servers[2].response_time_ms = 200.0
        
        # Should select server with lowest response time
        selected = algorithm.select_server(servers)
        assert selected.host == "host2"
        
        # Test fallback to least connections when no response times
        servers_no_times = [
            ServerNode("host1", 8080),
            ServerNode("host2", 8080)
        ]
        servers_no_times[0].current_connections = 5
        servers_no_times[1].current_connections = 2
        
        selected = algorithm.select_server(servers_no_times)
        assert selected.host == "host2"


class TestLoadBalancer:
    """Test LoadBalancer functionality."""
    
    def test_load_balancer_creation(self):
        """Test load balancer creation."""
        lb = LoadBalancer(
            strategy=LoadBalancingStrategy.ROUND_ROBIN,
            health_check_interval=30,
            health_check_timeout=5
        )
        
        assert lb.strategy == LoadBalancingStrategy.ROUND_ROBIN
        assert lb.health_check_interval == 30
        assert lb.health_check_timeout == 5
        assert len(lb._servers) == 0
    
    def test_server_management(self):
        """Test adding and removing servers."""
        lb = LoadBalancer()
        
        # Test adding server
        server_id = lb.add_server("127.0.0.1", 8080, weight=100, max_connections=1000)
        assert server_id == "127.0.0.1:8080"
        assert len(lb._servers) == 1
        
        server = lb._servers[server_id]
        assert server.host == "127.0.0.1"
        assert server.port == 8080
        assert server.weight == 100
        assert server.max_connections == 1000
        
        # Test duplicate server
        with pytest.raises(LoadBalancerError):
            lb.add_server("127.0.0.1", 8080)
        
        # Test removing server
        assert lb.remove_server(server_id) is True
        assert len(lb._servers) == 0
        
        # Test removing non-existent server
        assert lb.remove_server("nonexistent") is False
    
    def test_connection_assignment(self):
        """Test connection assignment."""
        lb = LoadBalancer(strategy=LoadBalancingStrategy.ROUND_ROBIN)
        
        # Add servers
        lb.add_server("host1", 8080, max_connections=2)
        lb.add_server("host2", 8080, max_connections=2)
        
        # Test connection assignment
        result1 = lb.get_server_for_connection()
        assert result1 is not None
        server_id1, server1 = result1
        assert server1.current_connections == 1
        
        result2 = lb.get_server_for_connection()
        assert result2 is not None
        server_id2, server2 = result2
        assert server_id2 != server_id1  # Should be different due to round-robin
        
        # Test connection release
        assert lb.release_connection(server_id1) is True
        assert server1.current_connections == 0
        
        # Test releasing non-existent connection
        assert lb.release_connection("nonexistent") is False
    
    def test_connection_limits(self):
        """Test connection limits."""
        lb = LoadBalancer()
        
        # Add server with low limit
        lb.add_server("127.0.0.1", 8080, max_connections=1)
        
        # Get first connection
        result1 = lb.get_server_for_connection()
        assert result1 is not None
        
        # Try to get second connection (should fail)
        result2 = lb.get_server_for_connection()
        assert result2 is None
    
    def test_failure_recording(self):
        """Test failure recording."""
        lb = LoadBalancer()
        
        server_id = lb.add_server("127.0.0.1", 8080)
        server = lb._servers[server_id]
        
        # Record failures
        lb.record_failure(server_id)
        assert server.failed_requests == 1
        
        # Record many failures to trigger unhealthy status
        for _ in range(20):
            server.increment_connections()
            server.decrement_connections()
            lb.record_failure(server_id)
        
        # Server should be marked unhealthy due to high failure rate
        assert server.is_healthy is False
    
    def test_statistics(self):
        """Test statistics collection."""
        lb = LoadBalancer()
        
        # Add servers
        server_id1 = lb.add_server("host1", 8080, weight=100)
        server_id2 = lb.add_server("host2", 8080, weight=200)
        
        # Get connections
        lb.get_server_for_connection()
        lb.get_server_for_connection()
        
        # Record some failures
        lb.record_failure(server_id1)
        
        stats = lb.get_statistics()
        
        assert stats['strategy'] == 'round_robin'
        assert stats['total_servers'] == 2
        assert stats['healthy_servers'] == 2
        assert stats['total_connections'] == 2
        assert stats['total_requests'] == 2
        assert stats['failed_requests'] == 1
        assert 'servers' in stats
        
        # Check server-specific stats
        server_stats = stats['servers']
        assert server_id1 in server_stats
        assert server_id2 in server_stats
        
        server1_stats = server_stats[server_id1]
        assert server1_stats['host'] == 'host1'
        assert server1_stats['weight'] == 100
        assert server1_stats['failed_requests'] == 1
    
    @patch('socket.socket')
    def test_health_checking(self, mock_socket):
        """Test health checking functionality."""
        # Mock successful connection
        mock_sock_instance = Mock()
        mock_sock_instance.connect_ex.return_value = 0
        mock_socket.return_value.__enter__.return_value = mock_sock_instance
        
        lb = LoadBalancer(health_check_interval=1, health_check_timeout=1)
        
        server_id = lb.add_server("127.0.0.1", 8080)
        server = lb._servers[server_id]
        
        # Manually trigger health check
        is_healthy = lb._check_server_health("127.0.0.1", 8080)
        assert is_healthy is True
        
        # Mock failed connection
        mock_sock_instance.connect_ex.return_value = 1  # Connection failed
        is_healthy = lb._check_server_health("127.0.0.1", 8080)
        assert is_healthy is False
    
    def test_shutdown(self):
        """Test load balancer shutdown."""
        lb = LoadBalancer()
        
        # Add servers
        lb.add_server("host1", 8080)
        lb.add_server("host2", 8080)
        
        assert len(lb._servers) == 2
        
        # Shutdown
        lb.shutdown()
        
        assert len(lb._servers) == 0


@pytest.mark.integration
class TestLoadBalancerIntegration:
    """Integration tests for load balancer."""
    
    def test_multiple_strategies(self):
        """Test different load balancing strategies."""
        strategies = [
            LoadBalancingStrategy.ROUND_ROBIN,
            LoadBalancingStrategy.LEAST_CONNECTIONS,
            LoadBalancingStrategy.WEIGHTED,
            LoadBalancingStrategy.RANDOM,
            LoadBalancingStrategy.LEAST_RESPONSE_TIME
        ]
        
        for strategy in strategies:
            lb = LoadBalancer(strategy=strategy)
            
            # Add servers
            lb.add_server("host1", 8080, weight=100)
            lb.add_server("host2", 8080, weight=200)
            
            # Test connection assignment
            result = lb.get_server_for_connection()
            assert result is not None
            
            server_id, server = result
            assert server_id in ["host1:8080", "host2:8080"]
            
            # Clean up
            lb.shutdown()
    
    def test_concurrent_access(self):
        """Test concurrent access to load balancer."""
        lb = LoadBalancer()
        
        # Add servers
        for i in range(5):
            lb.add_server(f"host{i}", 8080, max_connections=10)
        
        results = []
        errors = []
        
        def worker():
            try:
                for _ in range(10):
                    result = lb.get_server_for_connection()
                    if result:
                        results.append(result)
                        server_id, server = result
                        time.sleep(0.01)  # Simulate work
                        lb.release_connection(server_id)
            except Exception as e:
                errors.append(e)
        
        # Start multiple threads
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0
        assert len(results) == 100  # 10 threads * 10 requests each
        
        # Clean up
        lb.shutdown()
    
    def test_server_failure_recovery(self):
        """Test server failure and recovery."""
        lb = LoadBalancer()
        
        server_id = lb.add_server("127.0.0.1", 8080)
        server = lb._servers[server_id]
        
        # Server is initially healthy
        assert server.is_healthy is True
        
        # Simulate many failures
        for _ in range(50):
            server.increment_connections()
            server.decrement_connections()
            lb.record_failure(server_id)
        
        # Server should be unhealthy
        assert server.is_healthy is False
        
        # Simulate recovery by updating health
        server.update_health(True, 50.0)
        server.failed_requests = 0  # Reset failures
        server.total_requests = 0
        
        assert server.is_healthy is True
        
        # Clean up
        lb.shutdown()
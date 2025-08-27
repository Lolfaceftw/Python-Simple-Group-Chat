"""
Load Testing Tests

Tests for the load testing tools including load test client simulation,
test configuration, and result analysis.
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from chat_app.tools.load_tester import (
    LoadTester,
    LoadTestConfig,
    LoadTestClient,
    LoadTestResults,
    ClientStats
)
from chat_app.shared.exceptions import LoadTestError


class TestLoadTestConfig:
    """Test LoadTestConfig functionality."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = LoadTestConfig()
        
        assert config.server_host == "127.0.0.1"
        assert config.server_port == 8080
        assert config.num_clients == 100
        assert config.test_duration_seconds == 300
        assert config.ramp_up_seconds == 60
        assert config.message_rate_per_client == 1.0
        assert config.message_size_bytes == 100
        assert config.connection_timeout == 10
        assert config.think_time_seconds == 1.0
        assert config.load_pattern == "constant"
        assert config.enable_username_changes is True
        assert config.enable_disconnections is True
        assert config.enable_reconnections is True
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = LoadTestConfig(
            server_host="192.168.1.100",
            server_port=9090,
            num_clients=50,
            test_duration_seconds=120,
            message_rate_per_client=2.0,
            load_pattern="spike"
        )
        
        assert config.server_host == "192.168.1.100"
        assert config.server_port == 9090
        assert config.num_clients == 50
        assert config.test_duration_seconds == 120
        assert config.message_rate_per_client == 2.0
        assert config.load_pattern == "spike"


class TestClientStats:
    """Test ClientStats functionality."""
    
    def test_client_stats_creation(self):
        """Test client stats creation."""
        stats = ClientStats(client_id="test_client_001")
        
        assert stats.client_id == "test_client_001"
        assert stats.connected_at is None
        assert stats.disconnected_at is None
        assert stats.messages_sent == 0
        assert stats.messages_received == 0
        assert stats.bytes_sent == 0
        assert stats.bytes_received == 0
        assert stats.connection_errors == 0
        assert stats.send_errors == 0
        assert stats.receive_errors == 0
        assert len(stats.response_times) == 0
    
    def test_session_duration(self):
        """Test session duration calculation."""
        stats = ClientStats(client_id="test_client")
        
        # No connection times set
        assert stats.session_duration is None
        
        # Only connected time set
        stats.connected_at = datetime.now()
        duration = stats.session_duration
        assert duration is not None
        assert duration.total_seconds() >= 0
        
        # Both times set
        stats.disconnected_at = stats.connected_at + timedelta(seconds=30)
        assert stats.session_duration.total_seconds() == 30.0
    
    def test_average_response_time(self):
        """Test average response time calculation."""
        stats = ClientStats(client_id="test_client")
        
        # No response times
        assert stats.average_response_time == 0.0
        
        # Add response times
        stats.response_times = [0.1, 0.2, 0.3, 0.4, 0.5]
        assert stats.average_response_time == 0.3
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        stats = ClientStats(client_id="test_client")
        stats.connected_at = datetime.now()
        stats.messages_sent = 10
        stats.bytes_sent = 1000
        stats.response_times = [0.1, 0.2, 0.3]
        
        stats_dict = stats.to_dict()
        
        assert stats_dict['client_id'] == "test_client"
        assert stats_dict['messages_sent'] == 10
        assert stats_dict['bytes_sent'] == 1000
        assert stats_dict['average_response_time'] == 0.2
        assert 'connected_at' in stats_dict
        assert 'session_duration_seconds' in stats_dict


class TestLoadTestResults:
    """Test LoadTestResults functionality."""
    
    def test_load_test_results_creation(self):
        """Test load test results creation."""
        config = LoadTestConfig(num_clients=50)
        start_time = datetime.now()
        end_time = start_time + timedelta(seconds=120)
        
        results = LoadTestResults(
            config=config,
            start_time=start_time,
            end_time=end_time,
            total_clients=50,
            successful_connections=48,
            failed_connections=2,
            total_messages_sent=1000,
            total_messages_received=950,
            total_bytes_sent=100000,
            total_bytes_received=95000,
            average_response_time=0.15,
            min_response_time=0.05,
            max_response_time=0.50,
            percentile_95_response_time=0.30,
            percentile_99_response_time=0.45,
            throughput_messages_per_second=8.33,
            throughput_bytes_per_second=833.33,
            error_rate=4.0
        )
        
        assert results.config == config
        assert results.total_clients == 50
        assert results.successful_connections == 48
        assert results.failed_connections == 2
        assert results.total_messages_sent == 1000
        assert results.throughput_messages_per_second == 8.33
        assert results.error_rate == 4.0
        assert results.test_duration.total_seconds() == 120.0
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        config = LoadTestConfig()
        start_time = datetime.now()
        end_time = start_time + timedelta(seconds=60)
        
        results = LoadTestResults(
            config=config,
            start_time=start_time,
            end_time=end_time,
            total_clients=10,
            successful_connections=10,
            failed_connections=0,
            total_messages_sent=100,
            total_messages_received=100,
            total_bytes_sent=10000,
            total_bytes_received=10000,
            average_response_time=0.1,
            min_response_time=0.05,
            max_response_time=0.2,
            percentile_95_response_time=0.18,
            percentile_99_response_time=0.19,
            throughput_messages_per_second=1.67,
            throughput_bytes_per_second=166.67,
            error_rate=0.0
        )
        
        results_dict = results.to_dict()
        
        assert 'config' in results_dict
        assert 'start_time' in results_dict
        assert 'end_time' in results_dict
        assert 'test_duration_seconds' in results_dict
        assert results_dict['total_clients'] == 10
        assert results_dict['successful_connections'] == 10
        assert results_dict['error_rate'] == 0.0
    
    @patch('builtins.open')
    @patch('json.dump')
    def test_save_to_file(self, mock_json_dump, mock_open):
        """Test saving results to file."""
        config = LoadTestConfig()
        results = LoadTestResults(
            config=config,
            start_time=datetime.now(),
            end_time=datetime.now(),
            total_clients=10,
            successful_connections=10,
            failed_connections=0,
            total_messages_sent=100,
            total_messages_received=100,
            total_bytes_sent=10000,
            total_bytes_received=10000,
            average_response_time=0.1,
            min_response_time=0.05,
            max_response_time=0.2,
            percentile_95_response_time=0.18,
            percentile_99_response_time=0.19,
            throughput_messages_per_second=1.67,
            throughput_bytes_per_second=166.67,
            error_rate=0.0
        )
        
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file
        
        results.save_to_file("test_results.json")
        
        mock_open.assert_called_once_with("test_results.json", 'w')
        mock_json_dump.assert_called_once()


class TestLoadTestClient:
    """Test LoadTestClient functionality."""
    
    def test_client_creation(self):
        """Test load test client creation."""
        config = LoadTestConfig()
        client = LoadTestClient("client_001", config)
        
        assert client.client_id == "client_001"
        assert client.config == config
        assert client.stats.client_id == "client_001"
        assert client.socket is None
        assert client.is_running is False
        assert client.username == "LoadTestUser_client_001"
    
    def test_message_generation(self):
        """Test message content generation."""
        config = LoadTestConfig(message_size_bytes=50)
        client = LoadTestClient("client_001", config)
        
        message = client._generate_message_content()
        
        assert len(message) == 50
        assert "Load test message" in message
        assert "client_001" in message
    
    def test_message_generation_padding(self):
        """Test message padding for size requirements."""
        config = LoadTestConfig(message_size_bytes=200)
        client = LoadTestClient("client_001", config)
        
        message = client._generate_message_content()
        
        assert len(message) == 200
        assert message.endswith("x" * (200 - len("Load test message 1 from client_001 ")))
    
    def test_message_generation_truncation(self):
        """Test message truncation for size requirements."""
        config = LoadTestConfig(message_size_bytes=10)
        client = LoadTestClient("client_001", config)
        
        message = client._generate_message_content()
        
        assert len(message) == 10
        assert message == "Load test "
    
    @patch('socket.socket')
    def test_connection_success(self, mock_socket):
        """Test successful connection."""
        config = LoadTestConfig()
        client = LoadTestClient("client_001", config)
        
        mock_sock_instance = Mock()
        mock_socket.return_value = mock_sock_instance
        
        # Mock successful connection
        mock_sock_instance.connect.return_value = None
        
        success = client._connect()
        
        assert success is True
        assert client.socket == mock_sock_instance
        assert client.stats.connected_at is not None
        assert len(client.stats.response_times) == 1
        
        mock_sock_instance.settimeout.assert_called_with(config.connection_timeout)
        mock_sock_instance.connect.assert_called_with((config.server_host, config.server_port))
    
    @patch('socket.socket')
    def test_connection_failure(self, mock_socket):
        """Test connection failure."""
        config = LoadTestConfig()
        client = LoadTestClient("client_001", config)
        
        mock_sock_instance = Mock()
        mock_socket.return_value = mock_sock_instance
        
        # Mock connection failure
        mock_sock_instance.connect.side_effect = ConnectionRefusedError("Connection refused")
        
        success = client._connect()
        
        assert success is False
        assert client.socket is None
        assert client.stats.connection_errors == 1
    
    def test_disconnect(self):
        """Test disconnection."""
        config = LoadTestConfig()
        client = LoadTestClient("client_001", config)
        
        # Set up mock socket
        mock_socket = Mock()
        client.socket = mock_socket
        
        client._disconnect()
        
        mock_socket.close.assert_called_once()
        assert client.socket is None
        assert client.stats.disconnected_at is not None
    
    def test_send_message(self):
        """Test message sending."""
        config = LoadTestConfig()
        client = LoadTestClient("client_001", config)
        
        # Set up mock socket
        mock_socket = Mock()
        client.socket = mock_socket
        
        message = b"Test message"
        client._send_message(message)
        
        mock_socket.sendall.assert_called_once_with(message)
        assert client.stats.messages_sent == 1
        assert client.stats.bytes_sent == len(message)
    
    def test_send_message_error(self):
        """Test message sending error."""
        config = LoadTestConfig()
        client = LoadTestClient("client_001", config)
        
        # Set up mock socket that raises error
        mock_socket = Mock()
        mock_socket.sendall.side_effect = BrokenPipeError("Broken pipe")
        client.socket = mock_socket
        
        with pytest.raises(BrokenPipeError):
            client._send_message(b"Test message")
    
    @patch('socket.socket')
    def test_receive_messages(self, mock_socket):
        """Test message receiving."""
        config = LoadTestConfig()
        client = LoadTestClient("client_001", config)
        
        mock_sock_instance = Mock()
        mock_socket.return_value = mock_sock_instance
        client.socket = mock_sock_instance
        
        # Mock received data
        mock_sock_instance.recv.return_value = b"Server response"
        
        client._receive_messages()
        
        # The socket timeout should be set to 0.01 for non-blocking receive
        # Check that settimeout was called with 0.01 at some point
        calls = mock_sock_instance.settimeout.call_args_list
        timeout_calls = [call for call in calls if call == ((0.01,),)]
        assert len(timeout_calls) > 0, f"Expected settimeout(0.01) call, got calls: {calls}"
        mock_sock_instance.recv.assert_called_with(4096)
        assert client.stats.messages_received == 1
        assert client.stats.bytes_received == len(b"Server response")
    
    def test_receive_messages_timeout(self):
        """Test message receiving timeout."""
        config = LoadTestConfig()
        client = LoadTestClient("client_001", config)
        
        # Set up mock socket that times out
        mock_socket = Mock()
        mock_socket.recv.side_effect = TimeoutError("Timeout")
        client.socket = mock_socket
        
        # Should handle timeout gracefully
        client._receive_messages()
        
        assert client.stats.messages_received == 0
        assert client.stats.receive_errors == 0  # Timeout is not counted as error
    
    def test_stop_client(self):
        """Test stopping client."""
        config = LoadTestConfig()
        client = LoadTestClient("client_001", config)
        
        assert not client.should_stop.is_set()
        
        client.stop()
        
        assert client.should_stop.is_set()


class TestLoadTester:
    """Test LoadTester functionality."""
    
    def test_load_tester_creation(self):
        """Test load tester creation."""
        config = LoadTestConfig(num_clients=10)
        tester = LoadTester(config)
        
        assert tester.config == config
        assert len(tester.clients) == 0
        assert len(tester.client_futures) == 0
        assert tester.executor is None
        assert tester.start_time is None
        assert tester.end_time is None
    
    def test_create_clients(self):
        """Test client creation."""
        config = LoadTestConfig(num_clients=5)
        tester = LoadTester(config)
        
        tester._create_clients()
        
        assert len(tester.clients) == 5
        assert len(tester.client_stats) == 5
        assert tester.executor is not None
        
        # Check client IDs
        client_ids = [client.client_id for client in tester.clients]
        expected_ids = [f"client_{i:04d}" for i in range(5)]
        assert client_ids == expected_ids
    
    def test_update_client_stats(self):
        """Test client stats updating."""
        config = LoadTestConfig()
        tester = LoadTester(config)
        
        stats = ClientStats(client_id="test_client")
        stats.messages_sent = 10
        
        tester._update_client_stats(stats)
        
        assert "test_client" in tester.client_stats
        assert tester.client_stats["test_client"].messages_sent == 10
    
    @patch('time.time')
    def test_wait_for_completion(self, mock_time):
        """Test waiting for test completion."""
        config = LoadTestConfig(test_duration_seconds=5)
        tester = LoadTester(config)
        
        # Mock time progression
        start_time = 1000.0
        # Provide enough time values to avoid StopIteration
        time_values = [start_time + i for i in range(10)]  # 10 time values
        time_values[-1] = start_time + 6  # Last value exceeds test duration
        mock_time.side_effect = time_values
        
        # Create mock clients
        tester.clients = [Mock(is_running=True) for _ in range(3)]
        
        tester._wait_for_completion()
        
        # Should have waited for the full duration
        assert mock_time.call_count >= 3
    
    def test_wait_for_completion_early_exit(self):
        """Test early exit when all clients stop."""
        config = LoadTestConfig(test_duration_seconds=60)
        tester = LoadTester(config)
        
        # Create mock clients that are not running
        tester.clients = [Mock(is_running=False) for _ in range(3)]
        
        start_time = time.time()
        tester._wait_for_completion()
        end_time = time.time()
        
        # Should exit quickly since no clients are running
        assert end_time - start_time < 5  # Should be much less than 60 seconds
    
    def test_stop_clients(self):
        """Test stopping all clients."""
        config = LoadTestConfig()
        tester = LoadTester(config)
        
        # Create mock clients and futures
        mock_clients = [Mock() for _ in range(3)]
        mock_futures = [Mock() for _ in range(3)]
        
        tester.clients = mock_clients
        tester.client_futures = mock_futures
        tester.executor = Mock()
        
        tester._stop_clients()
        
        # All clients should be stopped
        for client in mock_clients:
            client.stop.assert_called_once()
        
        # All futures should be waited for
        for future in mock_futures:
            future.result.assert_called_once_with(timeout=10)
        
        # Executor should be shutdown
        tester.executor.shutdown.assert_called_once_with(wait=True)
    
    def test_generate_results(self):
        """Test results generation."""
        config = LoadTestConfig(num_clients=10)
        tester = LoadTester(config)
        
        # Set up timing
        tester.start_time = datetime.now() - timedelta(seconds=60)
        tester.end_time = datetime.now()
        
        # Create mock client stats
        for i in range(10):
            stats = ClientStats(client_id=f"client_{i:04d}")
            stats.connected_at = tester.start_time
            stats.messages_sent = 10
            stats.messages_received = 9
            stats.bytes_sent = 1000
            stats.bytes_received = 900
            stats.response_times = [0.1, 0.2, 0.15]
            tester.client_stats[stats.client_id] = stats
        
        results = tester._generate_results()
        
        assert results.config == config
        assert results.start_time == tester.start_time
        assert results.end_time == tester.end_time
        assert results.total_clients == 10
        assert results.successful_connections == 10
        assert results.failed_connections == 0
        assert results.total_messages_sent == 100
        assert results.total_messages_received == 90
        assert results.total_bytes_sent == 10000
        assert results.total_bytes_received == 9000
        assert results.average_response_time > 0
        assert results.throughput_messages_per_second > 0


@pytest.mark.integration
class TestLoadTestingIntegration:
    """Integration tests for load testing."""
    
    @patch('socket.socket')
    def test_single_client_run(self, mock_socket):
        """Test running a single client."""
        config = LoadTestConfig(
            num_clients=1,
            test_duration_seconds=2,
            ramp_up_seconds=0,
            message_rate_per_client=1.0
        )
        
        # Mock socket behavior
        mock_sock_instance = Mock()
        mock_socket.return_value = mock_sock_instance
        mock_sock_instance.connect.return_value = None
        mock_sock_instance.recv.side_effect = [b"Welcome", b"", TimeoutError()]
        
        client = LoadTestClient("test_client", config)
        
        # Mock the message loop to exit after a few iterations
        original_message_loop = client._message_loop
        call_count = 0
        
        def mock_message_loop():
            nonlocal call_count
            call_count += 1
            if call_count >= 3:  # Exit after 3 iterations
                client.should_stop.set()
                return
            # Simulate some message sending
            client.stats.messages_sent += 1
            client.stats.bytes_sent += 100
        
        with patch.object(client, '_message_loop', side_effect=mock_message_loop):
            stats = client.run()
        
        assert stats.client_id == "test_client"
        assert stats.connected_at is not None
        assert stats.messages_sent > 0
    
    def test_load_tester_run(self):
        """Test running load tester with multiple clients."""
        config = LoadTestConfig(
            num_clients=3,
            test_duration_seconds=1,
            ramp_up_seconds=0,
            message_rate_per_client=0.5
        )
        
        tester = LoadTester(config)
        
        # Mock the client run method to return mock stats quickly
        def mock_client_run():
            stats = ClientStats(client_id="mock_client")
            stats.connected_at = datetime.now()
            stats.messages_sent = 5
            stats.messages_received = 4
            stats.bytes_sent = 500
            stats.bytes_received = 400
            stats.response_times = [0.1, 0.2, 0.15]
            return stats
        
        # Mock the client creation and execution
        with patch.object(tester, '_create_clients') as mock_create, \
             patch.object(tester, '_start_clients') as mock_start, \
             patch.object(tester, '_wait_for_completion') as mock_wait, \
             patch.object(tester, '_stop_clients') as mock_stop:
            
            # Set up mock client stats
            for i in range(3):
                client_id = f"client_{i:04d}"
                tester.client_stats[client_id] = mock_client_run()
            
            tester.start_time = datetime.now()
            tester.end_time = tester.start_time + timedelta(seconds=1)
            
            results = tester.run_test()
        
        assert results.total_clients == 3
        assert results.start_time is not None
        assert results.end_time is not None
        assert results.test_duration.total_seconds() > 0
        assert results.total_messages_sent == 15  # 3 clients * 5 messages each
    
    def test_client_stats_callback(self):
        """Test client stats callback functionality."""
        config = LoadTestConfig()
        
        callback_calls = []
        
        def stats_callback(stats):
            callback_calls.append(stats)
        
        client = LoadTestClient("test_client", config, stats_callback)
        
        # Simulate stats update
        client.stats.messages_sent = 5
        stats_callback(client.stats)
        
        assert len(callback_calls) == 1
        assert callback_calls[0].messages_sent == 5
    
    def test_error_handling(self):
        """Test error handling in load testing."""
        config = LoadTestConfig(num_clients=2, test_duration_seconds=1)
        tester = LoadTester(config)
        
        # Create clients that will fail
        tester._create_clients()
        
        # Mock client run to raise exception
        for client in tester.clients:
            client.run = Mock(side_effect=Exception("Test error"))
        
        # Should handle errors gracefully
        results = tester.run_test()
        
        assert results.total_clients == 2
        assert results.failed_connections == 2
        assert results.successful_connections == 0
    
    def test_concurrent_client_execution(self):
        """Test concurrent execution of multiple clients."""
        config = LoadTestConfig(
            num_clients=5,
            test_duration_seconds=1,
            ramp_up_seconds=0
        )
        
        execution_times = []
        
        def mock_client_run():
            start_time = time.time()
            time.sleep(0.1)  # Simulate work
            end_time = time.time()
            execution_times.append((start_time, end_time))
            return ClientStats(client_id="mock_client")
        
        tester = LoadTester(config)
        tester._create_clients()
        
        # Mock client run methods
        for client in tester.clients:
            client.run = Mock(side_effect=mock_client_run)
        
        # Run test
        results = tester.run_test()
        
        # Check that clients ran concurrently
        assert len(execution_times) == 5
        
        # All clients should have started within a short time window
        start_times = [t[0] for t in execution_times]
        time_spread = max(start_times) - min(start_times)
        assert time_spread < 1.0  # Should start within 1 second of each other
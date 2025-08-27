"""
Load Testing Tool

Comprehensive load testing tool for the chat server with multiple
concurrent clients, various load patterns, and detailed reporting.
"""

import asyncio
import socket
import threading
import time
import random
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, Future
import statistics
import json

from chat_app.shared.exceptions import LoadTestError


logger = logging.getLogger(__name__)


@dataclass
class LoadTestConfig:
    """Configuration for load testing."""
    server_host: str = "127.0.0.1"
    server_port: int = 8080
    num_clients: int = 100
    test_duration_seconds: int = 300
    ramp_up_seconds: int = 60
    message_rate_per_client: float = 1.0  # messages per second per client
    message_size_bytes: int = 100
    connection_timeout: int = 10
    think_time_seconds: float = 1.0
    
    # Load patterns
    load_pattern: str = "constant"  # constant, ramp, spike, wave
    spike_multiplier: float = 5.0
    wave_period_seconds: int = 120
    
    # Test scenarios
    enable_username_changes: bool = True
    username_change_probability: float = 0.1
    enable_disconnections: bool = True
    disconnection_probability: float = 0.05
    enable_reconnections: bool = True
    
    # Reporting
    report_interval_seconds: int = 10
    detailed_logging: bool = False


@dataclass
class ClientStats:
    """Statistics for a single test client."""
    client_id: str
    connected_at: Optional[datetime] = None
    disconnected_at: Optional[datetime] = None
    messages_sent: int = 0
    messages_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    connection_errors: int = 0
    send_errors: int = 0
    receive_errors: int = 0
    response_times: List[float] = field(default_factory=list)
    
    @property
    def session_duration(self) -> Optional[timedelta]:
        """Get session duration."""
        if self.connected_at and self.disconnected_at:
            return self.disconnected_at - self.connected_at
        elif self.connected_at:
            return datetime.now() - self.connected_at
        return None
    
    @property
    def average_response_time(self) -> float:
        """Get average response time."""
        return statistics.mean(self.response_times) if self.response_times else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'client_id': self.client_id,
            'connected_at': self.connected_at.isoformat() if self.connected_at else None,
            'disconnected_at': self.disconnected_at.isoformat() if self.disconnected_at else None,
            'messages_sent': self.messages_sent,
            'messages_received': self.messages_received,
            'bytes_sent': self.bytes_sent,
            'bytes_received': self.bytes_received,
            'connection_errors': self.connection_errors,
            'send_errors': self.send_errors,
            'receive_errors': self.receive_errors,
            'session_duration_seconds': self.session_duration.total_seconds() if self.session_duration else 0,
            'average_response_time': self.average_response_time
        }


@dataclass
class LoadTestResults:
    """Results from a load test run."""
    config: LoadTestConfig
    start_time: datetime
    end_time: datetime
    total_clients: int
    successful_connections: int
    failed_connections: int
    total_messages_sent: int
    total_messages_received: int
    total_bytes_sent: int
    total_bytes_received: int
    average_response_time: float
    min_response_time: float
    max_response_time: float
    percentile_95_response_time: float
    percentile_99_response_time: float
    throughput_messages_per_second: float
    throughput_bytes_per_second: float
    error_rate: float
    client_stats: List[ClientStats] = field(default_factory=list)
    
    @property
    def test_duration(self) -> timedelta:
        """Get total test duration."""
        return self.end_time - self.start_time
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'config': {
                'server_host': self.config.server_host,
                'server_port': self.config.server_port,
                'num_clients': self.config.num_clients,
                'test_duration_seconds': self.config.test_duration_seconds,
                'message_rate_per_client': self.config.message_rate_per_client,
                'load_pattern': self.config.load_pattern
            },
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'test_duration_seconds': self.test_duration.total_seconds(),
            'total_clients': self.total_clients,
            'successful_connections': self.successful_connections,
            'failed_connections': self.failed_connections,
            'total_messages_sent': self.total_messages_sent,
            'total_messages_received': self.total_messages_received,
            'total_bytes_sent': self.total_bytes_sent,
            'total_bytes_received': self.total_bytes_received,
            'average_response_time': self.average_response_time,
            'min_response_time': self.min_response_time,
            'max_response_time': self.max_response_time,
            'percentile_95_response_time': self.percentile_95_response_time,
            'percentile_99_response_time': self.percentile_99_response_time,
            'throughput_messages_per_second': self.throughput_messages_per_second,
            'throughput_bytes_per_second': self.throughput_bytes_per_second,
            'error_rate': self.error_rate,
            'client_stats': [stats.to_dict() for stats in self.client_stats]
        }
    
    def save_to_file(self, filename: str) -> None:
        """Save results to JSON file."""
        with open(filename, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info(f"Load test results saved to {filename}")


class LoadTestClient:
    """Individual load test client."""
    
    def __init__(
        self,
        client_id: str,
        config: LoadTestConfig,
        stats_callback: Optional[Callable[[ClientStats], None]] = None
    ):
        """
        Initialize load test client.
        
        Args:
            client_id: Unique client identifier
            config: Load test configuration
            stats_callback: Optional callback for stats updates
        """
        self.client_id = client_id
        self.config = config
        self.stats_callback = stats_callback
        
        self.stats = ClientStats(client_id=client_id)
        self.socket: Optional[socket.socket] = None
        self.is_running = False
        self.should_stop = threading.Event()
        
        # Message generation
        self.message_counter = 0
        self.username = f"LoadTestUser_{client_id}"
        
    def run(self) -> ClientStats:
        """
        Run the load test client.
        
        Returns:
            Client statistics
        """
        self.is_running = True
        
        try:
            # Connect to server
            if not self._connect():
                return self.stats
            
            # Send initial username
            self._send_username_command()
            
            # Main message loop
            self._message_loop()
            
        except Exception as e:
            logger.error(f"Client {self.client_id} error: {e}")
            self.stats.connection_errors += 1
        finally:
            self._disconnect()
            self.is_running = False
        
        return self.stats
    
    def stop(self) -> None:
        """Stop the client."""
        self.should_stop.set()
    
    def _connect(self) -> bool:
        """Connect to the server."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.config.connection_timeout)
            
            start_time = time.time()
            self.socket.connect((self.config.server_host, self.config.server_port))
            connection_time = time.time() - start_time
            
            self.stats.connected_at = datetime.now()
            self.stats.response_times.append(connection_time)
            
            logger.debug(f"Client {self.client_id} connected in {connection_time:.3f}s")
            return True
            
        except Exception as e:
            logger.error(f"Client {self.client_id} connection failed: {e}")
            self.stats.connection_errors += 1
            # Clean up socket on failure
            if self.socket:
                try:
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None
            return False
    
    def _disconnect(self) -> None:
        """Disconnect from the server."""
        if self.socket:
            try:
                self.socket.close()
            except Exception as e:
                logger.error(f"Client {self.client_id} disconnect error: {e}")
            finally:
                self.socket = None
                self.stats.disconnected_at = datetime.now()
    
    def _send_username_command(self) -> None:
        """Send username command to server."""
        try:
            command = f"CMD_USER|{self.username}\n"
            self._send_message(command.encode('utf-8'))
        except Exception as e:
            logger.error(f"Client {self.client_id} username command failed: {e}")
    
    def _message_loop(self) -> None:
        """Main message sending loop."""
        last_message_time = time.time()
        message_interval = 1.0 / self.config.message_rate_per_client
        
        while not self.should_stop.is_set() and self.socket:
            try:
                current_time = time.time()
                
                # Check if it's time to send a message
                if current_time - last_message_time >= message_interval:
                    self._send_chat_message()
                    last_message_time = current_time
                
                # Handle random events
                self._handle_random_events()
                
                # Receive any incoming messages
                self._receive_messages()
                
                # Think time
                time.sleep(min(0.1, self.config.think_time_seconds))
                
                # Update stats callback
                if self.stats_callback:
                    self.stats_callback(self.stats)
                
            except Exception as e:
                logger.error(f"Client {self.client_id} message loop error: {e}")
                break
    
    def _send_chat_message(self) -> None:
        """Send a chat message."""
        self.message_counter += 1
        
        # Generate message content
        message_content = self._generate_message_content()
        message = f"MSG|{message_content}\n"
        
        try:
            start_time = time.time()
            self._send_message(message.encode('utf-8'))
            response_time = time.time() - start_time
            
            self.stats.response_times.append(response_time)
            
        except Exception as e:
            logger.error(f"Client {self.client_id} send message failed: {e}")
            self.stats.send_errors += 1
    
    def _send_message(self, message: bytes) -> None:
        """Send a message to the server."""
        if self.socket:
            self.socket.sendall(message)
            self.stats.messages_sent += 1
            self.stats.bytes_sent += len(message)
    
    def _receive_messages(self) -> None:
        """Receive messages from server (non-blocking)."""
        if not self.socket:
            return
        
        try:
            # Set socket to non-blocking for receiving
            self.socket.settimeout(0.01)
            data = self.socket.recv(4096)
            
            if data:
                self.stats.messages_received += 1
                self.stats.bytes_received += len(data)
                
                if self.config.detailed_logging:
                    logger.debug(f"Client {self.client_id} received: {data[:50]}...")
            
        except socket.timeout:
            # No data available, continue
            pass
        except Exception as e:
            logger.error(f"Client {self.client_id} receive error: {e}")
            self.stats.receive_errors += 1
        finally:
            # Reset socket timeout
            if self.socket:
                self.socket.settimeout(self.config.connection_timeout)
    
    def _generate_message_content(self) -> str:
        """Generate message content."""
        base_message = f"Load test message {self.message_counter} from {self.client_id}"
        
        # Pad to desired size
        if len(base_message) < self.config.message_size_bytes:
            padding_needed = self.config.message_size_bytes - len(base_message) - 1  # -1 for space
            if padding_needed > 0:
                padding = "x" * padding_needed
                return base_message + " " + padding
            else:
                return base_message
        
        return base_message[:self.config.message_size_bytes]
    
    def _handle_random_events(self) -> None:
        """Handle random events like username changes and disconnections."""
        # Username change
        if (self.config.enable_username_changes and 
            random.random() < self.config.username_change_probability):
            new_username = f"LoadTestUser_{self.client_id}_{random.randint(1000, 9999)}"
            try:
                command = f"CMD_USER|{new_username}\n"
                self._send_message(command.encode('utf-8'))
                self.username = new_username
            except Exception as e:
                logger.error(f"Client {self.client_id} username change failed: {e}")
        
        # Temporary disconnection
        if (self.config.enable_disconnections and 
            random.random() < self.config.disconnection_probability):
            try:
                self._disconnect()
                if self.config.enable_reconnections:
                    time.sleep(random.uniform(1, 5))  # Wait before reconnecting
                    self._connect()
                    self._send_username_command()
            except Exception as e:
                logger.error(f"Client {self.client_id} reconnection failed: {e}")


class LoadTester:
    """
    Main load testing orchestrator.
    
    Features:
    - Multiple concurrent clients
    - Various load patterns
    - Real-time monitoring
    - Detailed reporting
    - Configurable test scenarios
    """
    
    def __init__(self, config: LoadTestConfig):
        """
        Initialize load tester.
        
        Args:
            config: Load test configuration
        """
        self.config = config
        self.clients: List[LoadTestClient] = []
        self.client_futures: List[Future] = []
        self.executor: Optional[ThreadPoolExecutor] = None
        
        # Statistics
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.client_stats: Dict[str, ClientStats] = {}
        
        # Monitoring
        self.monitoring_thread: Optional[threading.Thread] = None
        self.should_stop_monitoring = threading.Event()
        
        logger.info(f"LoadTester initialized for {config.num_clients} clients")
    
    def run_test(self) -> LoadTestResults:
        """
        Run the load test.
        
        Returns:
            Load test results
        """
        logger.info(f"Starting load test with {self.config.num_clients} clients")
        
        self.start_time = datetime.now()
        
        try:
            # Start monitoring
            self._start_monitoring()
            
            # Create and start clients
            self._create_clients()
            self._start_clients()
            
            # Wait for test completion
            self._wait_for_completion()
            
            # Stop all clients
            self._stop_clients()
            
        finally:
            self._stop_monitoring()
            self.end_time = datetime.now()
        
        # Generate results
        results = self._generate_results()
        
        logger.info(f"Load test completed in {results.test_duration.total_seconds():.1f}s")
        return results
    
    def _create_clients(self) -> None:
        """Create load test clients."""
        self.executor = ThreadPoolExecutor(max_workers=self.config.num_clients)
        
        for i in range(self.config.num_clients):
            client_id = f"client_{i:04d}"
            client = LoadTestClient(
                client_id=client_id,
                config=self.config,
                stats_callback=self._update_client_stats
            )
            self.clients.append(client)
            self.client_stats[client_id] = client.stats
    
    def _start_clients(self) -> None:
        """Start all clients with ramp-up."""
        if not self.executor:
            raise LoadTestError("Executor not initialized")
        
        ramp_up_delay = self.config.ramp_up_seconds / self.config.num_clients
        
        for i, client in enumerate(self.clients):
            # Ramp-up delay
            if i > 0:
                time.sleep(ramp_up_delay)
            
            future = self.executor.submit(client.run)
            self.client_futures.append(future)
            
            logger.debug(f"Started client {client.client_id}")
    
    def _wait_for_completion(self) -> None:
        """Wait for test completion."""
        test_end_time = time.time() + self.config.test_duration_seconds
        
        while time.time() < test_end_time:
            time.sleep(1)
            
            # Check if all clients have failed
            active_clients = sum(1 for client in self.clients if client.is_running)
            if active_clients == 0:
                logger.warning("All clients have stopped, ending test early")
                break
    
    def _stop_clients(self) -> None:
        """Stop all clients."""
        logger.info("Stopping all clients...")
        
        # Signal all clients to stop
        for client in self.clients:
            client.stop()
        
        # Wait for all futures to complete
        if self.client_futures:
            for future in self.client_futures:
                try:
                    future.result(timeout=10)
                except Exception as e:
                    logger.error(f"Client future error: {e}")
        
        # Shutdown executor
        if self.executor:
            self.executor.shutdown(wait=True)
        
        logger.info("All clients stopped")
    
    def _start_monitoring(self) -> None:
        """Start monitoring thread."""
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            name="LoadTest-Monitor",
            daemon=True
        )
        self.monitoring_thread.start()
    
    def _stop_monitoring(self) -> None:
        """Stop monitoring thread."""
        self.should_stop_monitoring.set()
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5)
    
    def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        while not self.should_stop_monitoring.is_set():
            try:
                self._log_current_stats()
                self.should_stop_monitoring.wait(self.config.report_interval_seconds)
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
    
    def _log_current_stats(self) -> None:
        """Log current test statistics."""
        active_clients = sum(1 for client in self.clients if client.is_running)
        total_messages_sent = sum(stats.messages_sent for stats in self.client_stats.values())
        total_messages_received = sum(stats.messages_received for stats in self.client_stats.values())
        total_errors = sum(
            stats.connection_errors + stats.send_errors + stats.receive_errors
            for stats in self.client_stats.values()
        )
        
        elapsed_time = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        
        logger.info(
            f"Load test progress: {active_clients} active clients, "
            f"{total_messages_sent} sent, {total_messages_received} received, "
            f"{total_errors} errors, {elapsed_time:.1f}s elapsed"
        )
    
    def _update_client_stats(self, stats: ClientStats) -> None:
        """Update client statistics."""
        self.client_stats[stats.client_id] = stats
    
    def _generate_results(self) -> LoadTestResults:
        """Generate load test results."""
        if not self.start_time or not self.end_time:
            raise LoadTestError("Test timing not recorded")
        
        # Collect all response times
        all_response_times = []
        for stats in self.client_stats.values():
            all_response_times.extend(stats.response_times)
        
        # Calculate statistics
        successful_connections = sum(
            1 for stats in self.client_stats.values()
            if stats.connected_at is not None
        )
        failed_connections = self.config.num_clients - successful_connections
        
        total_messages_sent = sum(stats.messages_sent for stats in self.client_stats.values())
        total_messages_received = sum(stats.messages_received for stats in self.client_stats.values())
        total_bytes_sent = sum(stats.bytes_sent for stats in self.client_stats.values())
        total_bytes_received = sum(stats.bytes_received for stats in self.client_stats.values())
        
        total_errors = sum(
            stats.connection_errors + stats.send_errors + stats.receive_errors
            for stats in self.client_stats.values()
        )
        
        test_duration = (self.end_time - self.start_time).total_seconds()
        
        # Response time statistics
        if all_response_times:
            avg_response_time = statistics.mean(all_response_times)
            min_response_time = min(all_response_times)
            max_response_time = max(all_response_times)
            
            sorted_times = sorted(all_response_times)
            p95_index = int(len(sorted_times) * 0.95)
            p99_index = int(len(sorted_times) * 0.99)
            
            percentile_95 = sorted_times[p95_index] if p95_index < len(sorted_times) else max_response_time
            percentile_99 = sorted_times[p99_index] if p99_index < len(sorted_times) else max_response_time
        else:
            avg_response_time = min_response_time = max_response_time = 0.0
            percentile_95 = percentile_99 = 0.0
        
        # Throughput calculations
        throughput_messages_per_second = total_messages_sent / max(1, test_duration)
        throughput_bytes_per_second = total_bytes_sent / max(1, test_duration)
        
        # Error rate
        total_operations = total_messages_sent + successful_connections
        error_rate = (total_errors / max(1, total_operations)) * 100
        
        return LoadTestResults(
            config=self.config,
            start_time=self.start_time,
            end_time=self.end_time,
            total_clients=self.config.num_clients,
            successful_connections=successful_connections,
            failed_connections=failed_connections,
            total_messages_sent=total_messages_sent,
            total_messages_received=total_messages_received,
            total_bytes_sent=total_bytes_sent,
            total_bytes_received=total_bytes_received,
            average_response_time=avg_response_time,
            min_response_time=min_response_time,
            max_response_time=max_response_time,
            percentile_95_response_time=percentile_95,
            percentile_99_response_time=percentile_99,
            throughput_messages_per_second=throughput_messages_per_second,
            throughput_bytes_per_second=throughput_bytes_per_second,
            error_rate=error_rate,
            client_stats=list(self.client_stats.values())
        )
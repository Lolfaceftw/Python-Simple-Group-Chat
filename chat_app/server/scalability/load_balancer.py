"""
Load Balancer Module

Implements load balancing strategies for horizontal scaling preparation.
Supports multiple algorithms and health checking for server nodes.
"""

import threading
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
import random

from chat_app.shared.exceptions import LoadBalancerError


logger = logging.getLogger(__name__)


class LoadBalancingStrategy(Enum):
    """Load balancing strategies."""
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED = "weighted"
    RANDOM = "random"
    LEAST_RESPONSE_TIME = "least_response_time"


@dataclass
class ServerNode:
    """Represents a server node in the load balancer."""
    host: str
    port: int
    weight: int = 100
    max_connections: int = 1000
    current_connections: int = 0
    is_healthy: bool = True
    last_health_check: Optional[datetime] = None
    response_time_ms: float = 0.0
    total_requests: int = 0
    failed_requests: int = 0
    
    @property
    def connection_ratio(self) -> float:
        """Get the connection utilization ratio."""
        if self.max_connections == 0:
            return 1.0
        return self.current_connections / self.max_connections
    
    @property
    def failure_rate(self) -> float:
        """Get the failure rate percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.failed_requests / self.total_requests) * 100
    
    def update_health(self, is_healthy: bool, response_time_ms: float = 0.0) -> None:
        """Update health status and response time."""
        self.is_healthy = is_healthy
        self.last_health_check = datetime.now()
        if response_time_ms > 0:
            # Exponential moving average for response time
            if self.response_time_ms == 0:
                self.response_time_ms = response_time_ms
            else:
                self.response_time_ms = (self.response_time_ms * 0.8) + (response_time_ms * 0.2)
    
    def increment_connections(self) -> bool:
        """
        Increment connection count if under limit.
        
        Returns:
            True if connection was accepted, False if at capacity
        """
        if self.current_connections >= self.max_connections:
            return False
        self.current_connections += 1
        self.total_requests += 1
        return True
    
    def decrement_connections(self) -> None:
        """Decrement connection count."""
        if self.current_connections > 0:
            self.current_connections -= 1
    
    def record_failure(self) -> None:
        """Record a failed request."""
        self.failed_requests += 1


class LoadBalancingAlgorithm(ABC):
    """Abstract base class for load balancing algorithms."""
    
    @abstractmethod
    def select_server(self, servers: List[ServerNode]) -> Optional[ServerNode]:
        """
        Select a server from the available servers.
        
        Args:
            servers: List of available healthy servers
            
        Returns:
            Selected server node or None if no servers available
        """
        pass


class RoundRobinAlgorithm(LoadBalancingAlgorithm):
    """Round-robin load balancing algorithm."""
    
    def __init__(self):
        self._current_index = 0
        self._lock = threading.Lock()
    
    def select_server(self, servers: List[ServerNode]) -> Optional[ServerNode]:
        """Select next server in round-robin fashion."""
        if not servers:
            return None
        
        with self._lock:
            server = servers[self._current_index % len(servers)]
            self._current_index = (self._current_index + 1) % len(servers)
            return server


class LeastConnectionsAlgorithm(LoadBalancingAlgorithm):
    """Least connections load balancing algorithm."""
    
    def select_server(self, servers: List[ServerNode]) -> Optional[ServerNode]:
        """Select server with least connections."""
        if not servers:
            return None
        
        return min(servers, key=lambda s: s.current_connections)


class WeightedAlgorithm(LoadBalancingAlgorithm):
    """Weighted load balancing algorithm."""
    
    def select_server(self, servers: List[ServerNode]) -> Optional[ServerNode]:
        """Select server based on weights and current load."""
        if not servers:
            return None
        
        # Calculate effective weight (weight / connection_ratio)
        best_server = None
        best_score = -1
        
        for server in servers:
            # Higher weight and lower connection ratio = better score
            connection_penalty = server.connection_ratio * 0.5
            score = server.weight * (1.0 - connection_penalty)
            
            if score > best_score:
                best_score = score
                best_server = server
        
        return best_server


class RandomAlgorithm(LoadBalancingAlgorithm):
    """Random load balancing algorithm."""
    
    def select_server(self, servers: List[ServerNode]) -> Optional[ServerNode]:
        """Select random server."""
        if not servers:
            return None
        
        return random.choice(servers)


class LeastResponseTimeAlgorithm(LoadBalancingAlgorithm):
    """Least response time load balancing algorithm."""
    
    def select_server(self, servers: List[ServerNode]) -> Optional[ServerNode]:
        """Select server with lowest response time."""
        if not servers:
            return None
        
        # Filter servers with recorded response times
        servers_with_times = [s for s in servers if s.response_time_ms > 0]
        
        if not servers_with_times:
            # Fall back to least connections if no response times available
            return min(servers, key=lambda s: s.current_connections)
        
        return min(servers_with_times, key=lambda s: s.response_time_ms)


class LoadBalancer:
    """
    Load balancer for distributing client connections across multiple server nodes.
    
    Features:
    - Multiple load balancing algorithms
    - Health checking of server nodes
    - Connection tracking and limits
    - Statistics and monitoring
    - Dynamic server addition/removal
    """
    
    def __init__(
        self,
        strategy: LoadBalancingStrategy = LoadBalancingStrategy.ROUND_ROBIN,
        health_check_interval: int = 30,
        health_check_timeout: int = 5
    ):
        """
        Initialize the load balancer.
        
        Args:
            strategy: Load balancing strategy to use
            health_check_interval: Interval between health checks in seconds
            health_check_timeout: Timeout for health checks in seconds
        """
        self.strategy = strategy
        self.health_check_interval = health_check_interval
        self.health_check_timeout = health_check_timeout
        
        # Server management
        self._servers: Dict[str, ServerNode] = {}
        self._lock = threading.RLock()
        
        # Algorithm instances
        self._algorithms = {
            LoadBalancingStrategy.ROUND_ROBIN: RoundRobinAlgorithm(),
            LoadBalancingStrategy.LEAST_CONNECTIONS: LeastConnectionsAlgorithm(),
            LoadBalancingStrategy.WEIGHTED: WeightedAlgorithm(),
            LoadBalancingStrategy.RANDOM: RandomAlgorithm(),
            LoadBalancingStrategy.LEAST_RESPONSE_TIME: LeastResponseTimeAlgorithm()
        }
        
        # Health checking
        self._health_check_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        
        # Statistics
        self.total_requests = 0
        self.failed_requests = 0
        self.start_time = datetime.now()
        
        logger.info(f"LoadBalancer initialized with strategy: {strategy.value}")
    
    def add_server(
        self,
        host: str,
        port: int,
        weight: int = 100,
        max_connections: int = 1000
    ) -> str:
        """
        Add a server node to the load balancer.
        
        Args:
            host: Server hostname or IP
            port: Server port
            weight: Server weight for weighted algorithms
            max_connections: Maximum connections for this server
            
        Returns:
            Server ID for the added server
        """
        server_id = f"{host}:{port}"
        
        with self._lock:
            if server_id in self._servers:
                raise LoadBalancerError(f"Server {server_id} already exists")
            
            server = ServerNode(
                host=host,
                port=port,
                weight=weight,
                max_connections=max_connections
            )
            
            self._servers[server_id] = server
            
            logger.info(f"Server added: {server_id} (weight: {weight}, max_conn: {max_connections})")
            
            # Start health checking if this is the first server
            if len(self._servers) == 1:
                self._start_health_checking()
            
            return server_id
    
    def remove_server(self, server_id: str) -> bool:
        """
        Remove a server node from the load balancer.
        
        Args:
            server_id: Server ID to remove
            
        Returns:
            True if server was removed, False if not found
        """
        with self._lock:
            if server_id not in self._servers:
                return False
            
            server = self._servers[server_id]
            del self._servers[server_id]
            
            logger.info(f"Server removed: {server_id} (had {server.current_connections} connections)")
            
            # Stop health checking if no servers left
            if not self._servers:
                self._stop_health_checking()
            
            return True
    
    def get_server_for_connection(self) -> Optional[Tuple[str, ServerNode]]:
        """
        Get a server for a new connection.
        
        Returns:
            Tuple of (server_id, server_node) or None if no servers available
        """
        with self._lock:
            # Get healthy servers
            healthy_servers = [
                server for server in self._servers.values()
                if server.is_healthy and server.current_connections < server.max_connections
            ]
            
            if not healthy_servers:
                logger.warning("No healthy servers available for connection")
                return None
            
            # Select server using configured algorithm
            algorithm = self._algorithms[self.strategy]
            selected_server = algorithm.select_server(healthy_servers)
            
            if selected_server is None:
                return None
            
            # Find server ID
            server_id = None
            for sid, server in self._servers.items():
                if server is selected_server:
                    server_id = sid
                    break
            
            if server_id is None:
                return None
            
            # Increment connection count
            if selected_server.increment_connections():
                self.total_requests += 1
                logger.debug(f"Connection assigned to {server_id} ({selected_server.current_connections}/{selected_server.max_connections})")
                return server_id, selected_server
            else:
                logger.warning(f"Server {server_id} rejected connection (at capacity)")
                return None
    
    def release_connection(self, server_id: str) -> bool:
        """
        Release a connection from a server.
        
        Args:
            server_id: Server ID to release connection from
            
        Returns:
            True if connection was released, False if server not found
        """
        with self._lock:
            server = self._servers.get(server_id)
            if server is None:
                return False
            
            server.decrement_connections()
            logger.debug(f"Connection released from {server_id} ({server.current_connections}/{server.max_connections})")
            return True
    
    def record_failure(self, server_id: str) -> None:
        """
        Record a failure for a server.
        
        Args:
            server_id: Server ID that failed
        """
        with self._lock:
            server = self._servers.get(server_id)
            if server:
                server.record_failure()
                self.failed_requests += 1
                
                # Mark as unhealthy if failure rate is too high
                if server.failure_rate > 50.0 and server.total_requests > 10:
                    server.is_healthy = False
                    logger.warning(f"Server {server_id} marked unhealthy due to high failure rate: {server.failure_rate:.1f}%")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get load balancer statistics.
        
        Returns:
            Dictionary containing statistics
        """
        with self._lock:
            uptime = datetime.now() - self.start_time
            
            server_stats = {}
            total_connections = 0
            healthy_servers = 0
            
            for server_id, server in self._servers.items():
                server_stats[server_id] = {
                    'host': server.host,
                    'port': server.port,
                    'weight': server.weight,
                    'current_connections': server.current_connections,
                    'max_connections': server.max_connections,
                    'connection_ratio': server.connection_ratio,
                    'is_healthy': server.is_healthy,
                    'response_time_ms': server.response_time_ms,
                    'total_requests': server.total_requests,
                    'failed_requests': server.failed_requests,
                    'failure_rate': server.failure_rate,
                    'last_health_check': server.last_health_check
                }
                
                total_connections += server.current_connections
                if server.is_healthy:
                    healthy_servers += 1
            
            return {
                'strategy': self.strategy.value,
                'uptime_seconds': uptime.total_seconds(),
                'total_servers': len(self._servers),
                'healthy_servers': healthy_servers,
                'total_connections': total_connections,
                'total_requests': self.total_requests,
                'failed_requests': self.failed_requests,
                'success_rate': ((self.total_requests - self.failed_requests) / max(1, self.total_requests)) * 100,
                'servers': server_stats
            }
    
    def _start_health_checking(self) -> None:
        """Start the health checking thread."""
        if self._health_check_thread and self._health_check_thread.is_alive():
            return
        
        self._health_check_thread = threading.Thread(
            target=self._health_check_loop,
            name="LoadBalancer-HealthCheck",
            daemon=True
        )
        self._health_check_thread.start()
        logger.debug("Health checking started")
    
    def _stop_health_checking(self) -> None:
        """Stop the health checking thread."""
        self._shutdown_event.set()
        if self._health_check_thread and self._health_check_thread.is_alive():
            self._health_check_thread.join(timeout=5.0)
    
    def _health_check_loop(self) -> None:
        """Main health checking loop."""
        while not self._shutdown_event.is_set():
            try:
                self._perform_health_checks()
                self._shutdown_event.wait(self.health_check_interval)
            except Exception as e:
                logger.error(f"Health check error: {e}")
                self._shutdown_event.wait(self.health_check_interval)
    
    def _perform_health_checks(self) -> None:
        """Perform health checks on all servers."""
        with self._lock:
            servers_to_check = list(self._servers.items())
        
        for server_id, server in servers_to_check:
            try:
                # Simple TCP connection test
                start_time = time.time()
                is_healthy = self._check_server_health(server.host, server.port)
                response_time = (time.time() - start_time) * 1000  # Convert to ms
                
                server.update_health(is_healthy, response_time)
                
                if is_healthy and not server.is_healthy:
                    logger.info(f"Server {server_id} is now healthy")
                elif not is_healthy and server.is_healthy:
                    logger.warning(f"Server {server_id} is now unhealthy")
                    
            except Exception as e:
                logger.error(f"Health check failed for {server_id}: {e}")
                server.update_health(False)
    
    def _check_server_health(self, host: str, port: int) -> bool:
        """
        Check if a server is healthy by attempting a TCP connection.
        
        Args:
            host: Server hostname
            port: Server port
            
        Returns:
            True if server is healthy, False otherwise
        """
        import socket
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.health_check_timeout)
                result = sock.connect_ex((host, port))
                return result == 0
        except Exception:
            return False
    
    def shutdown(self) -> None:
        """Shutdown the load balancer."""
        logger.info("Shutting down LoadBalancer...")
        self._stop_health_checking()
        
        with self._lock:
            self._servers.clear()
        
        logger.info("LoadBalancer shutdown complete")
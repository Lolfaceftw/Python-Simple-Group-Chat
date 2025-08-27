"""
Cluster Manager Module

Manages server cluster discovery, coordination, and state synchronization
for horizontal scaling preparation.
"""

import json
import socket
import threading
import time
import uuid
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any, Callable
from enum import Enum

from chat_app.shared.exceptions import ClusterError


logger = logging.getLogger(__name__)


class ServerStatus(Enum):
    """Server status in the cluster."""
    STARTING = "starting"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    SHUTTING_DOWN = "shutting_down"


@dataclass
class ServerNode:
    """Represents a server node in the cluster."""
    node_id: str
    host: str
    port: int
    cluster_port: int
    status: ServerStatus
    last_heartbeat: datetime
    version: str = "1.0.0"
    capabilities: List[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = []
        if self.metadata is None:
            self.metadata = {}
    
    @property
    def is_alive(self) -> bool:
        """Check if the server is considered alive based on heartbeat."""
        if self.status == ServerStatus.SHUTTING_DOWN:
            return False
        
        # Consider server dead if no heartbeat for 60 seconds
        return (datetime.now() - self.last_heartbeat).total_seconds() < 60
    
    @property
    def is_healthy(self) -> bool:
        """Check if the server is healthy and can accept connections."""
        return self.is_alive and self.status in [ServerStatus.HEALTHY, ServerStatus.DEGRADED]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data['last_heartbeat'] = self.last_heartbeat.isoformat()
        data['status'] = self.status.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ServerNode':
        """Create from dictionary."""
        data = data.copy()
        data['last_heartbeat'] = datetime.fromisoformat(data['last_heartbeat'])
        data['status'] = ServerStatus(data['status'])
        return cls(**data)


class ClusterMessage:
    """Represents a message in the cluster protocol."""
    
    def __init__(
        self,
        message_type: str,
        sender_id: str,
        data: Dict[str, Any],
        timestamp: Optional[datetime] = None
    ):
        self.message_type = message_type
        self.sender_id = sender_id
        self.data = data
        self.timestamp = timestamp or datetime.now()
        self.message_id = str(uuid.uuid4())
    
    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps({
            'message_id': self.message_id,
            'message_type': self.message_type,
            'sender_id': self.sender_id,
            'timestamp': self.timestamp.isoformat(),
            'data': self.data
        })
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ClusterMessage':
        """Deserialize from JSON."""
        data = json.loads(json_str)
        msg = cls(
            message_type=data['message_type'],
            sender_id=data['sender_id'],
            data=data['data'],
            timestamp=datetime.fromisoformat(data['timestamp'])
        )
        msg.message_id = data['message_id']
        return msg


class ClusterManager:
    """
    Manages server cluster for horizontal scaling.
    
    Features:
    - Server discovery and registration
    - Heartbeat monitoring
    - Cluster state synchronization
    - Leader election (basic)
    - Message broadcasting
    - Health monitoring
    """
    
    def __init__(
        self,
        node_id: str,
        host: str,
        port: int,
        cluster_port: int,
        discovery_port: int = 8082,
        heartbeat_interval: int = 10,
        discovery_interval: int = 30
    ):
        """
        Initialize the cluster manager.
        
        Args:
            node_id: Unique identifier for this node
            host: Host address for this node
            port: Service port for this node
            cluster_port: Port for cluster communication
            discovery_port: Port for cluster discovery
            heartbeat_interval: Interval between heartbeats in seconds
            discovery_interval: Interval between discovery broadcasts in seconds
        """
        self.node_id = node_id
        self.host = host
        self.port = port
        self.cluster_port = cluster_port
        self.discovery_port = discovery_port
        self.heartbeat_interval = heartbeat_interval
        self.discovery_interval = discovery_interval
        
        # Cluster state
        self._lock = threading.RLock()
        self._nodes: Dict[str, ServerNode] = {}
        self._is_leader = False
        self._leader_id: Optional[str] = None
        self._shutdown_event = threading.Event()
        
        # Network components
        self._cluster_socket: Optional[socket.socket] = None
        self._discovery_socket: Optional[socket.socket] = None
        
        # Threads
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._discovery_thread: Optional[threading.Thread] = None
        self._listener_thread: Optional[threading.Thread] = None
        
        # Message handlers
        self._message_handlers: Dict[str, Callable[[ClusterMessage], None]] = {
            'heartbeat': self._handle_heartbeat,
            'discovery': self._handle_discovery,
            'leader_election': self._handle_leader_election,
            'cluster_state': self._handle_cluster_state,
            'shutdown': self._handle_shutdown
        }
        
        # Statistics
        self.start_time = datetime.now()
        self.messages_sent = 0
        self.messages_received = 0
        
        # Create our own node
        self._local_node = ServerNode(
            node_id=self.node_id,
            host=self.host,
            port=self.port,
            cluster_port=self.cluster_port,
            status=ServerStatus.STARTING,
            last_heartbeat=datetime.now(),
            capabilities=['chat_server', 'load_balancing'],
            metadata={'start_time': self.start_time.isoformat()}
        )
        
        self._nodes[self.node_id] = self._local_node
        
        logger.info(f"ClusterManager initialized for node {node_id} at {host}:{port}")
    
    def start(self) -> None:
        """Start the cluster manager."""
        try:
            self._setup_sockets()
            self._start_threads()
            
            # Update status to healthy
            self._local_node.status = ServerStatus.HEALTHY
            
            # Send initial discovery message
            self._send_discovery_message()
            
            logger.info(f"ClusterManager started for node {self.node_id}")
            
        except Exception as e:
            logger.error(f"Failed to start ClusterManager: {e}")
            self.shutdown()
            raise ClusterError(f"Cluster startup failed: {e}")
    
    def shutdown(self) -> None:
        """Shutdown the cluster manager."""
        logger.info(f"Shutting down ClusterManager for node {self.node_id}")
        
        # Update status
        self._local_node.status = ServerStatus.SHUTTING_DOWN
        
        # Send shutdown notification
        try:
            self._broadcast_message('shutdown', {'reason': 'graceful_shutdown'})
        except Exception as e:
            logger.error(f"Error sending shutdown message: {e}")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Stop threads
        self._stop_threads()
        
        # Close sockets
        self._close_sockets()
        
        logger.info("ClusterManager shutdown complete")
    
    def get_cluster_nodes(self) -> List[ServerNode]:
        """
        Get all nodes in the cluster.
        
        Returns:
            List of server nodes
        """
        with self._lock:
            return [node for node in self._nodes.values() if node.is_alive]
    
    def get_healthy_nodes(self) -> List[ServerNode]:
        """
        Get healthy nodes that can accept connections.
        
        Returns:
            List of healthy server nodes
        """
        with self._lock:
            return [node for node in self._nodes.values() if node.is_healthy]
    
    def is_leader(self) -> bool:
        """Check if this node is the cluster leader."""
        return self._is_leader
    
    def get_leader_id(self) -> Optional[str]:
        """Get the current cluster leader ID."""
        return self._leader_id
    
    def broadcast_to_cluster(self, message_type: str, data: Dict[str, Any]) -> int:
        """
        Broadcast a message to all cluster nodes.
        
        Args:
            message_type: Type of message
            data: Message data
            
        Returns:
            Number of nodes the message was sent to
        """
        return self._broadcast_message(message_type, data)
    
    def send_to_node(self, node_id: str, message_type: str, data: Dict[str, Any]) -> bool:
        """
        Send a message to a specific node.
        
        Args:
            node_id: Target node ID
            message_type: Type of message
            data: Message data
            
        Returns:
            True if message was sent successfully
        """
        with self._lock:
            node = self._nodes.get(node_id)
            if not node or not node.is_alive:
                return False
        
        try:
            message = ClusterMessage(message_type, self.node_id, data)
            self._send_message_to_node(node, message)
            return True
        except Exception as e:
            logger.error(f"Failed to send message to node {node_id}: {e}")
            return False
    
    def get_cluster_statistics(self) -> Dict[str, Any]:
        """
        Get cluster statistics.
        
        Returns:
            Dictionary containing cluster statistics
        """
        with self._lock:
            uptime = datetime.now() - self.start_time
            
            node_stats = {}
            healthy_nodes = 0
            total_nodes = 0
            
            for node in self._nodes.values():
                if node.is_alive:
                    total_nodes += 1
                    if node.is_healthy:
                        healthy_nodes += 1
                    
                    node_stats[node.node_id] = {
                        'host': node.host,
                        'port': node.port,
                        'status': node.status.value,
                        'last_heartbeat': node.last_heartbeat.isoformat(),
                        'is_healthy': node.is_healthy,
                        'capabilities': node.capabilities,
                        'metadata': node.metadata
                    }
            
            return {
                'node_id': self.node_id,
                'is_leader': self._is_leader,
                'leader_id': self._leader_id,
                'uptime_seconds': uptime.total_seconds(),
                'total_nodes': total_nodes,
                'healthy_nodes': healthy_nodes,
                'messages_sent': self.messages_sent,
                'messages_received': self.messages_received,
                'nodes': node_stats
            }
    
    def _setup_sockets(self) -> None:
        """Set up network sockets for cluster communication."""
        try:
            # Cluster communication socket
            self._cluster_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._cluster_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._cluster_socket.bind((self.host, self.cluster_port))
            self._cluster_socket.settimeout(1.0)
            
            # Discovery socket
            self._discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            logger.debug(f"Cluster sockets set up on port {self.cluster_port}")
            
        except Exception as e:
            raise ClusterError(f"Failed to set up cluster sockets: {e}")
    
    def _close_sockets(self) -> None:
        """Close network sockets."""
        for sock in [self._cluster_socket, self._discovery_socket]:
            if sock:
                try:
                    sock.close()
                except Exception as e:
                    logger.error(f"Error closing socket: {e}")
    
    def _start_threads(self) -> None:
        """Start background threads."""
        # Heartbeat thread
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"Cluster-Heartbeat-{self.node_id}",
            daemon=True
        )
        self._heartbeat_thread.start()
        
        # Discovery thread
        self._discovery_thread = threading.Thread(
            target=self._discovery_loop,
            name=f"Cluster-Discovery-{self.node_id}",
            daemon=True
        )
        self._discovery_thread.start()
        
        # Message listener thread
        self._listener_thread = threading.Thread(
            target=self._message_listener_loop,
            name=f"Cluster-Listener-{self.node_id}",
            daemon=True
        )
        self._listener_thread.start()
        
        logger.debug("Cluster threads started")
    
    def _stop_threads(self) -> None:
        """Stop background threads."""
        threads = [
            ("Heartbeat", self._heartbeat_thread),
            ("Discovery", self._discovery_thread),
            ("Listener", self._listener_thread)
        ]
        
        for name, thread in threads:
            if thread and thread.is_alive():
                try:
                    thread.join(timeout=5.0)
                    if thread.is_alive():
                        logger.warning(f"{name} thread did not stop gracefully")
                except Exception as e:
                    logger.error(f"Error stopping {name} thread: {e}")
    
    def _heartbeat_loop(self) -> None:
        """Main heartbeat loop."""
        while not self._shutdown_event.is_set():
            try:
                # Update our heartbeat
                self._local_node.last_heartbeat = datetime.now()
                
                # Send heartbeat to cluster
                self._broadcast_message('heartbeat', {
                    'status': self._local_node.status.value,
                    'metadata': self._local_node.metadata
                })
                
                # Clean up dead nodes
                self._cleanup_dead_nodes()
                
                # Check for leader election
                self._check_leader_election()
                
                self._shutdown_event.wait(self.heartbeat_interval)
                
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")
                self._shutdown_event.wait(self.heartbeat_interval)
    
    def _discovery_loop(self) -> None:
        """Main discovery loop."""
        while not self._shutdown_event.is_set():
            try:
                self._send_discovery_message()
                self._shutdown_event.wait(self.discovery_interval)
            except Exception as e:
                logger.error(f"Discovery loop error: {e}")
                self._shutdown_event.wait(self.discovery_interval)
    
    def _message_listener_loop(self) -> None:
        """Main message listener loop."""
        while not self._shutdown_event.is_set():
            try:
                if self._cluster_socket:
                    data, addr = self._cluster_socket.recvfrom(4096)
                    message_str = data.decode('utf-8')
                    message = ClusterMessage.from_json(message_str)
                    
                    # Don't process our own messages
                    if message.sender_id != self.node_id:
                        self._process_message(message, addr)
                        self.messages_received += 1
                        
            except socket.timeout:
                continue
            except Exception as e:
                if not self._shutdown_event.is_set():
                    logger.error(f"Message listener error: {e}")
    
    def _process_message(self, message: ClusterMessage, sender_addr: tuple) -> None:
        """Process a received cluster message."""
        try:
            handler = self._message_handlers.get(message.message_type)
            if handler:
                handler(message)
            else:
                logger.warning(f"Unknown message type: {message.message_type}")
        except Exception as e:
            logger.error(f"Error processing message {message.message_type}: {e}")
    
    def _handle_heartbeat(self, message: ClusterMessage) -> None:
        """Handle heartbeat message."""
        with self._lock:
            node = self._nodes.get(message.sender_id)
            if node:
                node.last_heartbeat = message.timestamp
                node.status = ServerStatus(message.data.get('status', 'healthy'))
                node.metadata.update(message.data.get('metadata', {}))
            else:
                logger.debug(f"Received heartbeat from unknown node: {message.sender_id}")
    
    def _handle_discovery(self, message: ClusterMessage) -> None:
        """Handle discovery message."""
        node_data = message.data.get('node_info')
        if not node_data:
            return
        
        try:
            node = ServerNode.from_dict(node_data)
            
            with self._lock:
                if node.node_id not in self._nodes:
                    self._nodes[node.node_id] = node
                    logger.info(f"Discovered new node: {node.node_id} at {node.host}:{node.port}")
                else:
                    # Update existing node info
                    existing_node = self._nodes[node.node_id]
                    existing_node.host = node.host
                    existing_node.port = node.port
                    existing_node.cluster_port = node.cluster_port
                    existing_node.capabilities = node.capabilities
                    existing_node.metadata.update(node.metadata)
                    
        except Exception as e:
            logger.error(f"Error processing discovery message: {e}")
    
    def _handle_leader_election(self, message: ClusterMessage) -> None:
        """Handle leader election message."""
        candidate_id = message.data.get('candidate_id')
        if not candidate_id:
            return
        
        # Simple leader election: lowest node_id wins
        with self._lock:
            all_nodes = [node.node_id for node in self._nodes.values() if node.is_healthy]
            if all_nodes:
                new_leader = min(all_nodes)
                if new_leader != self._leader_id:
                    self._leader_id = new_leader
                    self._is_leader = (new_leader == self.node_id)
                    logger.info(f"New cluster leader elected: {new_leader}")
    
    def _handle_cluster_state(self, message: ClusterMessage) -> None:
        """Handle cluster state synchronization message."""
        # This could be used for more complex state synchronization
        pass
    
    def _handle_shutdown(self, message: ClusterMessage) -> None:
        """Handle shutdown notification."""
        sender_id = message.sender_id
        with self._lock:
            if sender_id in self._nodes:
                self._nodes[sender_id].status = ServerStatus.SHUTTING_DOWN
                logger.info(f"Node {sender_id} is shutting down")
    
    def _broadcast_message(self, message_type: str, data: Dict[str, Any]) -> int:
        """Broadcast a message to all cluster nodes."""
        message = ClusterMessage(message_type, self.node_id, data)
        sent_count = 0
        
        with self._lock:
            nodes_to_send = [node for node in self._nodes.values() 
                           if node.node_id != self.node_id and node.is_alive]
        
        for node in nodes_to_send:
            try:
                self._send_message_to_node(node, message)
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send message to {node.node_id}: {e}")
        
        self.messages_sent += sent_count
        return sent_count
    
    def _send_message_to_node(self, node: ServerNode, message: ClusterMessage) -> None:
        """Send a message to a specific node."""
        if self._cluster_socket:
            message_data = message.to_json().encode('utf-8')
            self._cluster_socket.sendto(message_data, (node.host, node.cluster_port))
    
    def _send_discovery_message(self) -> None:
        """Send discovery message to find other nodes."""
        if not self._discovery_socket:
            return
        
        message = ClusterMessage('discovery', self.node_id, {
            'node_info': self._local_node.to_dict()
        })
        
        try:
            message_data = message.to_json().encode('utf-8')
            self._discovery_socket.sendto(
                message_data,
                ('<broadcast>', self.discovery_port)
            )
        except Exception as e:
            logger.error(f"Failed to send discovery message: {e}")
    
    def _cleanup_dead_nodes(self) -> None:
        """Remove nodes that haven't sent heartbeats recently."""
        current_time = datetime.now()
        dead_nodes = []
        
        with self._lock:
            for node_id, node in self._nodes.items():
                if node_id != self.node_id and not node.is_alive:
                    dead_nodes.append(node_id)
        
        for node_id in dead_nodes:
            with self._lock:
                if node_id in self._nodes:
                    del self._nodes[node_id]
                    logger.info(f"Removed dead node: {node_id}")
    
    def _check_leader_election(self) -> None:
        """Check if leader election is needed."""
        with self._lock:
            healthy_nodes = [node.node_id for node in self._nodes.values() if node.is_healthy]
            
            if not healthy_nodes:
                return
            
            # If no leader or leader is dead, trigger election
            if not self._leader_id or self._leader_id not in healthy_nodes:
                self._broadcast_message('leader_election', {
                    'candidate_id': self.node_id,
                    'healthy_nodes': healthy_nodes
                })
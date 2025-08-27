"""
Service Discovery

Implements UDP-based service discovery for finding chat servers on the network.
"""

import socket
import time
import threading
from typing import List, Set, Optional
from dataclasses import dataclass

from chat_app.shared.constants import (
    DISCOVERY_MESSAGE,
    DEFAULT_DISCOVERY_PORT,
    DEFAULT_DISCOVERY_TIMEOUT
)
from chat_app.shared.protocols import ServiceDiscovery as ServiceDiscoveryProtocol


@dataclass
class DiscoveryConfig:
    """Configuration for service discovery."""
    discovery_port: int = DEFAULT_DISCOVERY_PORT
    discovery_message: bytes = DISCOVERY_MESSAGE
    timeout: int = DEFAULT_DISCOVERY_TIMEOUT
    bind_address: str = ""


class ServiceDiscovery(ServiceDiscoveryProtocol):
    """
    UDP-based service discovery implementation.
    
    Allows clients to discover chat servers on the local network
    and servers to broadcast their presence.
    """
    
    def __init__(self, config: Optional[DiscoveryConfig] = None) -> None:
        """
        Initialize service discovery.
        
        Args:
            config: Discovery configuration.
        """
        self.config = config or DiscoveryConfig()
        self._broadcasting = False
        self._broadcast_thread: Optional[threading.Thread] = None
        self._broadcast_socket: Optional[socket.socket] = None
    
    def discover_servers(self, timeout: Optional[int] = None) -> List[str]:
        """
        Discover available servers on the network.
        
        Args:
            timeout: Discovery timeout in seconds.
            
        Returns:
            List of discovered server addresses.
        """
        if timeout is None:
            timeout = self.config.timeout
        
        discovered_servers: Set[str] = set()
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                # Allow multiple clients on the same machine to listen
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                
                # Bind to discovery port
                try:
                    sock.bind((self.config.bind_address, self.config.discovery_port))
                except OSError as e:
                    # Port might be in use by another client
                    return []
                
                # Set timeout for receiving
                sock.settimeout(timeout)
                
                # Listen for discovery messages
                end_time = time.time() + timeout
                while time.time() < end_time:
                    try:
                        data, addr = sock.recvfrom(1024)
                        if data == self.config.discovery_message:
                            discovered_servers.add(addr[0])
                    except socket.timeout:
                        break
                    except Exception:
                        # Ignore other errors and continue
                        continue
        
        except Exception:
            # Return empty list on any setup errors
            return []
        
        return sorted(list(discovered_servers))
    
    def start_broadcasting(self) -> None:
        """Start broadcasting server presence."""
        if self._broadcasting:
            return
        
        self._broadcasting = True
        self._broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self._broadcast_thread.start()
    
    def stop_broadcasting(self) -> None:
        """Stop broadcasting server presence."""
        self._broadcasting = False
        
        if self._broadcast_socket:
            try:
                self._broadcast_socket.close()
            except OSError:
                pass
            self._broadcast_socket = None
        
        if self._broadcast_thread and self._broadcast_thread.is_alive():
            self._broadcast_thread.join(timeout=2.0)
    
    def _broadcast_loop(self) -> None:
        """Main broadcasting loop."""
        try:
            self._broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            while self._broadcasting:
                try:
                    # Broadcast discovery message
                    self._broadcast_socket.sendto(
                        self.config.discovery_message,
                        ('<broadcast>', self.config.discovery_port)
                    )
                    
                    # Wait before next broadcast
                    time.sleep(5.0)  # Broadcast every 5 seconds
                    
                except OSError:
                    # Socket might be closed
                    break
                except Exception:
                    # Continue on other errors
                    continue
        
        except Exception:
            # Exit broadcast loop on setup errors
            pass
        finally:
            if self._broadcast_socket:
                try:
                    self._broadcast_socket.close()
                except OSError:
                    pass
                self._broadcast_socket = None
    
    def is_broadcasting(self) -> bool:
        """
        Check if currently broadcasting.
        
        Returns:
            True if broadcasting, False otherwise.
        """
        return self._broadcasting
    
    def get_config(self) -> DiscoveryConfig:
        """
        Get the current discovery configuration.
        
        Returns:
            Current discovery configuration.
        """
        return self.config
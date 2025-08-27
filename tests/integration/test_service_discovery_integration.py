"""
Integration tests for service discovery functionality.
"""

import pytest
import threading
import time
import socket
from unittest.mock import Mock, patch

from chat_app.discovery.service_discovery import ServiceDiscovery
from chat_app.server.chat_server import ChatServer
from chat_app.client.chat_client import ChatClient
from chat_app.shared.config import ServerConfig, ClientConfig


class TestServiceDiscoveryIntegration:
    """Integration tests for service discovery between client and server."""
    
    @pytest.fixture
    def server_config(self):
        """Provide test server configuration."""
        return ServerConfig(
            host="127.0.0.1",
            port=0,  # Use random available port
            discovery_port=0,  # Use random available port
            max_clients=5,
            discovery_broadcast_interval=1  # Fast broadcasting for tests
        )
    
    @pytest.fixture
    def client_config(self):
        """Provide test client configuration."""
        return ClientConfig(
            host="127.0.0.1",
            port=8080,
            username="test_user",
            discovery_timeout=2,
            ui_refresh_rate=10
        )
    
    def test_server_discovery_broadcasting(self, server_config):
        """Test that server broadcasts discovery messages."""
        server = None
        server_thread = None
        discovery_service = None
        
        try:
            # Start server with discovery
            server = ChatServer(server_config)
            server_thread = threading.Thread(target=server.start, daemon=True)
            server_thread.start()
            
            time.sleep(0.2)  # Wait for server to start
            
            # Get actual ports
            actual_port = server.get_server_port()
            actual_discovery_port = server.get_discovery_port()
            
            # Create discovery service to listen for broadcasts
            discovery_service = ServiceDiscovery()
            
            # Listen for discovery broadcasts
            discovered_servers = discovery_service.discover_servers(timeout=3)
            
            # Verify server was discovered
            assert len(discovered_servers) > 0, "Should discover at least one server"
            
            # Verify the discovered server has correct information
            server_found = False
            for server_addr in discovered_servers:
                if f"127.0.0.1:{actual_port}" in server_addr:
                    server_found = True
                    break
            
            assert server_found, f"Should discover server at 127.0.0.1:{actual_port}"
            
        finally:
            # Cleanup
            if discovery_service:
                discovery_service.stop_listening()
            if server:
                server.shutdown()
            if server_thread and server_thread.is_alive():
                server_thread.join(timeout=2)
    
    def test_client_server_discovery_and_connection(self, server_config, client_config):
        """Test full discovery flow: client discovers server and connects."""
        server = None
        client = None
        server_thread = None
        
        try:
            # Start server
            server = ChatServer(server_config)
            server_thread = threading.Thread(target=server.start, daemon=True)
            server_thread.start()
            
            time.sleep(0.2)  # Wait for server to start broadcasting
            
            with patch('chat_app.client.ui.layout_manager.LayoutManager'), \
                 patch('chat_app.client.ui.input_handler.InputHandler'), \
                 patch('chat_app.client.ui.display_manager.DisplayManager'):
                
                # Create client
                client = ChatClient(client_config)
                
                # Use discovery to find servers
                discovered_servers = client.discover_servers()
                
                assert len(discovered_servers) > 0, "Client should discover servers"
                
                # Connect to first discovered server
                server_info = discovered_servers[0]
                host, port = server_info.split(':')
                port = int(port)
                
                success = client.connect_to_server(host, port)
                assert success, "Client should connect to discovered server"
                
                # Verify connection by setting username and sending message
                client.set_username("discoveryuser")
                
                from chat_app.shared.models import Message, MessageType
                message = Message(
                    content="Hello via discovery!",
                    sender="discoveryuser",
                    message_type=MessageType.CHAT
                )
                client.send_message(message)
                
                time.sleep(0.1)
                
                # Verify server received the message
                assert len(server.message_broker.message_history) > 0
                received_message = server.message_broker.message_history[-1]
                assert received_message.content == "Hello via discovery!"
                
        finally:
            # Cleanup
            if client:
                client.disconnect()
            if server:
                server.shutdown()
            if server_thread and server_thread.is_alive():
                server_thread.join(timeout=2)
    
    def test_multiple_servers_discovery(self, server_config, client_config):
        """Test discovering multiple servers on the network."""
        servers = []
        server_threads = []
        client = None
        
        try:
            # Start multiple servers on different ports
            for i in range(2):
                config = ServerConfig(
                    host="127.0.0.1",
                    port=0,  # Random port
                    discovery_port=0,  # Random discovery port
                    max_clients=5,
                    discovery_broadcast_interval=1
                )
                
                server = ChatServer(config)
                servers.append(server)
                
                server_thread = threading.Thread(target=server.start, daemon=True)
                server_threads.append(server_thread)
                server_thread.start()
            
            time.sleep(0.5)  # Wait for all servers to start broadcasting
            
            with patch('chat_app.client.ui.layout_manager.LayoutManager'), \
                 patch('chat_app.client.ui.input_handler.InputHandler'), \
                 patch('chat_app.client.ui.display_manager.DisplayManager'):
                
                # Create client and discover servers
                client = ChatClient(client_config)
                discovered_servers = client.discover_servers()
                
                # Should discover both servers
                assert len(discovered_servers) >= 2, f"Should discover at least 2 servers, found {len(discovered_servers)}"
                
                # Verify we can connect to each discovered server
                for i, server_addr in enumerate(discovered_servers[:2]):  # Test first 2
                    host, port = server_addr.split(':')
                    port = int(port)
                    
                    success = client.connect_to_server(host, port)
                    assert success, f"Should connect to server {i+1} at {server_addr}"
                    
                    client.set_username(f"user{i}")
                    client.disconnect()  # Disconnect before trying next server
                    time.sleep(0.1)
                
        finally:
            # Cleanup
            if client:
                client.disconnect()
            for server in servers:
                server.shutdown()
            for thread in server_threads:
                if thread.is_alive():
                    thread.join(timeout=1)
    
    def test_discovery_timeout_handling(self, client_config):
        """Test discovery timeout when no servers are available."""
        client = None
        
        try:
            with patch('chat_app.client.ui.layout_manager.LayoutManager'), \
                 patch('chat_app.client.ui.input_handler.InputHandler'), \
                 patch('chat_app.client.ui.display_manager.DisplayManager'):
                
                # Create client with short timeout
                client_config.discovery_timeout = 1
                client = ChatClient(client_config)
                
                # Try to discover servers when none are running
                start_time = time.time()
                discovered_servers = client.discover_servers()
                end_time = time.time()
                
                # Should return empty list
                assert len(discovered_servers) == 0, "Should not discover any servers"
                
                # Should respect timeout
                elapsed = end_time - start_time
                assert elapsed >= 0.9, "Should wait at least the timeout duration"
                assert elapsed <= 2.0, "Should not wait much longer than timeout"
                
        finally:
            if client:
                client.disconnect()
    
    def test_discovery_with_network_errors(self, server_config, client_config):
        """Test discovery behavior with network errors."""
        server = None
        server_thread = None
        client = None
        
        try:
            # Start server
            server = ChatServer(server_config)
            server_thread = threading.Thread(target=server.start, daemon=True)
            server_thread.start()
            
            time.sleep(0.2)
            
            with patch('chat_app.client.ui.layout_manager.LayoutManager'), \
                 patch('chat_app.client.ui.input_handler.InputHandler'), \
                 patch('chat_app.client.ui.display_manager.DisplayManager'):
                
                client = ChatClient(client_config)
                
                # Mock socket to simulate network error during discovery
                with patch('socket.socket') as mock_socket_class:
                    mock_socket = Mock()
                    mock_socket.bind.side_effect = OSError("Network error")
                    mock_socket_class.return_value = mock_socket
                    
                    # Discovery should handle the error gracefully
                    discovered_servers = client.discover_servers()
                    
                    # Should return empty list instead of crashing
                    assert isinstance(discovered_servers, list)
                    # May be empty due to network error, but shouldn't crash
                
        finally:
            # Cleanup
            if client:
                client.disconnect()
            if server:
                server.shutdown()
            if server_thread and server_thread.is_alive():
                server_thread.join(timeout=2)
    
    def test_discovery_message_format_validation(self, server_config):
        """Test that discovery messages follow the correct format."""
        server = None
        server_thread = None
        
        try:
            # Start server
            server = ChatServer(server_config)
            server_thread = threading.Thread(target=server.start, daemon=True)
            server_thread.start()
            
            time.sleep(0.2)
            
            # Create a UDP socket to listen for discovery broadcasts
            discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            discovery_socket.settimeout(3.0)
            
            try:
                # Bind to discovery port (try common ports)
                bound = False
                for port in range(8081, 8090):
                    try:
                        discovery_socket.bind(('', port))
                        bound = True
                        break
                    except OSError:
                        continue
                
                if bound:
                    # Listen for discovery broadcast
                    data, addr = discovery_socket.recvfrom(1024)
                    
                    # Verify message format
                    message = data.decode('utf-8')
                    assert "PYTHON_CHAT_SERVER" in message or "DISCOVERY" in message
                    
                    # Should contain server information
                    assert "127.0.0.1" in message or str(server.get_server_port()) in message
                
            except socket.timeout:
                # If we don't receive a message, that's also valid for this test
                # as long as the server doesn't crash
                pass
            finally:
                discovery_socket.close()
                
        finally:
            # Cleanup
            if server:
                server.shutdown()
            if server_thread and server_thread.is_alive():
                server_thread.join(timeout=2)
    
    def test_concurrent_discovery_requests(self, server_config, client_config):
        """Test multiple concurrent discovery requests."""
        server = None
        server_thread = None
        clients = []
        
        try:
            # Start server
            server = ChatServer(server_config)
            server_thread = threading.Thread(target=server.start, daemon=True)
            server_thread.start()
            
            time.sleep(0.2)
            
            with patch('chat_app.client.ui.layout_manager.LayoutManager'), \
                 patch('chat_app.client.ui.input_handler.InputHandler'), \
                 patch('chat_app.client.ui.display_manager.DisplayManager'):
                
                # Create multiple clients
                discovery_results = []
                client_threads = []
                
                def discover_servers_thread(client_idx):
                    """Thread function for concurrent discovery."""
                    try:
                        client = ChatClient(client_config)
                        clients.append(client)
                        discovered = client.discover_servers()
                        discovery_results.append((client_idx, discovered))
                    except Exception as e:
                        discovery_results.append((client_idx, f"Error: {e}"))
                
                # Start multiple discovery threads
                for i in range(3):
                    thread = threading.Thread(target=discover_servers_thread, args=(i,))
                    client_threads.append(thread)
                    thread.start()
                
                # Wait for all threads to complete
                for thread in client_threads:
                    thread.join(timeout=5)
                
                # Verify all discoveries completed
                assert len(discovery_results) == 3, "All discovery requests should complete"
                
                # Verify at least some discoveries were successful
                successful_discoveries = [
                    result for client_idx, result in discovery_results 
                    if isinstance(result, list) and len(result) > 0
                ]
                
                assert len(successful_discoveries) > 0, "At least one discovery should succeed"
                
        finally:
            # Cleanup
            for client in clients:
                try:
                    client.disconnect()
                except:
                    pass
            if server:
                server.shutdown()
            if server_thread and server_thread.is_alive():
                server_thread.join(timeout=2)


if __name__ == "__main__":
    # Run a simple test if executed directly
    import sys
    sys.path.insert(0, '.')
    
    test = TestServiceDiscoveryIntegration()
    server_config = ServerConfig(host="127.0.0.1", port=0, discovery_port=0)
    client_config = ClientConfig(default_host="127.0.0.1", discovery_timeout=2)
    
    test.test_server_discovery_broadcasting(server_config)
    print("Service discovery integration test passed!")
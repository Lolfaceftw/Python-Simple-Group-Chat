"""
Integration tests for client-server communication flows.
"""

import pytest
import threading
import time
import socket
from unittest.mock import Mock, patch

from chat_app.server.chat_server import ChatServer
from chat_app.client.chat_client import ChatClient
from chat_app.shared.config import ServerConfig, ClientConfig
from chat_app.shared.models import Message, MessageType, ConnectionStatus


class TestClientServerCommunication:
    """Integration tests for full client-server communication."""
    
    @pytest.fixture
    def server_config(self):
        """Provide test server configuration."""
        return ServerConfig(
            host="127.0.0.1",
            port=0,  # Use random available port
            max_clients=5,
            rate_limit_messages_per_minute=100,
            max_message_length=500,
            max_username_length=25
        )
    
    @pytest.fixture
    def client_config(self):
        """Provide test client configuration."""
        return ClientConfig(
            host="127.0.0.1",
            port=8080,  # Will be updated with actual server port
            username="test_user",
            discovery_timeout=1,
            ui_refresh_rate=10,
            reconnect_attempts=1,
            reconnect_delay=1
        )
    
    def test_single_client_connection_and_messaging(self, server_config, client_config):
        """Test single client connecting and sending messages."""
        server = None
        client = None
        server_thread = None
        
        try:
            # Start server
            server = ChatServer(server_config)
            server_thread = threading.Thread(target=server.start, daemon=True)
            server_thread.start()
            
            # Wait for server to start and get actual port
            time.sleep(0.1)
            actual_port = server.get_server_port()
            client_config.port = actual_port
            
            # Create mock UI components for client
            with patch('chat_app.client.ui.layout_manager.LayoutManager'), \
                 patch('chat_app.client.ui.input_handler.InputHandler'), \
                 patch('chat_app.client.ui.display_manager.DisplayManager'):
                
                # Create proper client config with username
                from chat_app.client.chat_client import ClientConfig as LocalClientConfig
                local_client_config = LocalClientConfig(
                    host="127.0.0.1",
                    port=actual_port,
                    username="testuser",
                    ui_refresh_rate=10
                )
                
                # Start client
                client = ChatClient(local_client_config)
                
                # Start client in a separate thread
                client_thread = threading.Thread(target=client.start, daemon=True)
                client_thread.start()
                
                # Wait for client to connect
                time.sleep(0.2)
                
                # Verify client is connected
                assert client.get_connection_status() == ConnectionStatus.CONNECTED
                
                # Send a message
                success = client.send_message("Hello, server!")
                assert success, "Message should be sent successfully"
                
                # Wait for message processing
                time.sleep(0.1)
                
                # Verify server received the message
                message_history = server.message_broker.get_message_history()
                assert len(message_history) > 0
                received_message = message_history[-1]
                assert "Hello, server!" in received_message.content
                assert "testuser" in received_message.content
                
        finally:
            # Cleanup
            if client:
                client.shutdown()
            if server:
                server.shutdown()
            if server_thread and server_thread.is_alive():
                server_thread.join(timeout=1)
    
    def test_multiple_clients_communication(self, server_config, client_config):
        """Test multiple clients connecting and communicating."""
        server = None
        clients = []
        server_thread = None
        
        try:
            # Start server
            server = ChatServer(server_config)
            server_thread = threading.Thread(target=server.start, daemon=True)
            server_thread.start()
            
            # Wait for server to start
            time.sleep(0.1)
            actual_port = server.get_server_port()
            client_config.port = actual_port
            
            # Create multiple clients
            with patch('chat_app.client.ui.layout_manager.LayoutManager'), \
                 patch('chat_app.client.ui.input_handler.InputHandler'), \
                 patch('chat_app.client.ui.display_manager.DisplayManager'):
                
                for i in range(3):
                    client = ChatClient(client_config)
                    clients.append(client)
                    
                    # Connect each client
                    success = client.connect_to_server("127.0.0.1", actual_port)
                    assert success, f"Client {i} should connect successfully"
                    
                    # Set unique username
                    client.set_username(f"user{i}")
                
                # Wait for all connections to be established
                time.sleep(0.2)
                
                # Verify all clients are connected
                assert len(server.client_manager.get_all_clients()) == 3
                
                # Send messages from different clients
                for i, client in enumerate(clients):
                    message = Message(
                        content=f"Message from user{i}",
                        sender=f"user{i}",
                        message_type=MessageType.CHAT
                    )
                    client.send_message(message)
                
                # Wait for message processing
                time.sleep(0.2)
                
                # Verify all messages were received by server
                assert len(server.message_broker.message_history) >= 3
                
                # Verify messages from all users are present
                senders = [msg.sender for msg in server.message_broker.message_history]
                assert "user0" in senders
                assert "user1" in senders
                assert "user2" in senders
                
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
                server_thread.join(timeout=1)
    
    def test_client_disconnection_handling(self, server_config, client_config):
        """Test proper handling of client disconnections."""
        server = None
        clients = []
        server_thread = None
        
        try:
            # Start server
            server = ChatServer(server_config)
            server_thread = threading.Thread(target=server.start, daemon=True)
            server_thread.start()
            
            time.sleep(0.1)
            actual_port = server.get_server_port()
            client_config.port = actual_port
            
            with patch('chat_app.client.ui.layout_manager.LayoutManager'), \
                 patch('chat_app.client.ui.input_handler.InputHandler'), \
                 patch('chat_app.client.ui.display_manager.DisplayManager'):
                
                # Connect two clients
                for i in range(2):
                    client = ChatClient(client_config)
                    clients.append(client)
                    client.connect_to_server("127.0.0.1", actual_port)
                    client.set_username(f"user{i}")
                
                time.sleep(0.1)
                
                # Verify both clients are connected
                assert len(server.client_manager.get_all_clients()) == 2
                
                # Disconnect first client
                clients[0].disconnect()
                
                time.sleep(0.1)
                
                # Verify only one client remains
                assert len(server.client_manager.get_all_clients()) == 1
                
                # Remaining client should still be able to send messages
                message = Message(
                    content="Still here!",
                    sender="user1",
                    message_type=MessageType.CHAT
                )
                clients[1].send_message(message)
                
                time.sleep(0.1)
                
                # Verify message was processed
                assert len(server.message_broker.message_history) > 0
                last_message = server.message_broker.message_history[-1]
                assert last_message.content == "Still here!"
                
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
                server_thread.join(timeout=1)
    
    def test_message_broadcasting(self, server_config, client_config):
        """Test that messages are properly broadcast to all clients."""
        server = None
        clients = []
        server_thread = None
        received_messages = [[] for _ in range(3)]  # Track messages for each client
        
        try:
            # Start server
            server = ChatServer(server_config)
            server_thread = threading.Thread(target=server.start, daemon=True)
            server_thread.start()
            
            time.sleep(0.1)
            actual_port = server.get_server_port()
            client_config.port = actual_port
            
            with patch('chat_app.client.ui.layout_manager.LayoutManager'), \
                 patch('chat_app.client.ui.input_handler.InputHandler'), \
                 patch('chat_app.client.ui.display_manager.DisplayManager'):
                
                # Create clients with message tracking
                for i in range(3):
                    client = ChatClient(client_config)
                    clients.append(client)
                    
                    # Mock the message handler to track received messages
                    original_handle = client.message_handler.handle_message
                    def make_handler(client_idx):
                        def handler(message):
                            received_messages[client_idx].append(message)
                            return original_handle(message)
                        return handler
                    
                    client.message_handler.handle_message = make_handler(i)
                    
                    # Connect client
                    client.connect_to_server("127.0.0.1", actual_port)
                    client.set_username(f"user{i}")
                
                time.sleep(0.2)
                
                # Send a message from first client
                message = Message(
                    content="Broadcast test message",
                    sender="user0",
                    message_type=MessageType.CHAT
                )
                clients[0].send_message(message)
                
                time.sleep(0.2)
                
                # Verify message was broadcast to other clients (not sender)
                # Note: Typically sender doesn't receive their own message back
                assert len(received_messages[1]) > 0 or len(received_messages[2]) > 0
                
                # Check that the message content was preserved
                all_received = received_messages[1] + received_messages[2]
                broadcast_messages = [msg for msg in all_received 
                                    if hasattr(msg, 'content') and 
                                    msg.content == "Broadcast test message"]
                assert len(broadcast_messages) > 0
                
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
                server_thread.join(timeout=1)
    
    def test_rate_limiting_integration(self, server_config, client_config):
        """Test rate limiting prevents message spam."""
        # Configure aggressive rate limiting for testing
        server_config.rate_limit_messages_per_minute = 5
        
        server = None
        client = None
        server_thread = None
        
        try:
            # Start server
            server = ChatServer(server_config)
            server_thread = threading.Thread(target=server.start, daemon=True)
            server_thread.start()
            
            time.sleep(0.1)
            actual_port = server.get_server_port()
            client_config.port = actual_port
            
            with patch('chat_app.client.ui.layout_manager.LayoutManager'), \
                 patch('chat_app.client.ui.input_handler.InputHandler'), \
                 patch('chat_app.client.ui.display_manager.DisplayManager'):
                
                # Connect client
                client = ChatClient(client_config)
                client.connect_to_server("127.0.0.1", actual_port)
                client.set_username("spammer")
                
                time.sleep(0.1)
                
                # Send messages rapidly to trigger rate limiting
                successful_sends = 0
                for i in range(10):
                    try:
                        message = Message(
                            content=f"Spam message {i}",
                            sender="spammer",
                            message_type=MessageType.CHAT
                        )
                        client.send_message(message)
                        successful_sends += 1
                        time.sleep(0.01)  # Small delay between messages
                    except Exception:
                        # Rate limiting may cause exceptions
                        break
                
                time.sleep(0.2)
                
                # Verify that not all messages were processed due to rate limiting
                # The exact number depends on implementation, but should be limited
                message_count = len(server.message_broker.message_history)
                assert message_count <= server_config.rate_limit_messages_per_minute
                
        finally:
            # Cleanup
            if client:
                client.disconnect()
            if server:
                server.shutdown()
            if server_thread and server_thread.is_alive():
                server_thread.join(timeout=1)
    
    def test_error_scenarios(self, server_config, client_config):
        """Test various error scenarios in client-server communication."""
        server = None
        client = None
        server_thread = None
        
        try:
            # Start server
            server = ChatServer(server_config)
            server_thread = threading.Thread(target=server.start, daemon=True)
            server_thread.start()
            
            time.sleep(0.1)
            actual_port = server.get_server_port()
            
            with patch('chat_app.client.ui.layout_manager.LayoutManager'), \
                 patch('chat_app.client.ui.input_handler.InputHandler'), \
                 patch('chat_app.client.ui.display_manager.DisplayManager'):
                
                # Test connection to wrong port
                client = ChatClient(client_config)
                success = client.connect_to_server("127.0.0.1", actual_port + 1)
                assert not success, "Connection to wrong port should fail"
                
                # Test connection to correct port
                success = client.connect_to_server("127.0.0.1", actual_port)
                assert success, "Connection to correct port should succeed"
                
                # Test invalid username
                try:
                    client.set_username("")  # Empty username
                    # Should handle gracefully or raise appropriate exception
                except Exception as e:
                    # Verify it's a validation error, not a crash
                    assert "username" in str(e).lower() or "invalid" in str(e).lower()
                
                # Test message with invalid content
                try:
                    invalid_message = Message(
                        content="",  # Empty content
                        sender="testuser",
                        message_type=MessageType.CHAT
                    )
                    client.send_message(invalid_message)
                    # Should handle gracefully
                except Exception as e:
                    # Should be a validation error
                    assert "message" in str(e).lower() or "content" in str(e).lower()
                
        finally:
            # Cleanup
            if client:
                client.disconnect()
            if server:
                server.shutdown()
            if server_thread and server_thread.is_alive():
                server_thread.join(timeout=1)


if __name__ == "__main__":
    # Run a simple test if executed directly
    import sys
    sys.path.insert(0, '.')
    
    test = TestClientServerCommunication()
    server_config = ServerConfig(host="127.0.0.1", port=0, max_clients=5)
    client_config = ClientConfig(host="127.0.0.1", port=8080, username="test_user")
    
    test.test_single_client_connection_and_messaging(server_config, client_config)
    print("Client-server integration test passed!")
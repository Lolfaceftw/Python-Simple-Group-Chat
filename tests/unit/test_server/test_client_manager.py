"""
Unit tests for ClientManager module.
"""

import socket
import threading
import time
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
import pytest

from chat_app.server.client_manager import ClientManager
from chat_app.shared.models import Message, MessageType
from chat_app.shared.exceptions import DuplicateClientError, SecurityError


class TestClientManager:
    """Test cases for ClientManager class."""
    
    @pytest.fixture
    def mock_socket(self):
        """Create a mock socket object."""
        mock_sock = Mock(spec=socket.socket)
        mock_sock.getpeername.return_value = ('127.0.0.1', 12345)
        return mock_sock
    
    @pytest.fixture
    def mock_rate_limiter(self):
        """Create a mock rate limiter."""
        mock_limiter = Mock()
        mock_limiter.check_message_rate_limit.return_value = True
        return mock_limiter
    
    @pytest.fixture
    def mock_connection_limiter(self):
        """Create a mock connection limiter."""
        mock_limiter = Mock()
        mock_limiter.register_connection.return_value = None
        mock_limiter.unregister_connection.return_value = None
        mock_limiter.update_connection_activity.return_value = None
        return mock_limiter
    
    @pytest.fixture
    def client_manager(self, mock_rate_limiter, mock_connection_limiter):
        """Create a ClientManager instance with mocked dependencies."""
        return ClientManager(
            rate_limiter=mock_rate_limiter,
            connection_limiter=mock_connection_limiter,
            max_message_history=10
        )
    
    def test_init(self):
        """Test ClientManager initialization."""
        manager = ClientManager(max_message_history=20)
        
        assert manager.max_message_history == 20
        assert manager.total_clients_connected == 0
        assert manager.total_clients_disconnected == 0
        assert len(manager._clients) == 0
        assert isinstance(manager.start_time, datetime)
    
    def test_add_client_success(self, client_manager, mock_socket):
        """Test successful client addition."""
        address = ('127.0.0.1', 12345)
        
        client_id = client_manager.add_client(mock_socket, address, "TestUser")
        
        assert isinstance(client_id, str)
        assert len(client_id) > 0
        assert client_manager.get_client_count() == 1
        assert client_manager.total_clients_connected == 1
        
        # Verify client data
        connection = client_manager.get_client(client_id)
        assert connection is not None
        assert connection.user.username == "TestUser"
        assert connection.user.address == "127.0.0.1:12345"
        assert connection.socket == mock_socket
    
    def test_add_client_default_username(self, client_manager, mock_socket):
        """Test client addition with default username generation."""
        address = ('192.168.1.100', 8080)
        
        client_id = client_manager.add_client(mock_socket, address)
        
        connection = client_manager.get_client(client_id)
        assert connection.user.username == "User_192.168.1.100:8080"
    
    def test_add_client_duplicate_socket(self, client_manager, mock_socket):
        """Test adding a client with duplicate socket raises error."""
        address = ('127.0.0.1', 12345)
        
        # Add client first time
        client_manager.add_client(mock_socket, address, "TestUser1")
        
        # Try to add same socket again
        with pytest.raises(DuplicateClientError):
            client_manager.add_client(mock_socket, address, "TestUser2")
    
    def test_add_client_connection_limiter_failure(self, mock_rate_limiter, mock_socket):
        """Test client addition failure when connection limiter rejects."""
        mock_connection_limiter = Mock()
        mock_connection_limiter.register_connection.side_effect = Exception("Connection rejected")
        
        manager = ClientManager(
            rate_limiter=mock_rate_limiter,
            connection_limiter=mock_connection_limiter
        )
        
        address = ('127.0.0.1', 12345)
        
        with pytest.raises(SecurityError):
            manager.add_client(mock_socket, address, "TestUser")
    
    def test_remove_client_success(self, client_manager, mock_socket):
        """Test successful client removal."""
        address = ('127.0.0.1', 12345)
        client_id = client_manager.add_client(mock_socket, address, "TestUser")
        
        result = client_manager.remove_client(client_id)
        
        assert result is True
        assert client_manager.get_client_count() == 0
        assert client_manager.total_clients_disconnected == 1
        assert client_manager.get_client(client_id) is None
    
    def test_remove_client_not_found(self, client_manager):
        """Test removing non-existent client."""
        result = client_manager.remove_client("non-existent-id")
        assert result is False
    
    def test_get_client_by_socket(self, client_manager, mock_socket):
        """Test getting client by socket."""
        address = ('127.0.0.1', 12345)
        client_id = client_manager.add_client(mock_socket, address, "TestUser")
        
        connection = client_manager.get_client_by_socket(mock_socket)
        
        assert connection is not None
        assert connection.connection_id == client_id
        assert connection.user.username == "TestUser"
    
    def test_get_client_by_username(self, client_manager, mock_socket):
        """Test getting client by username."""
        address = ('127.0.0.1', 12345)
        client_id = client_manager.add_client(mock_socket, address, "TestUser")
        
        connection = client_manager.get_client_by_username("TestUser")
        
        assert connection is not None
        assert connection.connection_id == client_id
        assert connection.user.username == "TestUser"
    
    def test_get_all_clients(self, client_manager):
        """Test getting all clients."""
        # Add multiple clients
        mock_socket1 = Mock(spec=socket.socket)
        mock_socket2 = Mock(spec=socket.socket)
        
        client_manager.add_client(mock_socket1, ('127.0.0.1', 12345), "User1")
        client_manager.add_client(mock_socket2, ('127.0.0.1', 12346), "User2")
        
        all_clients = client_manager.get_all_clients()
        
        assert len(all_clients) == 2
        usernames = [conn.user.username for conn in all_clients]
        assert "User1" in usernames
        assert "User2" in usernames
    
    def test_update_username_success(self, client_manager, mock_socket):
        """Test successful username update."""
        address = ('127.0.0.1', 12345)
        client_id = client_manager.add_client(mock_socket, address, "OldUser")
        
        success, old_username = client_manager.update_username(client_id, "NewUser")
        
        assert success is True
        assert old_username == "OldUser"
        
        connection = client_manager.get_client(client_id)
        assert connection.user.username == "NewUser"
        
        # Verify old username mapping is removed
        assert client_manager.get_client_by_username("OldUser") is None
        assert client_manager.get_client_by_username("NewUser") is not None
    
    def test_update_username_conflict_resolution(self, client_manager):
        """Test username conflict resolution."""
        mock_socket1 = Mock(spec=socket.socket)
        mock_socket2 = Mock(spec=socket.socket)
        
        # Add two clients
        client_id1 = client_manager.add_client(mock_socket1, ('127.0.0.1', 12345), "User1")
        client_id2 = client_manager.add_client(mock_socket2, ('127.0.0.1', 12346), "User2")
        
        # Try to change User2 to User1 (should resolve conflict)
        success, old_username = client_manager.update_username(client_id2, "User1")
        
        assert success is True
        assert old_username == "User2"
        
        connection = client_manager.get_client(client_id2)
        # Should get a modified username to avoid conflict
        assert connection.user.username.startswith("User1_")
        assert connection.user.username != "User1"
    
    def test_update_client_activity(self, client_manager, mock_socket):
        """Test updating client activity."""
        address = ('127.0.0.1', 12345)
        client_id = client_manager.add_client(mock_socket, address, "TestUser")
        
        # Get initial activity time
        connection = client_manager.get_client(client_id)
        initial_activity = connection.user.last_activity
        
        # Wait a bit and update activity
        time.sleep(0.01)
        result = client_manager.update_client_activity(client_id)
        
        assert result is True
        updated_connection = client_manager.get_client(client_id)
        assert updated_connection.user.last_activity > initial_activity
    
    def test_check_rate_limit_with_limiter(self, client_manager, mock_socket):
        """Test rate limit checking with rate limiter."""
        address = ('127.0.0.1', 12345)
        client_id = client_manager.add_client(mock_socket, address, "TestUser")
        
        # Mock rate limiter should return True
        result = client_manager.check_rate_limit(client_id)
        assert result is True
        
        # Verify rate limiter was called
        client_manager.rate_limiter.check_message_rate_limit.assert_called_with(client_id, 1)
    
    def test_check_rate_limit_without_limiter(self, mock_socket):
        """Test rate limit checking without rate limiter."""
        manager = ClientManager(rate_limiter=None)
        address = ('127.0.0.1', 12345)
        client_id = manager.add_client(mock_socket, address, "TestUser")
        
        # Should always return True when no rate limiter
        result = manager.check_rate_limit(client_id)
        assert result is True
    
    def test_get_user_list(self, client_manager):
        """Test getting user list."""
        mock_socket1 = Mock(spec=socket.socket)
        mock_socket2 = Mock(spec=socket.socket)
        
        client_manager.add_client(mock_socket1, ('127.0.0.1', 12345), "User1")
        client_manager.add_client(mock_socket2, ('192.168.1.1', 8080), "User2")
        
        user_list = client_manager.get_user_list()
        
        assert len(user_list) == 2
        assert ("User1", "127.0.0.1:12345") in user_list
        assert ("User2", "192.168.1.1:8080") in user_list
    
    def test_get_user_list_string(self, client_manager):
        """Test getting user list as formatted string."""
        mock_socket1 = Mock(spec=socket.socket)
        mock_socket2 = Mock(spec=socket.socket)
        
        client_manager.add_client(mock_socket1, ('127.0.0.1', 12345), "User1")
        client_manager.add_client(mock_socket2, ('192.168.1.1', 8080), "User2")
        
        user_list_str = client_manager.get_user_list_string()
        
        # Should contain both users in the format "username(address)"
        assert "User1(127.0.0.1:12345)" in user_list_str
        assert "User2(192.168.1.1:8080)" in user_list_str
        assert "," in user_list_str  # Should be comma-separated
    
    def test_message_history(self, client_manager):
        """Test message history functionality."""
        # Add some messages
        msg1 = Message(content="Hello", sender="User1", message_type=MessageType.CHAT)
        msg2 = Message(content="World", sender="User2", message_type=MessageType.CHAT)
        
        client_manager.add_message_to_history(msg1)
        client_manager.add_message_to_history(msg2)
        
        history = client_manager.get_message_history()
        
        assert len(history) == 2
        assert history[0].content == "Hello"
        assert history[1].content == "World"
    
    def test_message_history_max_limit(self):
        """Test message history respects maximum limit."""
        manager = ClientManager(max_message_history=3)
        
        # Add more messages than the limit
        for i in range(5):
            msg = Message(content=f"Message {i}", sender="User", message_type=MessageType.CHAT)
            manager.add_message_to_history(msg)
        
        history = manager.get_message_history()
        
        # Should only keep the last 3 messages
        assert len(history) == 3
        assert history[0].content == "Message 2"
        assert history[1].content == "Message 3"
        assert history[2].content == "Message 4"
    
    def test_get_client_statistics(self, client_manager, mock_socket):
        """Test getting client statistics."""
        address = ('127.0.0.1', 12345)
        client_id = client_manager.add_client(mock_socket, address, "TestUser")
        
        # Add a message to history
        msg = Message(content="Test", sender="TestUser", message_type=MessageType.CHAT)
        client_manager.add_message_to_history(msg)
        
        stats = client_manager.get_client_statistics()
        
        assert stats['current_clients'] == 1
        assert stats['total_clients_connected'] == 1
        assert stats['total_clients_disconnected'] == 0
        assert stats['message_history_size'] == 1
        assert stats['max_message_history'] == 10
        assert 'uptime_seconds' in stats
        assert 'client_details' in stats
        
        # Check client details
        client_details = stats['client_details']
        assert client_id in client_details
        assert client_details[client_id]['username'] == "TestUser"
        assert client_details[client_id]['address'] == "127.0.0.1:12345"
    
    def test_cleanup_inactive_clients(self, client_manager):
        """Test cleanup of inactive clients."""
        mock_socket1 = Mock(spec=socket.socket)
        mock_socket2 = Mock(spec=socket.socket)
        
        # Add two clients
        client_id1 = client_manager.add_client(mock_socket1, ('127.0.0.1', 12345), "User1")
        client_id2 = client_manager.add_client(mock_socket2, ('127.0.0.1', 12346), "User2")
        
        # Manually set one client as inactive (simulate old activity)
        connection1 = client_manager.get_client(client_id1)
        connection1.user.last_activity = datetime.now() - timedelta(minutes=35)
        
        # Cleanup with 30-minute threshold
        cleanup_count = client_manager.cleanup_inactive_clients(inactive_threshold_minutes=30)
        
        assert cleanup_count == 1
        assert client_manager.get_client_count() == 1
        assert client_manager.get_client(client_id1) is None  # Should be removed
        assert client_manager.get_client(client_id2) is not None  # Should remain
    
    def test_thread_safety(self, client_manager):
        """Test thread safety of client operations."""
        results = []
        errors = []
        
        def add_clients():
            try:
                for i in range(10):
                    mock_sock = Mock(spec=socket.socket)
                    client_id = client_manager.add_client(
                        mock_sock, 
                        ('127.0.0.1', 12345 + i), 
                        f"User{i}"
                    )
                    results.append(client_id)
            except Exception as e:
                errors.append(e)
        
        # Run multiple threads adding clients
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=add_clients)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Check results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 30  # 3 threads * 10 clients each
        assert client_manager.get_client_count() == 30
        
        # All client IDs should be unique
        assert len(set(results)) == len(results)
    
    def test_shutdown(self, client_manager):
        """Test client manager shutdown."""
        mock_socket1 = Mock(spec=socket.socket)
        mock_socket2 = Mock(spec=socket.socket)
        
        # Add some clients
        client_manager.add_client(mock_socket1, ('127.0.0.1', 12345), "User1")
        client_manager.add_client(mock_socket2, ('127.0.0.1', 12346), "User2")
        
        # Add message to history
        msg = Message(content="Test", sender="User1", message_type=MessageType.CHAT)
        client_manager.add_message_to_history(msg)
        
        # Shutdown
        client_manager.shutdown()
        
        # Verify cleanup
        assert len(client_manager._clients) == 0
        assert len(client_manager._socket_to_client_id) == 0
        assert len(client_manager._username_to_client_id) == 0
        assert len(client_manager._message_history) == 0
        
        # Verify sockets were closed
        mock_socket1.close.assert_called_once()
        mock_socket2.close.assert_called_once()


class TestUsernameConflictResolution:
    """Test cases for username conflict resolution."""
    
    @pytest.fixture
    def client_manager(self):
        """Create a ClientManager instance."""
        return ClientManager()
    
    def test_no_conflict(self, client_manager):
        """Test username with no conflict."""
        result = client_manager._resolve_username_conflict("UniqueUser")
        assert result == "UniqueUser"
    
    def test_single_conflict(self, client_manager):
        """Test username with single conflict."""
        mock_socket = Mock(spec=socket.socket)
        
        # Add a client with the desired username
        client_manager.add_client(mock_socket, ('127.0.0.1', 12345), "TestUser")
        
        # Try to resolve conflict
        result = client_manager._resolve_username_conflict("TestUser")
        assert result == "TestUser_2"
    
    def test_multiple_conflicts(self, client_manager):
        """Test username with multiple conflicts."""
        # Add clients with conflicting usernames
        for i in range(3):
            mock_sock = Mock(spec=socket.socket)
            username = "TestUser" if i == 0 else f"TestUser_{i+1}"
            client_manager.add_client(mock_sock, ('127.0.0.1', 12345 + i), username)
        
        # Try to resolve conflict
        result = client_manager._resolve_username_conflict("TestUser")
        assert result == "TestUser_4"
    
    def test_exclude_client_id(self, client_manager):
        """Test username conflict resolution with excluded client ID."""
        mock_socket = Mock(spec=socket.socket)
        
        # Add a client
        client_id = client_manager.add_client(mock_socket, ('127.0.0.1', 12345), "TestUser")
        
        # Try to resolve conflict excluding the existing client (for username update)
        result = client_manager._resolve_username_conflict("TestUser", exclude_client_id=client_id)
        assert result == "TestUser"  # Should not conflict with itself
"""
Unit tests for the MessageHandler class.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from chat_app.client.network.message_handler import MessageHandler, MessageStats
from chat_app.shared.models import Message, MessageType


class TestMessageStats:
    """Test MessageStats dataclass."""
    
    def test_default_values(self):
        """Test default statistics values."""
        stats = MessageStats()
        
        assert stats.total_received == 0
        assert stats.chat_messages == 0
        assert stats.server_messages == 0
        assert stats.user_list_updates == 0
        assert stats.command_responses == 0
        assert stats.parse_errors == 0
        assert stats.last_message_time is None


class TestMessageHandler:
    """Test MessageHandler class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.handler = MessageHandler()
    
    def test_initial_state(self):
        """Test initial handler state."""
        stats = self.handler.get_stats()
        assert stats.total_received == 0
        assert stats.parse_errors == 0
    
    def test_set_callbacks(self):
        """Test setting callback functions."""
        chat_callback = Mock()
        server_callback = Mock()
        user_list_callback = Mock()
        error_callback = Mock()
        
        self.handler.set_callbacks(
            chat_callback=chat_callback,
            server_callback=server_callback,
            user_list_callback=user_list_callback,
            error_callback=error_callback
        )
        
        assert self.handler._chat_callback == chat_callback
        assert self.handler._server_callback == server_callback
        assert self.handler._user_list_callback == user_list_callback
        assert self.handler._error_callback == error_callback
    
    def test_register_handler(self):
        """Test registering message handlers."""
        handler_func = Mock()
        
        self.handler.register_handler(MessageType.CHAT, handler_func)
        
        assert handler_func in self.handler._handlers[MessageType.CHAT]
    
    def test_unregister_handler(self):
        """Test unregistering message handlers."""
        handler_func = Mock()
        
        # Register then unregister
        self.handler.register_handler(MessageType.CHAT, handler_func)
        self.handler.unregister_handler(MessageType.CHAT, handler_func)
        
        assert handler_func not in self.handler._handlers[MessageType.CHAT]
    
    def test_unregister_nonexistent_handler(self):
        """Test unregistering a handler that doesn't exist."""
        handler_func = Mock()
        
        # Should not raise an exception
        self.handler.unregister_handler(MessageType.CHAT, handler_func)
    
    def test_handle_chat_message(self):
        """Test handling chat messages."""
        message = Message(
            content="Hello, World!",
            sender="Alice",
            message_type=MessageType.CHAT
        )
        
        chat_callback = Mock()
        self.handler.set_callbacks(chat_callback=chat_callback)
        
        self.handler.handle_message(message)
        
        chat_callback.assert_called_once_with("Hello, World!")
        
        stats = self.handler.get_stats()
        assert stats.total_received == 1
        assert stats.chat_messages == 1
    
    def test_handle_server_message(self):
        """Test handling server messages."""
        message = Message(
            content="Welcome to the server!",
            sender="Server",
            message_type=MessageType.SERVER
        )
        
        server_callback = Mock()
        self.handler.set_callbacks(server_callback=server_callback)
        
        self.handler.handle_message(message)
        
        server_callback.assert_called_once_with("Welcome to the server!")
        
        stats = self.handler.get_stats()
        assert stats.total_received == 1
        assert stats.server_messages == 1
    
    def test_handle_user_list_message(self):
        """Test handling user list messages."""
        message = Message(
            content="Alice(192.168.1.1),Bob(192.168.1.2)",
            sender="Server",
            message_type=MessageType.USER_LIST
        )
        
        user_list_callback = Mock()
        self.handler.set_callbacks(user_list_callback=user_list_callback)
        
        self.handler.handle_message(message)
        
        expected_user_dict = {
            "Alice": "192.168.1.1",
            "Bob": "192.168.1.2"
        }
        user_list_callback.assert_called_once_with(expected_user_dict)
        
        stats = self.handler.get_stats()
        assert stats.total_received == 1
        assert stats.user_list_updates == 1
    
    def test_handle_command_message(self):
        """Test handling command messages."""
        message = Message(
            content="Command executed successfully",
            sender="Server",
            message_type=MessageType.COMMAND
        )
        
        self.handler.handle_message(message)
        
        stats = self.handler.get_stats()
        assert stats.total_received == 1
        assert stats.command_responses == 1
    
    def test_handle_message_with_registered_handler(self):
        """Test handling messages with registered handlers."""
        message = Message(
            content="Test message",
            sender="Alice",
            message_type=MessageType.CHAT
        )
        
        handler_func = Mock()
        self.handler.register_handler(MessageType.CHAT, handler_func)
        
        self.handler.handle_message(message)
        
        handler_func.assert_called_once_with(message)
    
    def test_handle_message_with_handler_exception(self):
        """Test handling messages when handler raises exception."""
        message = Message(
            content="Test message",
            sender="Alice",
            message_type=MessageType.CHAT
        )
        
        handler_func = Mock(side_effect=Exception("Handler error"))
        error_callback = Mock()
        
        self.handler.register_handler(MessageType.CHAT, handler_func)
        self.handler.set_callbacks(error_callback=error_callback)
        
        self.handler.handle_message(message)
        
        error_callback.assert_called_once()
        assert "Handler error" in error_callback.call_args[0][0]
    
    def test_handle_raw_message_chat(self):
        """Test handling raw chat message."""
        chat_callback = Mock()
        self.handler.set_callbacks(chat_callback=chat_callback)
        
        self.handler.handle_raw_message("MSG|Hello, World!")
        
        chat_callback.assert_called_once_with("Hello, World!")
    
    def test_handle_raw_message_server(self):
        """Test handling raw server message."""
        server_callback = Mock()
        self.handler.set_callbacks(server_callback=server_callback)
        
        self.handler.handle_raw_message("SRV|Server notification")
        
        server_callback.assert_called_once_with("Server notification")
    
    def test_handle_raw_message_user_list(self):
        """Test handling raw user list message."""
        user_list_callback = Mock()
        self.handler.set_callbacks(user_list_callback=user_list_callback)
        
        self.handler.handle_raw_message("ULIST|Alice(192.168.1.1),Bob(192.168.1.2)")
        
        expected_user_dict = {
            "Alice": "192.168.1.1",
            "Bob": "192.168.1.2"
        }
        user_list_callback.assert_called_once_with(expected_user_dict)
    
    def test_handle_raw_message_without_separator(self):
        """Test handling raw message without protocol separator."""
        chat_callback = Mock()
        self.handler.set_callbacks(chat_callback=chat_callback)
        
        self.handler.handle_raw_message("Just a plain message")
        
        chat_callback.assert_called_once_with("Just a plain message")
    
    def test_handle_raw_message_unknown_type(self):
        """Test handling raw message with unknown type."""
        chat_callback = Mock()
        self.handler.set_callbacks(chat_callback=chat_callback)
        
        self.handler.handle_raw_message("UNKNOWN|Some content")
        
        chat_callback.assert_called_once_with("Some content")
    
    def test_handle_raw_message_empty(self):
        """Test handling empty raw message."""
        chat_callback = Mock()
        self.handler.set_callbacks(chat_callback=chat_callback)
        
        self.handler.handle_raw_message("")
        
        chat_callback.assert_not_called()
        
        stats = self.handler.get_stats()
        assert stats.total_received == 0
    
    def test_handle_raw_message_parse_error(self):
        """Test handling raw message that causes parse error."""
        error_callback = Mock()
        self.handler.set_callbacks(error_callback=error_callback)
        
        # Mock the _parse_message method to raise an exception
        with patch.object(self.handler, '_parse_message', side_effect=Exception("Parse error")):
            self.handler.handle_raw_message("MSG|Test")
        
        error_callback.assert_called_once()
        assert "Message parse error" in error_callback.call_args[0][0]
        
        stats = self.handler.get_stats()
        assert stats.parse_errors == 1
    
    def test_handle_raw_messages_multiple(self):
        """Test handling multiple raw messages."""
        chat_callback = Mock()
        self.handler.set_callbacks(chat_callback=chat_callback)
        
        messages = [
            "MSG|First message",
            "MSG|Second message",
            "SRV|Server message"
        ]
        
        self.handler.handle_raw_messages(messages)
        
        assert chat_callback.call_count == 2
        stats = self.handler.get_stats()
        assert stats.total_received == 3
        assert stats.chat_messages == 2
        assert stats.server_messages == 1
    
    def test_parse_user_list_valid(self):
        """Test parsing valid user list."""
        user_dict = self.handler._parse_user_list("Alice(192.168.1.1),Bob(192.168.1.2)")
        
        expected = {
            "Alice": "192.168.1.1",
            "Bob": "192.168.1.2"
        }
        assert user_dict == expected
    
    def test_parse_user_list_single_user(self):
        """Test parsing user list with single user."""
        user_dict = self.handler._parse_user_list("Alice(192.168.1.1)")
        
        expected = {"Alice": "192.168.1.1"}
        assert user_dict == expected
    
    def test_parse_user_list_empty(self):
        """Test parsing empty user list."""
        user_dict = self.handler._parse_user_list("")
        assert user_dict == {}
        
        user_dict = self.handler._parse_user_list("   ")
        assert user_dict == {}
    
    def test_parse_user_list_malformed(self):
        """Test parsing malformed user list."""
        error_callback = Mock()
        self.handler.set_callbacks(error_callback=error_callback)
        
        # Malformed entry without parentheses
        user_dict = self.handler._parse_user_list("Alice,Bob(192.168.1.2)")
        
        # Should only parse the valid entry
        expected = {"Bob": "192.168.1.2"}
        assert user_dict == expected
    
    def test_parse_user_list_with_spaces(self):
        """Test parsing user list with extra spaces."""
        user_dict = self.handler._parse_user_list(" Alice ( 192.168.1.1 ) , Bob ( 192.168.1.2 ) ")
        
        expected = {
            "Alice": "192.168.1.1",
            "Bob": "192.168.1.2"
        }
        assert user_dict == expected
    
    def test_callback_exception_handling(self):
        """Test handling exceptions in callbacks."""
        error_callback = Mock()
        chat_callback = Mock(side_effect=Exception("Callback error"))
        
        self.handler.set_callbacks(
            chat_callback=chat_callback,
            error_callback=error_callback
        )
        
        message = Message(
            content="Test message",
            sender="Alice",
            message_type=MessageType.CHAT
        )
        
        self.handler.handle_message(message)
        
        error_callback.assert_called_once()
        assert "Callback error" in error_callback.call_args[0][0]
    
    def test_get_stats_thread_safety(self):
        """Test thread safety of statistics."""
        import threading
        
        def handle_messages():
            for i in range(100):
                message = Message(
                    content=f"Message {i}",
                    sender="Alice",
                    message_type=MessageType.CHAT
                )
                self.handler.handle_message(message)
        
        # Start multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=handle_messages)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        stats = self.handler.get_stats()
        assert stats.total_received == 500
        assert stats.chat_messages == 500
    
    def test_reset_stats(self):
        """Test resetting statistics."""
        # Generate some stats
        message = Message(
            content="Test message",
            sender="Alice",
            message_type=MessageType.CHAT
        )
        self.handler.handle_message(message)
        
        stats = self.handler.get_stats()
        assert stats.total_received == 1
        
        # Reset stats
        self.handler.reset_stats()
        
        stats = self.handler.get_stats()
        assert stats.total_received == 0
        assert stats.chat_messages == 0
        assert stats.last_message_time is None
    
    def test_clear_handlers(self):
        """Test clearing all registered handlers."""
        handler_func1 = Mock()
        handler_func2 = Mock()
        
        self.handler.register_handler(MessageType.CHAT, handler_func1)
        self.handler.register_handler(MessageType.SERVER, handler_func2)
        
        self.handler.clear_handlers()
        
        # Handlers should be cleared
        assert len(self.handler._handlers[MessageType.CHAT]) == 0
        assert len(self.handler._handlers[MessageType.SERVER]) == 0
    
    def test_stats_last_message_time(self):
        """Test that last message time is updated."""
        message = Message(
            content="Test message",
            sender="Alice",
            message_type=MessageType.CHAT
        )
        
        before_time = datetime.now()
        self.handler.handle_message(message)
        after_time = datetime.now()
        
        stats = self.handler.get_stats()
        assert stats.last_message_time is not None
        assert before_time <= stats.last_message_time <= after_time
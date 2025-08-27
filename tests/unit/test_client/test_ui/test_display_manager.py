"""
Unit tests for the DisplayManager class.
"""

import pytest
import threading
import time
from unittest.mock import Mock, patch
from datetime import datetime
from rich.text import Text

from chat_app.client.ui.display_manager import DisplayManager, DisplayStats
from chat_app.shared.models import ClientState, Message, MessageType


class TestDisplayStats:
    """Test DisplayStats dataclass."""
    
    def test_default_values(self):
        """Test default statistics values."""
        stats = DisplayStats()
        
        assert stats.total_messages == 0
        assert stats.chat_messages == 0
        assert stats.server_messages == 0
        assert stats.messages_trimmed == 0
        assert stats.last_message_time is None


class TestDisplayManager:
    """Test DisplayManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.display_manager = DisplayManager(max_history=100)
        self.client_state = ClientState(username="TestUser")
    
    def test_initialization(self):
        """Test display manager initialization."""
        assert self.display_manager.max_history == 100
        assert len(self.display_manager.chat_history) == 0
        
        stats = self.display_manager.get_stats()
        assert stats.total_messages == 0
    
    def test_add_message_basic(self):
        """Test adding a basic message."""
        self.display_manager.add_message("Hello, World!", "cyan")
        
        assert len(self.display_manager.chat_history) == 1
        assert self.display_manager.chat_history[0].plain == "Hello, World!"
        
        stats = self.display_manager.get_stats()
        assert stats.total_messages == 1
        assert stats.last_message_time is not None
    
    def test_add_message_with_client_state(self):
        """Test adding message with client state management."""
        # Test when at bottom
        self.client_state.is_scrolled_to_bottom = True
        self.display_manager.add_message("Message 1", "cyan", self.client_state)
        
        assert self.client_state.scroll_offset == 0
        assert self.client_state.unseen_messages_count == 0
        
        # Test when scrolled up
        self.client_state.is_scrolled_to_bottom = False
        self.client_state.unseen_messages_count = 2
        self.display_manager.add_message("Message 2", "cyan", self.client_state)
        
        assert self.client_state.unseen_messages_count == 3
    
    def test_add_chat_message(self):
        """Test adding chat messages."""
        self.display_manager.add_chat_message("Hello from Alice")
        
        assert len(self.display_manager.chat_history) == 1
        
        stats = self.display_manager.get_stats()
        assert stats.total_messages == 1
        assert stats.chat_messages == 1
    
    def test_add_server_message(self):
        """Test adding server messages."""
        self.display_manager.add_server_message("Welcome to the server")
        
        assert len(self.display_manager.chat_history) == 1
        message_text = self.display_manager.chat_history[0].plain
        assert message_text.startswith("=> ")
        
        stats = self.display_manager.get_stats()
        assert stats.total_messages == 1
        assert stats.server_messages == 1
    
    def test_add_user_message_own(self):
        """Test adding own user message."""
        self.display_manager.add_user_message("TestUser", "Hello!", is_own_message=True)
        
        assert len(self.display_manager.chat_history) == 1
        message_text = self.display_manager.chat_history[0].plain
        assert message_text == "TestUser: Hello!"
        
        stats = self.display_manager.get_stats()
        assert stats.chat_messages == 1
    
    def test_add_user_message_other(self):
        """Test adding other user's message."""
        self.display_manager.add_user_message("Alice", "Hi there!", is_own_message=False)
        
        assert len(self.display_manager.chat_history) == 1
        message_text = self.display_manager.chat_history[0].plain
        assert message_text == "Alice: Hi there!"
    
    def test_add_system_message(self):
        """Test adding system messages."""
        self.display_manager.add_system_message("Connection established", "green")
        
        assert len(self.display_manager.chat_history) == 1
        message_text = self.display_manager.chat_history[0].plain
        assert message_text == "Connection established"
    
    def test_get_chat_history(self):
        """Test getting chat history."""
        self.display_manager.add_message("Message 1", "cyan")
        self.display_manager.add_message("Message 2", "cyan")
        
        history = self.display_manager.get_chat_history()
        
        assert len(history) == 2
        assert isinstance(history[0], Text)
        assert history[0].plain == "Message 1"
        assert history[1].plain == "Message 2"
    
    def test_get_visible_history_at_bottom(self):
        """Test getting visible history when at bottom."""
        # Add more messages than panel height
        for i in range(20):
            self.display_manager.add_message(f"Message {i}", "cyan")
        
        self.client_state.scroll_offset = 0
        visible = self.display_manager.get_visible_history(self.client_state, 10)
        
        # Should get last 10 messages
        assert len(visible) == 10
        assert visible[-1].plain == "Message 19"
    
    def test_get_visible_history_scrolled(self):
        """Test getting visible history when scrolled up."""
        # Add messages
        for i in range(20):
            self.display_manager.add_message(f"Message {i}", "cyan")
        
        self.client_state.scroll_offset = 5
        visible = self.display_manager.get_visible_history(self.client_state, 10)
        
        # Should get messages ending 5 from the end
        assert len(visible) == 10
        assert visible[-1].plain == "Message 14"  # 20 - 5 - 1
    
    def test_clear_history(self):
        """Test clearing chat history."""
        self.display_manager.add_message("Message 1", "cyan")
        self.display_manager.add_message("Message 2", "cyan")
        
        self.display_manager.clear_history()
        
        assert len(self.display_manager.chat_history) == 0
        stats = self.display_manager.get_stats()
        assert stats.total_messages == 0
    
    def test_scroll_to_bottom(self):
        """Test scrolling to bottom."""
        self.client_state.scroll_offset = 10
        self.client_state.is_scrolled_to_bottom = False
        self.client_state.unseen_messages_count = 5
        
        self.display_manager.scroll_to_bottom(self.client_state)
        
        assert self.client_state.scroll_offset == 0
        assert self.client_state.is_scrolled_to_bottom is True
        assert self.client_state.unseen_messages_count == 0
    
    def test_scroll_up(self):
        """Test scrolling up."""
        # Add some messages
        for i in range(10):
            self.display_manager.add_message(f"Message {i}", "cyan")
        
        self.client_state.scroll_offset = 0
        self.client_state.is_scrolled_to_bottom = True
        
        self.display_manager.scroll_up(self.client_state, 3)
        
        assert self.client_state.scroll_offset == 3
        assert self.client_state.is_scrolled_to_bottom is False
    
    def test_scroll_up_with_limit(self):
        """Test scrolling up with history limit."""
        # Add only 5 messages
        for i in range(5):
            self.display_manager.add_message(f"Message {i}", "cyan")
        
        self.client_state.scroll_offset = 0
        
        # Try to scroll up 10 lines (more than available)
        self.display_manager.scroll_up(self.client_state, 10)
        
        # Should be limited to available messages
        assert self.client_state.scroll_offset == 4  # 5 - 1
    
    def test_scroll_down(self):
        """Test scrolling down."""
        self.client_state.scroll_offset = 5
        self.client_state.unseen_messages_count = 3
        
        self.display_manager.scroll_down(self.client_state, 2)
        
        assert self.client_state.scroll_offset == 3
        assert self.client_state.unseen_messages_count == 1  # 3 - 2
    
    def test_scroll_down_to_bottom(self):
        """Test scrolling down to bottom."""
        self.client_state.scroll_offset = 2
        self.client_state.unseen_messages_count = 5
        
        self.display_manager.scroll_down(self.client_state, 3)
        
        assert self.client_state.scroll_offset == 0
        assert self.client_state.is_scrolled_to_bottom is True
        assert self.client_state.unseen_messages_count == 0
    
    def test_format_message_chat(self):
        """Test formatting chat messages."""
        message = Message(
            content="Alice: Hello!",
            sender="Alice",
            message_type=MessageType.CHAT
        )
        
        formatted = self.display_manager.format_message(message, "TestUser")
        
        assert isinstance(formatted, Text)
        assert formatted.plain == "Alice: Hello!"
    
    def test_format_message_own_chat(self):
        """Test formatting own chat messages."""
        message = Message(
            content="TestUser: Hello!",
            sender="TestUser",
            message_type=MessageType.CHAT
        )
        
        formatted = self.display_manager.format_message(message, "TestUser")
        
        assert isinstance(formatted, Text)
        assert formatted.plain == "TestUser: Hello!"
    
    def test_format_message_server(self):
        """Test formatting server messages."""
        message = Message(
            content="Welcome to the server",
            sender="Server",
            message_type=MessageType.SERVER
        )
        
        formatted = self.display_manager.format_message(message)
        
        assert isinstance(formatted, Text)
        assert formatted.plain == "=> Welcome to the server"
    
    def test_format_message_unknown_type(self):
        """Test formatting unknown message types."""
        message = Message(
            content="Unknown message",
            sender="System",
            message_type=MessageType.COMMAND
        )
        
        formatted = self.display_manager.format_message(message)
        
        assert isinstance(formatted, Text)
        assert formatted.plain == "Unknown message"
    
    def test_get_stats(self):
        """Test getting display statistics."""
        self.display_manager.add_chat_message("Chat message")
        self.display_manager.add_server_message("Server message")
        
        stats = self.display_manager.get_stats()
        
        assert stats.total_messages == 2
        assert stats.chat_messages == 1
        assert stats.server_messages == 1
        assert stats.messages_trimmed == 0
        assert stats.last_message_time is not None
    
    def test_reset_stats(self):
        """Test resetting statistics."""
        self.display_manager.add_message("Test", "cyan")
        
        self.display_manager.reset_stats()
        
        stats = self.display_manager.get_stats()
        assert stats.total_messages == 0
        assert stats.last_message_time is None
    
    def test_set_max_history(self):
        """Test setting maximum history size."""
        # Add messages
        for i in range(10):
            self.display_manager.add_message(f"Message {i}", "cyan")
        
        # Reduce max history
        self.display_manager.set_max_history(5)
        
        assert self.display_manager.max_history == 5
        assert len(self.display_manager.chat_history) == 5
        
        stats = self.display_manager.get_stats()
        assert stats.messages_trimmed == 5
    
    def test_get_history_info(self):
        """Test getting history information."""
        self.display_manager.add_message("Test", "cyan")
        
        info = self.display_manager.get_history_info()
        
        assert "current_size" in info
        assert "max_size" in info
        assert "total_messages" in info
        assert "messages_trimmed" in info
        assert "last_message_time" in info
        
        assert info["current_size"] == 1
        assert info["max_size"] == 100
        assert info["total_messages"] == 1
    
    def test_history_trimming(self):
        """Test automatic history trimming."""
        # Create display manager with small max history
        dm = DisplayManager(max_history=5)
        
        # Add more messages than max
        for i in range(10):
            dm.add_message(f"Message {i}", "cyan")
        
        assert len(dm.chat_history) == 5
        # Should keep the most recent messages
        assert dm.chat_history[-1].plain == "Message 9"
        
        stats = dm.get_stats()
        assert stats.messages_trimmed == 5
    
    def test_export_history_basic(self):
        """Test exporting history without timestamps."""
        self.display_manager.add_message("Message 1", "cyan")
        self.display_manager.add_message("Message 2", "cyan")
        
        exported = self.display_manager.export_history(include_timestamps=False)
        
        assert len(exported) == 2
        assert exported[0] == "Message 1"
        assert exported[1] == "Message 2"
    
    def test_export_history_with_timestamps(self):
        """Test exporting history with timestamps."""
        self.display_manager.add_message("Message 1", "cyan")
        
        exported = self.display_manager.export_history(include_timestamps=True)
        
        assert len(exported) == 1
        assert "Message 1" in exported[0]
        assert "[" in exported[0]  # Timestamp format
        assert "]" in exported[0]
    
    def test_search_history_basic(self):
        """Test basic history search."""
        self.display_manager.add_message("Hello World", "cyan")
        self.display_manager.add_message("Goodbye World", "cyan")
        self.display_manager.add_message("Hello Alice", "cyan")
        
        matches = self.display_manager.search_history("Hello")
        
        assert len(matches) == 2
        assert 0 in matches  # "Hello World"
        assert 2 in matches  # "Hello Alice"
    
    def test_search_history_case_sensitive(self):
        """Test case-sensitive history search."""
        self.display_manager.add_message("Hello World", "cyan")
        self.display_manager.add_message("hello world", "cyan")
        
        matches = self.display_manager.search_history("Hello", case_sensitive=True)
        
        assert len(matches) == 1
        assert 0 in matches
    
    def test_search_history_case_insensitive(self):
        """Test case-insensitive history search."""
        self.display_manager.add_message("Hello World", "cyan")
        self.display_manager.add_message("hello world", "cyan")
        
        matches = self.display_manager.search_history("HELLO", case_sensitive=False)
        
        assert len(matches) == 2
        assert 0 in matches
        assert 1 in matches
    
    def test_search_history_empty_query(self):
        """Test searching with empty query."""
        self.display_manager.add_message("Test", "cyan")
        
        matches = self.display_manager.search_history("")
        
        assert len(matches) == 0
    
    def test_search_history_no_matches(self):
        """Test searching with no matches."""
        self.display_manager.add_message("Hello World", "cyan")
        
        matches = self.display_manager.search_history("xyz")
        
        assert len(matches) == 0
    
    def test_thread_safety(self):
        """Test thread safety of display manager."""
        # Use a display manager with higher max_history for this test
        dm = DisplayManager(max_history=200)
        
        results = []
        errors = []
        
        def add_messages():
            try:
                for i in range(50):
                    dm.add_message(f"Message {i}", "cyan")
                    time.sleep(0.001)  # Small delay to encourage race conditions
                results.append("success")
            except Exception as e:
                errors.append(e)
        
        # Start multiple threads
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=add_messages)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Should not have any errors
        assert len(errors) == 0
        assert len(results) == 3
        
        # Should have all messages (150 total)
        assert len(dm.chat_history) == 150
        
        stats = dm.get_stats()
        assert stats.total_messages == 150
    
    def test_concurrent_stats_access(self):
        """Test concurrent access to statistics."""
        def get_stats_repeatedly():
            for _ in range(100):
                stats = self.display_manager.get_stats()
                assert isinstance(stats, DisplayStats)
        
        def add_messages_repeatedly():
            for i in range(100):
                self.display_manager.add_message(f"Message {i}", "cyan")
        
        # Start concurrent operations
        thread1 = threading.Thread(target=get_stats_repeatedly)
        thread2 = threading.Thread(target=add_messages_repeatedly)
        
        thread1.start()
        thread2.start()
        
        thread1.join()
        thread2.join()
        
        # Should complete without errors
        final_stats = self.display_manager.get_stats()
        assert final_stats.total_messages == 100
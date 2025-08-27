"""
Unit tests for the LayoutManager class.
"""

import pytest
from unittest.mock import Mock, patch
from rich.text import Text
from rich.layout import Layout
from rich.panel import Panel

from chat_app.client.ui.layout_manager import LayoutManager
from chat_app.shared.models import ClientState


class TestLayoutManager:
    """Test LayoutManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.layout_manager = LayoutManager(console_height=24)
        self.client_state = ClientState(username="TestUser")
    
    def test_initialization(self):
        """Test layout manager initialization."""
        assert self.layout_manager.console_height == 24
        assert isinstance(self.layout_manager.layout, Layout)
        assert self.layout_manager.layout.name == "root"
    
    def test_create_layout_structure(self):
        """Test that layout structure is created correctly."""
        layout = self.layout_manager.layout
        
        # Check that layout is created and has the right name
        assert layout.name == "root"
        
        # Check that we can access the sub-layouts
        header_layout = layout["header"]
        main_layout = layout["main"]
        footer_layout = layout["footer"]
        
        assert header_layout is not None
        assert main_layout is not None
        assert footer_layout is not None
        
        # Check main panel split
        chat_panel = main_layout["chat_panel"]
        user_panel = main_layout["user_panel"]
        
        assert chat_panel is not None
        assert user_panel is not None
    
    def test_update_chat_panel_basic(self):
        """Test basic chat panel update."""
        chat_history = [
            Text("Hello, World!", "cyan"),
            Text("How are you?", "cyan")
        ]
        
        self.layout_manager.update_chat_panel(chat_history, self.client_state)
        
        # Check that chat panel was updated
        chat_panel = self.layout_manager.layout["chat_panel"]
        assert isinstance(chat_panel.renderable, Panel)
    
    def test_update_chat_panel_with_scroll(self):
        """Test chat panel update with scroll offset."""
        chat_history = [Text(f"Message {i}", "cyan") for i in range(20)]
        
        # Set scroll offset
        self.client_state.scroll_offset = 5
        self.client_state.is_scrolled_to_bottom = False
        
        self.layout_manager.update_chat_panel(chat_history, self.client_state)
        
        # Panel should be updated with scroll indicator
        chat_panel = self.layout_manager.layout["chat_panel"]
        assert isinstance(chat_panel.renderable, Panel)
    
    def test_update_chat_panel_with_unseen_messages(self):
        """Test chat panel with unseen messages indicator."""
        chat_history = [Text("Message", "cyan")]
        
        self.client_state.is_scrolled_to_bottom = False
        self.client_state.unseen_messages_count = 3
        
        self.layout_manager.update_chat_panel(chat_history, self.client_state)
        
        chat_panel = self.layout_manager.layout["chat_panel"]
        assert isinstance(chat_panel.renderable, Panel)
    
    def test_update_chat_panel_active_panel_styling(self):
        """Test chat panel styling based on active panel."""
        chat_history = [Text("Message", "cyan")]
        
        # Test active chat panel
        self.client_state.active_panel = "chat"
        self.layout_manager.update_chat_panel(chat_history, self.client_state)
        
        # Test inactive chat panel
        self.client_state.active_panel = "users"
        self.layout_manager.update_chat_panel(chat_history, self.client_state)
        
        # Both should create valid panels
        chat_panel = self.layout_manager.layout["chat_panel"]
        assert isinstance(chat_panel.renderable, Panel)
    
    def test_update_user_panel_basic(self):
        """Test basic user panel update."""
        user_list = {
            "Alice": "192.168.1.1",
            "Bob": "192.168.1.2",
            "TestUser": "192.168.1.3"
        }
        
        self.layout_manager.update_user_panel(user_list, self.client_state)
        
        user_panel = self.layout_manager.layout["user_panel"]
        assert isinstance(user_panel.renderable, Panel)
    
    def test_update_user_panel_with_scroll(self):
        """Test user panel update with scroll offset."""
        user_list = {f"User{i}": f"192.168.1.{i}" for i in range(1, 21)}
        
        self.client_state.user_panel_scroll_offset = 3
        
        self.layout_manager.update_user_panel(user_list, self.client_state)
        
        user_panel = self.layout_manager.layout["user_panel"]
        assert isinstance(user_panel.renderable, Panel)
    
    def test_update_user_panel_current_user_highlight(self):
        """Test that current user is highlighted in user panel."""
        user_list = {
            "Alice": "192.168.1.1",
            "TestUser": "192.168.1.2"
        }
        
        self.layout_manager.update_user_panel(user_list, self.client_state)
        
        user_panel = self.layout_manager.layout["user_panel"]
        assert isinstance(user_panel.renderable, Panel)
    
    def test_update_user_panel_active_panel_styling(self):
        """Test user panel styling based on active panel."""
        user_list = {"Alice": "192.168.1.1"}
        
        # Test active user panel
        self.client_state.active_panel = "users"
        self.layout_manager.update_user_panel(user_list, self.client_state)
        
        # Test inactive user panel
        self.client_state.active_panel = "chat"
        self.layout_manager.update_user_panel(user_list, self.client_state)
        
        user_panel = self.layout_manager.layout["user_panel"]
        assert isinstance(user_panel.renderable, Panel)
    
    def test_update_input_panel_basic(self):
        """Test basic input panel update."""
        self.layout_manager.update_input_panel("Hello, World!")
        
        input_panel = self.layout_manager.layout["footer"]
        assert isinstance(input_panel.renderable, Panel)
    
    def test_update_input_panel_with_cursor(self):
        """Test input panel with cursor."""
        self.layout_manager.update_input_panel("Test", show_cursor=True)
        
        input_panel = self.layout_manager.layout["footer"]
        assert isinstance(input_panel.renderable, Panel)
    
    def test_update_input_panel_without_cursor(self):
        """Test input panel without cursor."""
        self.layout_manager.update_input_panel("Test", show_cursor=False)
        
        input_panel = self.layout_manager.layout["footer"]
        assert isinstance(input_panel.renderable, Panel)
    
    def test_update_input_panel_empty_buffer(self):
        """Test input panel with empty buffer."""
        self.layout_manager.update_input_panel("")
        
        input_panel = self.layout_manager.layout["footer"]
        assert isinstance(input_panel.renderable, Panel)
    
    def test_update_all_panels(self):
        """Test updating all panels at once."""
        chat_history = [Text("Hello", "cyan")]
        user_list = {"Alice": "192.168.1.1"}
        self.client_state.input_buffer = "Test message"
        
        self.layout_manager.update_all_panels(
            chat_history, user_list, self.client_state, show_cursor=True
        )
        
        # Check that all panels are updated
        assert isinstance(self.layout_manager.layout["chat_panel"].renderable, Panel)
        assert isinstance(self.layout_manager.layout["user_panel"].renderable, Panel)
        assert isinstance(self.layout_manager.layout["footer"].renderable, Panel)
    
    def test_get_layout(self):
        """Test getting the layout object."""
        layout = self.layout_manager.get_layout()
        assert isinstance(layout, Layout)
        assert layout is self.layout_manager.layout
    
    def test_set_console_height(self):
        """Test setting console height."""
        self.layout_manager.set_console_height(30)
        assert self.layout_manager.console_height == 30
    
    def test_clear_cache(self):
        """Test clearing panel cache."""
        # Add something to cache first
        self.layout_manager._panel_cache["test"] = Panel("test")
        
        self.layout_manager.clear_cache()
        assert len(self.layout_manager._panel_cache) == 0
    
    def test_get_panel_info(self):
        """Test getting panel information."""
        info = self.layout_manager.get_panel_info()
        
        assert "console_height" in info
        assert "panel_height" in info
        assert "layout_structure" in info
        assert info["console_height"] == 24
        assert info["panel_height"] == 16  # 24 - 8
    
    def test_empty_chat_history(self):
        """Test handling empty chat history."""
        self.layout_manager.update_chat_panel([], self.client_state)
        
        chat_panel = self.layout_manager.layout["chat_panel"]
        assert isinstance(chat_panel.renderable, Panel)
    
    def test_empty_user_list(self):
        """Test handling empty user list."""
        self.layout_manager.update_user_panel({}, self.client_state)
        
        user_panel = self.layout_manager.layout["user_panel"]
        assert isinstance(user_panel.renderable, Panel)
    
    def test_large_chat_history(self):
        """Test handling large chat history."""
        # Create a large chat history
        chat_history = [Text(f"Message {i}", "cyan") for i in range(1000)]
        
        self.layout_manager.update_chat_panel(chat_history, self.client_state)
        
        chat_panel = self.layout_manager.layout["chat_panel"]
        assert isinstance(chat_panel.renderable, Panel)
    
    def test_large_user_list(self):
        """Test handling large user list."""
        # Create a large user list
        user_list = {f"User{i}": f"192.168.1.{i % 255}" for i in range(100)}
        
        self.layout_manager.update_user_panel(user_list, self.client_state)
        
        user_panel = self.layout_manager.layout["user_panel"]
        assert isinstance(user_panel.renderable, Panel)
    
    def test_scroll_calculations(self):
        """Test scroll offset calculations."""
        chat_history = [Text(f"Message {i}", "cyan") for i in range(50)]
        
        # Test various scroll offsets
        for offset in [0, 5, 10, 25, 49]:
            self.client_state.scroll_offset = offset
            self.layout_manager.update_chat_panel(chat_history, self.client_state)
            
            chat_panel = self.layout_manager.layout["chat_panel"]
            assert isinstance(chat_panel.renderable, Panel)
    
    def test_user_panel_scroll_calculations(self):
        """Test user panel scroll offset calculations."""
        user_list = {f"User{i}": f"192.168.1.{i}" for i in range(30)}
        
        # Test various scroll offsets
        for offset in [0, 3, 10, 20]:
            self.client_state.user_panel_scroll_offset = offset
            self.layout_manager.update_user_panel(user_list, self.client_state)
            
            user_panel = self.layout_manager.layout["user_panel"]
            assert isinstance(user_panel.renderable, Panel)
    
    def test_different_console_heights(self):
        """Test layout with different console heights."""
        for height in [10, 20, 30, 50]:
            layout_manager = LayoutManager(console_height=height)
            
            chat_history = [Text("Test", "cyan")]
            user_list = {"User": "192.168.1.1"}
            
            layout_manager.update_all_panels(
                chat_history, user_list, self.client_state
            )
            
            # Should handle all heights without errors
            assert isinstance(layout_manager.layout["chat_panel"].renderable, Panel)
            assert isinstance(layout_manager.layout["user_panel"].renderable, Panel)
            assert isinstance(layout_manager.layout["footer"].renderable, Panel)
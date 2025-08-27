"""
Unit tests for the InputHandler class.
"""

import pytest
import sys
from unittest.mock import Mock, patch, MagicMock

from chat_app.client.ui.input_handler import InputHandler, InputAction, InputResult
from chat_app.shared.models import ClientState


class TestInputResult:
    """Test InputResult dataclass."""
    
    def test_basic_creation(self):
        """Test basic InputResult creation."""
        result = InputResult(action=InputAction.NO_ACTION)
        
        assert result.action == InputAction.NO_ACTION
        assert result.data is None
        assert result.command is None
        assert result.args is None
        assert result.state_changes is None
    
    def test_full_creation(self):
        """Test InputResult with all fields."""
        state_changes = {"input_buffer": "test"}
        result = InputResult(
            action=InputAction.SEND_MESSAGE,
            data="Hello",
            command="nick",
            args="NewName",
            state_changes=state_changes
        )
        
        assert result.action == InputAction.SEND_MESSAGE
        assert result.data == "Hello"
        assert result.command == "nick"
        assert result.args == "NewName"
        assert result.state_changes == state_changes


class TestInputHandler:
    """Test InputHandler class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.handler = InputHandler()
        self.client_state = ClientState(username="TestUser")
    
    def test_initialization(self):
        """Test input handler initialization."""
        assert isinstance(self.handler.is_supported_platform, bool)
        assert len(self.handler._input_callbacks) == 0
    
    def test_platform_support_detection(self):
        """Test platform support detection."""
        # Test current platform
        is_supported = self.handler.is_platform_supported()
        expected = sys.platform == "win32"
        assert is_supported == expected
    
    def test_set_callback(self):
        """Test setting input callbacks."""
        callback = Mock()
        
        self.handler.set_callback(InputAction.SEND_MESSAGE, callback)
        
        assert InputAction.SEND_MESSAGE in self.handler._input_callbacks
        assert self.handler._input_callbacks[InputAction.SEND_MESSAGE] == callback
    
    def test_remove_callback(self):
        """Test removing input callbacks."""
        callback = Mock()
        
        # Set then remove callback
        self.handler.set_callback(InputAction.SEND_MESSAGE, callback)
        self.handler.remove_callback(InputAction.SEND_MESSAGE)
        
        assert InputAction.SEND_MESSAGE not in self.handler._input_callbacks
    
    def test_remove_nonexistent_callback(self):
        """Test removing a callback that doesn't exist."""
        # Should not raise an exception
        self.handler.remove_callback(InputAction.SEND_MESSAGE)
    
    def test_process_input_result(self):
        """Test processing input results."""
        callback = Mock()
        self.handler.set_callback(InputAction.SEND_MESSAGE, callback)
        
        result = InputResult(action=InputAction.SEND_MESSAGE, data="test")
        self.handler.process_input_result(result)
        
        callback.assert_called_once_with(result)
    
    def test_process_input_result_no_callback(self):
        """Test processing input result with no registered callback."""
        result = InputResult(action=InputAction.SEND_MESSAGE, data="test")
        
        # Should not raise an exception
        self.handler.process_input_result(result)
    
    def test_get_platform_info(self):
        """Test getting platform information."""
        info = self.handler.get_platform_info()
        
        assert "platform" in info
        assert "supported" in info
        assert "input_method" in info
        assert info["platform"] == sys.platform
    
    def test_parse_command_valid(self):
        """Test parsing valid commands."""
        command, args = self.handler.parse_command("/nick Alice")
        assert command == "nick"
        assert args == "Alice"
        
        command, args = self.handler.parse_command("/quit")
        assert command == "quit"
        assert args is None
        
        command, args = self.handler.parse_command("/help me please")
        assert command == "help"
        assert args == "me please"
    
    def test_parse_command_invalid(self):
        """Test parsing invalid commands."""
        command, args = self.handler.parse_command("not a command")
        assert command is None
        assert args is None
        
        command, args = self.handler.parse_command("")
        assert command is None
        assert args is None
    
    def test_validate_nickname_valid(self):
        """Test validating valid nicknames."""
        is_valid, error = self.handler.validate_nickname("Alice")
        assert is_valid is True
        assert error is None
        
        is_valid, error = self.handler.validate_nickname("User123")
        assert is_valid is True
        assert error is None
        
        is_valid, error = self.handler.validate_nickname("Test_User")
        assert is_valid is True
        assert error is None
    
    def test_validate_nickname_invalid(self):
        """Test validating invalid nicknames."""
        # Empty nickname
        is_valid, error = self.handler.validate_nickname("")
        assert is_valid is False
        assert "empty" in error.lower()
        
        # Whitespace only
        is_valid, error = self.handler.validate_nickname("   ")
        assert is_valid is False
        assert "empty" in error.lower()
        
        # Too long
        long_name = "a" * 51
        is_valid, error = self.handler.validate_nickname(long_name)
        assert is_valid is False
        assert "too long" in error.lower()
        
        # Invalid characters
        is_valid, error = self.handler.validate_nickname("user|name")
        assert is_valid is False
        assert "invalid character" in error.lower()
        
        is_valid, error = self.handler.validate_nickname("user\nname")
        assert is_valid is False
        assert "invalid character" in error.lower()
    
    @patch('sys.platform', 'linux')
    def test_handle_input_unsupported_platform(self):
        """Test handling input on unsupported platform."""
        handler = InputHandler()
        result = handler.handle_input(self.client_state)
        assert result is None
    
    @patch('sys.platform', 'win32')
    @patch('chat_app.client.ui.input_handler.msvcrt')
    def test_handle_windows_input_no_input(self, mock_msvcrt):
        """Test Windows input handling when no input is available."""
        mock_msvcrt.kbhit.return_value = False
        
        result = self.handler.handle_input(self.client_state)
        assert result is None
    
    @patch('sys.platform', 'win32')
    @patch('chat_app.client.ui.input_handler.msvcrt')
    def test_handle_windows_input_tab_key(self, mock_msvcrt):
        """Test handling TAB key (panel switching)."""
        mock_msvcrt.kbhit.return_value = True
        mock_msvcrt.getch.return_value = b'\t'
        
        # Test switching from chat to users
        self.client_state.active_panel = "chat"
        result = self.handler.handle_input(self.client_state)
        
        assert result.action == InputAction.SWITCH_PANEL
        assert result.state_changes["active_panel"] == "users"
        
        # Test switching from users to chat
        self.client_state.active_panel = "users"
        result = self.handler.handle_input(self.client_state)
        
        assert result.action == InputAction.SWITCH_PANEL
        assert result.state_changes["active_panel"] == "chat"
    
    @patch('sys.platform', 'win32')
    @patch('chat_app.client.ui.input_handler.msvcrt')
    def test_handle_windows_input_enter_quit(self, mock_msvcrt):
        """Test handling ENTER key with quit command."""
        mock_msvcrt.kbhit.return_value = True
        mock_msvcrt.getch.return_value = b'\r'
        
        self.client_state.input_buffer = "/quit"
        result = self.handler.handle_input(self.client_state)
        
        assert result.action == InputAction.QUIT
    
    @patch('sys.platform', 'win32')
    @patch('chat_app.client.ui.input_handler.msvcrt')
    def test_handle_windows_input_enter_nick_command(self, mock_msvcrt):
        """Test handling ENTER key with nick command."""
        mock_msvcrt.kbhit.return_value = True
        mock_msvcrt.getch.return_value = b'\r'
        
        self.client_state.input_buffer = "/nick Alice"
        result = self.handler.handle_input(self.client_state)
        
        assert result.action == InputAction.SEND_COMMAND
        assert result.command == "nick"
        assert result.args == "Alice"
        assert result.state_changes["input_buffer"] == ""
    
    @patch('sys.platform', 'win32')
    @patch('chat_app.client.ui.input_handler.msvcrt')
    def test_handle_windows_input_enter_invalid_nick(self, mock_msvcrt):
        """Test handling ENTER key with invalid nick command."""
        mock_msvcrt.kbhit.return_value = True
        mock_msvcrt.getch.return_value = b'\r'
        
        self.client_state.input_buffer = "/nick "
        result = self.handler.handle_input(self.client_state)
        
        assert result.action == InputAction.NO_ACTION
        assert result.state_changes["input_buffer"] == ""
    
    @patch('sys.platform', 'win32')
    @patch('chat_app.client.ui.input_handler.msvcrt')
    def test_handle_windows_input_enter_message(self, mock_msvcrt):
        """Test handling ENTER key with regular message."""
        mock_msvcrt.kbhit.return_value = True
        mock_msvcrt.getch.return_value = b'\r'
        
        self.client_state.input_buffer = "Hello, World!"
        result = self.handler.handle_input(self.client_state)
        
        assert result.action == InputAction.SEND_MESSAGE
        assert result.data == "Hello, World!"
        assert result.state_changes["input_buffer"] == ""
    
    @patch('sys.platform', 'win32')
    @patch('chat_app.client.ui.input_handler.msvcrt')
    def test_handle_windows_input_enter_empty(self, mock_msvcrt):
        """Test handling ENTER key with empty buffer."""
        mock_msvcrt.kbhit.return_value = True
        mock_msvcrt.getch.return_value = b'\r'
        
        self.client_state.input_buffer = ""
        result = self.handler.handle_input(self.client_state)
        
        assert result.action == InputAction.NO_ACTION
    
    @patch('sys.platform', 'win32')
    @patch('chat_app.client.ui.input_handler.msvcrt')
    def test_handle_windows_input_backspace(self, mock_msvcrt):
        """Test handling BACKSPACE key."""
        mock_msvcrt.kbhit.return_value = True
        mock_msvcrt.getch.return_value = b'\x08'
        
        self.client_state.input_buffer = "Hello"
        result = self.handler.handle_input(self.client_state)
        
        assert result.action == InputAction.UPDATE_BUFFER
        assert result.data == "Hell"
        assert result.state_changes["input_buffer"] == "Hell"
    
    @patch('sys.platform', 'win32')
    @patch('chat_app.client.ui.input_handler.msvcrt')
    def test_handle_windows_input_regular_char(self, mock_msvcrt):
        """Test handling regular character input."""
        mock_msvcrt.kbhit.return_value = True
        mock_msvcrt.getch.return_value = b'a'
        
        self.client_state.input_buffer = "Hell"
        result = self.handler.handle_input(self.client_state)
        
        assert result.action == InputAction.UPDATE_BUFFER
        assert result.data == "Hella"
        assert result.state_changes["input_buffer"] == "Hella"
    
    @patch('sys.platform', 'win32')
    @patch('chat_app.client.ui.input_handler.msvcrt')
    def test_handle_windows_input_unicode_error(self, mock_msvcrt):
        """Test handling unicode decode error."""
        mock_msvcrt.kbhit.return_value = True
        mock_msvcrt.getch.return_value = b'\xff'  # Invalid UTF-8
        
        result = self.handler.handle_input(self.client_state)
        assert result is None
    
    @patch('sys.platform', 'win32')
    @patch('chat_app.client.ui.input_handler.msvcrt')
    def test_handle_windows_input_arrow_up_chat(self, mock_msvcrt):
        """Test handling UP arrow in chat panel."""
        mock_msvcrt.kbhit.return_value = True
        mock_msvcrt.getch.side_effect = [b'\xe0', b'H']  # UP arrow sequence
        
        self.client_state.active_panel = "chat"
        self.client_state.scroll_offset = 0
        
        result = self.handler.handle_input(self.client_state)
        
        assert result.action == InputAction.SCROLL_UP
        assert result.state_changes["scroll_offset"] == 1
        assert result.state_changes["is_scrolled_to_bottom"] is False
    
    @patch('sys.platform', 'win32')
    @patch('chat_app.client.ui.input_handler.msvcrt')
    def test_handle_windows_input_arrow_down_chat(self, mock_msvcrt):
        """Test handling DOWN arrow in chat panel."""
        mock_msvcrt.kbhit.return_value = True
        mock_msvcrt.getch.side_effect = [b'\xe0', b'P']  # DOWN arrow sequence
        
        self.client_state.active_panel = "chat"
        self.client_state.scroll_offset = 5
        self.client_state.unseen_messages_count = 3
        
        result = self.handler.handle_input(self.client_state)
        
        assert result.action == InputAction.SCROLL_DOWN
        assert result.state_changes["scroll_offset"] == 4
        assert result.state_changes["unseen_messages_count"] == 2
    
    @patch('sys.platform', 'win32')
    @patch('chat_app.client.ui.input_handler.msvcrt')
    def test_handle_windows_input_arrow_down_to_bottom(self, mock_msvcrt):
        """Test handling DOWN arrow scrolling to bottom."""
        mock_msvcrt.kbhit.return_value = True
        mock_msvcrt.getch.side_effect = [b'\xe0', b'P']  # DOWN arrow sequence
        
        self.client_state.active_panel = "chat"
        self.client_state.scroll_offset = 1
        self.client_state.unseen_messages_count = 2
        
        result = self.handler.handle_input(self.client_state)
        
        assert result.action == InputAction.SCROLL_DOWN
        assert result.state_changes["scroll_offset"] == 0
        assert result.state_changes["is_scrolled_to_bottom"] is True
        assert result.state_changes["unseen_messages_count"] == 0
    
    @patch('sys.platform', 'win32')
    @patch('chat_app.client.ui.input_handler.msvcrt')
    def test_handle_windows_input_arrow_up_users(self, mock_msvcrt):
        """Test handling UP arrow in users panel."""
        mock_msvcrt.kbhit.return_value = True
        mock_msvcrt.getch.side_effect = [b'\xe0', b'H']  # UP arrow sequence
        
        self.client_state.active_panel = "users"
        self.client_state.user_panel_scroll_offset = 0
        
        result = self.handler.handle_input(self.client_state)
        
        assert result.action == InputAction.SCROLL_UP
        assert result.state_changes["user_panel_scroll_offset"] == 1
    
    @patch('sys.platform', 'win32')
    @patch('chat_app.client.ui.input_handler.msvcrt')
    def test_handle_windows_input_arrow_down_users(self, mock_msvcrt):
        """Test handling DOWN arrow in users panel."""
        mock_msvcrt.kbhit.return_value = True
        mock_msvcrt.getch.side_effect = [b'\xe0', b'P']  # DOWN arrow sequence
        
        self.client_state.active_panel = "users"
        self.client_state.user_panel_scroll_offset = 3
        
        result = self.handler.handle_input(self.client_state)
        
        assert result.action == InputAction.SCROLL_DOWN
        assert result.state_changes["user_panel_scroll_offset"] == 2
    
    @patch('sys.platform', 'win32')
    @patch('chat_app.client.ui.input_handler.msvcrt')
    def test_handle_windows_input_unknown_special_key(self, mock_msvcrt):
        """Test handling unknown special key."""
        mock_msvcrt.kbhit.return_value = True
        mock_msvcrt.getch.side_effect = [b'\xe0', b'X']  # Unknown key sequence
        
        result = self.handler.handle_input(self.client_state)
        assert result is None
    
    def test_state_changes_on_text_input(self):
        """Test that text input resets scroll state."""
        with patch('sys.platform', 'win32'), \
             patch('chat_app.client.ui.input_handler.msvcrt') as mock_msvcrt:
            
            mock_msvcrt.kbhit.return_value = True
            mock_msvcrt.getch.return_value = b'a'
            
            # Set up scrolled state
            self.client_state.active_panel = "users"
            self.client_state.scroll_offset = 5
            self.client_state.is_scrolled_to_bottom = False
            self.client_state.unseen_messages_count = 3
            self.client_state.user_panel_scroll_offset = 2
            
            result = self.handler.handle_input(self.client_state)
            
            # Should reset all scroll state
            assert result.state_changes["active_panel"] == "chat"
            assert result.state_changes["scroll_offset"] == 0
            assert result.state_changes["is_scrolled_to_bottom"] is True
            assert result.state_changes["unseen_messages_count"] == 0
            assert result.state_changes["user_panel_scroll_offset"] == 0
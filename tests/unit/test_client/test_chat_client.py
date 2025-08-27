"""
Unit tests for the ChatClient class.
"""

import pytest
import threading
import time
from unittest.mock import Mock, patch, MagicMock

from chat_app.client.chat_client import ChatClient, ClientConfig
from chat_app.shared.models import ConnectionStatus
from chat_app.client.ui.input_handler import InputResult, InputAction


class TestClientConfig:
    """Test ClientConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = ClientConfig("localhost", 8080, "TestUser")
        
        assert config.host == "localhost"
        assert config.port == 8080
        assert config.username == "TestUser"
        assert config.ui_refresh_rate == 20
        assert config.max_message_history == 2000
        assert config.console_height == 24
    
    def test_custom_values(self):
        """Test custom configuration values."""
        config = ClientConfig(
            host="192.168.1.1",
            port=9090,
            username="Alice",
            ui_refresh_rate=30,
            max_message_history=1000,
            console_height=30
        )
        
        assert config.host == "192.168.1.1"
        assert config.port == 9090
        assert config.username == "Alice"
        assert config.ui_refresh_rate == 30
        assert config.max_message_history == 1000
        assert config.console_height == 30


class TestChatClient:
    """Test ChatClient class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = ClientConfig("localhost", 8080, "TestUser")
        
        # Mock all the components to avoid actual network/UI operations
        with patch('chat_app.client.chat_client.Connection'), \
             patch('chat_app.client.chat_client.MessageHandler'), \
             patch('chat_app.client.chat_client.LayoutManager'), \
             patch('chat_app.client.chat_client.InputHandler'), \
             patch('chat_app.client.chat_client.DisplayManager'), \
             patch('chat_app.client.chat_client.ServiceDiscovery'):
            
            self.client = ChatClient(self.config)
    
    def test_initialization(self):
        """Test client initialization."""
        assert self.client.config == self.config
        assert self.client.client_state.username == "TestUser"
        assert self.client.client_state.connection_status == ConnectionStatus.DISCONNECTED
        assert not self.client.is_running
        assert len(self.client.user_list) == 0
    
    def test_set_callbacks(self):
        """Test setting external callbacks."""
        on_connected = Mock()
        on_disconnected = Mock()
        on_error = Mock()
        
        self.client.set_callbacks(
            on_connected=on_connected,
            on_disconnected=on_disconnected,
            on_error=on_error
        )
        
        assert self.client._on_connected == on_connected
        assert self.client._on_disconnected == on_disconnected
        assert self.client._on_error == on_error
    
    @patch('chat_app.client.chat_client.sys.platform', 'linux')
    def test_start_unsupported_platform(self):
        """Test starting on unsupported platform."""
        self.client.input_handler.is_platform_supported.return_value = False
        
        with patch.object(self.client.console, 'print') as mock_print:
            self.client.start()
            
            mock_print.assert_called()
            # Should print unsupported platform message
            assert any("Windows" in str(call) for call in mock_print.call_args_list)
    
    def test_start_connection_failure(self):
        """Test starting with connection failure."""
        self.client.input_handler.is_platform_supported.return_value = True
        self.client.connection.connect.return_value = False
        
        with patch.object(self.client.console, 'print') as mock_print:
            self.client.start()
            
            mock_print.assert_called()
            # Should print connection failure message
            assert any("Failed to connect" in str(call) for call in mock_print.call_args_list)
    
    def test_shutdown(self):
        """Test client shutdown."""
        # Set up running state
        self.client.is_running = True
        self.client._network_thread = Mock()
        self.client._network_thread.is_alive.return_value = True
        
        with patch.object(self.client.console, 'print') as mock_print:
            self.client.shutdown()
            
            assert not self.client.is_running
            self.client.connection.close.assert_called_once()
            self.client._network_thread.join.assert_called_once_with(timeout=2.0)
            mock_print.assert_called()
    
    def test_mark_ui_dirty(self):
        """Test marking UI as dirty."""
        self.client._ui_dirty = False
        self.client._mark_ui_dirty()
        assert self.client._ui_dirty is True
    
    def test_apply_state_changes(self):
        """Test applying state changes."""
        state_changes = {
            "active_panel": "users",
            "scroll_offset": 5,
            "input_buffer": "test"
        }
        
        self.client._apply_state_changes(state_changes)
        
        assert self.client.client_state.active_panel == "users"
        assert self.client.client_state.scroll_offset == 5
        assert self.client.client_state.input_buffer == "test"
        assert self.client._ui_dirty is True
    
    def test_apply_state_changes_none(self):
        """Test applying None state changes."""
        original_dirty = self.client._ui_dirty
        self.client._apply_state_changes(None)
        assert self.client._ui_dirty == original_dirty
    
    def test_on_connection_established(self):
        """Test connection establishment handler."""
        on_connected = Mock()
        self.client.set_callbacks(on_connected=on_connected)
        
        self.client._on_connection_established()
        
        assert self.client.client_state.connection_status == ConnectionStatus.CONNECTED
        assert self.client.client_state.server_host == "localhost"
        assert self.client.client_state.server_port == 8080
        
        self.client.display_manager.add_system_message.assert_called()
        on_connected.assert_called_once()
        assert self.client._ui_dirty is True
    
    def test_on_connection_lost(self):
        """Test connection loss handler."""
        on_disconnected = Mock()
        self.client.set_callbacks(on_disconnected=on_disconnected)
        self.client.is_running = True
        
        self.client._on_connection_lost()
        
        assert self.client.client_state.connection_status == ConnectionStatus.DISCONNECTED
        assert not self.client.is_running
        
        self.client.display_manager.add_system_message.assert_called()
        on_disconnected.assert_called_once()
        assert self.client._ui_dirty is True
    
    def test_on_connection_error(self):
        """Test connection error handler."""
        on_error = Mock()
        self.client.set_callbacks(on_error=on_error)
        
        self.client._on_connection_error("Test error")
        
        assert self.client.client_state.connection_status == ConnectionStatus.ERROR
        
        self.client.display_manager.add_system_message.assert_called()
        on_error.assert_called_once_with("Test error")
        assert self.client._ui_dirty is True
    
    def test_on_chat_message(self):
        """Test chat message handler."""
        self.client._on_chat_message("Hello, World!")
        
        self.client.display_manager.add_chat_message.assert_called_once_with(
            "Hello, World!", self.client.client_state
        )
        assert self.client._ui_dirty is True
    
    def test_on_server_message(self):
        """Test server message handler."""
        self.client._on_server_message("Welcome to the server")
        
        self.client.display_manager.add_server_message.assert_called_once_with(
            "Welcome to the server", self.client.client_state
        )
        assert self.client._ui_dirty is True
    
    def test_on_user_list_update(self):
        """Test user list update handler."""
        user_dict = {"Alice": "192.168.1.1", "Bob": "192.168.1.2"}
        
        self.client._on_user_list_update(user_dict)
        
        assert self.client.user_list == user_dict
        assert self.client._ui_dirty is True
    
    def test_on_message_error(self):
        """Test message error handler."""
        self.client._on_message_error("Parse error")
        
        self.client.display_manager.add_system_message.assert_called()
        assert self.client._ui_dirty is True
    
    def test_on_send_message(self):
        """Test send message handler."""
        result = InputResult(action=InputAction.SEND_MESSAGE, data="Hello!")
        
        self.client._on_send_message(result)
        
        self.client.connection.send_message.assert_called_once_with("MSG|TestUser: Hello!")
        self.client.display_manager.add_user_message.assert_called_once()
        assert self.client._ui_dirty is True
    
    def test_on_send_message_error(self):
        """Test send message with connection error."""
        result = InputResult(action=InputAction.SEND_MESSAGE, data="Hello!")
        self.client.connection.send_message.side_effect = Exception("Connection error")
        
        self.client._on_send_message(result)
        
        self.client.display_manager.add_system_message.assert_called()
        assert self.client._ui_dirty is True
    
    def test_on_send_command_nick(self):
        """Test send nick command handler."""
        result = InputResult(
            action=InputAction.SEND_COMMAND,
            command="nick",
            args="NewName"
        )
        self.client.input_handler.validate_nickname.return_value = (True, None)
        
        self.client._on_send_command(result)
        
        assert self.client.client_state.username == "NewName"
        self.client.connection.send_message.assert_called_once_with("CMD_USER|NewName")
        self.client.display_manager.add_system_message.assert_called()
        assert self.client._ui_dirty is True
    
    def test_on_send_command_nick_invalid(self):
        """Test send nick command with invalid nickname."""
        result = InputResult(
            action=InputAction.SEND_COMMAND,
            command="nick",
            args="Invalid|Name"
        )
        self.client.input_handler.validate_nickname.return_value = (False, "Invalid character")
        
        self.client._on_send_command(result)
        
        # Username should not change
        assert self.client.client_state.username == "TestUser"
        self.client.display_manager.add_system_message.assert_called()
        assert self.client._ui_dirty is True
    
    def test_on_quit_requested(self):
        """Test quit request handler."""
        self.client.is_running = True
        result = InputResult(action=InputAction.QUIT)
        
        self.client._on_quit_requested(result)
        
        assert not self.client.is_running
    
    def test_on_switch_panel(self):
        """Test panel switch handler."""
        result = InputResult(action=InputAction.SWITCH_PANEL)
        
        self.client._on_switch_panel(result)
        
        assert self.client._ui_dirty is True
    
    def test_on_scroll_up(self):
        """Test scroll up handler."""
        self.client.client_state.active_panel = "chat"
        result = InputResult(action=InputAction.SCROLL_UP)
        
        self.client._on_scroll_up(result)
        
        self.client.display_manager.scroll_up.assert_called_once_with(self.client.client_state)
        assert self.client._ui_dirty is True
    
    def test_on_scroll_down(self):
        """Test scroll down handler."""
        self.client.client_state.active_panel = "chat"
        result = InputResult(action=InputAction.SCROLL_DOWN)
        
        self.client._on_scroll_down(result)
        
        self.client.display_manager.scroll_down.assert_called_once_with(self.client.client_state)
        assert self.client._ui_dirty is True
    
    def test_on_update_buffer(self):
        """Test update buffer handler."""
        result = InputResult(action=InputAction.UPDATE_BUFFER)
        
        self.client._on_update_buffer(result)
        
        assert self.client._ui_dirty is True
    
    def test_get_connection_status(self):
        """Test getting connection status."""
        self.client.client_state.connection_status = ConnectionStatus.CONNECTED
        
        status = self.client.get_connection_status()
        
        assert status == ConnectionStatus.CONNECTED
    
    def test_get_user_list(self):
        """Test getting user list."""
        self.client.user_list = {"Alice": "192.168.1.1", "Bob": "192.168.1.2"}
        
        user_list = self.client.get_user_list()
        
        assert user_list == {"Alice": "192.168.1.1", "Bob": "192.168.1.2"}
        # Should return a copy
        assert user_list is not self.client.user_list
    
    def test_get_client_info(self):
        """Test getting client information."""
        self.client.client_state.connection_status = ConnectionStatus.CONNECTED
        self.client.client_state.server_host = "localhost"
        self.client.client_state.server_port = 8080
        self.client.is_running = True
        self.client.user_list = {"Alice": "192.168.1.1"}
        
        # Mock display manager stats
        mock_stats = Mock()
        mock_stats.total_messages = 42
        self.client.display_manager.get_stats.return_value = mock_stats
        
        info = self.client.get_client_info()
        
        assert info["username"] == "TestUser"
        assert info["connection_status"] == "connected"
        assert info["server_host"] == "localhost"
        assert info["server_port"] == 8080
        assert info["active_panel"] == "chat"
        assert info["is_running"] is True
        assert info["user_count"] == 1
        assert info["message_count"] == 42
    
    def test_send_message_programmatic(self):
        """Test sending message programmatically."""
        result = self.client.send_message("Hello, World!")
        
        assert result is True
        self.client.connection.send_message.assert_called_once_with("MSG|TestUser: Hello, World!")
        self.client.display_manager.add_user_message.assert_called_once()
        assert self.client._ui_dirty is True
    
    def test_send_message_programmatic_error(self):
        """Test sending message programmatically with error."""
        self.client.connection.send_message.side_effect = Exception("Connection error")
        
        result = self.client.send_message("Hello, World!")
        
        assert result is False
    
    def test_change_username_programmatic(self):
        """Test changing username programmatically."""
        self.client.input_handler.validate_nickname.return_value = (True, None)
        
        result = self.client.change_username("NewName")
        
        assert result is True
        assert self.client.client_state.username == "NewName"
        self.client.connection.send_message.assert_called_once_with("CMD_USER|NewName")
        self.client.display_manager.add_system_message.assert_called()
        assert self.client._ui_dirty is True
    
    def test_change_username_programmatic_invalid(self):
        """Test changing username programmatically with invalid name."""
        self.client.input_handler.validate_nickname.return_value = (False, "Invalid character")
        
        result = self.client.change_username("Invalid|Name")
        
        assert result is False
        assert self.client.client_state.username == "TestUser"  # Should not change
    
    def test_change_username_programmatic_error(self):
        """Test changing username programmatically with connection error."""
        self.client.input_handler.validate_nickname.return_value = (True, None)
        self.client.connection.send_message.side_effect = Exception("Connection error")
        
        result = self.client.change_username("NewName")
        
        assert result is False
    
    def test_update_ui(self):
        """Test UI update method."""
        mock_history = [Mock(), Mock()]
        self.client.display_manager.get_chat_history.return_value = mock_history
        self.client.user_list = {"Alice": "192.168.1.1"}
        
        self.client._update_ui()
        
        self.client.layout_manager.update_all_panels.assert_called_once_with(
            chat_history=mock_history,
            user_list={"Alice": "192.168.1.1"},
            client_state=self.client.client_state,
            show_cursor=True
        )
    
    def test_network_loop_messages(self):
        """Test network loop processing messages."""
        self.client.is_running = True
        messages = ["MSG|Hello", "SRV|Welcome"]
        
        # Mock connection to return messages once, then empty
        self.client.connection.receive_messages.side_effect = [messages, []]
        
        # Run one iteration of the network loop
        with patch('time.sleep'):  # Speed up the test
            # Manually call the method once
            try:
                self.client._network_loop()
            except Exception:
                pass  # Expected when is_running becomes False
        
        self.client.message_handler.handle_raw_messages.assert_called_with(messages)
    
    def test_network_loop_exception(self):
        """Test network loop handling exceptions."""
        self.client.is_running = True
        self.client.connection.receive_messages.side_effect = Exception("Network error")
        
        with patch('time.sleep'):  # Speed up the test
            self.client._network_loop()
        
        # Should not crash and should call error handler
        # The loop should exit gracefully
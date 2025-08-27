"""
Input Handler

Handles keyboard input processing for the chat client.
"""

import sys
from typing import Optional, Callable, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from chat_app.shared.models import ClientState
from chat_app.shared.constants import (
    WINDOWS_PLATFORM,
    WINDOWS_TAB_KEY,
    WINDOWS_ENTER_KEY,
    WINDOWS_BACKSPACE_KEY,
    WINDOWS_SPECIAL_KEY_PREFIX,
    WINDOWS_UP_ARROW,
    WINDOWS_DOWN_ARROW,
    QUIT_COMMAND,
    NICK_COMMAND
)

# Platform-specific imports
if sys.platform == WINDOWS_PLATFORM:
    import msvcrt


class InputAction(Enum):
    """Enumeration of input actions."""
    NO_ACTION = "no_action"
    SEND_MESSAGE = "send_message"
    SEND_COMMAND = "send_command"
    QUIT = "quit"
    SCROLL_UP = "scroll_up"
    SCROLL_DOWN = "scroll_down"
    SWITCH_PANEL = "switch_panel"
    UPDATE_BUFFER = "update_buffer"


@dataclass
class InputResult:
    """Result of input processing."""
    action: InputAction
    data: Optional[str] = None
    command: Optional[str] = None
    args: Optional[str] = None
    state_changes: Optional[Dict[str, Any]] = None


class InputHandler:
    """
    Handles keyboard input processing for the chat client.
    
    Processes platform-specific keyboard input and converts it to
    application actions and state changes.
    """
    
    def __init__(self) -> None:
        """Initialize the input handler."""
        self.is_supported_platform = sys.platform == WINDOWS_PLATFORM
        self._input_callbacks: Dict[InputAction, Callable[[InputResult], None]] = {}
    
    def set_callback(self, action: InputAction, callback: Callable[[InputResult], None]) -> None:
        """
        Set a callback for a specific input action.
        
        Args:
            action: The input action to handle.
            callback: The callback function.
        """
        self._input_callbacks[action] = callback
    
    def remove_callback(self, action: InputAction) -> None:
        """
        Remove a callback for a specific input action.
        
        Args:
            action: The input action to remove callback for.
        """
        if action in self._input_callbacks:
            del self._input_callbacks[action]
    
    def handle_input(self, client_state: ClientState) -> Optional[InputResult]:
        """
        Handle keyboard input and return the result.
        
        Args:
            client_state: Current client state.
            
        Returns:
            InputResult if input was processed, None otherwise.
        """
        if not self.is_supported_platform:
            return None
        
        return self._handle_windows_input(client_state)
    
    def _handle_windows_input(self, client_state: ClientState) -> Optional[InputResult]:
        """
        Handle Windows-specific keyboard input.
        
        Args:
            client_state: Current client state.
            
        Returns:
            InputResult if input was processed, None otherwise.
        """
        if not msvcrt.kbhit():
            return None
        
        char = msvcrt.getch()
        
        # Handle TAB key (switch panels)
        if char == WINDOWS_TAB_KEY:
            new_panel = "users" if client_state.active_panel == "chat" else "chat"
            return InputResult(
                action=InputAction.SWITCH_PANEL,
                state_changes={"active_panel": new_panel}
            )
        
        # Handle special keys (arrows, function keys, etc.)
        if char in WINDOWS_SPECIAL_KEY_PREFIX:
            return self._handle_special_key(client_state)
        
        # Reset to chat panel and scroll position on any text input
        state_changes = {
            "active_panel": "chat",
            "scroll_offset": 0,
            "is_scrolled_to_bottom": True,
            "unseen_messages_count": 0,
            "user_panel_scroll_offset": 0
        }
        
        # Handle ENTER key
        if char == WINDOWS_ENTER_KEY:
            if client_state.input_buffer:
                message_text = client_state.input_buffer
                state_changes["input_buffer"] = ""
                
                # Check for commands
                if message_text.lower() == QUIT_COMMAND:
                    return InputResult(action=InputAction.QUIT)
                elif message_text.startswith(NICK_COMMAND + " "):
                    new_username = message_text.split(' ', 1)[1].strip()
                    if new_username:
                        return InputResult(
                            action=InputAction.SEND_COMMAND,
                            command="nick",
                            args=new_username,
                            state_changes=state_changes
                        )
                    else:
                        # Invalid nickname - no action but clear buffer
                        return InputResult(
                            action=InputAction.NO_ACTION,
                            state_changes=state_changes
                        )
                else:
                    # Regular message
                    return InputResult(
                        action=InputAction.SEND_MESSAGE,
                        data=message_text,
                        state_changes=state_changes
                    )
            else:
                # Empty buffer - no action
                return InputResult(action=InputAction.NO_ACTION)
        
        # Handle BACKSPACE key
        elif char == WINDOWS_BACKSPACE_KEY:
            new_buffer = client_state.input_buffer[:-1]
            state_changes["input_buffer"] = new_buffer
            return InputResult(
                action=InputAction.UPDATE_BUFFER,
                data=new_buffer,
                state_changes=state_changes
            )
        
        # Handle regular character input
        else:
            try:
                char_str = char.decode('utf-8')
                new_buffer = client_state.input_buffer + char_str
                state_changes["input_buffer"] = new_buffer
                return InputResult(
                    action=InputAction.UPDATE_BUFFER,
                    data=new_buffer,
                    state_changes=state_changes
                )
            except UnicodeDecodeError:
                # Skip invalid characters
                return None
    
    def _handle_special_key(self, client_state: ClientState) -> Optional[InputResult]:
        """
        Handle special keys (arrows, function keys).
        
        Args:
            client_state: Current client state.
            
        Returns:
            InputResult if key was handled, None otherwise.
        """
        key_code = msvcrt.getch()
        
        # Up Arrow
        if key_code == WINDOWS_UP_ARROW:
            if client_state.active_panel == 'chat':
                # Scroll up in chat
                state_changes = {}
                if client_state.scroll_offset == 0:
                    # Moving from bottom to scrolled state
                    state_changes["is_scrolled_to_bottom"] = False
                
                # Increment scroll offset (limit to reasonable bounds)
                new_offset = min(1000, client_state.scroll_offset + 1)  # Arbitrary max
                state_changes["scroll_offset"] = new_offset
                
                return InputResult(
                    action=InputAction.SCROLL_UP,
                    state_changes=state_changes
                )
            else:
                # Scroll up in user panel
                new_offset = min(1000, client_state.user_panel_scroll_offset + 1)
                return InputResult(
                    action=InputAction.SCROLL_UP,
                    state_changes={"user_panel_scroll_offset": new_offset}
                )
        
        # Down Arrow
        elif key_code == WINDOWS_DOWN_ARROW:
            if client_state.active_panel == 'chat':
                # Scroll down in chat
                old_offset = client_state.scroll_offset
                new_offset = max(0, old_offset - 1)
                
                state_changes = {"scroll_offset": new_offset}
                
                # Handle unseen messages when scrolling down
                if new_offset < old_offset and client_state.unseen_messages_count > 0:
                    lines_scrolled = old_offset - new_offset
                    new_unseen = max(0, client_state.unseen_messages_count - lines_scrolled)
                    state_changes["unseen_messages_count"] = new_unseen
                
                # If scrolled to bottom, reset state
                if new_offset == 0 and old_offset > 0:
                    state_changes["is_scrolled_to_bottom"] = True
                    state_changes["unseen_messages_count"] = 0
                
                return InputResult(
                    action=InputAction.SCROLL_DOWN,
                    state_changes=state_changes
                )
            else:
                # Scroll down in user panel
                new_offset = max(0, client_state.user_panel_scroll_offset - 1)
                return InputResult(
                    action=InputAction.SCROLL_DOWN,
                    state_changes={"user_panel_scroll_offset": new_offset}
                )
        
        return None
    
    def process_input_result(self, result: InputResult) -> None:
        """
        Process an input result by calling appropriate callbacks.
        
        Args:
            result: The input result to process.
        """
        if result.action in self._input_callbacks:
            self._input_callbacks[result.action](result)
    
    def is_platform_supported(self) -> bool:
        """
        Check if the current platform is supported.
        
        Returns:
            True if platform is supported, False otherwise.
        """
        return self.is_supported_platform
    
    def get_platform_info(self) -> Dict[str, Any]:
        """
        Get platform information.
        
        Returns:
            Dictionary with platform details.
        """
        return {
            "platform": sys.platform,
            "supported": self.is_supported_platform,
            "input_method": "msvcrt" if self.is_supported_platform else "unsupported"
        }
    
    def parse_command(self, message: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Parse a command from a message string.
        
        Args:
            message: The message to parse.
            
        Returns:
            Tuple of (command, args) or (None, None) if not a command.
        """
        if not message.startswith('/'):
            return None, None
        
        parts = message.split(' ', 1)
        command = parts[0][1:]  # Remove leading '/'
        args = parts[1] if len(parts) > 1 else None
        
        return command, args
    
    def validate_nickname(self, nickname: str) -> Tuple[bool, Optional[str]]:
        """
        Validate a nickname.
        
        Args:
            nickname: The nickname to validate.
            
        Returns:
            Tuple of (is_valid, error_message).
        """
        if not nickname or not nickname.strip():
            return False, "Nickname cannot be empty"
        
        nickname = nickname.strip()
        
        if len(nickname) > 50:  # Reasonable limit
            return False, "Nickname too long (max 50 characters)"
        
        # Check for invalid characters
        invalid_chars = ['|', '\n', '\r', '\t']
        for char in invalid_chars:
            if char in nickname:
                return False, f"Nickname contains invalid character: {repr(char)}"
        
        return True, None
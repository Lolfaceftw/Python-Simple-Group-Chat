"""
Display Manager

Manages message display and scrolling functionality for the chat client.
"""

import threading
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field

from rich.text import Text
from rich.console import Console

from chat_app.shared.models import ClientState, Message, MessageType
from chat_app.shared.constants import MAX_MESSAGE_HISTORY


@dataclass
class DisplayStats:
    """Statistics for display management."""
    total_messages: int = 0
    chat_messages: int = 0
    server_messages: int = 0
    messages_trimmed: int = 0
    last_message_time: Optional[datetime] = None


class DisplayManager:
    """
    Manages message display and scrolling for the chat client.
    
    Handles chat history, message formatting, and scroll state management.
    """
    
    def __init__(self, max_history: int = MAX_MESSAGE_HISTORY) -> None:
        """
        Initialize the display manager.
        
        Args:
            max_history: Maximum number of messages to keep in history.
        """
        self.max_history = max_history
        self.chat_history: List[Text] = []
        self._lock = threading.Lock()
        self._stats = DisplayStats()
        
        # Message formatting styles
        self._message_styles = {
            MessageType.CHAT: "cyan",
            MessageType.SERVER: "yellow italic",
            MessageType.USER_LIST: "dim",
            MessageType.COMMAND: "green",
            MessageType.USER_COMMAND: "green"
        }
    
    def add_message(self, message: str, style: str = "cyan", 
                   client_state: Optional[ClientState] = None) -> None:
        """
        Add a message to the chat history.
        
        Args:
            message: The message text to add.
            style: Rich style for the message.
            client_state: Current client state for scroll management.
        """
        with self._lock:
            text_message = Text(message, style)
            self.chat_history.append(text_message)
            
            # Update statistics
            self._stats.total_messages += 1
            self._stats.last_message_time = datetime.now()
            
            # Handle scroll state if client state is provided
            if client_state:
                if not client_state.is_scrolled_to_bottom:
                    client_state.unseen_messages_count += 1
                else:
                    # If at bottom, ensure scroll offset is 0
                    client_state.scroll_offset = 0
                    client_state.unseen_messages_count = 0
            
            # Trim history if needed
            self._trim_history()
    
    def add_chat_message(self, message: str, 
                        client_state: Optional[ClientState] = None) -> None:
        """
        Add a chat message with appropriate styling.
        
        Args:
            message: The chat message text.
            client_state: Current client state.
        """
        self.add_message(message, self._message_styles[MessageType.CHAT], client_state)
        with self._lock:
            self._stats.chat_messages += 1
    
    def add_server_message(self, message: str, 
                          client_state: Optional[ClientState] = None) -> None:
        """
        Add a server message with appropriate styling.
        
        Args:
            message: The server message text.
            client_state: Current client state.
        """
        formatted_message = f"=> {message}"
        self.add_message(formatted_message, self._message_styles[MessageType.SERVER], client_state)
        with self._lock:
            self._stats.server_messages += 1
    
    def add_user_message(self, username: str, message: str, 
                        is_own_message: bool = False,
                        client_state: Optional[ClientState] = None) -> None:
        """
        Add a user message with username formatting.
        
        Args:
            username: The username of the sender.
            message: The message content.
            is_own_message: Whether this is the current user's message.
            client_state: Current client state.
        """
        formatted_message = f"{username}: {message}"
        style = "bright_blue" if is_own_message else self._message_styles[MessageType.CHAT]
        self.add_message(formatted_message, style, client_state)
        with self._lock:
            self._stats.chat_messages += 1
    
    def add_system_message(self, message: str, style: str = "green",
                          client_state: Optional[ClientState] = None) -> None:
        """
        Add a system message (like connection status, errors).
        
        Args:
            message: The system message text.
            style: Rich style for the message.
            client_state: Current client state.
        """
        self.add_message(message, style, client_state)
    
    def get_chat_history(self) -> List[Text]:
        """
        Get the current chat history.
        
        Returns:
            List of Text objects representing chat messages.
        """
        with self._lock:
            return self.chat_history.copy()
    
    def get_visible_history(self, client_state: ClientState, 
                           panel_height: int) -> List[Text]:
        """
        Get the visible portion of chat history based on scroll state.
        
        Args:
            client_state: Current client state with scroll information.
            panel_height: Height of the display panel.
            
        Returns:
            List of visible Text messages.
        """
        with self._lock:
            if client_state.scroll_offset > 0:
                # Scrolled up - show historical messages
                end_index = len(self.chat_history) - client_state.scroll_offset
                start_index = max(0, end_index - panel_height)
                return self.chat_history[start_index:end_index]
            else:
                # At bottom - show most recent messages
                return self.chat_history[-panel_height:]
    
    def clear_history(self) -> None:
        """Clear all chat history."""
        with self._lock:
            self.chat_history.clear()
            self._stats = DisplayStats()
    
    def scroll_to_bottom(self, client_state: ClientState) -> None:
        """
        Scroll to the bottom of the chat history.
        
        Args:
            client_state: Client state to update.
        """
        client_state.scroll_offset = 0
        client_state.is_scrolled_to_bottom = True
        client_state.unseen_messages_count = 0
    
    def scroll_up(self, client_state: ClientState, lines: int = 1) -> None:
        """
        Scroll up in the chat history.
        
        Args:
            client_state: Client state to update.
            lines: Number of lines to scroll up.
        """
        if client_state.scroll_offset == 0:
            # Moving from bottom to scrolled state
            client_state.is_scrolled_to_bottom = False
        
        max_scroll = len(self.chat_history) - 1
        client_state.scroll_offset = min(max_scroll, client_state.scroll_offset + lines)
    
    def scroll_down(self, client_state: ClientState, lines: int = 1) -> None:
        """
        Scroll down in the chat history.
        
        Args:
            client_state: Client state to update.
            lines: Number of lines to scroll down.
        """
        old_offset = client_state.scroll_offset
        client_state.scroll_offset = max(0, old_offset - lines)
        
        # Handle unseen messages when scrolling down
        if client_state.scroll_offset < old_offset and client_state.unseen_messages_count > 0:
            lines_scrolled = old_offset - client_state.scroll_offset
            client_state.unseen_messages_count = max(0, 
                client_state.unseen_messages_count - lines_scrolled)
        
        # If scrolled to bottom, reset state
        if client_state.scroll_offset == 0 and old_offset > 0:
            client_state.is_scrolled_to_bottom = True
            client_state.unseen_messages_count = 0
    
    def format_message(self, message: Message, current_username: str = "") -> Text:
        """
        Format a Message object into a Rich Text object.
        
        Args:
            message: The message to format.
            current_username: Current user's username for styling.
            
        Returns:
            Formatted Text object.
        """
        if message.message_type == MessageType.CHAT:
            # Check if it's the current user's message
            is_own = message.sender == current_username
            style = "bright_blue" if is_own else self._message_styles[MessageType.CHAT]
            return Text(message.content, style)
        
        elif message.message_type == MessageType.SERVER:
            formatted_content = f"=> {message.content}"
            return Text(formatted_content, self._message_styles[MessageType.SERVER])
        
        else:
            # Default formatting for other message types
            style = self._message_styles.get(message.message_type, "white")
            return Text(message.content, style)
    
    def get_stats(self) -> DisplayStats:
        """
        Get display statistics.
        
        Returns:
            Current display statistics.
        """
        with self._lock:
            return DisplayStats(
                total_messages=self._stats.total_messages,
                chat_messages=self._stats.chat_messages,
                server_messages=self._stats.server_messages,
                messages_trimmed=self._stats.messages_trimmed,
                last_message_time=self._stats.last_message_time
            )
    
    def reset_stats(self) -> None:
        """Reset display statistics."""
        with self._lock:
            self._stats = DisplayStats()
    
    def set_max_history(self, max_history: int) -> None:
        """
        Set the maximum history size.
        
        Args:
            max_history: New maximum history size.
        """
        self.max_history = max_history
        self._trim_history()
    
    def get_history_info(self) -> Dict[str, Any]:
        """
        Get information about the chat history.
        
        Returns:
            Dictionary with history information.
        """
        with self._lock:
            return {
                "current_size": len(self.chat_history),
                "max_size": self.max_history,
                "total_messages": self._stats.total_messages,
                "messages_trimmed": self._stats.messages_trimmed,
                "last_message_time": self._stats.last_message_time
            }
    
    def _trim_history(self) -> None:
        """Trim chat history to maximum size."""
        if len(self.chat_history) > self.max_history:
            messages_to_remove = len(self.chat_history) - self.max_history
            self.chat_history = self.chat_history[messages_to_remove:]
            self._stats.messages_trimmed += messages_to_remove
    
    def export_history(self, include_timestamps: bool = True) -> List[str]:
        """
        Export chat history as plain text.
        
        Args:
            include_timestamps: Whether to include timestamps.
            
        Returns:
            List of plain text messages.
        """
        with self._lock:
            exported = []
            for text_obj in self.chat_history:
                message = text_obj.plain
                if include_timestamps:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    message = f"[{timestamp}] {message}"
                exported.append(message)
            return exported
    
    def search_history(self, query: str, case_sensitive: bool = False) -> List[int]:
        """
        Search for messages containing a query string.
        
        Args:
            query: The search query.
            case_sensitive: Whether search should be case sensitive.
            
        Returns:
            List of message indices that match the query.
        """
        if not query:
            return []
        
        with self._lock:
            matches = []
            search_query = query if case_sensitive else query.lower()
            
            for i, text_obj in enumerate(self.chat_history):
                message_text = text_obj.plain
                search_text = message_text if case_sensitive else message_text.lower()
                
                if search_query in search_text:
                    matches.append(i)
            
            return matches
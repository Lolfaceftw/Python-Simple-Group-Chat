"""
Message Handler

Processes incoming messages from the server and routes them appropriately.
"""

import threading
from typing import Dict, List, Callable, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from chat_app.shared.models import Message, MessageType, User
from chat_app.shared.constants import PROTOCOL_SEPARATOR
from chat_app.shared.protocols import MessageHandler as MessageHandlerProtocol


@dataclass
class MessageStats:
    """Statistics for message handling."""
    total_received: int = 0
    chat_messages: int = 0
    server_messages: int = 0
    user_list_updates: int = 0
    command_responses: int = 0
    parse_errors: int = 0
    last_message_time: Optional[datetime] = None


class MessageHandler(MessageHandlerProtocol):
    """
    Handles incoming messages from the server.
    
    Parses protocol messages and routes them to appropriate handlers
    based on message type.
    """
    
    def __init__(self) -> None:
        """Initialize the message handler."""
        self._handlers: Dict[MessageType, List[Callable[[Message], None]]] = {
            MessageType.CHAT: [],
            MessageType.SERVER: [],
            MessageType.USER_LIST: [],
            MessageType.COMMAND: [],
            MessageType.USER_COMMAND: []
        }
        self._lock = threading.Lock()
        self._stats = MessageStats()
        
        # Default handlers
        self._chat_callback: Optional[Callable[[str], None]] = None
        self._server_callback: Optional[Callable[[str], None]] = None
        self._user_list_callback: Optional[Callable[[Dict[str, str]], None]] = None
        self._error_callback: Optional[Callable[[str], None]] = None
    
    def set_callbacks(self,
                     chat_callback: Optional[Callable[[str], None]] = None,
                     server_callback: Optional[Callable[[str], None]] = None,
                     user_list_callback: Optional[Callable[[Dict[str, str]], None]] = None,
                     error_callback: Optional[Callable[[str], None]] = None) -> None:
        """
        Set callback functions for different message types.
        
        Args:
            chat_callback: Called for chat messages with message content.
            server_callback: Called for server messages with message content.
            user_list_callback: Called for user list updates with user dict.
            error_callback: Called when message parsing errors occur.
        """
        self._chat_callback = chat_callback
        self._server_callback = server_callback
        self._user_list_callback = user_list_callback
        self._error_callback = error_callback
    
    def register_handler(self, message_type: MessageType, 
                        handler: Callable[[Message], None]) -> None:
        """
        Register a handler for a specific message type.
        
        Args:
            message_type: The type of message to handle.
            handler: The handler function.
        """
        with self._lock:
            if message_type not in self._handlers:
                self._handlers[message_type] = []
            self._handlers[message_type].append(handler)
    
    def unregister_handler(self, message_type: MessageType,
                          handler: Callable[[Message], None]) -> None:
        """
        Unregister a handler for a specific message type.
        
        Args:
            message_type: The type of message.
            handler: The handler function to remove.
        """
        with self._lock:
            if message_type in self._handlers:
                try:
                    self._handlers[message_type].remove(handler)
                except ValueError:
                    pass  # Handler not found
    
    def handle_message(self, message: Message, sender: Any = None) -> None:
        """
        Handle an incoming message.
        
        Args:
            message: The message to handle.
            sender: The sender of the message (unused in client).
        """
        with self._lock:
            self._stats.total_received += 1
            self._stats.last_message_time = datetime.now()
            
            # Update type-specific stats
            if message.message_type == MessageType.CHAT:
                self._stats.chat_messages += 1
            elif message.message_type == MessageType.SERVER:
                self._stats.server_messages += 1
            elif message.message_type == MessageType.USER_LIST:
                self._stats.user_list_updates += 1
            elif message.message_type in [MessageType.COMMAND, MessageType.USER_COMMAND]:
                self._stats.command_responses += 1
        
        # Call registered handlers
        handlers = self._handlers.get(message.message_type, [])
        for handler in handlers:
            try:
                handler(message)
            except Exception as e:
                if self._error_callback:
                    self._error_callback(f"Handler error: {e}")
        
        # Call default callbacks
        self._call_default_callback(message)
    
    def handle_raw_message(self, raw_message: str) -> None:
        """
        Handle a raw message string from the network.
        
        Args:
            raw_message: The raw message string to parse and handle.
        """
        try:
            message = self._parse_message(raw_message)
            if message:
                self.handle_message(message)
        except Exception as e:
            with self._lock:
                self._stats.parse_errors += 1
            
            if self._error_callback:
                self._error_callback(f"Message parse error: {e}")
    
    def handle_raw_messages(self, raw_messages: List[str]) -> None:
        """
        Handle multiple raw message strings.
        
        Args:
            raw_messages: List of raw message strings to process.
        """
        for raw_message in raw_messages:
            self.handle_raw_message(raw_message)
    
    def _parse_message(self, raw_message: str) -> Optional[Message]:
        """
        Parse a raw message string into a Message object.
        
        Args:
            raw_message: The raw message string.
            
        Returns:
            Parsed Message object, or None if parsing failed.
        """
        if not raw_message.strip():
            return None
        
        parts = raw_message.split(PROTOCOL_SEPARATOR, 1)
        if len(parts) < 2:
            # Assume it's a chat message if no separator
            return Message(
                content=raw_message,
                sender="Unknown",
                message_type=MessageType.CHAT
            )
        
        msg_type_str, content = parts
        
        # Convert string to MessageType enum
        try:
            if msg_type_str == "MSG":
                message_type = MessageType.CHAT
            elif msg_type_str == "SRV":
                message_type = MessageType.SERVER
            elif msg_type_str == "ULIST":
                message_type = MessageType.USER_LIST
            elif msg_type_str == "CMD":
                message_type = MessageType.COMMAND
            elif msg_type_str == "CMD_USER":
                message_type = MessageType.USER_COMMAND
            else:
                # Default to chat message for unknown types
                message_type = MessageType.CHAT
        except ValueError:
            message_type = MessageType.CHAT
        
        return Message(
            content=content,
            sender="Server",  # Server is the sender for client-received messages
            message_type=message_type
        )
    
    def _call_default_callback(self, message: Message) -> None:
        """
        Call the appropriate default callback based on message type.
        
        Args:
            message: The message to process.
        """
        try:
            if message.message_type == MessageType.CHAT and self._chat_callback:
                self._chat_callback(message.content)
            
            elif message.message_type == MessageType.SERVER and self._server_callback:
                self._server_callback(message.content)
            
            elif message.message_type == MessageType.USER_LIST and self._user_list_callback:
                user_dict = self._parse_user_list(message.content)
                self._user_list_callback(user_dict)
            
        except Exception as e:
            if self._error_callback:
                self._error_callback(f"Callback error: {e}")
    
    def _parse_user_list(self, user_list_content: str) -> Dict[str, str]:
        """
        Parse user list content into a dictionary.
        
        Args:
            user_list_content: The user list content string.
            
        Returns:
            Dictionary mapping usernames to addresses.
        """
        user_dict = {}
        
        if not user_list_content.strip():
            return user_dict
        
        try:
            user_entries = user_list_content.split(',')
            for entry in user_entries:
                entry = entry.strip()
                if '(' in entry and entry.endswith(')'):
                    # Format is "username(address)"
                    username, address_part = entry.rsplit('(', 1)
                    address = address_part[:-1]  # Remove trailing ')'
                    user_dict[username.strip()] = address.strip()
        except Exception as e:
            if self._error_callback:
                self._error_callback(f"User list parse error: {e}")
        
        return user_dict
    
    def get_stats(self) -> MessageStats:
        """
        Get message handling statistics.
        
        Returns:
            Current message statistics.
        """
        with self._lock:
            return MessageStats(
                total_received=self._stats.total_received,
                chat_messages=self._stats.chat_messages,
                server_messages=self._stats.server_messages,
                user_list_updates=self._stats.user_list_updates,
                command_responses=self._stats.command_responses,
                parse_errors=self._stats.parse_errors,
                last_message_time=self._stats.last_message_time
            )
    
    def reset_stats(self) -> None:
        """Reset message handling statistics."""
        with self._lock:
            self._stats = MessageStats()
    
    def clear_handlers(self) -> None:
        """Clear all registered handlers."""
        with self._lock:
            for message_type in self._handlers:
                self._handlers[message_type].clear()
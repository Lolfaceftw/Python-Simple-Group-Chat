"""
Main Chat Client

The main chat client class that orchestrates UI, network, and input handling.
"""

import sys
import threading
import time
import logging
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass

from rich.console import Console
from rich.live import Live
from rich.text import Text

from chat_app.shared.models import ClientState, ConnectionStatus
from chat_app.shared.constants import (
    WINDOWS_PLATFORM,
    DEFAULT_UI_REFRESH_RATE,
    QUIT_COMMAND,
    NICK_COMMAND
)
from chat_app.client.network import Connection, MessageHandler
from chat_app.client.network.connection import ConnectionConfig
from chat_app.client.ui import LayoutManager, InputHandler, DisplayManager
from chat_app.client.ui.input_handler import InputAction, InputResult
from chat_app.client.performance.ui_optimizer import UIOptimizer, UIConfig
from chat_app.client.performance.update_scheduler import UpdateScheduler, UpdateConfig, UpdatePriority
from chat_app.discovery.service_discovery import ServiceDiscovery


@dataclass
class ClientConfig:
    """Configuration for the chat client."""
    host: str
    port: int
    username: str
    ui_refresh_rate: int = DEFAULT_UI_REFRESH_RATE
    max_message_history: int = 2000
    console_height: int = 24


class ChatClient:
    """
    Main chat client class.
    
    Orchestrates the UI, network communication, input handling,
    and service discovery for the chat application.
    """
    
    def __init__(self, config: ClientConfig) -> None:
        """
        Initialize the chat client.
        
        Args:
            config: Client configuration.
        """
        self.config = config
        self.console = Console()
        self.logger = logging.getLogger(__name__)
        
        # Client state
        self.client_state = ClientState(username=config.username)
        self.is_running = False
        self.user_list: Dict[str, str] = {}
        
        # Performance components
        ui_config = UIConfig(
            target_fps=config.ui_refresh_rate,
            enable_frame_limiting=True,
            enable_content_caching=True
        )
        self.ui_optimizer = UIOptimizer(self.console, ui_config)
        
        update_config = UpdateConfig(
            max_update_frequency_hz=config.ui_refresh_rate,
            enable_adaptive_scheduling=True,
            enable_update_coalescing=True
        )
        self.update_scheduler = UpdateScheduler(update_config)
        
        # Components
        self._setup_components()
        
        # Threading
        self._network_thread: Optional[threading.Thread] = None
        self._ui_dirty = True
        self._lock = threading.Lock()
        
        # Callbacks
        self._on_connected: Optional[Callable[[], None]] = None
        self._on_disconnected: Optional[Callable[[], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None
    
    def _setup_components(self) -> None:
        """Set up all client components."""
        # Network components
        connection_config = ConnectionConfig(
            host=self.config.host,
            port=self.config.port,
            timeout=1.0,
            max_reconnect_attempts=3
        )
        self.connection = Connection(connection_config)
        self.message_handler = MessageHandler()
        
        # UI components
        self.layout_manager = LayoutManager(console_height=self.config.console_height)
        self.input_handler = InputHandler()
        self.display_manager = DisplayManager(max_history=self.config.max_message_history)
        
        # Service discovery
        self.service_discovery = ServiceDiscovery()
        
        # Set up callbacks
        self._setup_callbacks()
    
    def _setup_callbacks(self) -> None:
        """Set up callbacks between components."""
        # Connection callbacks
        self.connection.set_callbacks(
            on_connected=self._on_connection_established,
            on_disconnected=self._on_connection_lost,
            on_error=self._on_connection_error
        )
        
        # Message handler callbacks
        self.message_handler.set_callbacks(
            chat_callback=self._on_chat_message,
            server_callback=self._on_server_message,
            user_list_callback=self._on_user_list_update,
            error_callback=self._on_message_error
        )
        
        # Input handler callbacks
        self.input_handler.set_callback(InputAction.SEND_MESSAGE, self._on_send_message)
        self.input_handler.set_callback(InputAction.SEND_COMMAND, self._on_send_command)
        self.input_handler.set_callback(InputAction.QUIT, self._on_quit_requested)
        self.input_handler.set_callback(InputAction.SWITCH_PANEL, self._on_switch_panel)
        self.input_handler.set_callback(InputAction.SCROLL_UP, self._on_scroll_up)
        self.input_handler.set_callback(InputAction.SCROLL_DOWN, self._on_scroll_down)
        self.input_handler.set_callback(InputAction.UPDATE_BUFFER, self._on_update_buffer)
    
    def set_callbacks(self,
                     on_connected: Optional[Callable[[], None]] = None,
                     on_disconnected: Optional[Callable[[], None]] = None,
                     on_error: Optional[Callable[[str], None]] = None) -> None:
        """
        Set external callbacks for client events.
        
        Args:
            on_connected: Called when connection is established.
            on_disconnected: Called when connection is lost.
            on_error: Called when an error occurs.
        """
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected
        self._on_error = on_error
    
    def start(self) -> None:
        """Start the chat client."""
        if not self.input_handler.is_platform_supported():
            self.console.print("[bold red]This UI is currently only supported on Windows.[/bold red]")
            self.console.print("A future version will add support for macOS and Linux.")
            return
        
        try:
            # Connect to server
            if not self.connection.connect():
                self.console.print(f"[bold red]Failed to connect to {self.config.host}:{self.config.port}[/bold red]")
                return
            
            # Send initial user command
            self.connection.send_message(f"CMD_USER|{self.config.username}")
            
            # Start network thread
            self._start_network_thread()
            
            # Start UI loop
            self._run_ui_loop()
            
        except KeyboardInterrupt:
            self.logger.info("Client interrupted by user")
        except Exception as e:
            self.logger.error(f"Client error: {e}")
            if self._on_error:
                self._on_error(str(e))
        finally:
            self.shutdown()
    
    def shutdown(self) -> None:
        """Shutdown the chat client gracefully."""
        self.logger.info("Shutting down chat client")
        self.is_running = False
        
        # Shutdown performance components
        try:
            self.update_scheduler.shutdown(timeout=2.0)
            self.ui_optimizer.shutdown()
        except Exception as e:
            self.logger.error(f"Error shutting down performance components: {e}")
        
        # Stop network thread
        if self._network_thread and self._network_thread.is_alive():
            self._network_thread.join(timeout=2.0)
        
        # Close connection
        self.connection.close()
        
        self.console.print("[bold blue]You have been disconnected. Goodbye![/bold blue]")
    
    def _start_network_thread(self) -> None:
        """Start the network message handling thread."""
        self.is_running = True
        self._network_thread = threading.Thread(target=self._network_loop, daemon=True)
        self._network_thread.start()
    
    def _network_loop(self) -> None:
        """Network message processing loop."""
        while self.is_running:
            try:
                messages = self.connection.receive_messages()
                if messages:
                    self.message_handler.handle_raw_messages(messages)
                    self._mark_ui_dirty()
                
                time.sleep(0.01)  # Small delay to prevent busy waiting
                
            except Exception as e:
                if self.is_running:
                    self.logger.error(f"Network loop error: {e}")
                    self._on_connection_error(str(e))
                break
    
    def _run_ui_loop(self) -> None:
        """Run the main UI loop."""
        with Live(self.layout_manager.get_layout(), 
                 screen=True, 
                 redirect_stderr=False, 
                 refresh_per_second=self.config.ui_refresh_rate) as live:
            
            while self.is_running:
                # Handle input
                input_result = self.input_handler.handle_input(self.client_state)
                if input_result:
                    self._apply_state_changes(input_result.state_changes)
                    self.input_handler.process_input_result(input_result)
                
                # Update UI if needed
                if self._ui_dirty:
                    self._update_ui()
                    self._ui_dirty = False
                
                # Small sleep to prevent busy waiting
                time.sleep(1.0 / self.config.ui_refresh_rate)
    
    def _update_ui(self) -> None:
        """Update the UI with current state using performance optimization."""
        with self._lock:
            chat_history = self.display_manager.get_chat_history()
            
            # Schedule UI updates through the optimizer
            self.update_scheduler.schedule_ui_update(
                "chat_history",
                self.ui_optimizer.add_chat_message,
                chat_history[-1] if chat_history else "",
                "system",
                None
            )
            
            self.update_scheduler.schedule_ui_update(
                "user_list",
                self.ui_optimizer.update_user_list,
                list(self.user_list.keys())
            )
            
            self.update_scheduler.schedule_ui_update(
                "status",
                self.ui_optimizer.update_status,
                f"Connected to {self.client_state.server_host}:{self.client_state.server_port} as {self.client_state.username}"
            )
            
            # Fallback to original method for now
            self.layout_manager.update_all_panels(
                chat_history=chat_history,
                user_list=self.user_list,
                client_state=self.client_state,
                show_cursor=True
            )
    
    def _mark_ui_dirty(self) -> None:
        """Mark the UI as needing an update."""
        self._ui_dirty = True
    
    def _apply_state_changes(self, state_changes: Optional[Dict[str, Any]]) -> None:
        """Apply state changes to the client state."""
        if not state_changes:
            return
        
        for key, value in state_changes.items():
            if hasattr(self.client_state, key):
                setattr(self.client_state, key, value)
        
        self._mark_ui_dirty()
    
    # Connection event handlers
    def _on_connection_established(self) -> None:
        """Handle connection establishment."""
        self.client_state.connection_status = ConnectionStatus.CONNECTED
        self.client_state.server_host = self.config.host
        self.client_state.server_port = self.config.port
        
        self.display_manager.add_system_message(
            f"Successfully connected to {self.config.host}:{self.config.port}",
            "green",
            self.client_state
        )
        
        if self._on_connected:
            self._on_connected()
        
        self._mark_ui_dirty()
    
    def _on_connection_lost(self) -> None:
        """Handle connection loss."""
        self.client_state.connection_status = ConnectionStatus.DISCONNECTED
        
        if self.is_running:
            self.display_manager.add_system_message(
                "Connection to server lost.",
                "bold red",
                self.client_state
            )
            self.is_running = False
        
        if self._on_disconnected:
            self._on_disconnected()
        
        self._mark_ui_dirty()
    
    def _on_connection_error(self, error: str) -> None:
        """Handle connection errors."""
        self.client_state.connection_status = ConnectionStatus.ERROR
        
        self.display_manager.add_system_message(
            f"Connection error: {error}",
            "bold red",
            self.client_state
        )
        
        if self._on_error:
            self._on_error(error)
        
        self._mark_ui_dirty()
    
    # Message event handlers
    def _on_chat_message(self, message: str) -> None:
        """Handle incoming chat messages."""
        self.display_manager.add_chat_message(message, self.client_state)
        self._mark_ui_dirty()
    
    def _on_server_message(self, message: str) -> None:
        """Handle server messages."""
        self.display_manager.add_server_message(message, self.client_state)
        self._mark_ui_dirty()
    
    def _on_user_list_update(self, user_dict: Dict[str, str]) -> None:
        """Handle user list updates."""
        with self._lock:
            self.user_list = user_dict.copy()
        self._mark_ui_dirty()
    
    def _on_message_error(self, error: str) -> None:
        """Handle message processing errors."""
        self.logger.warning(f"Message error: {error}")
        self.display_manager.add_system_message(
            f"Message error: {error}",
            "yellow",
            self.client_state
        )
        self._mark_ui_dirty()
    
    # Input event handlers
    def _on_send_message(self, result: InputResult) -> None:
        """Handle sending chat messages."""
        if result.data:
            try:
                # Send to server
                full_message = f"MSG|{self.client_state.username}: {result.data}"
                self.connection.send_message(full_message)
                
                # Add to local display
                self.display_manager.add_user_message(
                    self.client_state.username,
                    result.data,
                    is_own_message=True,
                    client_state=self.client_state
                )
                
                self._mark_ui_dirty()
                
            except Exception as e:
                self.display_manager.add_system_message(
                    f"Failed to send message: {e}",
                    "red",
                    self.client_state
                )
                self._mark_ui_dirty()
    
    def _on_send_command(self, result: InputResult) -> None:
        """Handle sending commands."""
        if result.command == "nick" and result.args:
            try:
                # Validate nickname
                is_valid, error = self.input_handler.validate_nickname(result.args)
                if not is_valid:
                    self.display_manager.add_system_message(
                        f"Invalid nickname: {error}",
                        "red",
                        self.client_state
                    )
                    self._mark_ui_dirty()
                    return
                
                # Update local state optimistically
                old_username = self.client_state.username
                self.client_state.username = result.args
                
                # Send to server
                self.connection.send_message(f"CMD_USER|{result.args}")
                
                # Add confirmation message
                self.display_manager.add_system_message(
                    f"Username changed from {old_username} to {result.args}",
                    "green",
                    self.client_state
                )
                
                self._mark_ui_dirty()
                
            except Exception as e:
                self.display_manager.add_system_message(
                    f"Failed to change nickname: {e}",
                    "red",
                    self.client_state
                )
                self._mark_ui_dirty()
    
    def _on_quit_requested(self, result: InputResult) -> None:
        """Handle quit requests."""
        self.is_running = False
    
    def _on_switch_panel(self, result: InputResult) -> None:
        """Handle panel switching."""
        self._mark_ui_dirty()
    
    def _on_scroll_up(self, result: InputResult) -> None:
        """Handle scrolling up."""
        if self.client_state.active_panel == "chat":
            self.display_manager.scroll_up(self.client_state)
        self._mark_ui_dirty()
    
    def _on_scroll_down(self, result: InputResult) -> None:
        """Handle scrolling down."""
        if self.client_state.active_panel == "chat":
            self.display_manager.scroll_down(self.client_state)
        self._mark_ui_dirty()
    
    def _on_update_buffer(self, result: InputResult) -> None:
        """Handle input buffer updates."""
        self._mark_ui_dirty()
    
    # Public methods
    def get_connection_status(self) -> ConnectionStatus:
        """Get the current connection status."""
        return self.client_state.connection_status
    
    def get_user_list(self) -> Dict[str, str]:
        """Get the current user list."""
        with self._lock:
            return self.user_list.copy()
    
    def get_client_info(self) -> Dict[str, Any]:
        """Get client information."""
        return {
            "username": self.client_state.username,
            "connection_status": self.client_state.connection_status.value,
            "server_host": self.client_state.server_host,
            "server_port": self.client_state.server_port,
            "active_panel": self.client_state.active_panel,
            "is_running": self.is_running,
            "user_count": len(self.user_list),
            "message_count": self.display_manager.get_stats().total_messages
        }
    
    def send_message(self, message: str) -> bool:
        """
        Send a message programmatically.
        
        Args:
            message: The message to send.
            
        Returns:
            True if message was sent successfully.
        """
        try:
            full_message = f"MSG|{self.client_state.username}: {message}"
            self.connection.send_message(full_message)
            
            self.display_manager.add_user_message(
                self.client_state.username,
                message,
                is_own_message=True,
                client_state=self.client_state
            )
            
            self._mark_ui_dirty()
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            return False
    
    def change_username(self, new_username: str) -> bool:
        """
        Change the username programmatically.
        
        Args:
            new_username: The new username.
            
        Returns:
            True if username was changed successfully.
        """
        try:
            # Validate nickname
            is_valid, error = self.input_handler.validate_nickname(new_username)
            if not is_valid:
                self.logger.error(f"Invalid nickname: {error}")
                return False
            
            # Update state and send to server
            old_username = self.client_state.username
            self.client_state.username = new_username
            self.connection.send_message(f"CMD_USER|{new_username}")
            
            self.display_manager.add_system_message(
                f"Username changed from {old_username} to {new_username}",
                "green",
                self.client_state
            )
            
            self._mark_ui_dirty()
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to change username: {e}")
            return False
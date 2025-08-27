"""
Layout Manager

Manages Rich layout components and panel organization for the chat client.
"""

from typing import Dict, Any, Optional
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich.console import Group

from chat_app.shared.models import ClientState
from chat_app.shared.constants import DEFAULT_PANEL_HEIGHT_OFFSET


class LayoutManager:
    """
    Manages the Rich layout structure for the chat client.
    
    Handles the creation and updating of layout panels including
    header, chat panel, user panel, and footer.
    """
    
    def __init__(self, console_height: int = 24) -> None:
        """
        Initialize the layout manager.
        
        Args:
            console_height: Height of the console for layout calculations.
        """
        self.console_height = console_height
        self.layout = self._create_layout()
        self._panel_cache: Dict[str, Panel] = {}
    
    def _create_layout(self) -> Layout:
        """
        Create the initial UI layout structure.
        
        Returns:
            Configured Rich Layout object.
        """
        layout = Layout(name="root")
        layout.split(
            Layout(name="header", size=3),
            Layout(ratio=1, name="main"),
            Layout(size=3, name="footer"),
        )
        layout["main"].split_row(
            Layout(name="chat_panel"), 
            Layout(name="user_panel", size=40)
        )
        
        # Store layout before updating header
        temp_layout = self.layout if hasattr(self, 'layout') else None
        self.layout = layout
        
        # Set initial header
        self._update_header()
        
        return layout
    
    def _update_header(self) -> None:
        """Update the header panel with application information."""
        header_text = Text(
            "Python Group Chat | Commands: /nick <name>, /quit | Press TAB to switch panels",
            justify="center",
        )
        header_panel = Panel(header_text, border_style="blue")
        self.layout["header"].update(header_panel)
    
    def update_chat_panel(self, 
                         chat_history: list[Text], 
                         client_state: ClientState) -> None:
        """
        Update the chat panel with current chat history and state.
        
        Args:
            chat_history: List of chat message Text objects.
            client_state: Current client state.
        """
        panel_height = self.console_height - DEFAULT_PANEL_HEIGHT_OFFSET
        
        # Calculate visible history based on scroll state
        if client_state.scroll_offset > 0:
            end_index = len(chat_history) - client_state.scroll_offset
            start_index = max(0, end_index - panel_height)
            visible_history = chat_history[start_index:end_index]
        else:
            # Show most recent messages
            visible_history = chat_history[-panel_height:]
        
        # Create chat content
        chat_group = Group(*visible_history) if visible_history else Group()
        
        # Build title with status indicators
        title = f"Chatting as [cyan]{client_state.username}[/cyan]"
        
        # Add new message notification if scrolled up
        if not client_state.is_scrolled_to_bottom and client_state.unseen_messages_count > 0:
            title += f" [yellow]({client_state.unseen_messages_count} New Messages)[/yellow]"
        elif client_state.scroll_offset > 0:
            title += f" [yellow](scrolled up {client_state.scroll_offset} lines)[/yellow]"
        
        # Set border style based on active panel
        border_style = "green" if client_state.active_panel == "chat" else "dim"
        
        chat_panel = Panel(
            chat_group,
            title=title,
            border_style=border_style,
            expand=True,
        )
        
        self.layout["chat_panel"].update(chat_panel)
    
    def update_user_panel(self, 
                         user_list: Dict[str, str], 
                         client_state: ClientState) -> None:
        """
        Update the user panel with current user list.
        
        Args:
            user_list: Dictionary mapping usernames to addresses.
            client_state: Current client state.
        """
        panel_height = self.console_height - DEFAULT_PANEL_HEIGHT_OFFSET
        user_items = sorted(user_list.items())
        
        # Handle scrolling for user panel
        if client_state.user_panel_scroll_offset > 0:
            end_index = len(user_items) - client_state.user_panel_scroll_offset
            start_index = max(0, end_index - panel_height)
            visible_users = user_items[start_index:end_index]
        else:
            visible_users = user_items[-panel_height:]
        
        # Create user text objects
        user_texts = []
        for username, address in visible_users:
            if username == client_state.username:
                # Highlight current user
                user_texts.append(Text(f"-> {username}", style="bold bright_blue"))
            else:
                user_texts.append(Text(username))
        
        # Create user content
        user_group = Group(*user_texts) if user_texts else Group()
        
        # Build title
        title = "Users"
        if client_state.user_panel_scroll_offset > 0:
            title += f" [yellow](scrolled)[/yellow]"
        
        # Set border style based on active panel
        border_style = "green" if client_state.active_panel == "users" else "dim"
        
        user_panel = Panel(
            user_group,
            title=title,
            border_style=border_style,
            expand=True,
        )
        
        self.layout["user_panel"].update(user_panel)
    
    def update_input_panel(self, input_buffer: str, show_cursor: bool = True) -> None:
        """
        Update the input panel with current input buffer.
        
        Args:
            input_buffer: Current input text.
            show_cursor: Whether to show the cursor.
        """
        prompt = Text("Your message: ", style="bold")
        prompt.append(input_buffer, style="bright_blue")
        
        if show_cursor:
            prompt.append("_", style="blink bold")
        
        input_panel = Panel(prompt, border_style="red")
        self.layout["footer"].update(input_panel)
    
    def update_all_panels(self, 
                         chat_history: list[Text],
                         user_list: Dict[str, str],
                         client_state: ClientState,
                         show_cursor: bool = True) -> None:
        """
        Update all panels with current data.
        
        Args:
            chat_history: List of chat message Text objects.
            user_list: Dictionary mapping usernames to addresses.
            client_state: Current client state.
            show_cursor: Whether to show the cursor in input panel.
        """
        self.update_chat_panel(chat_history, client_state)
        self.update_user_panel(user_list, client_state)
        self.update_input_panel(client_state.input_buffer, show_cursor)
    
    def get_layout(self) -> Layout:
        """
        Get the current layout object.
        
        Returns:
            The Rich Layout object.
        """
        return self.layout
    
    def set_console_height(self, height: int) -> None:
        """
        Update the console height for layout calculations.
        
        Args:
            height: New console height.
        """
        self.console_height = height
    
    def clear_cache(self) -> None:
        """Clear the panel cache."""
        self._panel_cache.clear()
    
    def get_panel_info(self) -> Dict[str, Any]:
        """
        Get information about current panels.
        
        Returns:
            Dictionary with panel information.
        """
        return {
            "console_height": self.console_height,
            "panel_height": self.console_height - DEFAULT_PANEL_HEIGHT_OFFSET,
            "layout_structure": {
                "header": {"size": 3},
                "main": {"ratio": 1},
                "footer": {"size": 3},
                "chat_panel": {"expandable": True},
                "user_panel": {"size": 40}
            }
        }
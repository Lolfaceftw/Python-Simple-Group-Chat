# client.py

import socket
import sys
import threading
import time
from typing import Dict, List

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

# Platform-specific imports for non-blocking keyboard input
if sys.platform == "win32":
    import msvcrt
else:
    # For Linux/macOS, this would require termios and tty, which is more complex.
    # For now, we'll add a placeholder.
    pass

console = Console()

class ChatClient:
    """
    A TCP chat client with a rich, interactive command-line interface.
    """

    def __init__(self, host: str, port: int, username: str) -> None:
        """
        Initializes the ChatClient.
        """
        self.host: str = host
        self.port: int = port
        self.username: str = username
        self.client_socket: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.is_running: bool = False
        self.chat_history: List[Text] = []
        self._lock: threading.Lock = threading.Lock()
        
        # UI State
        self.input_buffer: str = ""
        self.scroll_offset: int = 0
        self.ui_dirty: bool = True # Flag to trigger UI updates
        
        # User list state
        self.user_list: Dict[str, str] = {}
        self.user_panel_scroll_offset: int = 0
        self.active_panel: str = "chat" # 'chat' or 'users'

        self.network_buffer: bytes = b""
        self.layout: Layout = self._create_layout()

    def _create_layout(self) -> Layout:
        """Creates the initial UI layout."""
        layout = Layout(name="root")
        layout.split(
            Layout(name="header", size=3),
            Layout(ratio=1, name="main"),
            Layout(size=3, name="footer"),
        )
        layout["main"].split_row(Layout(name="chat_panel"), Layout(name="user_panel", size=40))
        layout["header"].update(
            Panel(
                Text(
                    "Python Group Chat | Commands: /nick <name>, /quit | Press TAB to switch panels",
                    justify="center",
                ),
                border_style="blue",
            )
        )
        # Panels will be updated in the main loop
        return layout

    def _get_chat_panel(self) -> Panel:
        """Creates the chat history panel, respecting the scroll offset."""
        with self._lock:
            # If scrolled, slice from the end of the list based on the offset.
            if self.scroll_offset > 0:
                end_index = len(self.chat_history) - self.scroll_offset
                # Define a fixed window size for scrolled view
                panel_height = console.height - 8
                start_index = max(0, end_index - panel_height)
                visible_history = self.chat_history[start_index:end_index]
            # If at the bottom, just show the most recent messages.
            # Slicing with a negative index is a robust way to get the last N items.
            else:
                # Display the last N messages, where N is the available space.
                panel_height = console.height - 8
                visible_history = self.chat_history[-panel_height:]

            chat_group = Group(*visible_history)

        # Add a scroll indicator if not at the bottom
        is_scrolled = self.scroll_offset > 0
        title = f"Chatting as [cyan]{self.username}[/cyan]"
        if is_scrolled:
            title += f" [yellow](scrolled up {self.scroll_offset} lines)[/yellow]"

        border_style = "green" if self.active_panel == "chat" else "dim"

        return Panel(
            chat_group,
            title=title,
            border_style=border_style,
            expand=True,
        )

    def _get_users_panel(self) -> Panel:
        """Creates the user list panel."""
        with self._lock:
            user_list = sorted(self.user_list.items())

        # Handle scrolling for the user panel
        panel_height = console.height - 8
        if self.user_panel_scroll_offset > 0:
            end_index = len(user_list) - self.user_panel_scroll_offset
            start_index = max(0, end_index - panel_height)
            visible_users = user_list[start_index:end_index]
        else:
            visible_users = user_list[-panel_height:]

        user_texts = []
        for username, address in visible_users:
            # Add a marker for the current user
            if username == self.username:
                user_texts.append(Text(f"-> {username}", style="bold bright_blue"))
            else:
                user_texts.append(Text(username))
        
        border_style = "green" if self.active_panel == "users" else "dim"
        title = "Users"
        if self.user_panel_scroll_offset > 0:
            title += f" [yellow](scrolled)[/yellow]"

        return Panel(
            Group(*user_texts),
            title=title,
            border_style=border_style,
            expand=True,
        )

    def _get_input_panel(self) -> Panel:
        """Creates the message input panel."""
        prompt = Text("Your message: ", style="bold")
        prompt.append(self.input_buffer, style="bright_blue")
        prompt.append("_", style="blink bold") # Cursor
        return Panel(prompt, border_style="red")

    def _update_layout(self) -> None:
        """Updates the layout with the latest chat and input data."""
        self.layout["chat_panel"].update(self._get_chat_panel())
        self.layout["user_panel"].update(self._get_users_panel())
        self.layout["footer"].update(self._get_input_panel())

    def _add_message(self, message: Text) -> None:
        """Adds a message to the chat history in a thread-safe manner."""
        with self._lock:
            self.chat_history.append(message)
            # Always jump to the bottom when a new message is added
            self.scroll_offset = 0
            self.ui_dirty = True # Signal that the UI needs to be updated

            # Optional: Trim history to prevent infinite growth
            if len(self.chat_history) > 2000:
                self.chat_history.pop(0)

    def _receive_messages(self) -> None:
        """
        Listens for incoming messages and processes them from a buffer.
        """
        while self.is_running:
            try:
                # Receive data and append it to the buffer
                data = self.client_socket.recv(4096)
                if not data:
                    self.is_running = False
                    break
                self.network_buffer += data

                # Process all complete messages (newline-terminated) in the buffer
                while b'\n' in self.network_buffer:
                    message, self.network_buffer = self.network_buffer.split(b'\n', 1)
                    message_str = message.decode('utf-8').strip()
                    if not message_str:
                        continue

                    parts = message_str.split('|', 1)
                    msg_type = parts[0]
                    payload = parts[1] if len(parts) > 1 else ""
                    
                    if msg_type == "MSG":
                        self._add_message(Text(payload, "cyan"))
                    elif msg_type == "SRV":
                        if "Username changed to" in payload:
                            new_name = payload.split(" ")[-1]
                            self.username = new_name
                        self._add_message(Text(f"=> {payload}", "yellow italic"))
                    elif msg_type == "ULIST":
                        with self._lock:
                            self.user_list.clear()
                            if not payload:
                                continue
                            user_entries = payload.split(',')
                            for entry in user_entries:
                                # Format is "username(address)"
                                if '(' in entry and entry.endswith(')'):
                                    username, address = entry.rsplit('(', 1)
                                    self.user_list[username] = address[:-1] # Remove trailing ')'
                        self.ui_dirty = True

            except (ConnectionResetError, OSError):
                if self.is_running:
                    self._add_message(Text("Connection to server lost.", "bold red"))
                self.is_running = False
                break
            except UnicodeDecodeError:
                # Handle cases where a partial multi-byte character is received
                # The loop will continue and hopefully get the rest of the character
                pass

    def _send_message(self, message: str) -> None:
        """Sends a formatted message to the server."""
        try:
            self.client_socket.send(message.encode('utf-8'))
        except BrokenPipeError:
            pass

    def _handle_input_windows(self) -> None:
        """Handles non-blocking keyboard input on Windows."""
        if msvcrt.kbhit():
            self.ui_dirty = True
            char = msvcrt.getch()

            # TAB key to switch active panel
            if char == b'\t':
                self.active_panel = "users" if self.active_panel == "chat" else "chat"
                return

            # Special keys (like arrows)
            if char in [b'\xe0', b'\x00']:
                key_code = msvcrt.getch()
                # Up Arrow
                if key_code == b'H':
                    if self.active_panel == 'chat':
                        self.scroll_offset = min(len(self.chat_history) - 1, self.scroll_offset + 1)
                    else:
                        self.user_panel_scroll_offset = min(len(self.user_list) - 1, self.user_panel_scroll_offset + 1)
                # Down Arrow
                elif key_code == b'P':
                    if self.active_panel == 'chat':
                        self.scroll_offset = max(0, self.scroll_offset - 1)
                    else:
                        self.user_panel_scroll_offset = max(0, self.user_panel_scroll_offset - 1)
                return

            # On any other key, reset focus to chat panel and handle input
            self.active_panel = "chat"
            self.scroll_offset = 0
            self.user_panel_scroll_offset = 0

            # Enter key
            if char == b'\r':
                if self.input_buffer:
                    message_text = self.input_buffer
                    self.input_buffer = ""

                    if message_text.lower() == '/quit':
                        self.is_running = False
                        return
                    elif message_text.startswith('/nick '):
                        new_username = message_text.split(' ', 1)[1].strip()
                        if new_username:
                            self._send_message(f"CMD_USER|{new_username}")
                        else:
                            self._add_message(Text("Invalid nickname.", "red"))
                    else:
                        full_message = f"MSG|{self.username}: {message_text}"
                        self._send_message(full_message)
                        self._add_message(Text(f"{self.username}: {message_text}", "bright_blue"))
            # Backspace
            elif char == b'\x08':
                self.input_buffer = self.input_buffer[:-1]
            # Regular character
            else:
                try:
                    self.input_buffer += char.decode('utf-8')
                except UnicodeDecodeError:
                    pass

    def start(self) -> None:
        """
        Connects to the server and starts the main UI and I/O loops.
        """
        if sys.platform != "win32":
            console.print("[bold red]This UI is currently only supported on Windows.[/bold red]")
            console.print("A future version will add support for macOS and Linux.")
            return
            
        try:
            self.client_socket.connect((self.host, self.port))
            self.is_running = True
            
            self._send_message(f"CMD_USER|{self.username}")

            self._add_message(Text(f"Successfully connected to {self.host}:{self.port}", "green"))

            # Start the thread for receiving messages
            receive_thread = threading.Thread(target=self._receive_messages)
            receive_thread.daemon = True
            receive_thread.start()

            with Live(self.layout, screen=True, redirect_stderr=False, refresh_per_second=20) as live:
                while self.is_running:
                    # Handle keyboard input
                    self._handle_input_windows()
                    
                    # Only update the layout if something has changed
                    if self.ui_dirty:
                        self._update_layout()
                        self.ui_dirty = False # Reset the flag
                    
                    # Small sleep to prevent busy-waiting and save CPU
                    time.sleep(0.01)

        except ConnectionRefusedError:
            console.print(f"[bold red]Connection failed. Is the server running at {self.host}:{self.port}?[/bold red]")
        except socket.gaierror:
            console.print(f"[bold red]Hostname could not be resolved. Check the IP address.[/bold red]")
        finally:
            self.is_running = False
            self.client_socket.close()
            # Ensure the live display is stopped before printing final messages
            console.print("[bold blue]You have been disconnected. Goodbye![/bold blue]")


if __name__ == "__main__":
    console.print(Panel("[bold cyan]Welcome to the Python Chat Client![/bold cyan]", border_style="cyan"))
    try:
        server_ip = Prompt.ask("[cyan]Enter Server IP[/cyan]", default="127.0.0.1")
        server_port_str = Prompt.ask("[cyan]Enter Server Port[/cyan]", default="8080")
        username = Prompt.ask("[cyan]Enter your Username[/cyan]", default="Guest")

        server_port = int(server_port_str)

        client = ChatClient(server_ip, server_port, username)
        client.start()

    except ValueError:
        console.print("[bold red]Invalid port number. Please enter an integer.[/bold red]")
    except (KeyboardInterrupt, EOFError):
        console.print("\n[bold blue]Client startup cancelled.[/bold blue]")
    except Exception as e:
        console.print(f"[bold red]An error occurred during startup: {e}[/bold red]")

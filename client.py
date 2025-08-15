# client.py

import socket
import sys
import threading
import time
from typing import List

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
        self.layout: Layout = self._create_layout()

    def _create_layout(self) -> Layout:
        """Creates the initial UI layout."""
        layout = Layout(name="root")
        layout.split(
            Layout(name="header", size=3),
            Layout(ratio=1, name="main"),
            Layout(size=3, name="footer"),
        )
        layout["header"].update(
            Panel(
                Text(
                    "Python Group Chat | Commands: /nick <name>, /quit",
                    justify="center",
                ),
                border_style="blue",
            )
        )
        layout["main"].update(self._get_chat_panel())
        layout["footer"].update(self._get_input_panel())
        return layout

    def _get_chat_panel(self) -> Panel:
        """Creates the chat history panel."""
        with self._lock:
            # The visible chat history
            chat_group = Group(*self.chat_history)
        return Panel(
            chat_group,
            title=f"Chatting as [cyan]{self.username}[/cyan]",
            border_style="green",
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
        self.layout["main"].update(self._get_chat_panel())
        self.layout["footer"].update(self._get_input_panel())

    def _add_message(self, message: Text) -> None:
        """Adds a message to the chat history in a thread-safe manner."""
        with self._lock:
            self.chat_history.append(message)
            # Optional: Trim history to prevent infinite growth
            if len(self.chat_history) > 1000:
                self.chat_history.pop(0)

    def _receive_messages(self) -> None:
        """
        Listens for incoming messages from the server.
        This method runs in a separate thread.
        """
        while self.is_running:
            try:
                message = self.client_socket.recv(4096).decode('utf-8')
                if not message:
                    self.is_running = False
                    break

                parts = message.split('|', 1)
                msg_type = parts[0]
                payload = parts[1] if len(parts) > 1 else ""
                
                if msg_type == "MSG":
                    self._add_message(Text(payload, "cyan"))
                elif msg_type == "SRV":
                    # Check for username change confirmation
                    if "Username changed to" in payload:
                        new_name = payload.split(" ")[-1]
                        self.username = new_name
                    self._add_message(Text(f"=> {payload}", "yellow italic"))
                
            except (ConnectionResetError, OSError):
                if self.is_running:
                    self._add_message(Text("Connection to server lost.", "bold red"))
                self.is_running = False
                break

    def _send_message(self, message: str) -> None:
        """Sends a formatted message to the server."""
        try:
            self.client_socket.send(message.encode('utf-8'))
        except BrokenPipeError:
            pass

    def _handle_input_windows(self) -> None:
        """Handles non-blocking keyboard input on Windows."""
        if msvcrt.kbhit():
            char = msvcrt.getch()
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
                        # Add the message to our own history for local display
                        self._add_message(Text(f"{self.username}: {message_text}", "bright_blue"))
            # Backspace
            elif char == b'\x08':
                self.input_buffer = self.input_buffer[:-1]
            # Regular character
            else:
                try:
                    self.input_buffer += char.decode('utf-8')
                except UnicodeDecodeError:
                    pass # Ignore non-UTF-8 characters

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
                    
                    # Update and refresh the layout
                    self._update_layout()
                    
                    # Small sleep to prevent busy-waiting and save CPU
                    time.sleep(0.05)

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

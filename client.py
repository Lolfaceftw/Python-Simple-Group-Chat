# client.py

import socket
import threading
from typing import List

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

console = Console()

class ChatClient:
    """
    A TCP chat client with a rich, interactive command-line interface.

    Connects to the chat server and allows the user to send and receive
    messages in real-time within a structured layout.
    """

    def __init__(self, host: str, port: int, username: str) -> None:
        """
        Initializes the ChatClient.

        Args:
            host (str): The IP address of the server to connect to.
            port (int): The port number of the server.
            username (str): The user's chosen display name.
        """
        self.host: str = host
        self.port: int = port
        self.username: str = username
        self.client_socket: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.is_running: bool = False
        self.chat_history: List[Text] = []
        self.layout: Layout = self._make_layout()

    def _make_layout(self) -> Layout:
        """Creates the rich layout for the chat UI."""
        layout = Layout()
        layout.split(
            Layout(name="header"),
            Layout(ratio=1, name="main"),
            Layout(size=3, name="footer")
        )
        layout["header"].update(Panel(f"[b]Chatting as [cyan]{self.username}[/cyan][/b]", title="ECE 168 Chat", border_style="green"))
        layout["main"].update(Panel(self._get_chat_renderable(), title="Conversation", border_style="blue"))
        layout["footer"].update(Panel("[dim]Enter message...[/dim]", border_style="red"))
        return layout

    def _get_chat_renderable(self) -> Text:
        """Creates a renderable Text object from the chat history."""
        return Text("\n").join(self.chat_history)

    def _add_message_to_history(self, message: Text) -> None:
        """
        Adds a new message to the chat history and updates the display.

        Args:
            message (Text): The Rich Text object to be added.
        """
        self.chat_history.append(message)
        self.layout["main"].update(Panel(self._get_chat_renderable(), title="Conversation", border_style="blue"))

    def _receive_messages(self) -> None:
        """
        Listens for incoming messages from the server and updates the UI.

        This method runs in a separate thread to handle receiving messages
        asynchronously from user input.
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
                    self._add_message_to_history(Text(payload, "cyan"))
                elif msg_type == "SRV":
                    self._add_message_to_history(Text(f"=> {payload}", "yellow italic"))

            except (ConnectionResetError, OSError):
                if self.is_running:
                    self._add_message_to_history(Text("Connection to server lost.", "bold red"))
                self.is_running = False
                break

    def _send_message(self, message: str) -> None:
        """
        Sends a formatted message to the server.

        Args:
            message (str): The raw message string to send.
        """
        try:
            self.client_socket.send(message.encode('utf-8'))
        except BrokenPipeError:
            pass 

    def start(self) -> None:
        """
        Connects to the server and starts the send/receive loops within a live UI.
        """
        try:
            self.client_socket.connect((self.host, self.port))
            self.is_running = True
            
            self._send_message(f"CMD_USER|{self.username}")

            receive_thread = threading.Thread(target=self._receive_messages)
            receive_thread.daemon = True
            receive_thread.start()
            
            # Add initial help messages
            self._add_message_to_history(Text(f"Successfully connected to {self.host}:{self.port}", "green"))
            self._add_message_to_history(Text("Type '/nick <new_name>' to change your username or '/quit' to exit.", "dim"))

            with Live(self.layout, screen=True, redirect_stderr=False, refresh_per_second=15) as live:
                while self.is_running:
                    try:
                        self.layout["footer"].update(Panel("[b]Your message: [/b]", border_style="red"))
                        live.refresh()
                        
                        message_text = console.input()

                        self.layout["footer"].update(Panel("[dim]Enter message...[/dim]", border_style="red"))
                        live.refresh()
                        
                        if not self.is_running:
                            break

                        if message_text.lower() == '/quit':
                            break
                        elif message_text.startswith('/nick '):
                            new_username = message_text.split(' ', 1)[1].strip()
                            if new_username:
                                self.username = new_username
                                self._send_message(f"CMD_USER|{self.username}")
                                self.layout["header"].update(Panel(f"[b]Chatting as [cyan]{self.username}[/cyan][/b]", title="ECE 168 Chat", border_style="green"))
                                self._add_message_to_history(Text(f"Username changed to {self.username}", "green"))
                            else:
                                self._add_message_to_history(Text("Invalid nickname.", "red"))
                        elif message_text:
                            full_message = f"MSG|{self.username}: {message_text}"
                            self._send_message(full_message)
                            # Display user's own message immediately
                            self._add_message_to_history(Text(f"{self.username}: {message_text}", "bright_blue"))

                    except (KeyboardInterrupt, EOFError):
                        break

        except ConnectionRefusedError:
            console.print(f"[bold red]Connection failed. Is the server running at {self.host}:{self.port}?[/bold red]")
        except socket.gaierror:
            console.print(f"[bold red]Hostname could not be resolved. Check the IP address.[/bold red]")
        finally:
            self.is_running = False
            self.client_socket.close()
            console.clear()
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
    except Exception as e:
        console.print(f"[bold red]An error occurred during startup: {e}[/bold red]")
# client.py

import socket
import threading
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

# Initialize a Rich console for a beautiful UI
console = Console()

class ChatClient:
    """
    A TCP chat client with a rich command-line interface.

    Connects to the chat server and allows the user to send and receive
    messages in real-time.
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

    def _receive_messages(self) -> None:
        """
        Listens for incoming messages from the server and prints them.

        This method runs in a separate thread to handle receiving messages
        asynchronously from user input.
        """
        while self.is_running:
            try:
                message = self.client_socket.recv(4096).decode('utf-8')
                if not message:
                    # Server closed the connection
                    console.print("\n[bold red]Connection to server lost.[/bold red]")
                    self.is_running = False
                    break

                parts = message.split('|', 1)
                msg_type = parts[0]
                payload = parts[1] if len(parts) > 1 else ""

                if msg_type == "MSG":
                    console.print(f"[cyan]{payload}[/cyan]")
                elif msg_type == "SRV":
                    console.print(f"[yellow i]=> {payload}[/yellow i]")

            except (ConnectionResetError, OSError):
                if self.is_running:
                    console.print("\n[bold red]An error occurred. Disconnected from the server.[/bold red]")
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
            # This can happen if the server disconnects while we are trying to send
            pass # The receive thread will handle the disconnect message

    def start(self) -> None:
        """
        Connects to the server and starts the send/receive loops.
        """
        try:
            self.client_socket.connect((self.host, self.port))
            self.is_running = True
            console.print(Panel(f"[bold green]Successfully connected to {self.host}:{self.port} as {self.username}[/bold green]",
                                title="Connection Status"))
            console.print("[yellow]Type your message and press Enter to send.")
            console.print("[yellow]Type [b]/nick <new_name>[/b] to change your username.")
            console.print("[yellow]Type [b]/quit[/b] to exit.[/yellow]")

            # Send initial username to the server
            self._send_message(f"CMD_USER|{self.username}")

            # Start the thread for receiving messages
            receive_thread = threading.Thread(target=self._receive_messages)
            receive_thread.daemon = True
            receive_thread.start()

            # Main loop for sending messages
            while self.is_running:
                try:
                    message_text = input()
                    if not self.is_running:
                        break # Exit if receive thread has stopped

                    if message_text.lower() == '/quit':
                        break
                    elif message_text.startswith('/nick '):
                        new_username = message_text.split(' ', 1)[1].strip()
                        if new_username:
                            self.username = new_username
                            self._send_message(f"CMD_USER|{self.username}")
                            console.print(f"[green]Your username has been changed to {self.username}[/green]")
                        else:
                            console.print("[red]Invalid nickname.[/red]")
                    elif message_text:
                        # Format as a chat message: "MSG|<username>: <text>"
                        full_message = f"MSG|{self.username}: {message_text}"
                        self._send_message(full_message)

                except (KeyboardInterrupt, EOFError):
                    break # Allow Ctrl+C and Ctrl+D to exit gracefully

        except ConnectionRefusedError:
            console.print(f"[bold red]Connection failed. Is the server running at {self.host}:{self.port}?[/bold red]")
        except socket.gaierror:
            console.print(f"[bold red]Hostname could not be resolved. Check the IP address.[/bold red]")
        except Exception as e:
            console.print(f"[bold red]An unexpected error occurred: {e}[/bold red]")
        finally:
            self.is_running = False
            self.client_socket.close()
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
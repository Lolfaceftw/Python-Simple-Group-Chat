# server.py

import socket
import threading
from typing import Dict, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

# Initialize a Rich console for beautiful server-side logging
console = Console()

class ChatServer:
    """
    A multi-threaded TCP chat server.

    Manages incoming client connections and facilitates message broadcasting
    among all connected clients.
    """

    def __init__(self, host: str, port: int) -> None:
        """
        Initializes the ChatServer.

        Args:
            host (str): The IP address the server will bind to.
            port (int): The port number the server will listen on.
        """
        self.host: str = host
        self.port: int = port
        self.server_socket: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # A dictionary to store connected clients {socket: (address, username)}
        self.clients: Dict[socket.socket, Tuple[str, str]] = {}
        # A lock to ensure thread-safe access to the clients dictionary
        self.lock: threading.Lock = threading.Lock()

    def _broadcast(self, message: str, sender_socket: socket.socket = None) -> None:
        """
        Sends a message to all connected clients except the sender.

        Args:
            message (str): The message to be broadcasted.
            sender_socket (socket.socket, optional): The socket of the client who
                                                     sent the message. If None,
                                                     sends to all clients.
        """
        with self.lock:
            for client_socket in self.clients:
                if client_socket != sender_socket:
                    try:
                        client_socket.send(message.encode('utf-8'))
                    except socket.error:
                        # If sending fails, assume the client is disconnected and handle it
                        self._remove_client(client_socket)

    def _remove_client(self, client_socket: socket.socket) -> None:
        """
        Removes a client from the active connections.

        This method is called when a client disconnects or an error occurs.

        Args:
            client_socket (socket.socket): The socket of the client to remove.
        """
        with self.lock:
            if client_socket in self.clients:
                address, username = self.clients[client_socket]
                console.log(f"[bold red]Client {username} ({address}) has disconnected.[/bold red]")
                del self.clients[client_socket]
                client_socket.close()
                # Notify remaining clients about the disconnection
                notification = f"SRV|{username} has left the chat."
                self._broadcast(notification)

    def _handle_client(self, client_socket: socket.socket, address: Tuple[str, int]) -> None:
        """
        Handles communication with a single client in a dedicated thread.

        Listens for messages, processes them, and handles client disconnection.

        Args:
            client_socket (socket.socket): The socket object for the connected client.
            address (Tuple[str, int]): The address tuple (host, port) of the client.
        """
        addr_str = f"{address[0]}:{address[1]}"
        username = f"User_{addr_str}" # Default username

        with self.lock:
            self.clients[client_socket] = (addr_str, username)

        console.log(f"[bold green]New connection from {addr_str}.[/bold green]")

        try:
            while True:
                # Receive data from the client (up to 4096 bytes)
                data = client_socket.recv(4096)
                if not data:
                    # Empty data means the client has closed the connection
                    break

                message = data.decode('utf-8')
                parts = message.split('|', 1)
                msg_type = parts[0]
                payload = parts[1] if len(parts) > 1 else ""

                if msg_type == "CMD_USER":
                    with self.lock:
                        old_username = self.clients[client_socket][1]
                        self.clients[client_socket] = (addr_str, payload)
                    notification = f"SRV|{old_username} is now known as {payload}."
                    console.log(f"[yellow]{notification}[/yellow]")
                    self._broadcast(notification)

                elif msg_type == "MSG":
                    # Broadcast chat message to other clients
                    console.log(f"[cyan]{payload}[/cyan]")
                    self._broadcast(f"MSG|{payload}", client_socket)

        except (ConnectionResetError, BrokenPipeError):
            console.log(f"[bold red]Connection lost with {username} ({addr_str}).[/bold red]")
        finally:
            # Ensure client is removed on any exit path
            self._remove_client(client_socket)

    def start(self) -> None:
        """
        Binds the server to the host and port and starts listening for connections.
        """
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            console.print(Panel(f"[bold green]Server is listening on {self.host}:{self.port}[/bold green]", title="Server Status"))
        except OSError as e:
            console.print(f"[bold red]Error: Could not bind to port {self.port}. {e}[/bold red]")
            console.print("[yellow]Hint: The port might be in use, or you may need administrative privileges.[/yellow]")
            return

        try:
            while True:
                # Accept a new connection
                client_socket, address = self.server_socket.accept()
                # Create and start a new thread to handle this client
                thread = threading.Thread(target=self._handle_client, args=(client_socket, address))
                thread.daemon = True # Allows main thread to exit even if client threads are running
                thread.start()
        except KeyboardInterrupt:
            console.log("[bold yellow]Server shutting down...[/bold yellow]")
        finally:
            # Cleanly close all sockets when the server stops
            with self.lock:
                for s in self.clients:
                    s.close()
            self.server_socket.close()
            console.log("[bold red]Server has been shut down.[/bold red]")


if __name__ == "__main__":
    try:
        port_str = Prompt.ask("[cyan]Enter the port number to run the server on[/cyan]", default="8080")
        port = int(port_str)
        if not 1024 <= port <= 65535:
            console.print("[bold red]Error: Port must be between 1024 and 65535.[/bold red]")
        else:
            chat_server = ChatServer('0.0.0.0', port) # Bind to all available interfaces
            chat_server.start()
    except ValueError:
        console.print("[bold red]Invalid port number. Please enter an integer.[/bold red]")
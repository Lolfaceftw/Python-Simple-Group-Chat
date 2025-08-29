# server.py

import socket
import sys
import threading
import time
import netifaces
from collections import deque
from typing import Deque, Dict, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

# Initialize a Rich console for beautiful server-side logging
console = Console()

# --- Service Discovery Protocol --- #
DISCOVERY_PORT = 8081
DISCOVERY_MESSAGE = b"PYTHON_CHAT_SERVER_DISCOVERY_V1"
BROADCAST_INTERVAL_S = 5
# ---------------------------------- #

VERSION = '1.2'

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
        # A deque to store the last 50 messages for new clients
        self.message_history: Deque[str] = deque(maxlen=50)
        # A lock to ensure thread-safe access to shared resources
        self.lock: threading.RLock = threading.RLock()

    def _broadcast(self, message: str, sender_socket: socket.socket = None) -> None:
        """
        Broadcast a message to all connected clients, optionally excluding the sender.
        
        If provided, sender_socket is excluded from delivery so the originator does not receive their own message.
        This operation is safe to call from multiple threads.
        Parameters:
            message (str): Message to send (already formatted).
            sender_socket (socket.socket, optional): Socket to exclude from the broadcast.
        """
        with self.lock:
            for client_socket in list(self.clients):
                if client_socket != sender_socket:
                    self._send_direct_message(client_socket, message)

    def _broadcast_user_list(self) -> None:
        """Constructs and broadcasts the current user list to all clients."""
        with self.lock:
            if not self.clients:
                return
            # Format: "user1(addr1),user2(addr2)"
            user_list_str = ",".join(
                [f"{username}({addr})" for addr, username in self.clients.values()]
            )
            message = f"ULIST|{user_list_str}"
            self._broadcast(message)

    def _send_direct_message(self, client_socket: socket.socket, message: str) -> None:
        """Sends a newline-terminated message directly to a single client."""
        try:
            client_socket.send((message + '\n').encode('utf-8'))
        except socket.error:
            self._remove_client(client_socket)

    def _remove_client(self, client_socket: socket.socket) -> None:
        """
        Remove a connected client, close its socket, and notify remaining users.
        
        Acquires the server lock, and if the given client socket is registered removes its mapping,
        closes the socket, appends a server "left" notification to the message history, broadcasts
        that notification to all remaining clients, and broadcasts the updated user list.
        
        Parameters:
            client_socket (socket.socket): The connected client socket to remove; expected to be a key in self.clients.
        """
        with self.lock:
            if client_socket in self.clients:
                address, username = self.clients[client_socket]
                console.log(f"[bold red]Client {username} ({address}) has disconnected.[/bold red]")
                del self.clients[client_socket]
                client_socket.close()
                # Notify remaining clients and log the event
                notification = f"SRV|{username} has left the chat."
                self.message_history.append(notification)
                self._broadcast(notification)
                self._broadcast_user_list()

    def _is_username_taken(self, username: str, requesting_socket: socket.socket) -> bool:
        """
        Return True if `username` is already in use by another connected client (case-insensitive).
        
        Excludes the provided `requesting_socket` from the check so a client can compare against others when attempting a rename.
        
        Returns:
            bool: True if the username is taken by a different client, False otherwise.
        """
        with self.lock:
            for client_socket, (_, existing_username) in self.clients.items():
                # Check against other clients, not the one making the request
                if client_socket != requesting_socket and existing_username.lower() == username.lower():
                    return True
            return False

    def _handle_client(self, client_socket: socket.socket, address: Tuple[str, int]) -> None:
        """
        Handle communication for a single connected client in its own thread.
        
        Accepts messages from the client (both prefixed messages like "CMD_USER|name" and "MSG|text"
        and plain-text commands), updates server state, and broadcasts events to other clients.
        
        Behavior:
        - On connect: assigns a default username "User_<ip>:<port>", sends a welcome message and recent
          message history, appends a join notification to history, broadcasts the join, and broadcasts
          the current user list.
        - Prefixed messages:
          - "CMD_USER|<name>": attempt to rename the client. Rejects if unchanged or name is already
            taken (case-insensitive). On success updates the server's client entry, broadcasts a rename
            notification, and refreshes the user list.
          - "MSG|<text>": records "MSG|<text>" to message history and broadcasts it to other clients.
        - Plain-text messages:
          - "/quit": disconnects the client (causes cleanup).
          - "/nick <name>": same validation and rename semantics as CMD_USER.
          - Any other text: treated as chat content; formatted as "<username>: <text>", recorded to
            history as "MSG|<username>: <text>" and broadcast to other clients.
        - Thread-safety: mutates shared state (clients mapping and message_history) while holding
          self.lock.
        - On socket closure or network error the client is removed and a left-chat notification is sent.
        
        Parameters:
            client_socket (socket.socket): The connected client's socket.
            address (Tuple[str, int]): The client's (ip, port) address.
        """
        addr_str = f"{address[0]}:{address[1]}"
        console.log(f"[bold green]New connection from {addr_str}.[/bold green]")
        
        with self.lock:
            username = f"User_{addr_str}"
            self.clients[client_socket] = (addr_str, username)

            self._send_direct_message(client_socket, "SRV|Welcome! Here are the recent messages:")
            for msg in self.message_history:
                self._send_direct_message(client_socket, msg)
        
        join_notification = f"SRV|{username} has joined the chat."
        with self.lock:
            self.message_history.append(join_notification)
        self._broadcast(join_notification, client_socket)
        self._broadcast_user_list() # Send initial user list

        try:
            while True:
                data = client_socket.recv(4096)
                if not data:
                    break

                message = data.decode('utf-8').strip()
                if not message:
                    continue

                # Handle both prefixed and raw messages
                if '|' in message:
                    # Handle prefixed messages (from the rich client)
                    parts = message.split('|', 1)
                    msg_type = parts[0]
                    payload = parts[1] if len(parts) > 1 else ""

                    if msg_type == "CMD_USER":
                        with self.lock:
                            _, current_username = self.clients[client_socket]
                        
                        if current_username.lower() == payload.lower():
                            self._send_direct_message(client_socket, "SRV|Did you even change your name?")
                        elif self._is_username_taken(payload, client_socket):
                            self._send_direct_message(client_socket, f"SRV|Nickname '{payload}' is already taken.")
                        else:
                            with self.lock:
                                old_username = self.clients[client_socket][1]
                                self.clients[client_socket] = (addr_str, payload)
                                username = payload # Update local username variable for logging
                            notification = f"SRV|{old_username} is now known as {username}."
                            console.log(f"[yellow]{notification}[/yellow]")
                            self._broadcast(notification)
                            self._broadcast_user_list()

                    elif msg_type == "MSG":
                        console.log(f"[cyan]{payload}[/cyan]")
                        full_message = f"MSG|{payload}"
                        with self.lock:
                            self.message_history.append(full_message)
                        self._broadcast(full_message, client_socket)
                else:
                    # Handle raw messages (from a basic client)
                    if message.lower() == '/quit':
                        console.log(f"[yellow]Client {username} ({addr_str}) issued /quit command.[/yellow]")
                        break  # Exit loop; the 'finally' block will handle cleanup

                    elif message.lower().startswith('/nick '):
                        new_username = message.split(' ', 1)[1].strip()
                        if new_username:
                            with self.lock:
                                _, current_username = self.clients[client_socket]

                            if current_username.lower() == new_username.lower():
                                self._send_direct_message(client_socket, "SRV|Did you even change your name?")
                            elif self._is_username_taken(new_username, client_socket):
                                self._send_direct_message(client_socket, f"SRV|Nickname '{new_username}' is already taken.")
                            else:
                                with self.lock:
                                    old_username = self.clients[client_socket][1]
                                    self.clients[client_socket] = (addr_str, new_username)
                                    username = new_username  # Update local username variable
                                notification = f"SRV|{old_username} is now known as {username}."
                                console.log(f"[yellow]{notification}[/yellow]")
                                self._broadcast(notification)
                                self._broadcast_user_list()
                        else:
                            self._send_direct_message(client_socket, "SRV|Invalid nickname provided.")
                    else:
                        # It's a regular message
                        with self.lock:
                            _, current_username = self.clients[client_socket]
                        
                        formatted_payload = f"{current_username}: {message}"
                        console.log(f"[cyan]{formatted_payload}[/cyan]")
                        
                        broadcast_message = f"MSG|{formatted_payload}"
                        with self.lock:
                            self.message_history.append(broadcast_message)
                        self._broadcast(broadcast_message, client_socket)

        except (ConnectionResetError, BrokenPipeError):
            console.log(f"[bold red]Connection lost with {username} ({addr_str}).[/bold red]")
        finally:
            self._remove_client(client_socket)

    def start(self) -> None:
        """
        Binds the server and starts the main loop with a timeout.
        This allows the server to listen for connections while still being
        able to gracefully shut down on a KeyboardInterrupt.
        """
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            # Set a timeout on the server socket to allow for periodic checks
            # for the KeyboardInterrupt signal.
            self.server_socket.settimeout(1.0)
            console.print(Panel(f"[bold green]Server is listening on {self.host}:{self.port}[/bold green]", title="Server Status"))

            # Start the discovery broadcast thread
            broadcast_thread = threading.Thread(target=self._broadcast_presence)
            broadcast_thread.daemon = True
            broadcast_thread.start()

        except OSError as e:
            console.print(f"[bold red]Error: Could not bind to port {self.port}. {e}[/bold red]")
            console.print("[yellow]Hint: The port might be in use, or you may need administrative privileges.[/yellow]")
            return

        try:
            while True:
                try:
                    # Accept a new connection
                    client_socket, address = self.server_socket.accept()
                    # Create and start a new thread to handle this client
                    thread = threading.Thread(target=self._handle_client, args=(client_socket, address))
                    thread.daemon = True
                    thread.start()
                except socket.timeout:
                    # The timeout allows the loop to continue and check for KeyboardInterrupt
                    continue
        except KeyboardInterrupt:
            console.log("[bold yellow]Server shutting down...[/bold yellow]")
        finally:
            # Cleanly close all sockets when the server stops
            with self.lock:
                client_sockets = list(self.clients.keys())
                console.log(f"Closing {len(client_sockets)} client connection(s)...")
                for s in client_sockets:
                    s.close()
            self.server_socket.close()
            console.log("[bold red]Server has been shut down.[/bold red]")
            # A clean exit is preferred
            sys.exit(0)

    def _broadcast_presence(self) -> None:
        """
        Periodically broadcasts a discovery message to all network interfaces.
        This is more robust than a single broadcast as it targets all subnets
        the server is connected to.
        """
        # Create a UDP socket for broadcasting
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
            # Set the socket to allow broadcasting
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            console.log(f"Starting service discovery broadcast on port {DISCOVERY_PORT}")

            while True:
                try:
                    #  Collect  broadcast targets from all IPv4 addresses on all interfaces.
                    targets = set()
                    for iface in netifaces.interfaces():
                        try:
                            for addr in netifaces.ifaddresses(iface).get(netifaces.AF_INET, []):
                                bcast = addr.get('broadcast')
                                if bcast: targets.add(bcast)
                        except Exception:
                            # Ignore ifaces that fail.
                            continue
                    
                    # Generic fallback
                    targets.update({'<broadcast>', '255.255.255.255'})
                    
                    # Send discovery
                    for bcast in targets:
                        try:
                            sock.sendto(DISCOVERY_MESSAGE, (bcast, DISCOVERY_PORT))
                        except Exception as e:
                            console.log(f"[dim]Discovery send failed for {bcast}: {e}[/dim]")
                            continue
                    time.sleep(BROADCAST_INTERVAL_S)
                except Exception as e:
                    console.log(f"[bold red]Discovery broadcast failed: {e}[/bold red]")
                    # Avoid busy-looping on persistent errors
                    time.sleep(BROADCAST_INTERVAL_S * 2)


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
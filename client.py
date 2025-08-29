# client.py

import socket
import sys
import threading
import time
import concurrent.futures
from typing import Dict, List

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text
from rich.progress import Progress
from rich.table import Table

# Platform-specific imports for non-blocking keyboard input
if sys.platform == "win32":
    import msvcrt
else:
    # For Linux/macOS, this would require termios and tty, which is more complex.
    # For now, we'll add a placeholder.
    pass

# --- Service Discovery Protocol --- #
DISCOVERY_PORT = 8081
DISCOVERY_MESSAGE = b"PYTHON_CHAT_SERVER_DISCOVERY_V1"
DISCOVERY_TIMEOUT_S = 5
# ---------------------------------- #

VERSION = "1.3"

console = Console()

def discover_servers() -> List[str]:
    """Listens for server discovery broadcasts on the network."""
    discovered_servers = set()
    with console.status("[cyan]Scanning for servers on the local network...[/cyan]", spinner="dots"):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            # Set socket options to allow multiple clients to listen on the same port.
            # SO_REUSEADDR allows binding to a port that is in a TIME_WAIT state.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # SO_REUSEPORT allows multiple sockets to be bound to the exact same
            # address and port. This is key for allowing multiple clients on the
            # same machine to discover the server simultaneously.
            # This option is not available on Windows.
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError as e:
                    # This might fail on systems that define the constant but don't fully support it.
                    console.log(f"[yellow]Could not set SO_REUSEPORT: {e}[/yellow]")


            # Bind to the discovery port to receive broadcasts
            try:
                sock.bind(("", DISCOVERY_PORT))
            except OSError as e:
                console.print(f"[bold red]Error: Could not bind to port {DISCOVERY_PORT} for discovery. {e}[/bold red]")
                console.print("[yellow]Hint: Is another client already running or is the port in use?[/yellow]")
                return []
            
            # Listen for a few seconds
            sock.settimeout(DISCOVERY_TIMEOUT_S)

            end_time = time.time() + DISCOVERY_TIMEOUT_S
            while time.time() < end_time:
                try:
                    data, addr = sock.recvfrom(1024)
                    if data == DISCOVERY_MESSAGE:
                        discovered_servers.add(addr[0])
                except socket.timeout:
                    break # No more messages
                except Exception as e:
                    console.log(f"[red]Error during discovery: {e}[/red]")
                    break
        
        server_list = sorted(list(discovered_servers))
    if server_list:
        console.print(f"[green]Found {len(server_list)} server(s): {', '.join(server_list)}[/green]")
    else:
        console.print("[yellow]No servers found on the network.[/yellow]")

    return server_list

# client.py
# client.py

# client.py

def scan_and_probe_ports(host: str) -> Dict[int, str]:
    """
    Scans a large port range at high speed and can be cancelled with Ctrl+C.
    Uses rich.progress for a real-time UI.

    Returns:
        A dictionary mapping the port number to its status ("Joinable" or "Open").
    """
    results = {}
    scan_range = range(4000, 65536)
    lock = threading.Lock()

    progress = Progress(
        "[progress.description]{task.description}",
        "[progress.percentage]{task.percentage:>3.0f}%",
        "Ports: {task.completed}/{task.total}",
        console=console
    )

    def probe_port(port: int):
        """Worker function to probe a single port."""
        status = ""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.1)
                if sock.connect_ex((host, port)) == 0:
                    status = "Open"
                    try:
                        banner = sock.recv(1024)
                        if banner:
                            if banner.strip().startswith(b'SRV|'):
                                status = "Joinable"
                            else:
                                banner_text = banner.decode('utf-8', errors='ignore')
                                if 'NICK' in banner_text:
                                    status = "Joinable"
                    except (socket.timeout, ConnectionResetError, OSError):
                        pass
        except socket.error:
            pass
        
        if status:
            with lock:
                results[port] = status
        
        progress.advance(task_id)

    try:
        with progress:
            task_id = progress.add_task(f"[cyan]Scanning {host} (Press Ctrl+C to cancel)...[/cyan]", total=len(scan_range))
            with concurrent.futures.ThreadPoolExecutor(max_workers=1024) as executor:
                for port in scan_range:
                    executor.submit(probe_port, port)
        
        sorted_results = dict(sorted(results.items()))
        
        if sorted_results:
            joinable_count = list(sorted_results.values()).count("Joinable")
            console.print(f"[green]Scan complete on {host}. Found {len(sorted_results)} open port(s), with {joinable_count} identified as joinable chat servers.[/green]")
        else:
            console.print(f"[yellow]No joinable chat servers found in the range {scan_range.start}-{scan_range.stop-1}.[/yellow]")
            
        return sorted_results

    except KeyboardInterrupt:
        # When Ctrl+C is pressed, this block is executed.
        console.print("\n[bold yellow]Scan cancelled by user.[/bold yellow]")
        # Return an empty dictionary to signify no selection was made.
        return {}

class ChatClient:
    """
    A TCP chat client with a rich, interactive command-line interface.
    """

    def __init__(self, host: str, port: int) -> None:
        """
        Initializes the ChatClient.
        """
        self.host: str = host
        self.port: int = port
        self.username: str = "Guest" # A temporary name
        self.is_rich_server: bool = False # Flag to track if the server supports ULIST
        self.client_socket: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.is_running: bool = False
        self.chat_history: List[Text] = []
        self._lock: threading.Lock = threading.Lock()
        self.initial_user_list_received = threading.Event()

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
        """Creates the user list panel based on server type."""
        border_style = "green" if self.active_panel == "users" else "dim"
        title = "Users"
        panel_content = ""

        if self.is_rich_server:
            with self._lock:
                user_list = sorted(self.user_list.items())

            panel_height = console.height - 8
            if self.user_panel_scroll_offset > 0:
                end_index = len(user_list) - self.user_panel_scroll_offset
                start_index = max(0, end_index - panel_height)
                visible_users = user_list[start_index:end_index]
            else:
                visible_users = user_list[-panel_height:]

            user_texts = []
            for username, address in visible_users:
                if username == self.username:
                    user_texts.append(Text(f"-> {username}", style="bold bright_blue"))
                else:
                    user_texts.append(Text(username))
            
            if self.user_panel_scroll_offset > 0:
                title += f" [yellow](scrolled)[/gyellow]"
            
            panel_content = Group(*user_texts)
        else:
            # Display a "Not Supported" message for basic servers
            panel_content = Text(
                "\nUser list not\nsupported by\nthis server.",
                justify="center",
                style="dim italic"
            )

        return Panel(
            panel_content,
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

# client.py
    def _receive_messages(self) -> None:
        """
        Listens for incoming messages and processes them based on server type.
        """
        while self.is_running:
            try:
                data = self.client_socket.recv(4096)
                if not data:
                    self.is_running = False
                    break

                # --- BEHAVIOR CHANGE BASED ON SERVER TYPE ---
                if self.is_rich_server:
                    self.network_buffer += data
                    # Process all complete messages (newline-terminated) in the buffer
                    while b'\n' in self.network_buffer:
                        message, self.network_buffer = self.network_buffer.split(b'\n', 1)
                        message_str = message.decode('utf-8', errors='ignore').strip()
                        if not message_str: continue

                        parts = message_str.split('|', 1)
                        msg_type = parts[0]
                        payload = parts[1] if len(parts) > 1 else ""
                        
                        if msg_type == "MSG":
                            self._add_message(Text(payload, "cyan"))
                        elif msg_type == "SRV":
                            if " is now known as " in payload:
                                try:
                                    old_name, new_name_part = payload.split(" is now known as ", 1)
                                    new_name = new_name_part.rstrip('.')
                                    with self._lock:
                                        if old_name == self.username: self.username = new_name
                                except ValueError: pass
                            self._add_message(Text(f"=> {payload}", "yellow italic"))
                        elif msg_type == "ULIST":
                            with self._lock:
                                self.user_list.clear()
                                if payload:
                                    for entry in payload.split(','):
                                        if '(' in entry and entry.endswith(')'):
                                            username, address = entry.rsplit('(', 1)
                                            self.user_list[username] = address[:-1]
                            if not self.initial_user_list_received.is_set():
                                self.initial_user_list_received.set()
                            self.ui_dirty = True
                else:
                    # --- Basic Server Logic (process raw data immediately) ---
                    # Treat each received chunk as a potential message or group of messages.
                    # This avoids buffering and waiting for a newline that may never come.
                    message_str = data.decode('utf-8', errors='ignore')
                    if message_str:
                        # Use splitlines() to handle cases where a basic server might send
                        # multiple messages at once, separated by its own newlines.
                        for line in message_str.splitlines():
                            if line.strip():
                                self._add_message(Text(line.strip(), "cyan"))

            except (ConnectionResetError, OSError):
                if self.is_running:
                    self._add_message(Text("Connection to server lost.", "bold red"))
                self.is_running = False
                break
            except UnicodeDecodeError:
                pass

    def _send_message(self, message: str) -> None:
        """Sends a formatted message to the server."""
        try:
            self.client_socket.send(( message + "\n").encode('utf-8'))
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
                    
                    # --- BEHAVIOR CHANGE BASED ON SERVER TYPE ---
                    if self.is_rich_server:
                        # --- Rich Server Logic ---
                        if message_text.startswith('/nick '):
                            new_username = message_text.split(' ', 1)[1].strip()
                            if new_username:
                                self._send_message(f"CMD_USER|{new_username}")
                                self._add_message(Text(f"Attempting to change nickname to '{new_username}'...", "yellow"))
                            else:
                                self._add_message(Text("Invalid nickname.", "red"))
                        else:
                            full_message = f"MSG|{self.username}: {message_text}"
                            self._send_message(full_message)
                            self._add_message(Text(f"{self.username}: {message_text}", "bright_blue"))
                    else:
                        # --- Basic Server Logic ---
                        if message_text.startswith('/nick '):
                            new_username = message_text.split(' ', 1)[1].strip()
                            if new_username:
                                # For basic servers, just send the raw command and update locally
                                self._send_message(message_text)
                                self.username = new_username
                                self._add_message(Text(f"Username changed to {self.username}", "green"))
                            else:
                                self._add_message(Text("Invalid nickname.", "red"))
                        else:
                            # Send the raw message and display it locally
                            self._send_message(message_text)
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

# client.py
    def start(self) -> None:
        """
        Connects, determines server type, handles username, and starts the main UI.
        """
        if sys.platform != "win32":
            console.print("[bold red]This UI is currently only supported on Windows.[/bold red]")
            return

        try:
            self.client_socket.connect((self.host, self.port))
            self.is_running = True

            # --- Instant Server Type Detection ---
            # Receive the very first packet to identify the server type instantly.
            initial_data = self.client_socket.recv(1024)
            if initial_data.strip().startswith(b'SRV|'):
                self.is_rich_server = True
            
            # Pre-load the buffer so the receive thread can process this first packet.
            self.network_buffer = initial_data
            
            # Now that the buffer is primed, start the receive thread.
            receive_thread = threading.Thread(target=self._receive_messages)
            receive_thread.daemon = True
            receive_thread.start()

            # --- Username Logic based on detected server type ---
            if self.is_rich_server:
                console.print("[green]Rich server detected (supports user lists).[/green]")
                # Wait for the user list to arrive before prompting for a name.
                with console.status("[cyan]Receiving user list...[/cyan]"):
                    if not self.initial_user_list_received.wait(timeout=5.0):
                        console.print("[bold red]Warning: Did not receive user list from server.[/bold red]")

                # Validation loop for rich servers
                while self.is_running:
                    chosen_username = Prompt.ask("[cyan]Enter your Username[/cyan]", default="Guest")
                    if not chosen_username: continue
                    is_taken = any(u.lower() == chosen_username.lower() for u in self.user_list.keys())
                    if is_taken:
                        console.print(f"[bold red]Nickname '{chosen_username}' is already in use.[/bold red]")
                    else:
                        self.username = chosen_username
                        self._send_message(f"CMD_USER|{self.username}")
                        break
            else:
                # --- MODIFIED: No nickname prompt for basic servers ---
                console.print("[yellow]Basic server detected. Joining with default name 'Guest'.[/yellow]")
                # The default username is "Guest" from __init__.
                # We must send it to satisfy the basic server's 'NICK' prompt.
                self._send_message(self.username + '\n')

            if not self.is_running:
                self.client_socket.close()
                return
            
            self._add_message(Text(f"Successfully joined as {self.username}", "green"))

            # --- Main UI Loop ---
            with Live(self.layout, screen=True, redirect_stderr=False, refresh_per_second=20) as live:
                while self.is_running:
                    self._handle_input_windows()
                    if self.ui_dirty:
                        self._update_layout()
                        self.ui_dirty = False
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



# client.py

if __name__ == "__main__":
    console.print(Panel(f"[bold cyan]Welcome to the Python Group Chat Client!\nVersion: {VERSION}[/bold cyan]", border_style="cyan"))
    try:
        # --- Step 1: Discover or Enter Server IP ---
        available_servers = discover_servers()
        manual_ip_option = "Enter IP manually..."

        if available_servers:
            # Display discovered servers in a neat table with an explanatory caption
            server_table = Table(
                title="Discovered Servers",
                show_header=True,
                header_style="bold magenta",
                caption="[dim]Servers are discovered only if they support and broadcast the discovery protocol.[/dim]"
            )
            server_table.add_column("Option", style="dim", width=8)
            server_table.add_column("IP Address")

            for i, ip in enumerate(available_servers, 1):
                server_table.add_row(str(i), ip)
            
            console.print(server_table)
            
            prompt_choices = [str(i) for i in range(1, len(available_servers) + 1)] + [manual_ip_option]
            selection = Prompt.ask("[cyan]Select a server by number or choose an option[/cyan]", choices=prompt_choices, default="1")

            if selection == manual_ip_option:
                server_ip = Prompt.ask("[cyan]Enter Server IP[/cyan]", default="127.0.0.1")
            else:
                server_ip = available_servers[int(selection) - 1]
        else:
            # Add clarity for when no servers are found
            console.print("[yellow]No servers were found advertising on the network.[/yellow]")
            console.print("[dim]This is normal for basic servers or servers on a different network.[/dim]")
            server_ip = Prompt.ask("[cyan]Please enter the Server IP manually[/cyan]", default="127.0.0.1")

        # --- Step 2: Scan, Probe, and Select Port ---
        probed_ports = scan_and_probe_ports(server_ip)
        manual_port_option = "Enter port manually..."
        
        if probed_ports:
            port_table = Table(
                title=f"Scan Results for {server_ip}",
                show_header=True,
                header_style="bold magenta",
                caption="[dim]A '[bold green]Joinable[/bold green]' server is one that was responsive and returned text upon connection.[/dim]"
            )
            port_table.add_column("Port", justify="right", style="cyan", no_wrap=True)
            port_table.add_column("Status")

            prompt_choices = []
            joinable_ports = {p: s for p, s in probed_ports.items() if s == "Joinable"}
            open_ports = {p: s for p, s in probed_ports.items() if s == "Open"}

            # List joinable ports first for convenience
            for port, status in joinable_ports.items():
                port_table.add_row(str(port), f"[bold green]{status}[/bold green]")
                prompt_choices.append(str(port))
            for port, status in open_ports.items():
                port_table.add_row(str(port), f"[yellow]{status}[/yellow]")
                prompt_choices.append(str(port))
            
            console.print(port_table)
            prompt_choices.append(manual_port_option)

            port_selection = Prompt.ask(
                "[cyan]Select a port or enter one manually[/cyan]", 
                choices=prompt_choices, 
                default=prompt_choices[0] if prompt_choices else manual_port_option
            )
            
            if port_selection == manual_port_option:
                server_port_str = Prompt.ask("[cyan]Enter Server Port[/cyan]", default="8080")
            else:
                server_port_str = port_selection
        else:
            server_port_str = Prompt.ask("[cyan]Enter Server Port[/cyan]", default="8080")

        server_port = int(server_port_str)

        # --- Step 3: Connect and Start Client ---
        client = ChatClient(server_ip, server_port)
        client.start()

    except ValueError:
        console.print("[bold red]Invalid port number. Please enter an integer.[/bold red]")
    except (KeyboardInterrupt, EOFError):
        console.print("\n[bold blue]Client startup cancelled.[/bold blue]")
    except Exception as e:
        console.print(f"[bold red]An error occurred during startup: {e}[/bold red]")    
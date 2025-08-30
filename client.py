# client.py

import socket
import sys
import threading
import time
import concurrent.futures
import netifaces
import ipaddress
import requests
import nmap
from typing import Dict, List, Tuple

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
    scan_range = range(0, 65536)
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
def get_os_from_ip(ip_address: str) -> str:
    """
    Performs an Nmap OS detection scan on a given IP address.

    Args:
        ip_address (str): The IP address to scan.

    Returns:
        str: The detected OS, or "Unknown" if detection fails.
    """
    nm = nmap.PortScanner()
    try:
        # The -O flag requires root privileges on Linux/macOS,
        # and administrator privileges on Windows.
        # The script must be run with these privileges.
        nm.scan(hosts=ip_address, arguments='-O')
        if nm.all_hosts() and 'osmatch' in nm[ip_address] and nm[ip_address]['osmatch']:
            return nm[ip_address]['osmatch'][0]['name']
        else:
            return "Unknown"
    except nmap.nmap.PortScannerError as e:
        if "requires root privileges" in str(e).lower():
            console.log("[bold red]Nmap OS detection requires root/administrator privileges. Please run the script with sudo (on Linux/macOS) or as an administrator (on Windows).[/bold red]")
        else:
            console.log(f"[bold red]Nmap error: {e}. Please make sure Nmap is installed and in your PATH.[/bold red]")
        return "Unknown"
    except Exception as e:
        # This will catch other errors, like permission denied if not run with sudo
        console.log(f"[red]An error occurred during OS detection for {ip_address}: {e}[/red]")
        return "Unknown"

def get_local_ipv4_addresses() -> List[str]:
    """
    Gets all non-loopback IPv4 addresses of the local machine using netifaces.
    These are potential IPs if running the server on the same local network.
    """
    local_ips = set()
    try:
        for iface in netifaces.interfaces():
            ifaddresses = netifaces.ifaddresses(iface)
            if netifaces.AF_INET in ifaddresses:
                for addr_info in ifaddresses[netifaces.AF_INET]:
                    ip = addr_info.get('addr')
                    # Filter out the loopback address and ensure it's not None
                    if ip and ip != '127.0.0.1':
                        local_ips.add(ip)
    except Exception as e:
        console.log(f"[yellow]Could not enumerate local IP addresses: {e}[/yellow]")
    return sorted(list(local_ips))
def get_lan_scan_target() -> str | None:
    """
    Intelligently determines the correct LAN network range (e.g., 192.168.1.0/24)
    by finding the local IP and its corresponding netmask.
    """
    try:
        # Find a primary, non-loopback IP address for the local machine
        local_ip = get_local_ipv4_addresses()[0]

        # Find the netmask associated with that IP address
        for iface in netifaces.interfaces():
            ifaddresses = netifaces.ifaddresses(iface)
            if netifaces.AF_INET in ifaddresses:
                for addr_info in ifaddresses[netifaces.AF_INET]:
                    if addr_info.get('addr') == local_ip:
                        netmask = addr_info.get('netmask')
                        # Use the ipaddress module to calculate the network range in CIDR notation
                        network = ipaddress.ip_network(f"{local_ip}/{netmask}", strict=False)
                        return str(network)
    except (IndexError, KeyError):
        # Fails if no suitable network interface is found
        return None
    return None

def get_vendor_from_mac_api(mac_address: str) -> str:
    """
    Looks up the vendor of a device from its MAC address using multiple sources.

    Args:
        mac_address (str): The MAC address to look up.

    Returns:
        str: The vendor of the device, or "Unknown" if the lookup fails.
    """
    # 1. Try scapy's local database first
    try:
        from scapy.config import conf
        vendor = conf.manufdb._get_manuf(mac_address)
        if vendor != mac_address:
            return vendor
    except Exception:
        pass

    # 2. Try macvendors.com API
    try:
        response = requests.get(f"https://api.macvendors.com/{mac_address}", timeout=2)
        if response.status_code == 200 and response.text:
            return response.text
    except requests.exceptions.RequestException:
        pass

    # 3. Try macvendorlookup.com API
    try:
        response = requests.get(f"https://www.macvendorlookup.com/api/v1/{mac_address}", timeout=2)
        if response.status_code == 200 and response.text:
            # The response is "The company is <vendor_name>"
            return response.text.replace("The company is ", "")
    except requests.exceptions.RequestException:
        pass

    return "Unknown"

# client.py
def discover_lan_hosts() -> List[Tuple[str, str, str]]:
    """
    Discovers other hosts on the local network using an ARP scan.
    Returns a list of tuples: (ip_address, device_vendor, mac_address).
    Requires scapy and admin privileges.
    """
    lan_hosts = []
    try:
        # Import scapy and its config object
        from scapy.all import ARP, Ether, srp
        from scapy.config import conf
    except ImportError:
        console.log("[yellow]Scapy is not installed. Skipping LAN host discovery.[/yellow]")
        console.log("[dim]Install it with: pip install scapy[/dim]")
        return []

    try:
        scan_target = get_lan_scan_target()
        if not scan_target:
            console.log("[yellow]Could not determine local network range. Skipping LAN host discovery.[/yellow]")
            return []

        with console.status(f"[cyan]Performing ARP scan on network: {scan_target}...[/cyan]", spinner="dots"):
            arp = ARP(pdst=scan_target)
            ether = Ether(dst="ff:ff:ff:ff:ff:ff")
            packet = ether/arp

            result = srp(packet, timeout=2, verbose=False)[0]

        # Parse results to get both IP and the MAC address vendor
        for sent, received in result:
            mac_address = received.src
            device_vendor = "Unknown"
            try:
                # This is the robust, programmatic way to perform an OUI lookup
                device_vendor = conf.manufdb._get_manuf(mac_address)
                if device_vendor == mac_address: # if scapy returns mac address, it means it's unknown
                    device_vendor = "Unknown"
            except Exception:
                # If the lookup fails for any reason, we default to "Unknown"
                pass

            if device_vendor == "Unknown":
                device_vendor = get_vendor_from_mac_api(mac_address)

            lan_hosts.append((received.psrc, device_vendor, mac_address))

    except PermissionError:
        console.log("[bold red]Permission denied for ARP scan. Please run as an administrator (or with sudo).[/bold red]")
    except Exception as e:
        console.log(f"[red]An error occurred during LAN host discovery: {e}[/red]")
        
    # Sort numerically
    return sorted(lan_hosts, key=lambda item: tuple(map(int, item[0].split('.'))))
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
                title += f" [yellow](scrolled)[/yellow]"
            
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

            # --- Non-Blocking Server Type Detection ---
            initial_data = b''
            try:
                # Set a short timeout to prevent blocking indefinitely on silent servers.
                self.client_socket.settimeout(0.5)
                initial_data = self.client_socket.recv(1024)
            except socket.timeout:
                # It's a silent server that sends no banner. Treat as basic.
                pass
            finally:
                # Always restore the socket to blocking mode for the main receive loop.
                self.client_socket.settimeout(None)

            if initial_data and initial_data.strip().startswith(b'SRV|'):
                self.is_rich_server = True
            
            # Pre-load the buffer with whatever we received (even if it's empty).
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
                self._send_message(self.username)

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

if __name__ == "__main__":
    console.print(Panel(f"[bold cyan]Welcome to the Python Group Chat Client!\nVersion: {VERSION}[/bold cyan]", border_style="cyan"))
    try:
        # --- Step 1: Discover all potential servers ---
        advertised_servers = discover_servers()
        lan_hosts_with_mac = discover_lan_hosts()
        local_interfaces = get_local_ipv4_addresses()
        manual_ip_option = "Enter IP manually..."
        
        discovered_devices = {}
        
        progress = Progress(
            "[progress.description]{task.description}",
            "[progress.percentage]{task.percentage:>3.0f}%",
            "Hosts: {task.completed}/{task.total}",
            console=console
        )

        with progress:
            task_id = progress.add_task("[cyan]Scanning for OS...[/cyan]", total=len(lan_hosts_with_mac))
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                future_to_ip = {executor.submit(get_os_from_ip, ip): (ip, vendor, mac) for ip, vendor, mac in lan_hosts_with_mac}
                for future in concurrent.futures.as_completed(future_to_ip):
                    ip, vendor, mac = future_to_ip[future]
                    try:
                        os = future.result()
                        discovered_devices[ip] = {"vendor": vendor, "mac": mac, "os": os}
                    except Exception as exc:
                        console.log(f'[red]{ip} generated an exception: {exc}[/red]')
                    progress.advance(task_id)

        selectable_ips = []
        server_table = Table(
            title="Server Selection",
            show_header=True,
            header_style="bold magenta",
            caption="[dim]'Advertised' servers are broadcasting. 'Discovered' are other hosts on your LAN.[/dim]"
        )
        server_table.add_column("Option", style="dim", width=8)
        server_table.add_column("IP Address")
        server_table.add_column("Device / Manufacturer", style="italic")
        server_table.add_column("Operating System", style="italic")
        server_table.add_column("Type")

        option_num = 1

        # Add advertised servers (highest priority)
        if advertised_servers:
            server_table.add_section()
            for ip in advertised_servers:
                if ip not in selectable_ips:
                    # We don't have device info for these, so leave it blank
                    server_table.add_row(str(option_num), ip, "N/A", "N/A", "[bold green]Advertised[/bold green]")
                    selectable_ips.append(ip)
                    option_num += 1
        
        # Add other discovered LAN hosts with their device info
        if discovered_devices:
            server_table.add_section()
            # Sort by IP address for consistent ordering
            sorted_devices = sorted(discovered_devices.items(), key=lambda item: tuple(map(int, item[0].split('.'))))
            for ip, data in sorted_devices:
                if ip not in selectable_ips:
                    device_info = Text(data["vendor"])
                    device_info.append(f"\n{data['mac']}", style="dim")
                    server_table.add_row(str(option_num), ip, device_info, data["os"], "[yellow]Discovered[/yellow]")
                    selectable_ips.append(ip)
                    option_num += 1

        # Add your own machine's IPs as a fallback
        if local_interfaces:
            server_table.add_section()
            for ip in local_interfaces:
                if ip not in selectable_ips:
                    server_table.add_row(str(option_num), ip, "This PC", "N/A", "[cyan]Local Interface[/cyan]")
                    selectable_ips.append(ip)
                    option_num += 1

        # --- Prompt user for selection ---
        if selectable_ips:
            console.print(server_table)
            prompt_choices = [str(i) for i in range(1, len(selectable_ips) + 1)] + [manual_ip_option]
            selection = Prompt.ask("[cyan]Select a server by number or choose an option[/cyan]", choices=prompt_choices, default="1")

            if selection == manual_ip_option:
                server_ip = Prompt.ask("[cyan]Enter Server IP[/cyan]", default="127.0.0.1")
            else:
                server_ip = selectable_ips[int(selection) - 1]
        else:
            console.print("[yellow]No servers were found. Please enter an IP manually.[/yellow]")
            server_ip = Prompt.ask("[cyan]Enter Server IP[/cyan]", default="127.0.0.1")



        # --- Step 2: Scan, Probe, and Select Port (This part remains the same) ---
        probed_ports = scan_and_probe_ports(server_ip)
        manual_port_option = "Enter port manually..."
        
        if probed_ports:
            port_table = Table(
                title=f"Scan Results for {server_ip}",
                show_header=True,
                header_style="bold magenta",
                caption="[dim]A '[bold green]Joinable[/bold green]' server is one that was responsive to our probe.[/dim]"
            )
            port_table.add_column("Port", justify="right", style="cyan", no_wrap=True)
            port_table.add_column("Status")

            prompt_choices = []
            joinable_ports = {p: s for p, s in probed_ports.items() if s == "Joinable"}
            open_ports = {p: s for p, s in probed_ports.items() if s == "Open"}

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

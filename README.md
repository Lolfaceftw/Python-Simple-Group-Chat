A modern, multi-threaded TCP chat application built with Python. It features a sophisticated server and an interactive, rich-text client interface powered by the `rich` library. The application supports advanced network discovery, making it easy to find and connect to chat servers.

## Key Features

### Server (`server.py`)
- **Multi-threaded:** Handles multiple client connections concurrently without blocking.
- **Service Discovery:** Periodically broadcasts its presence over UDP, allowing clients to find it automatically on the local network.
- **Message History:** New clients receive the last 50 messages upon joining, providing immediate context.
- **Real-time User List:** Keeps all clients synchronized with the current list of connected users.
- **Graceful Shutdown:** Handles `Ctrl+C` to cleanly disconnect all clients and shut down.
- **Thread-Safe:** Uses locks to ensure safe access to shared resources like the client list and message history.
- **Broad Compatibility:** Accepts connections from both the included rich client and basic tools like `netcat`, handling raw and protocol-based messages.

### Client (`main.py` & `client.py`)
- **Advanced Network Discovery:**
    - **Advertised Servers:** Automatically detects servers using the application's UDP broadcast.
    - **LAN Host Discovery:** Performs an ARP scan to discover all other devices on the local network.
    - **OS Detection:** Optionally runs an Nmap scan to identify the operating system of discovered devices (requires admin privileges).
- **Intelligent Port Scanning:** After selecting a host, the client scans a wide range of ports, probing for open and joinable chat services.
- **Rich TUI:** A polished and interactive Terminal User Interface built with the `rich` library.
- **Dual-Panel Layout:** Simultaneously view the live chat history and the list of online users.
- **Interactive Controls:**
    - Switch between chat and user panels with the `TAB` key.
    - Scroll through chat history and the user list using arrow keys.
- **User Commands:** Change your nickname on the fly with `/nick <new_name>` or exit with `/quit`.
- **Non-blocking Input:** (Currently Windows-only) The UI remains responsive while waiting for user input.

## Requirements

The project requires Python 3.6+ and the following libraries:

- `rich`: For the beautiful and interactive client-side TUI.
- `netifaces`: For robust network interface discovery.
- `scapy`: For LAN host discovery via ARP scans (requires admin privileges).
- `python-nmap`: For OS detection scans (requires admin privileges and Nmap installation).
- `requests`: Used for network-related utilities.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://your-repository-url.com/python-rich-chat.git
    cd python-rich-chat
    ```

2.  **(Optional but Recommended) Install Nmap:** For the OS detection feature to work, you must have the Nmap utility installed and available in your system's PATH.

3.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## How to Use

### 1. Start the Server

First, run the server script. It will prompt you to enter a port number.

```bash
python server.py
```
You will be asked for a port to run on (e.g., `8080`). The server will then bind to all available network interfaces (`0.0.0.0`) and start listening for connections and broadcasting its presence.

### 2. Start the Client

Next, run the main script in a new terminal. This will launch the interactive discovery and connection wizard.

```bash
python main.py
```
The client will guide you through the following steps:
1.  **Server Discovery:** It scans the network and presents a table of all found devices, categorized as "Advertised", "Discovered" (from ARP scan), or "Local Interface". You can also choose to enter an IP address manually.
2.  **Port Selection:** After you select a host, it scans for open ports and displays a list of potentially "Joinable" services. You can select a port from the list or enter one manually.
3.  **Username:** Once connected, you will be prompted to choose a username. The client prevents you from selecting a name that is already in use on the server.

### 3. Start Chatting!
- Type your message and press `Enter` to send.
- Use `/nick <new_name>` to change your display name.
- Use `TAB` to switch focus between the chat panel and the user list panel.
- Use the `Up`/`Down` arrow keys to scroll through the history of the active panel.
- Type `/quit` or press `Ctrl+C` to disconnect.

## Communication Protocol

Communication between the client and server uses a simple newline-terminated, pipe-separated (`|`) protocol.

-   `MSG|username: message`: A standard chat message from a user.
-   `SRV|text`: A notification or system message from the server (e.g., user join/leave events).
-   `ULIST|user1(addr1),user2(addr2)`: A comma-separated list of all connected users and their addresses.
-   `CMD_USER|new_username`: A command from a client to change their username.

This simple protocol allows clients to parse incoming data easily and determines how it should be displayed. Basic clients that don't use this protocol (like `netcat`) can still send and receive messages, which are handled as raw text by the server.

## Server and Client Sequence Diagram

The following diagram illustrates the updated flow, from discovery and connection to message exchange.

```mermaid
sequenceDiagram
    participant User
    participant MainScript as main.py
    participant Client
    participant Server

    %% Server Startup %%
    User->>Server: python server.py
    Server->>Server: Start TCP Listener & UDP Broadcast

    %% Client Startup & Discovery %%
    User->>MainScript: python main.py
    MainScript->>MainScript: Discover Servers (UDP & ARP)
    Server-->>MainScript: Discovery Message (UDP)
    MainScript->>MainScript: Scan Ports for selected host
    MainScript->>User: Display discovered servers & ports
    User->>MainScript: Select Server & Port

    %% Client Connection %%
    MainScript->>Client: Start Client(ip, port)
    Client->>Server: Establish TCP Connection
    Server->>Client: Send Welcome & Message History
    Server->>Client: ULIST|... (current user list)
    
    %% Client Handshake %%
    Client->>User: Prompt for Username
    User->>Client: Enter Username
    Client->>Server: CMD_USER|Alice
    Server->>Server: Validate & Store Username
    Server-->>Client: SRV|Alice has joined the chat.
    Server-->>Client: ULIST|Alice(addr)

    %% Chatting (Simplified) %%
    Client->>Server: MSG|Alice: Hello!
    Server-->>Client: MSG|Alice: Hello!

    %% Disconnection %%
    User->>Client: /quit
    Client-xServer: TCP connection lost
    Server->>Server: Detect disconnection, remove Client
    Server-->>Server: Broadcast user departure & new ULIST

```

## Limitations and Future Work

-   **Platform Support:** The rich client's interactive UI currently relies on `msvcrt` and is **Windows-only**. Support for Linux and macOS would require implementing non-blocking input using `termios` and `tty`.
-   **Private Messaging:** Implement a `/msg <user> <message>` command for one-on-one conversations.
-   **Channels/Rooms:** Add the ability for users to create and join different chat rooms.
-   **Encryption:** Secure the communication channel using SSL/TLS.
-   **File Sharing:** Allow users to send and receive files.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

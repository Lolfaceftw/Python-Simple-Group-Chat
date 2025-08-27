"""
Chat Client Main Entry Point

Main entry point for the modular chat client.
"""

import sys
import logging
from typing import List

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from chat_app.client.chat_client import ChatClient, ClientConfig
from chat_app.discovery.service_discovery import ServiceDiscovery
from chat_app.shared.logging_config import setup_logging


def discover_servers() -> List[str]:
    """
    Discover available chat servers on the network.
    
    Returns:
        List of discovered server addresses.
    """
    console = Console()
    console.print("[cyan]Scanning for servers on the local network...[/cyan]")
    
    discovery = ServiceDiscovery()
    try:
        servers = discovery.discover_servers(timeout=3)
        
        if servers:
            console.print(f"[green]Found {len(servers)} server(s): {', '.join(servers)}[/green]")
        else:
            console.print("[yellow]No servers found on the network.[/yellow]")
        
        return servers
        
    except Exception as e:
        console.print(f"[red]Error during server discovery: {e}[/red]")
        return []


def get_user_input() -> tuple[str, int, str]:
    """
    Get connection parameters from user input.
    
    Returns:
        Tuple of (host, port, username).
    """
    console = Console()
    
    # Discover servers first
    available_servers = discover_servers()
    
    # Get server IP
    if available_servers:
        server_ip = Prompt.ask(
            "[cyan]Enter Server IP[/cyan]",
            choices=available_servers,
            default=available_servers[0]
        )
    else:
        server_ip = Prompt.ask("[cyan]Enter Server IP[/cyan]", default="127.0.0.1")
    
    # Get server port
    server_port_str = Prompt.ask("[cyan]Enter Server Port[/cyan]", default="8080")
    try:
        server_port = int(server_port_str)
    except ValueError:
        console.print("[bold red]Invalid port number. Using default port 8080.[/bold red]")
        server_port = 8080
    
    # Get username
    username = Prompt.ask("[cyan]Enter your Username[/cyan]", default="Guest")
    
    return server_ip, server_port, username


def main() -> None:
    """Main entry point for the chat client."""
    console = Console()
    
    # Set up logging
    setup_logging(level="INFO")
    logger = logging.getLogger(__name__)
    
    console.print(Panel("[bold cyan]Welcome to the Python Chat Client![/bold cyan]", border_style="cyan"))
    
    try:
        # Get connection parameters
        host, port, username = get_user_input()
        
        # Create client configuration
        config = ClientConfig(
            host=host,
            port=port,
            username=username,
            console_height=console.height if hasattr(console, 'height') else 24
        )
        
        # Create and start client
        client = ChatClient(config)
        
        # Set up client callbacks for logging
        def on_connected():
            logger.info(f"Connected to {host}:{port} as {username}")
        
        def on_disconnected():
            logger.info("Disconnected from server")
        
        def on_error(error: str):
            logger.error(f"Client error: {error}")
        
        client.set_callbacks(
            on_connected=on_connected,
            on_disconnected=on_disconnected,
            on_error=on_error
        )
        
        # Start the client
        logger.info(f"Starting chat client - connecting to {host}:{port} as {username}")
        client.start()
        
    except ValueError as e:
        console.print(f"[bold red]Invalid input: {e}[/bold red]")
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[bold blue]Client startup cancelled.[/bold blue]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[bold red]An error occurred during startup: {e}[/bold red]")
        logger.exception("Startup error")
        sys.exit(1)


if __name__ == "__main__":
    main()

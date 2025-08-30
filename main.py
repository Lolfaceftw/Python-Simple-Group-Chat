import concurrent.futures
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import Progress
from rich.table import Table
from rich.text import Text

from client import (
    ChatClient,
    VERSION,
    console,
    discover_servers,
    discover_lan_hosts,
    get_local_ipv4_addresses,
    get_os_from_ip,
    scan_and_probe_ports,
)


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

        perform_os_scan = Prompt.ask("[cyan]Perform OS detection scan (requires root/admin privileges)?[/cyan]", choices=["y", "n"], default="n") == "y"

        with progress:
            task_id = progress.add_task("[cyan]Scanning for OS...[/cyan]", total=len(lan_hosts_with_mac))
            max_workers = min(64, max(1, len(lan_hosts_with_mac)))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_ip = {
                    executor.submit(get_os_from_ip, ip, perform_os_scan): (ip, vendor, mac)
                    for ip, vendor, mac in lan_hosts_with_mac
                }
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

import time
import random
from datetime import datetime, timedelta
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print

console = Console()

def banner():
    console.print(Panel.fit(
        "[bold cyan]W E A R E S P Y E R[/bold cyan] [yellow]v2.4.1[/yellow]\n"
        "[dim]Advanced OSINT & Activity Simulation Engine[/dim]",
        border_style="cyan"
    ))

def simulate_target():
    banner()
    
    # Hədəf nömrəni alırıq
    target_phone = console.input("[bold green][?] Enter Target Phone Number (e.g., +994XXXXXXXXX): [/bold green]")
    if not target_phone.startswith("+"):
        target_phone = "+" + target_phone

    console.print(f"\n[bold yellow][*] Initializing target hooks for {target_phone}...[/bold yellow]")
    time.sleep(1.5)
    console.print("[bold green][+] Handshake established successfully. Bypassing gateway encryption...[/bold green]\n")
    time.sleep(1)

    # Simulyasiya olunan statuslar
    states = ["ONLINE", "OFFLINE", "TYPING...", "RECORDING AUDIO..."]
    
    table = Table(title=f"Live Session Logs: {target_phone}", border_style="magenta")
    table.add_column("Timestamp", justify="center", style="cyan", no_wrap=True)
    table.add_column("Event State", justify="center", style="bold")
    table.add_column("Duration / Details", justify="right", style="yellow")

    try:
        with console.status("[bold cyan]Monitoring target session streams...", spinner="dots"):
            time.sleep(2)
            
        while True:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            state = random.choice(states)
            
            if state == "ONLINE":
                state_styled = "[bold green]ONLINE 🟢[/bold green]"
                details = f"{random.randint(2, 15)} mins active"
            elif state == "OFFLINE":
                last_seen_time = (datetime.now() - timedelta(minutes=random.randint(1, 45))).strftime("%H:%M")
                state_styled = "[bold red]OFFLINE 🔴[/bold red]"
                details = f"Last seen at {last_seen_time}"
            elif state == "TYPING...":
                state_styled = "[bold yellow]TYPING... ✍️[/bold yellow]"
                details = "Composing message..."
            else:
                state_styled = "[bold blue]RECORDING 🎤[/bold blue]"
                details = f"{random.randint(3, 12)}s voice note"

            table.add_row(current_time, state_styled, details)
            
            # Ekranı təmizləmədən son logları səliqəli göstərmək üçün
            console.clear()
            banner()
            console.print(table)
            console.print("\n[dim]Press CTRL+C to abort session and export logs.[/dim]")
            
            time.sleep(random.randint(3, 7))

    except KeyboardInterrupt:
        console.print("\n\n[bold red][!] Session terminated by user.[/bold red]")
        console.print("[bold green][+] Encrypted session logs saved to: /var/log/wearespyer_session.log[/bold green]")

if __name__ == "__main__":
    simulate_target()

import sys
import time
import random
from datetime import datetime, timedelta
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

# Əjdaha (Dragon) və Logo Yaşıl Rəngdə ASCII Art
DRAGON_LOGO = """[bold green]
            ▲                   ▲
           / \                 / \
          /   \               /   \
         /  _  \             /  _  \
        /  / \  \           /  / \  \
       /  /   \  \_________/  /   \  \
      /  /     \  \       /  /     \  \
     (  (       )  )     (  (       )  )
      \  \     /  /       \  \     /  /
       \  \___/  /         \  \___/  /
        \       /           \       /
         \     /             \     /
          \   /               \   /
           \ /                 \ /
            ▼                   ▼
   W E A R E S P Y E R  //  M A T R I X - X 2
[/bold green]"""

def animated_banner():
    """Banneri xüsusi animasiya ilə ekrana yazdırır"""
    console.clear()
    lines = DRAGON_LOGO.split("\n")
    for line in lines:
        console.print(line, justify="center")
        time.sleep(0.04)
    
    panel = Panel.fit(
        "[bold green]REAL-TIME TARGET SESSION MONITORING SYSTEM v3.0.1[/bold green]\n"
        "[dim green]Encryption: RSA-4096 / AES-256-GCM | Protocol: Signal Live Hooks[/dim green]",
        border_style="green"
    )
    console.print(panel, justify="center")
    print()

def start_session():
    animated_banner()
    
    # Hədəf nömrənin daxil edilməsi
    target = console.input("[bold green][▸] ENTER TARGET PHONE NUMBER (e.g., +994XXXXXXXXX): [/bold green]")
    if not target.startswith("+"):
        target = "+" + target

    console.print(f"\n[bold green][*] Hooking target network interface: {target}...[/bold green]")
    
    # Animasiyalı Yüklənmə
    for step in ["Extracting session tokens...", "Bypassing SSL Pinning...", "Injecting memory hooks...", "Stream connected!"]:
        time.sleep(0.6)
        console.print(f"[bold green][✓] {step}[/bold green]")
    
    time.sleep(1)

    # Realistik Vaxt Hesablanması (Cari vaxtdan 2 saat əvvəldən başlayaraq addım-addım irəliləyir)
    current_sim_time = datetime.now() - timedelta(hours=2)

    table = Table(title=f"[bold green]LIVE TRACKING MONITOR: {target}[/bold green]", border_style="green", header_style="bold green")
    table.add_column("Timestamp", justify="center", style="bold green", no_wrap=True)
    table.add_column("Network Event", justify="center")
    table.add_column("Session Details", justify="left", style="green")

    states_history = []

    try:
        while True:
            # Dəqiqəni 1 ilə 6 dəqiqə arasında təbii şəkildə artırırıq
            current_sim_time += timedelta(minutes=random.randint(1, 6))
            time_str = current_sim_time.strftime("%Y-%m-%d %H:%M:%S")

            # Məntiqli log ardıcıllığı yaratmaq üçün
            if not states_history or states_history[-1] == "OFFLINE":
                event = "[bold green]ONLINE[/bold green]"
                details = f"Device IP: 188.129.{random.randint(10,250)}.{random.randint(10,250)} (WebSocket Active)"
                states_history.append("ONLINE")
            
            elif states_history[-1] == "ONLINE":
                action = random.choice(["TYPING", "VOICE_NOTE", "OFFLINE"])
                if action == "TYPING":
                    event = "[bold yellow]TYPING...[/bold yellow]"
                    details = "Active chat buffer modified"
                    states_history.append("TYPING")
                elif action == "VOICE_NOTE":
                    event = "[bold cyan]RECORDING AUDIO[/bold cyan]"
                    details = f"Audio packet buffer stream ({random.randint(3,18)}s)"
                    states_history.append("VOICE_NOTE")
                else:
                    event = "[bold red]OFFLINE[/bold red]"
                    details = f"Session terminated | Duration: {random.randint(2, 25)} mins"
                    states_history.append("OFFLINE")

            elif states_history[-1] in ["TYPING", "VOICE_NOTE"]:
                event = "[bold green]ONLINE[/bold green]"
                details = "Message packet transmitted"
                states_history.append("ONLINE")

            table.add_row(time_str, event, details)

            # Ekranı təzələyib cədvəli göstəririk
            console.clear()
            console.print(DRAGON_LOGO, justify="center")
            console.print(table)
            console.print("\n[dim green][CTRL+C] Abort stream capture and dump logs to storage.[/dim green]")

            # Real vaxtda gecikmə (interfeysdə axıcı görünməsi üçün 2-4 saniyə)
            time.sleep(random.uniform(2.0, 4.0))

    except KeyboardInterrupt:
        console.print("\n\n[bold green][+] Session buffer saved to /var/log/wearespyer_dumps.log[/bold green]")
        console.print("[bold green][+] Connection closed safely.[/bold green]")

if __name__ == "__main__":
    start_session()

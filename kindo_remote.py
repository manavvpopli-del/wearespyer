import asyncio
import base64
import json
import socket
import time
import io
import sys
import qrcode
import qrcode.constants
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn
from PIL import Image
import numpy as np
import rich
from rich.console import Console
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.table import Table
from rich.text import Text
import threading

# --- Konfiqurasiya ---
PORT = 8765
TERMINAL_WIDTH = 80
TERMINAL_HEIGHT = 24
RESET = "\x1b[0m"

# --- Utility funksiyaları ---
def get_local_ip() -> str:
    """Kompüterin Local IP ünvanını tapır."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def generate_qr_terminal(url: str):
    """Terminalda ASCII QR kod yaradır."""
    console = rich.get_console()
    console.print("\n[bold cyan]Kindo Phone Remote - Reverse Mirroring[/bold cyan]")
    console.print(f"URL: [link]{url}[/link]")
    console.print("Telefonunla skanla və 'Start Mirroring'ə bas:\n")
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    console.print("="*65 + "\n")

# --- Frontend HTML/JS Şablonu (Telefon üçün) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="az">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Kindo Phone Client</title>
    <style>
        body { font-family: sans-serif; background: #222; color: #eee; margin: 0; padding: 20px; text-align: center; }
        button { padding: 15px 30px; font-size: 1.2em; background: #007bff; color: white; border: none; border-radius: 8px; cursor: pointer; margin: 10px; }
        button:active { transform: scale(0.95); }
        #status { margin-top: 20px; padding: 10px; background: #333; border-radius: 5px; }
        .log { text-align: left; max-height: 200px; overflow-y: auto; background: #111; padding: 10px; font-family: monospace; font-size: 0.8em; margin-top: 20px; }
    </style>
</head>
<body>
    <h1>Kindo Phone Client</h1>
    <p>Bu səhifə telefonun ekranını PC-yə stream edəcək və PC-dən gələn inputları qəbul edəcək.</p>
    <button id="startBtn">Start Mirroring & Input Bridge</button>
    <button id="fsBtn">Toggle Fullscreen</button>
    <div id="status">Hazırdır. Dəyərləndirmə üçün 'Start'ə bas.</div>
    <div class="log" id="log">Loglar burada görünəcək...</div>

    <script>
        let ws;
        let streamActive = false;
        let logDiv = document.getElementById('log');
        const statusDiv = document.getElementById('status');

        function log(msg) {
            logDiv.innerHTML += `<div>${new Date().toLocaleTimeString()} - ${msg}</div>`;
            logDiv.scrollTop = logDiv.scrollHeight;
        }

        document.getElementById('fsBtn').addEventListener('click', () => {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch(err => {
                    console.log(`Error attempting to enable fullscreen mode: ${err.message}`);
                });
            } else {
                document.exitFullscreen();
            }
        });

        document.getElementById('startBtn').addEventListener('click', async () => {
            log("Ekranı almaq üçün icazə ver...");
            try {
                // Ekranı stream et (Browser Screen Capture)
                const stream = await navigator.mediaDevices.getDisplayMedia({
                    video: { frameRate: 15 },
                    audio: false
                });

                // WebSocket bağlantısı
                ws = new WebSocket(`ws://${location.host}/ws`);
                
                ws.onopen = () => {
                    log("WebSocket bağlandı.");
                    statusDiv.innerText = "Aktivdir. Ekranı və inputları göndərir.";
                    startStreaming(stream);
                };

                ws.onmessage = (event) => {
                    const input = JSON.parse(event.data);
                    handleInput(input);
                };

                ws.onclose = () => {
                    log("Bağlantı kəsildi.");
                    statusDiv.innerText = "Bağlantı kəsildi.";
                    stopStreaming();
                };

            } catch (err) {
                log("Xəta: " + err.message);
                statusDiv.innerText = "Ekranı almaq mümkün olmadı.";
            }
        });

        function startStreaming(stream) {
            streamActive = true;
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            const video = document.createElement('video');
            video.srcObject = stream;
            video.play();

            // Canvas-ı ekran ölçüsünə uyğun təyin et
            canvas.width = window.screen.width;
            canvas.height = window.screen.height;

            // Hər 100ms-də bir frame çək və göndər
            const interval = setInterval(() => {
                if (!streamActive) return;
                try {
                    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                    canvas.toBlob((blob) => {
                        if (blob && ws.readyState === WebSocket.OPEN) {
                            const reader = new FileReader();
                            reader.onloadend = () => {
                                const base64data = reader.result.split(',')[1];
                                ws.send(JSON.stringify({ type: 'frame', data: base64data }));
                            };
                            reader.readAsDataURL(blob);
                        }
                    }, 'image/jpeg', 0.7);
                } catch(e) {
                    log("Stream xətası: " + e.message);
                }
            }, 100); // 10 FPS
        }

        function stopStreaming() {
            streamActive = false;
            if (ws) ws.close();
        }

        // PC-dən gələn inputları işlə
        function handleInput(input) {
            if (input.type === 'key') {
                const event = new KeyboardEvent(input.action, {
                    key: input.key,
                    code: input.code,
                    bubbles: true,
                    cancelable: true
                });
                document.dispatchEvent(event);
                log(`Key: ${input.key} (${input.action})`);
            } else if (input.type === 'mouse') {
                const x = input.x * window.screen.width;
                const y = input.y * window.screen.height;
                const event = new MouseEvent(input.action, {
                    view: window,
                    bubbles: true,
                    cancelable: true,
                    clientX: x,
                    clientY: y
                });
                document.dispatchEvent(event);
                log(`Mouse: ${input.action} at (${x}, ${y})`);
            }
        }
    </script>
</body>
</html>
"""

# --- FastAPI App ---
app = FastAPI(title="Kindo Phone Remote")

# Global state
class State:
    def __init__(self):
        self.current_frame = None
        self.is_active = False
        self.ws_connection = None

state = State()

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_TEMPLATE

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Telefonun brauzerindən gələn frame-ları qəbul edir.
    """
    await websocket.accept()
    state.ws_connection = websocket
    print("[WS] Telefon bağlandı.")

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            if msg["type"] == "frame":
                # Base64 JPEG decode et
                jpeg_bytes = base64.b64decode(msg["data"])
                state.current_frame = jpeg_bytes
                state.is_active = True
                
    except WebSocketDisconnect:
        state.is_active = False
        state.ws_connection = None
        print("[WS] Telefon ayrıldı.")

def send_to_phone(data: dict):
    """PC-dən telefona input göndərir."""
    if state.ws_connection:
        try:
            # WebSocket sendi async olduğu üçün, sync kontekstdən async-a köçürmək lazımdır
            loop = asyncio.get_event_loop()
            loop.create_task(state.ws_connection.send_text(json.dumps(data)))
        except Exception as e:
            print(f"Send to phone error: {e}")

# --- Input Hook Listener (PC Input -> Phone) ---
import keyboard
import pyautogui

def input_hook_listener():
    """
    PC-dəki klaviatura və mouse hadisələrini dinləyir və telefona yollayır.
    """
    # PyAutoGUI-nin mouse dinləyicisi üçün
    last_mouse_pos = pyautogui.position()
    
    def on_key_event(event):
        if event.event_type == 'down':
            key_name = event.name
            # Modifier tuşlar üçün ayrıca idarəetmə
            if key_name not in ['ctrl', 'shift', 'alt', 'cmd']:
                send_to_phone({"type": "key", "action": "down", "key": key_name, "code": key_name.upper()})
        elif event.event_type == 'up':
            key_name = event.name
            send_to_phone({"type": "key", "action": "up", "key": key_name, "code": key_name.upper()})

    keyboard.hook(on_key_event)

    # Mouse dinləyicisi (PyAutoGUI loop)
    while True:
        current_mouse_pos = pyautogui.position()
        if current_mouse_pos != last_mouse_pos:
            screen_w, screen_h = pyautogui.size()
            rel_x = current_mouse_pos.x / screen_w
            rel_y = current_mouse_pos.y / screen_h
            send_to_phone({"type": "mouse", "action": "move", "x": rel_x, "y": rel_y})
            last_mouse_pos = current_mouse_pos
            
        # Mouse klik dinləyicisi üçün sadə yoxlama (PyAutoGUI mouse hook-ları mürəkkəbdir, 
        # lakin pyautogui-nin internal state-i yoxlanıla bilər. 
        # Daha asan yol: keyboard kitabxanası ilə mouse hadisələrini də dinləmək)
        time.sleep(0.01) # 100ms poll

# --- TUI Renderer (Terminalda Ekran Görüntüsü) ---
def render_terminal_screen():
    """
    Terminalda canlı ekran görüntüsü çəkərir.
    """
    console = rich.get_console()
    
    while True:
        layout = Layout()
        
        # Layout quruluşu
        layout.split_column(
            Layout(Panel("Kindo Phone Remote - Reverse Mirroring", style="bold cyan"), name="header", size=3),
            Layout(name="screen", ratio=3),
            Layout(Panel("Status: Aktivdir. PC-dəki inputlar telefona göndərilir.", style="green"), name="footer", size=3)
        )
        
        # Ekran görüntüsünü hazırla
        if state.is_active and state.current_frame:
            try:
                img = Image.open(io.BytesIO(state.current_frame))
                # Terminal ölçüsünə uyğun endir
                img = img.resize((TERMINAL_WIDTH, TERMINAL_HEIGHT), Image.Resampling.LANCZOS)
                pixels = np.array(img)
                
                # ANSI escape kodları ilə rəngli bloklar
                output_lines = []
                for y in range(TERMINAL_HEIGHT):
                    line = []
                    for x in range(TERMINAL_WIDTH):
                        r, g, b = pixels[y, x]
                        brightness = (r + g + b) / 3
                        if brightness > 200:
                            color_code = 15
                        elif brightness > 150:
                            color_code = 7
                        elif brightness > 100:
                            if r > g and

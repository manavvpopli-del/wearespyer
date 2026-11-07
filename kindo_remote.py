import asyncio
import json
import socket
import time
import io
import sys
import qrcode
import qrcode.constants
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
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
from rich.status import Status
import threading

# --- Konfiqurasiya ---
PORT = 8765
FPS = 10  # Terminal rendering üçün optimal FPS
TERMINAL_WIDTH = 80
TERMINAL_HEIGHT = 24
ANSI_COLORS = [
    "\x1b[38;5;0m",  # Black
    "\x1b[38;5;9m",  # Red
    "\x1b[38;5;2m",  # Green
    "\x1b[38;5;11m", # Yellow
    "\x1b[38;5;12m", # Blue
    "\x1b[38;5;13m", # Magenta
    "\x1b[38;5;6m",  # Cyan
    "\x1b[38;5;15m"  # White
]
RESET = "\x1b[0m"

# --- Utility ---
def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def generate_qr_terminal(url: str):
    console = rich.get_console()
    console.print("\n[bold cyan]Kindo Phone Remote[/bold cyan]")
    console.print(f"URL: [link]{url}[/link]")
    console.print("Telefonunla skanla və 'Start Mirroring'ə bas:\n")
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=1, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)

# --- TUI Renderer (Terminalda Ekran Görüntüsü) ---
class TerminalScreenRenderer:
    def __init__(self, width=TERMINAL_WIDTH, height=TERMINAL_HEIGHT):
        self.width = width
        self.height = height
        self.current_frame = None
        self.last_update = 0
        self.is_active = False

    def update_frame(self, jpeg_bytes):
        """Gələn JPEG frame-i rəngli ASCII bloklarına çevirir."""
        try:
            img = Image.open(io.BytesIO(jpeg_bytes))
            # Terminal ölçüsünə uyğun endir
            img = img.resize((self.width, self.height), Image.Resampling.LANCZOS)
            self.current_frame = img
            self.last_update = time.time()
            self.is_active = True
        except Exception as e:
            print(f"Render error: {e}")

    def render(self):
        """Terminal üçün ANSI escape kodlarını qaytarır."""
        if not self.current_frame:
            return "[dim]Waiting for screen stream...[/dim]"
        
        pixels = np.array(self.current_frame)
        output = []
        
        # Hər sətir üçün
        for y in range(self.height):
            line = []
            for x in range(self.width):
                r, g, b = pixels[y, x]
                # Sadə rəng mapləməsi (256 rəngdən birini seç)
                # Burada sadə bir heuristik istifadə edirik
                brightness = (r + g + b) / 3
                if brightness > 200:
                    color_code = 15 # White
                elif brightness > 150:
                    color_code = 7  # Light Gray
                elif brightness > 100:
                    # Qırmızı/Yaşıl/Mavi balansına görə
                    if r > g and r > b: color_code = 9
                    elif g > r and g > b: color_code = 2
                    elif b > r and b > g: color_code = 12
                    else: color_code = 11
                else:
                    color_code = 0 # Black/Dark
                
                # Block character (şkilik blok)
                block = "█"
                line.append(f"\x1b[38;5;{color_code}m{block}")
            output.append("".join(line) + RESET)
        
        return "\n".join(output)

# --- FastAPI App ---
app = FastAPI(title="Kindo Phone Remote")
app.add_middleware(CORSMiddleware, allow_origins=["*"])

# Global state
renderer = TerminalScreenRenderer()
input_queue = asyncio.Queue()
connection_status = {"connected": False, "phone_info": "No Connection"}

@app.get("/", response_class=HTMLResponse)
async def index():
    # Telefonun brauzerində açılacaq HTML
    return """
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
                                // Base64 olaraq göndər (MJPEG sadəliyi üçün)
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
                    // Virtual klaviatura hadisəsi yarat
                    const event = new KeyboardEvent(input.action, {
                        key: input.key,
                        code: input.code,
                        bubbles: true,
                        cancelable: true
                    });
                    document.dispatchEvent(event);
                    log(`Key: ${input.key} (${input.action})`);
                } else if (input.type === 'mouse') {
                    // Virtual mouse hadisəsi yarat
                    // Koordinatlar ekrana nisbətən olmalıdır
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

            // Ekranı tam ekran rejimində aç (İstifadəçi təcrübəsi üçün)
            function toggleFullscreen() {
                if (!document.fullscreenElement) {
                    document.documentElement.requestFullscreen().catch(err => {
                        console.log(`Error attempting to enable fullscreen mode: ${err.message}`);
                    });
                } else {
                    document.exitFullscreen();
                }
            }
            
            // Add a button for fullscreen
            const fsBtn = document.createElement('button');
            fsBtn.innerText = "Toggle Fullscreen";
            fsBtn.onclick = toggleFullscreen;
            document.body.insertBefore(fsBtn, document.getElementById('startBtn'));
        </script>
    </body>
    </html>
    """

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Telefonun brauzerindən gələn frame-ları qəbul edir və TUI renderer-a yollayır.
    Eyni zamanda, PC-dən gələn inputları telefona göndərir.
    """
    await websocket.accept()
    connection_status["connected"] = True
    connection_status["phone_info"] = "Connected"
    print("[WS] Telefon bağlandı.")

    # Input handler thread (PC klaviatura/mouse -> WebSocket)
    # Bu hissə üçün, sən PC-dəki klaviatura hadisələrini dinləməliyəm.
    # PyAutoGUI istifadə edib, inputları qəbul etmək üçün "Input Hook" quraq.
    
    input_thread = threading.Thread(target=input_hook_listener, daemon=True)
    input_thread.start()

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            if msg["type"] == "frame":
                # Base64 JPEG decode et
                jpeg_bytes = base64.b64decode(msg["data"])
                renderer.update_frame(jpeg_bytes)
                
    except WebSocketDisconnect:
        connection_status["connected"] = False
        connection_status["phone_info"] = "Disconnected"
        print("[WS] Telefon ayrıldı.")

# --- Input Hook Listener (PC Input -> Phone) ---
import pyautogui
import keyboard

def input_hook_listener():
    """
    PC-dəki klaviatura və mouse hadisələrini dinləyir və WebSocket-ə yollayır.
    """
    # PyAutoGUI-nin mouse dinləyicisi üçün
    last_mouse_pos = pyautogui.position()
    
    def on_key_event(event):
        if event.event_type == 'down':
            # Klaviş adını al
            key_name = event.name
            # Xüsusi tuşları əhatə et
            if key_name in ['ctrl', 'shift', 'alt', 'cmd']:
                pass # Modifier tuşlar üçün ayrıca idarəetmə
            else:
                send_to_phone({"type": "key", "action": "down", "key": key_name, "code": key_name.upper()})
        elif event.event_type == 'up':
            key_name = event.name
            send_to_phone({"type": "key", "action": "up", "key": key_name, "code": key_name.upper()})

    keyboard.hook(on_key_event)

    # Mouse dinləyicisi (PyAutoGUI loop)
    while True:
        current_mouse_pos = pyautogui.position()
        if current_mouse_pos != last_mouse_pos:
            # Normalizə edilmiş koordinatlar (0.0 - 1.0)
            screen_w, screen_h = pyautogui.size()
            rel_x = current_mouse_pos.x / screen_w
            rel_y = current_mouse_pos.y / screen_h
            send_to_phone({"type": "mouse", "action": "move", "x": rel_x, "

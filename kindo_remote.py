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

def generate_qr_terminal(url: str) -> Panel:
    """TUI daxilində skan edilə bilən QR paneli yaradır."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)

    matrix = qr.get_matrix()
    if len(matrix) % 2:
        matrix.append([False] * len(matrix[0]))

    qr_text = Text()
    for row in range(0, len(matrix), 2):
        for col in range(len(matrix[row])):
            top = matrix[row][col]
            bottom = matrix[row + 1][col]
            if top and bottom:
                char = "█"
            elif top:
                char = "▀"
            elif bottom:
                char = "▄"
            else:
                char = " "
            qr_text.append(char, style="black on white")
        qr_text.append("\n", style="black on white")

    qr_text.append("\n" + url, style="bold cyan on white")
    return Panel(
        qr_text,
        title="Telefonla QR kodu skanla",
        border_style="green",
        style="on white",
    )

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
    <p>Bu səhifə telefon ekranını PC-yə ötürür və brauzer daxilində sintez edilmiş input hadisələrini qəbul edir. Təhlükəsizlik məhdudiyyətlərinə görə başqa tətbiqləri və əməliyyat sistemini idarə edə bilməz.</p>
    <button id="startBtn">Start Mirroring & Input Bridge</button>
    <button id="fsBtn">Toggle Fullscreen</button>
    <div id="status">Hazırdır. Dəyərləndirmə üçün 'Start'ə bas.</div>
    <div class="log" id="log">Loglar burada görünəcək...</div>

    <script>
        let ws;
        let streamActive = false;
        let streamInterval = null;
        let activeStream = null;
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
                stream.getVideoTracks()[0].addEventListener('ended', stopStreaming);

                // WebSocket bağlantısı
                ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
                
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
            activeStream = stream;
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            const video = document.createElement('video');
            video.srcObject = stream;
            video.play();

            // Canvas-ı ekran ölçüsünə uyğun təyin et
            canvas.width = window.screen.width;
            canvas.height = window.screen.height;

            // Hər 100ms-də bir frame çək və göndər
            streamInterval = setInterval(() => {
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
            if (streamInterval !== null) {
                clearInterval(streamInterval);
                streamInterval = null;
            }
            if (activeStream) {
                activeStream.getTracks().forEach(track => track.stop());
                activeStream = null;
            }
            if (ws && ws.readyState !== WebSocket.CLOSED) {
                ws.close();
            }
        }

        // PC-dən gələn inputları işlə
        function handleInput(input) {
            if (input.type === 'key') {
                const eventType = input.action === 'down' ? 'keydown' : 'keyup';
                const event = new KeyboardEvent(eventType, {
                    key: input.key,
                    code: input.code,
                    bubbles: true,
                    cancelable: true
                });
                document.dispatchEvent(event);
                log(`Key: ${input.key} (${input.action})`);
            } else if (input.type === 'mouse') {
                const x = input.x * window.innerWidth;
                const y = input.y * window.innerHeight;
                const eventType = input.action === 'move' ? 'mousemove' : input.action;
                const event = new MouseEvent(eventType, {
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
        self.loop = None
        self.send_lock = None
        self.qr_panel = None

state = State()

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_TEMPLATE

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Telefon brauzerindən gələn frame-ları qəbul edir."""
    await websocket.accept()
    state.ws_connection = websocket
    state.loop = asyncio.get_running_loop()
    state.send_lock = asyncio.Lock()
    print("[WS] Telefon bağlandı.")

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "frame" and isinstance(msg.get("data"), str):
                jpeg_bytes = base64.b64decode(msg["data"], validate=True)
                state.current_frame = jpeg_bytes
                state.is_active = True
    except WebSocketDisconnect:
        print("[WS] Telefon ayrıldı.")
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        print(f"[WS] Yanlış mesaj qəbul edildi: {exc}")
    finally:
        if state.ws_connection is websocket:
            state.is_active = False
            state.ws_connection = None
            state.loop = None
            state.send_lock = None
async def _send_to_phone_async(websocket: WebSocket, lock: asyncio.Lock, payload: str):
    """WebSocket-ə yalnız onun event loop-u daxilində təhlükəsiz yazır."""
    async with lock:
        if state.ws_connection is websocket:
            await websocket.send_text(payload)


def send_to_phone(data: dict):
    """PC-dən telefona input göndərir; aktiv paylaşım olmayanda heç nə ötürmür."""
    loop = state.loop
    websocket = state.ws_connection
    lock = state.send_lock

    if not state.is_active or loop is None or websocket is None or lock is None:
        return
    if not loop.is_running():
        return

    try:
        payload = json.dumps(data)
        future = asyncio.run_coroutine_threadsafe(
            _send_to_phone_async(websocket, lock, payload),
            loop,
        )

        def report_send_error(result):
            try:
                result.result()
            except Exception as exc:
                print(f"Send to phone error: {exc}")

        future.add_done_callback(report_send_error)
    except Exception as exc:
        print(f"Send to phone error: {exc}")
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
def render_frame(frame_bytes: bytes | None) -> Text:
    """JPEG frame-i terminal ölçüsünə uyğun rəngli simvollara çevirir."""
    if not frame_bytes:
        return Text("Telefon gözlənilir. QR kodu skan edib paylaşımı başladın.", style="dim")

    width = max(20, min(TERMINAL_WIDTH - 4, 120))
    pixel_height = max(16, (TERMINAL_HEIGHT - 8) * 2)

    try:
        with Image.open(io.BytesIO(frame_bytes)) as image:
            image = image.convert("RGB")
            image.thumbnail((width, pixel_height), Image.LANCZOS)

            canvas = Image.new("RGB", (width, pixel_height), (0, 0, 0))
            x_offset = (width - image.width) // 2
            y_offset = (pixel_height - image.height) // 2
            canvas.paste(image, (x_offset, y_offset))
            pixels = np.asarray(canvas)

        result = Text()
        for y in range(0, pixel_height, 2):
            for x in range(width):
                top = pixels[y, x]
                bottom = pixels[min(y + 1, pixel_height - 1), x]
                style = (
                    f"rgb({int(top[0])},{int(top[1])},{int(top[2])}) "
                    f"on rgb({int(bottom[0])},{int(bottom[1])},{int(bottom[2])})"
                )
                result.append("▀", style=style)
            if y + 2 < pixel_height:
                result.append("\n")
        return result
    except Exception as exc:
        return Text(f"Görüntü emal edilə bilmədi: {exc}", style="bold red")


def build_terminal_layout():
    layout = Layout()
    layout.split_column(
        Layout(
            Panel("Kindo Phone Remote — Reverse Mirroring", style="bold cyan"),
            name="header",
            size=3,
        ),
        Layout(name="content", ratio=1),
        Layout(
            Panel(
                "Status: Aktiv paylaşım" if state.is_active else "Status: Telefon bağlantısı gözlənilir",
                style="green" if state.is_active else "yellow",
            ),
            name="footer",
            size=3,
        ),
    )

    if state.is_active:
        layout["content"].update(
            Panel(render_frame(state.current_frame), title="Telefon ekranı", border_style="cyan")
        )
    else:
        layout["content"].split_row(
            Layout(name="screen", ratio=1),
            Layout(name="qr", size=38),
        )
        layout["content"]["screen"].update(
            Panel(render_frame(state.current_frame), title="Telefon ekranı", border_style="cyan")
        )
        layout["content"]["qr"].update(
            state.qr_panel or Panel("QR kodu hazırlanır...", title="Telefonla tara")
        )

    return layout

def render_terminal_screen():
    """Terminalda canlı telefon görüntüsünü göstərir."""
    console = Console()
    try:
        with Live(
            build_terminal_layout(),
            console=console,
            refresh_per_second=10,
            screen=True,
            transient=False,
        ) as live:
            while True:
                live.update(build_terminal_layout(), refresh=True)
                time.sleep(0.1)
    except KeyboardInterrupt:
        pass


def run_server():
    """FastAPI serverini ayrıca thread-də başladır."""
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="warning",
        access_log=False,
    )


def main():
    local_ip = get_local_ip()
    url = f"http://{local_ip}:{PORT}/"

    server_thread = threading.Thread(
        target=run_server,
        name="kindo-fastapi",
        daemon=True,
    )
    server_thread.start()

    input_thread = threading.Thread(
        target=input_hook_listener,
        name="kindo-input-listener",
        daemon=True,
    )
    input_thread.start()

    time.sleep(0.7)
    state.qr_panel = generate_qr_terminal(url)
    print("Çıxmaq üçün Ctrl+C basın.")

    try:
        render_terminal_screen()
    except KeyboardInterrupt:
        pass
    finally:
        print("\nServer bağlanır...")


if __name__ == "__main__":
    main()

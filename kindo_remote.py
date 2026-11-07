import asyncio
import json
import socket
import time
import io
import sys
import qrcode
import qrcode.constants
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, HTMLResponse
import mss
import mss.tools
import pyautogui
import uvicorn
from PIL import Image

# --- Konfiqurasiya ---
PORT = 8765
FPS = 12  # Sanayə 12 kadr (Performance üçün balanslaşdırılmış)
JPEG_QUALITY = 70

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
    print("\n" + "="*30 + " Kİndo REMOTE " + "="*30)
    print(f"URL: {url}")
    print("Telefonunuzla skan edin:\n")
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=1,
        border=1,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    print("="*65 + "\n")

# --- Frontend HTML/JS Şablonu ---
# Bu kod telefonun brauzerində işləyəcək interfeysdir
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="az">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Kindo Remote Session</title>
    <style>
        body { 
            margin: 0; padding: 0; background: #111; color: #eee; 
            font-family: sans-serif; display: flex; flex-direction: column; height: 100vh; 
            touch-action: none; /* Mobil üçün touch events idarəetməsi */
        }
        header { padding: 10px; background: #222; text-align: center; font-weight: bold; }
        #container { flex: 1; display: flex; justify-content: center; align-items: center; overflow: hidden; position: relative; }
        #screen { 
            max-width: 100%; max-height: 100%; object-fit: contain; 
            cursor: crosshair; background: #000; 
        }
        #status { padding: 5px; background: #333; text-align: center; font-size: 0.8rem; }
        .connected { color: #4caf50; }
        .disconnected { color: #f44336; }
    </style>
</head>
<body>
    <header>Kindo Remote - İdarəetmə Paneli</header>
    <div id="container">
        <!-- Ekran streami bu img elementinə gəlir -->
        <img id="screen" src="/stream" alt="Remote Screen">
    </div>
    <div id="status" class="disconnected">Bağlanır...</div>

    <script>
        const screen = document.getElementById('screen');
        const status = document.getElementById('status');
        let ws;
        let isDragging = false;

        function connect() {
            // WebSocket bağlantısı qurulur
            ws = new WebSocket(`ws://${location.host}/ws`);
            
            ws.onopen = () => {
                status.innerText = "Bağlı (Connected)";
                status.className = "connected";
            };
            
            ws.onclose = () => {
                status.innerText = "Bağlantı kəsildi. 2 saniyəyə yenidən cəhd edilir...";
                status.className = "disconnected";
                setTimeout(connect, 2000);
            };

            ws.onerror = (e) => console.error(e);
        }

        // Ekran üzərindəki relative koordinatları tapır (0.0 - 1.0 arası)
        function getCoords(e) {
            const rect = screen.getBoundingClientRect();
            // ClientX/Y ekrandakı absolut nöqtədir, rect.left/top isə elementin yeri
            // Bu hesablamada elementin daxili hissəsinə klikləməni təmin edir
            return {
                x: Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)),
                y: Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height))
            };
        }

        function sendInput(data) {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify(data));
            }
        }

        // --- Mouse Events (Desktop brauzer üçün) ---
        screen.addEventListener('mousedown', (e) => {
            isDragging = true;
            const c = getCoords(e);
            sendInput({ type: 'mouse', action: 'down', x: c.x, y: c.y, button: e.button });
        });

        screen.addEventListener('mouseup', (e) => {
            isDragging = false;
            const c = getCoords(e);
            sendInput({ type: 'mouse', action: 'up', x: c.x, y: c.y, button: e.button });
        });

        screen.addEventListener('mousemove', (e) => {
            if (isDragging) {
                const c = getCoords(e);
                sendInput({ type: 'mouse', action: 'move', x: c.x, y: c.y });
            }
        });

        // --- Touch Events (Telefon üçün) ---
        screen.addEventListener('touchstart', (e) => {
            e.preventDefault();
            const touch = e.touches[0];
            isDragging = true;
            const c = getCoords(touch);
            sendInput({ type: 'mouse', action: 'down', x: c.x, y: c.y, button: 0 });
        }, { passive: false });

        screen.addEventListener('touchmove', (e) => {
            e.preventDefault();
            if (isDragging) {
                const touch = e.touches[0];
                const c = getCoords(touch);
                sendInput({ type: 'mouse', action: 'move', x: c.x, y: c.y });
            }
        }, { passive: false });

        screen.addEventListener('touchend', (e) => {
            e.preventDefault();
            isDragging = false;
            const touch = e.changedTouches[0];
            const c = getCoords(touch);
            sendInput({ type: 'mouse', action: 'up', x: c.x, y: c.y, button: 0 });
        }, { passive: false });

        // --- Keyboard Events ---
        document.addEventListener('keydown', (e) => {
            // Saytın scroll olmaması üçün bu tuşları bloklayaq
            if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', ' '].includes(e.key)) {
                e.preventDefault();
            }
            if (!e.repeat) { // Həmin tuşun bir dəfə basıldığını göndər
                sendInput({ type: 'key', action: 'down', key: e.key, code: e.code });
            }
        });

        document.addEventListener('keyup', (e) => {
            sendInput({ type: 'key', action: 'up', key: e.key, code: e.code });
        });

        connect();
    </script>
</body>
</html>
"""

# --- FastAPI Tətbiqi ---
app = FastAPI(title="Kindo Remote Terminal")

@app.get("/", response_class=HTMLResponse)
async def index():
    """Ana səhifə - İnterfeysi qaytarır"""
    return HTML_TEMPLATE

@app.get("/stream")
async def stream():
    """
    MJPEG Video Stream.
    Ekranı tutub, JPEG formatına çevirir və brauzerə yollayır.
    """
    def event_generator():
        with mss.mss() as sct:
            # 1-ci monitor (adətən əsas ekran)
            monitor = sct.monitors[1] 
            while True:
                im = sct.grab(monitor)
                
                # MSS PNG verir, biz JPEG-a çeviririk ki, fayl kiçik olsun
                png = mss.tools.to_png(im, monitor)
                image = Image.open(io.BytesIO(png))
                
                # Performans üçün, ekranda çox böyükdirsə, azaldırıq (opsional)
                if image.width > 1920:
                    image = image.resize((1920, int(image.height * (1920/image.width))))

                f = io.BytesIO()
                image.save(f, format="JPEG", quality=JPEG_QUALITY)
                data = f.getvalue()
                
                # MJPEG formatında frame göndər
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + data + b'\r\n')
                
                # FPS-lə uyğun pauza
                time.sleep(1 / FPS)

    return StreamingResponse(event_generator(), media_type="multipart/x-mixed-replace;boundary=frame")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint.
    Brauzerdən gələn inputları (mouse, klaviatura) qəbul edir və OS-a tətbiq edir.
    """
    await websocket.accept()
    screen_w, screen_h = pyautogui.size()
    
    # Failsafe (Ctrl+C ilə dayandırmaq üçün) - istəyirsinizsə sökdürün
    pyautogui.FAILSAFE = False 
    
    print(f"[WS] Müştəri qoşuldu. Ekran ölçüsü: {screen_w}x{screen_h}")
    
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            if msg["type"] == "mouse":
                # Normalizə edilmiş koordinatları real pikselə çevir
                x = int(msg["x"] * screen_w)
                y = int(msg["y"] * screen_h)
                
                # Sərhədləri yoxla (güvənlik üçün)
                x = max(0, min(x, screen_w - 1))
                y = max(0, min(y, screen_h - 1))

                if msg["action"] == "move":
                    pyautogui.moveTo(x, y, _pause=False)
                elif msg["action"] == "down":
                    # Sol və ya sağ klik
                    button = 'left' if msg.get("button", 0) == 0 else 'right'
                    pyautogui.mouseDown(x=x, y=y, button=button, _pause=False)
                elif msg["action"] == "up":
                    button = 'left' if msg.get("button", 0) == 0 else 'right'
                    pyautogui.mouseUp(x=x, y=y, button=button, _pause=False)

            elif msg["type"] == "key":
                key = msg["key"]
                # Xüsusi tuşlar (Enter, Shift, etc.)
                # PyAutoGUI üçün düzgün sintaksısdan istifadə et
                if key == 'Enter':
                    key = 'enter'
                elif key == ' ':
                    key = 'space'
                elif key == 'Shift':
                    key = 'shift'
                
                if msg["action"] == "down":
                    pyautogui.keyDown(key, _pause=False)
                elif msg["action"] == "up":
                    pyautogui.keyUp(key, _pause=False)
                    
    except WebSocketDisconnect:
        print("[WS] Müştəri ayrıldı.")

# --- Main Executor ---
if __name__ == "__main__":
    ip = get_local_ip()
    url = f"http://{ip}:{PORT}"
    
    # Terminalda QR kod göstər
    generate_qr_terminal(url)
    
    # Uvicorn serveri başlat
    print(f"Server {url} ünvanında işləyir... (Dayandırmaq üçün Ctrl+C)")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")

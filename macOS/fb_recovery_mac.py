#!/usr/local/bin/python3
# -*- coding: utf-8 -*-
"""
Facebook Hacked Recovery Tool — macOS
Python 3.11 | selenium | webdriver-manager | fake-useragent
"""

import json
import os
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from typing import Callable, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
# ChromeDriverManager replaced by selenium built-in

try:
    from PIL import Image, ImageTk
    import io
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ---------------------------------------------------------------------------
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36"
)

RECOVERY_URL = (
    "https://www.facebook.com/login/identify/"
    "?ctx=self_identify_hacked&ars=facebook_login"
)

SUPPORT_JS = """
const targets = ["Nhận hỗ trợ","Get support","Get Support","Contact support",
                 "Liên hệ hỗ trợ","Chat với AI","Chat with AI"];
const els = document.querySelectorAll("button,a,div[role='button'],span,div");
for (const el of els) {
    const txt = (el.innerText||'').trim();
    if (txt.length > 90) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width===0||rect.height===0) continue;
    const style = getComputedStyle(el);
    if (style.display==='none'||style.visibility==='hidden'||style.opacity==='0') continue;
    if (el.closest('#pageFooter,footer')) continue;
    for (const t of targets) {
        if (txt.toLowerCase()===t.toLowerCase()||txt.toLowerCase().includes(t.toLowerCase()))
            return txt;
    }
}
return null;
"""


# ---------------------------------------------------------------------------
import subprocess
import os
import socket
import socketserver
import http.server
import base64
import urllib.parse


class ProxyBridge:
    """Local HTTP proxy bridge — forward traffic qua proxy có auth.
    Chrome connect vào localhost:port (không auth), bridge tự thêm auth.
    Cho phép dùng --headless=new vì không cần Chrome Extension.
    """
    def __init__(self, upstream: str):
        self.upstream = upstream  # ip:port:user:pass hoặc http://user:pass@ip:port
        self._server = None
        self._thread = None
        self.local_port = None
        self._parse()

    def _parse(self):
        p = self.upstream
        if p.startswith("http://") or p.startswith("https://"):
            import re
            m = re.match(r'https?://([^:]+):([^@]+)@([^:]+):(\d+)', p)
            if m:
                self.user, self.pw, self.host, self.port = m.group(1), m.group(2), m.group(3), m.group(4)
        elif p.count(":") == 3:
            parts = p.split(":")
            self.host, self.port, self.user, self.pw = parts
        elif p.count(":") == 1:
            self.host, self.port = p.split(":")
            self.user = self.pw = ""
        else:
            self.host = p; self.port = "3128"; self.user = self.pw = ""

    def start(self) -> int:
        upstream = self
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_CONNECT(self):
                try:
                    host, port = self.path.split(":")
                    sock = socket.create_connection((upstream.host, int(upstream.port)), timeout=10)
                    if upstream.user:
                        cred = base64.b64encode(f"{upstream.user}:{upstream.pw}".encode()).decode()
                        sock.sendall(f"CONNECT {self.path} HTTP/1.1\r\nHost: {self.path}\r\nProxy-Authorization: Basic {cred}\r\nConnection: keep-alive\r\n\r\n".encode())
                    else:
                        sock.sendall(f"CONNECT {self.path} HTTP/1.1\r\nHost: {self.path}\r\nConnection: keep-alive\r\n\r\n".encode())
                    resp = b""
                    while b"\r\n\r\n" not in resp:
                        resp += sock.recv(4096)
                    self.send_response(200, "Connection established")
                    self.end_headers()
                    self._tunnel(self.connection, sock)
                except Exception as e:
                    self.send_error(502)
            def _tunnel(self, a, b):
                import select
                a.setblocking(False); b.setblocking(False)
                while True:
                    r, _, _ = select.select([a, b], [], [], 10)
                    if not r: break
                    for s in r:
                        try:
                            d = s.recv(65536)
                            if not d: return
                            (b if s is a else a).sendall(d)
                        except: return
            def do_GET(self): self._forward()
            def do_POST(self): self._forward()
            def _forward(self):
                try:
                    parsed = urllib.parse.urlparse(self.path)
                    sock = socket.create_connection((upstream.host, int(upstream.port)), timeout=10)
                    headers = dict(self.headers)
                    if upstream.user:
                        cred = base64.b64encode(f"{upstream.user}:{upstream.pw}".encode()).decode()
                        headers["Proxy-Authorization"] = f"Basic {cred}"
                    body = self.rfile.read(int(headers.get("Content-Length", 0)))
                    req = f"{self.command} {self.path} HTTP/1.1\r\n"
                    req += "".join(f"{k}: {v}\r\n" for k, v in headers.items()) + "\r\n"
                    sock.sendall(req.encode() + body)
                    resp = b""
                    while True:
                        chunk = sock.recv(65536)
                        if not chunk: break
                        resp += chunk
                    self.connection.sendall(resp)
                except: self.send_error(502)

        self._server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self._server.allow_reuse_address = True
        self.local_port = self._server.server_address[1]
        import threading as _t
        self._thread = _t.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.local_port

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None

class SSHTunnel:
    """SSH dynamic SOCKS5 tunnel qua VPS — dùng ssh -D."""

    def __init__(self, host: str, user: str, key_path: str, local_port: int, ssh_port: int = 22):
        self.host = host
        self.user = user
        self.key_path = os.path.expanduser(key_path)
        self.local_port = local_port
        self.ssh_port = ssh_port
        self._proc = None

    def start(self) -> bool:
        """Start SSH SOCKS5 tunnel. Return True nếu thành công."""
        import socket
        # Kill process cũ trên port này nếu có
        try:
            subprocess.run(
                ["pkill", "-f", f"ssh.*-D.*{self.local_port}"],
                capture_output=True
            )
            time.sleep(0.5)
        except Exception:
            pass

        cmd = [
            "ssh",
            "-D", str(self.local_port),
            "-N",  # không execute lệnh remote
            "-o", "StrictHostKeyChecking=no",
            "-o", "ServerAliveInterval=10",
            "-o", "ConnectTimeout=15",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ControlMaster=no",
            "-i", self.key_path,
            "-p", str(self.ssh_port),
            f"{self.user}@{self.host}",
        ]
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Đợi tunnel ready bằng cách check port open
            for _ in range(20):  # max 4 giây
                time.sleep(0.2)
                if self._proc.poll() is not None:
                    return False  # process đã chết
                try:
                    s = socket.create_connection(("127.0.0.1", self.local_port), timeout=0.5)
                    s.close()
                    return True  # port open = tunnel ready
                except (ConnectionRefusedError, OSError):
                    continue
            return False
        except Exception:
            return False

    def stop(self):
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                pass
            self._proc = None

    def proxy_url(self) -> str:
        return f"socks5://127.0.0.1:{self.local_port}"


class VPSPool:
    """Parse VPS list từ textarea.
    Format đơn giản — giống Termius:
      ip user [port]
    Ví dụ:
      178.128.113.1 root
      45.77.10.20 root 2222
    Key mặc định: ~/.ssh/vps_key_openssh (hoặc ~/.ssh/id_rsa nếu không có)
    """

    DEFAULT_KEYS = [
        "~/.ssh/vps_key_openssh",
        "~/.ssh/id_rsa",
        "~/.ssh/id_ed25519",
    ]

    def __init__(self, raw: str):
        self.entries: list = []
        if not raw or not raw.strip():
            return
        # Tìm key mặc định có sẵn
        default_key = None
        for k in self.DEFAULT_KEYS:
            expanded = os.path.expanduser(k)
            if os.path.isfile(expanded):
                default_key = expanded
                break

        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                entry = {
                    "host": parts[0],
                    "user": parts[1],
                    "port": int(parts[2]) if len(parts) > 2 else 22,
                    "key": parts[3] if len(parts) > 3 else default_key,
                }
                self.entries.append(entry)

    def get(self, index: int) -> Optional[dict]:
        if not self.entries:
            return None
        return self.entries[index % len(self.entries)]


# ---------------------------------------------------------------------------
class ProxyPool:
    def __init__(self, raw: str):
        self.proxies: list = []
        if not raw or not raw.strip():
            return
        raw = raw.strip()
        # Check if it's a file path
        import os
        if os.path.isfile(raw):
            try:
                with open(raw, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except Exception:
                lines = []
        else:
            lines = raw.splitlines()
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                self.proxies.append(line)

    def get(self, index: int) -> Optional[str]:
        if not self.proxies:
            return None
        return self.proxies[index % len(self.proxies)]


import hashlib
import math

class FingerprintProfile:
    """Generate deterministic per-nick fingerprint từ email hash."""

    GPU_LIST = [
        ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (AMD)", "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) HD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ]
    SCREENS = [(1920,1080),(1366,768),(1536,864),(1440,900),(1280,720),(1600,900)]
    HW_CONCURRENCY = [2, 4, 4, 8, 8, 8, 16]
    DEVICE_MEMORY = [2, 4, 4, 8, 8]
    TIMEZONES = ["Asia/Ho_Chi_Minh","Asia/Singapore","Asia/Bangkok","Asia/Manila","America/New_York","Europe/London"]

    def __init__(self, email: str):
        seed_bytes = hashlib.md5(email.encode()).digest()
        self._seed = int.from_bytes(seed_bytes, "big")

    def _pick(self, lst):
        idx = self._seed % len(lst)
        self._seed = (self._seed * 1103515245 + 12345) & 0x7fffffff
        return lst[idx]

    def _noise(self):
        val = (self._seed % 100) / 10000.0
        self._seed = (self._seed * 1103515245 + 12345) & 0x7fffffff
        return val

    def generate(self) -> dict:
        screen = self._pick(self.SCREENS)
        gpu = self._pick(self.GPU_LIST)
        return {
            "screenWidth": screen[0],
            "screenHeight": screen[1],
            "hardwareConcurrency": self._pick(self.HW_CONCURRENCY),
            "deviceMemory": self._pick(self.DEVICE_MEMORY),
            "timezone": self._pick(self.TIMEZONES),
            "gpuVendor": gpu[0],
            "gpuRenderer": gpu[1],
            "canvasNoise": self._noise(),
            "audioNoise": self._noise(),
        }


# ---------------------------------------------------------------------------
class AccountWorker(threading.Thread):
    def __init__(
        self,
        email: str,
        proxy: Optional[str],
        idx: int,
        callbacks: dict,
        stop_event: threading.Event,
        vps: Optional[dict] = None,
        semaphore: Optional[threading.Semaphore] = None,
        vps_list: Optional[list] = None,
        proxy_list: Optional[list] = None,
    ):
        super().__init__(daemon=True)
        self.email = email
        self.proxy = proxy
        self.idx = idx
        self._stop = stop_event
        self.driver: Optional[webdriver.Chrome] = None
        self._attempt = 0
        self.callbacks = callbacks
        self.vps = vps  # {"host", "user", "key", "port"}
        self._tunnel: Optional[SSHTunnel] = None
        self._semaphore = semaphore
        self._vps_list = vps_list or ([vps] if vps else [])
        self._proxy_list = proxy_list or ([proxy] if proxy else [])
        self._screenshot_active = False
        self._proxy_bridge = None

    def _start_tunnel(self) -> Optional[str]:
        """Start SSH tunnel nếu có VPS. Return proxy_url hoặc None."""
        if not self.vps:
            return None
        local_port = 10000 + self.idx
        # Stop tunnel cũ nếu có
        if self._tunnel:
            self._tunnel.stop()
        tunnel = SSHTunnel(
            host=self.vps["host"],
            user=self.vps["user"],
            key_path=self.vps["key"],
            local_port=local_port,
            ssh_port=self.vps.get("port", 22),
        )
        self.callbacks["log"](self.email, f"[VPS] SSH → {self.vps['host']} port:{local_port} key:{self.vps.get('key','NO_KEY')}")
        ok = tunnel.start()
        if ok:
            self._tunnel = tunnel
            self.callbacks["log"](self.email, f"[VPS] ✓ Tunnel SOCKS5://127.0.0.1:{local_port}")
            return tunnel.proxy_url()
        else:
            # Log stderr để debug
            try:
                err_cmd = ["ssh", "-v", "-o", "StrictHostKeyChecking=no",
                           "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
                           "-i", tunnel.key_path, f"{self.vps['user']}@{self.vps['host']}", "exit"]
                import subprocess
                r = subprocess.run(err_cmd, capture_output=True, timeout=8, text=True)
                self.callbacks["log"](self.email, f"[VPS] ✗ SSH stderr: {r.stderr[-200:]}")
            except Exception as e:
                self.callbacks["log"](self.email, f"[VPS] ✗ SSH test err: {e}")
            return None

    # ------------------------------------------------------------------
    def run(self):
        total = len(self._vps_list) + len(self._proxy_list)
        while not self._stop.is_set():
            self._attempt += 1
            # Xoay vòng liên tục qua VPS rồi proxy rồi lại VPS...
            attempt_idx = (self._attempt - 1) % max(total, 1)
            if self._vps_list and attempt_idx < len(self._vps_list):
                self.vps = self._vps_list[attempt_idx]
                self.proxy = None
                self.callbacks["log"](self.email, f"[Attempt {self._attempt}] VPS: {self.vps['host']}")
            else:
                proxy_idx = attempt_idx - len(self._vps_list)
                self.proxy = self._proxy_list[proxy_idx % len(self._proxy_list)] if self._proxy_list else None
                self.vps = None
                self.callbacks["log"](self.email, f"[Attempt {self._attempt}] Proxy: {self.proxy}")
            success = False
            self._safe_quit()
            if self._semaphore:
                self.callbacks["log"](self.email, "[WAIT] Waiting for Chrome slot...")
                while not self._semaphore.acquire(timeout=2):
                    if self._stop.is_set():
                        return  # STOP ALL pressed while waiting
                self.callbacks["log"](self.email, "[SLOT] Chrome slot acquired")
            try:
                self._make_driver()
                self._start_screenshot_thread()
                success = self._do_attempt()
            except Exception as exc:
                self.callbacks["log"](self.email, f"[ERROR] {exc}")
                success = False
            finally:
                if not success:
                    self._safe_quit()
                if self._semaphore:
                    self._semaphore.release()

            if success:
                # SUCCESS — không bao giờ tắt bất cứ thứ gì
                self.callbacks["result"](self.email, "SUCCESS")
                self.callbacks["success_keep"](self.email)
                # Giữ driver + tunnel + screenshot mãi mãi — không tắt dù STOP ALL
                # Chrome view của user hoàn toàn độc lập, không bị đụng
                while True:
                    time.sleep(30)  # sleep vô hạn, không bao giờ thoát
                # (unreachable — SUCCESS worker không bao giờ kết thúc)

            if not self._stop.is_set():
                self.callbacks["log"](self.email, f"[RETRY] Chờ 15s trước lần thử {self._attempt + 1}...")
                for _ in range(15):
                    if self._stop.is_set():
                        break
                    time.sleep(1)

        self._stop_screenshot_thread()
        self.callbacks["result"](self.email, "STOPPED")
        self._safe_quit()

    # ------------------------------------------------------------------
    def _safe_quit(self):
        drv = self.driver
        self.driver = None
        if drv:
            # ĐÚNG THỨ TỰ: quit() trước (chromedriver còn sống → Chrome nhận lệnh đóng)
            # Sau đó mới kill chromedriver process
            try:
                drv.quit()  # Gửi quit tới Chrome qua chromedriver đang sống
            except Exception:
                pass
            try:
                drv.service.process.kill()  # Kill chromedriver sau
            except Exception:
                pass
            time.sleep(1.5)  # Chờ Chrome thực sự chết
        if self._tunnel:
            self._tunnel.stop()
            self._tunnel = None

    def quit_driver(self):
        """Called by GUI when user presses STOP."""
        self._safe_quit()

    # ------------------------------------------------------------------
    def _make_driver(self):
        options = Options()
        fp = FingerprintProfile(self.email).generate()
        options.add_argument(f"user-agent={DESKTOP_UA}")
        options.add_argument("--window-size=1280,900")
        # headless=new — ẩn hoàn toàn, thumbnail vẫn hoạt động qua CDP screenshot
        options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--lang=en-US")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-features=Translate")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_experimental_option(
            "prefs", {"intl.accept_languages": "en-US,en"}
        )
        # Disable WebRTC để không lộ IP thật
        options.add_argument("--disable-features=WebRtcHideLocalIpsWithMdns")
        options.add_experimental_option("prefs", {
            "intl.accept_languages": "en-US,en",
            "webrtc.ip_handling_policy": "disable_non_proxied_udp",
            "webrtc.multiple_routes_enabled": False,
            "webrtc.nonproxied_udp_enabled": False,
        })

        # VPS SSH tunnel ưu tiên hơn proxy
        tunnel_url = self._start_tunnel()
        proxy_ext_dir = None
        if tunnel_url:
            options.add_argument(f"--proxy-server={tunnel_url}")
        elif self.proxy:
            proxy_ext_dir = self._make_proxy_extension(self.proxy)
            if proxy_ext_dir:
                options.add_argument(f"--load-extension={proxy_ext_dir}")
                self.callbacks["log"](self.email, f"[Proxy] Extension loaded: {self.proxy}")
            else:
                options.add_argument(f"--proxy-server={self.proxy}")
                self.callbacks["log"](self.email, f"[Proxy] {self.proxy}")

        service = Service()
        self.driver = webdriver.Chrome(service=service, options=options)
        self._proxy_ext_dir = proxy_ext_dir

        # CDP: override UA + platform + disable WebRTC leak
        self.driver.execute_cdp_cmd(
            "Network.setUserAgentOverride",
            {
                "userAgent": DESKTOP_UA,
                "platform": "Win32",
                "acceptLanguage": "en-US,en;q=0.9",
            },
        )
        # Disable WebRTC via CDP
        self.driver.execute_cdp_cmd("Network.enable", {})
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": f"""
(function() {{
    // === NAVIGATOR ===
    Object.defineProperty(navigator,'webdriver',{{get:()=>undefined}});
    Object.defineProperty(navigator,'platform',{{get:()=>'Win32'}});
    Object.defineProperty(navigator,'maxTouchPoints',{{get:()=>0}});
    Object.defineProperty(navigator,'vendor',{{get:()=>'Google Inc.'}});
    Object.defineProperty(navigator,'languages',{{get:()=>['en-US','en']}});
    Object.defineProperty(navigator,'hardwareConcurrency',{{get:()=>{fp['hardwareConcurrency']}}});
    Object.defineProperty(navigator,'deviceMemory',{{get:()=>{fp['deviceMemory']}}});

    // === SCREEN ===
    Object.defineProperty(screen,'width',{{get:()=>{fp['screenWidth']}}});
    Object.defineProperty(screen,'height',{{get:()=>{fp['screenHeight']}}});
    Object.defineProperty(screen,'availWidth',{{get:()=>{fp['screenWidth']}}});
    Object.defineProperty(screen,'availHeight',{{get:()=>{fp['screenHeight']}-40}});
    Object.defineProperty(screen,'colorDepth',{{get:()=>24}});
    Object.defineProperty(screen,'pixelDepth',{{get:()=>24}});

    // === TIMEZONE ===
    const _tz = '{fp['timezone']}';
    const _origDTF = Intl.DateTimeFormat;
    Intl.DateTimeFormat = function(loc, opts) {{
        if (!opts) opts = {{}};
        if (!opts.timeZone) opts.timeZone = _tz;
        return new _origDTF(loc, opts);
    }};
    Intl.DateTimeFormat.prototype = _origDTF.prototype;

    // === WEBGL FINGERPRINT ===
    const _origGetParam = WebGLRenderingContext.prototype.getParameter;
    const _origGetParam2 = WebGL2RenderingContext ? WebGL2RenderingContext.prototype.getParameter : null;
    function patchWebGL(proto) {{
        proto.getParameter = function(param) {{
            if (param === 37445) return '{fp['gpuVendor']}';
            if (param === 37446) return '{fp['gpuRenderer']}';
            return _origGetParam.call(this, param);
        }};
    }}
    patchWebGL(WebGLRenderingContext.prototype);
    if (_origGetParam2) patchWebGL(WebGL2RenderingContext.prototype);

    // === CANVAS NOISE ===
    const _noise = {fp['canvasNoise']};
    const _origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type, quality) {{
        const ctx = this.getContext('2d');
        if (ctx) {{
            const img = ctx.getImageData(0, 0, this.width || 1, this.height || 1);
            img.data[0] = (img.data[0] + Math.floor(_noise * 255)) % 256;
            ctx.putImageData(img, 0, 0);
        }}
        return _origToDataURL.call(this, type, quality);
    }};

    // === AUDIO CONTEXT NOISE ===
    const _audioNoise = {fp['audioNoise']};
    const _origGetChannelData = AudioBuffer.prototype.getChannelData;
    AudioBuffer.prototype.getChannelData = function(channel) {{
        const data = _origGetChannelData.call(this, channel);
        for (let i = 0; i < data.length; i += 100) {{
            data[i] += _audioNoise * 0.0001;
        }}
        return data;
    }};

    // === BLOCK WEBRTC ===
    const origRTC = window.RTCPeerConnection || window.webkitRTCPeerConnection;
    if (origRTC) {{
        const fakeRTC = function(cfg) {{
            if (cfg && cfg.iceServers) cfg.iceServers = [];
            return new origRTC(cfg);
        }};
        fakeRTC.prototype = origRTC.prototype;
        window.RTCPeerConnection = window.webkitRTCPeerConnection = fakeRTC;
    }}

    // === CHROME OBJECT ===
    if (!window.chrome) {{
        window.chrome = {{ runtime: {{}}, loadTimes: function(){{}}, csi: function(){{}} }};
    }}

    // === PLUGINS (non-empty) ===
    Object.defineProperty(navigator,'plugins',{{get:()=>{{
        return [
            {{name:'Chrome PDF Plugin',filename:'internal-pdf-viewer',description:'Portable Document Format'}},
            {{name:'Chrome PDF Viewer',filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai',description:''}},
            {{name:'Native Client',filename:'internal-nacl-plugin',description:''}}
        ];
    }}}});
}})();
"""
            },
        )

    def _make_proxy_extension(self, proxy_str: str):
        """Tạo Chrome extension tạm để xử lý proxy auth. Return đường dẫn dir hoặc None."""
        try:
            # Parse formats: ip:port:user:pass hoặc http://user:pass@ip:port
            host = port = user = pw = ""
            if proxy_str.startswith("http://") or proxy_str.startswith("https://"):
                import re
                m = re.match(r'https?://([^:]+):([^@]+)@([^:]+):(\d+)', proxy_str)
                if m:
                    user, pw, host, port = m.group(1), m.group(2), m.group(3), m.group(4)
            elif proxy_str.count(":") == 3:
                parts = proxy_str.split(":")
                host, port, user, pw = parts[0], parts[1], parts[2], parts[3]
            elif proxy_str.count(":") == 1:
                host, port = proxy_str.split(":")
            if not host or not port:
                return None
            d = tempfile.mkdtemp(prefix="crx_proxy_")
            manifest = {
                "version": "1.0.0", "manifest_version": 2,
                "name": "Proxy Auth", "permissions": ["proxy", "webRequest", "webRequestBlocking", "<all_urls>"],
                "background": {"scripts": ["bg.js"]},
            }
            bg = f"""
var config = {{mode:"fixed_servers",rules:{{singleProxy:{{scheme:"http",host:"{host}",port:parseInt("{port}")}},bypassList:["localhost"]}}}};
chrome.proxy.settings.set({{value:config,scope:"regular"}},function(){{}});
chrome.webRequest.onAuthRequired.addListener(
  function(details) {{ return {{authCredentials:{{username:"{user}",password:"{pw}"}}}}; }},
  {{urls:["<all_urls>"]}}, ["blocking"]
);
"""
            with open(os.path.join(d, "manifest.json"), "w") as f:
                json.dump(manifest, f)
            with open(os.path.join(d, "bg.js"), "w") as f:
                f.write(bg)
            return d
        except Exception:
            return None

    def _show_window(self):
        try:
            self.driver.set_window_position(0, 0)
            self.driver.maximize_window()
        except Exception:
            pass

    def _start_screenshot_thread(self):
        self._screenshot_active = True
        import threading as _t
        def _loop():
            while self._screenshot_active and not self._stop.is_set():
                try:
                    if self.driver:
                        png_b64 = self.driver.execute_cdp_cmd("Page.captureScreenshot", {"format": "jpeg", "quality": 25})
                        if png_b64 and "data" in png_b64:
                            self.callbacks.get("thumbnail", lambda e, d: None)(self.email, png_b64["data"])
                except Exception:
                    pass
                import time as _t2
                _t2.sleep(2)
        _t.Thread(target=_loop, daemon=True).start()

    def _stop_screenshot_thread(self):
        self._screenshot_active = False

    # ------------------------------------------------------------------
    def _do_attempt(self) -> bool:
        driver = self.driver

        # 1. Navigate
        self.callbacks["log"](self.email, f"[1] Navigate → {RECOVERY_URL}")
        driver.get(RECOVERY_URL)
        WebDriverWait(driver, 20).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(2)

        if "m.facebook.com" in driver.current_url:
            self.callbacks["log"](self.email, "[ABORT] Mobile redirect")
            return False

        # Check trang lỗi proxy/network
        page_src = driver.page_source or ""
        if "ERR_" in driver.current_url or ("This site can" in page_src and "ERR_" in page_src):
            self.callbacks["log"](self.email, f"[ABORT] Page load error — likely proxy fail. URL: {driver.current_url}")
            return False

        # 2. Input email
        self.callbacks["log"](self.email, f"[2] Input email: {self.email}")
        self._input_email_direct()

        # 3. Click Continue (button#did_submit only)
        self.callbacks["log"](self.email, "[3] Click Continue...")
        self._click_continue_direct()
        time.sleep(4)
        self.callbacks["log"](self.email, f"[3] URL: {driver.current_url}")

        # 4. Click Recover (a[aria-label='Recover'] only) — chỉ khi ở /recover/
        if "/recover/" in driver.current_url:
            self.callbacks["log"](self.email, "[4] Click Recover...")
            self._click_recover_direct()
            time.sleep(3)
            self.callbacks["log"](self.email, f"[4] URL: {driver.current_url}")
        else:
            self.callbacks["log"](self.email, f"[4] Skip — not on recover page")

        # 5. Check support button — delay 10s rồi mới tắt nếu không có
        time.sleep(3)
        if self._check_support_button():
            return True
        # Đợi thêm 10s (tổng ~13s) trước khi kết luận không có Get Support
        time.sleep(10)
        if self._check_support_button():
            return True

        return False

    # ------------------------------------------------------------------
    # Simple direct methods (no fallback complexity)
    # ------------------------------------------------------------------

    def _input_email_direct(self):
        driver = self.driver
        try:
            f = driver.find_element(By.XPATH, '//input[@placeholder="Mobile number or email address"]')
            f.click(); f.clear(); f.send_keys(self.email)
            self.callbacks["log"](self.email, f"[Input] ✓ {self.email}")
            return
        except Exception:
            pass
        try:
            f = driver.find_element(By.XPATH, '//input[@placeholder="Số điện thoại di động hoặc địa chỉ email"]')
            f.click(); f.clear(); f.send_keys(self.email)
            self.callbacks["log"](self.email, f"[Input] ✓ {self.email}")
        except Exception as e:
            self.callbacks["log"](self.email, f"[Input] ✗ {e}")

    def _click_continue_direct(self):
        driver = self.driver
        try:
            btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.ID, "did_submit"))
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            btn.click()
            self.callbacks["log"](self.email, "[Continue] ✓")
        except Exception as e:
            self.callbacks["log"](self.email, f"[Continue] ✗ {e}")

    def _click_recover_direct(self):
        """Click <a aria-label='Recover'> — xác nhận từ DOM inspection."""
        driver = self.driver
        time.sleep(1)
        try:
            btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.XPATH, '//a[@aria-label="Recover"]'))
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            btn.click()
            self.callbacks["log"](self.email, "[Recover] ✓")
            return
        except Exception:
            pass
        try:
            btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, '//a[@aria-label="Khôi phục"]'))
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            btn.click()
            self.callbacks["log"](self.email, "[Recover] ✓ (Khôi phục)")
        except Exception as e:
            self.callbacks["log"](self.email, f"[Recover] ✗ {e}")

    # ------------------------------------------------------------------
    def _input_email(self, wait: WebDriverWait) -> bool:
        # Selector chính xác từ DOM inspection:
        # Trang identify có 2 input[name=email] — phân biệt bằng placeholder
        selectors = [
            '//input[@placeholder="Mobile number or email address"]',  # chính xác nhất
            '//input[@placeholder="Số điện thoại di động hoặc địa chỉ email"]',
            '//input[@name="email"][@type="text"]',  # identify input, không phải login
        ]
        for xpath in selectors:
            try:
                els = self.driver.find_elements(By.XPATH, xpath)
                visible = [e for e in els if e.is_displayed()]
                if visible:
                    f = visible[0]
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", f)
                    f.click()
                    f.clear()
                    f.send_keys(self.email)
                    self.callbacks["log"](self.email, f"[Input] ✓ Email entered")
                    return True
            except Exception:
                pass

        # CSS fallback — input visible cuối cùng
        try:
            els = self.driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='email']")
            visible = [e for e in els if e.is_displayed()]
            if visible:
                f = visible[-1]  # lấy cái cuối — thường là form identify, không phải login
                f.click(); f.clear(); f.send_keys(self.email)
                self.callbacks["log"](self.email, "[Input] ✓ Email entered (fallback)")
                return True
        except Exception:
            pass

        self.callbacks["log"](self.email, "[Input] ✗ FAIL — no email field found")
        return False

    # ------------------------------------------------------------------
    def _click_continue(self, wait: WebDriverWait) -> bool:
        """Bấm Continue — KHÔNG bấm Log in.
        button#did_submit chỉ tồn tại trong identify form, không bao giờ ở header.
        """
        driver = self.driver

        # Primary: button#did_submit — ID duy nhất trong identify form
        try:
            btn = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button#did_submit"))
            )
            btn_text = (btn.text or btn.get_attribute("value") or "").strip()
            self.callbacks["log"](self.email, f"[Continue] Found button text: '{btn_text}'")
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            btn.click()
            self.callbacks["log"](self.email, f"[Continue] ✓ Clicked button#did_submit")
            return True
        except Exception as exc:
            self.callbacks["log"](self.email, f"[Continue] button#did_submit not found: {exc}")

        # Fallback: button[name="did_submit"]
        try:
            btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[name="did_submit"]'))
            )
            btn_text = (btn.text or btn.get_attribute("value") or "").strip()
            self.callbacks["log"](self.email, f"[Continue] Found fallback button text: '{btn_text}'")
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            btn.click()
            self.callbacks["log"](self.email, "[Continue] ✓ Clicked button[name='did_submit'] (fallback)")
            return True
        except Exception as exc2:
            self.callbacks["log"](self.email, f"[Continue] fallback also failed: {exc2}")

        self.callbacks["log"](self.email, "[Continue] ✗ Not found")
        return False

    # ------------------------------------------------------------------
    def _handle_account_selection(self):
        """Chỉ chạy nếu đang ở trang recover — không chạy trên identify/login."""
        driver = self.driver
        # BUG FIX: nếu vẫn ở identify/login page → skip hoàn toàn
        current = driver.current_url
        if "/login/" in current or "identify" in current:
            self.callbacks["log"](self.email, "[Account Select] Skipped — still on login/identify page")
            return
        try:
            time.sleep(1)
            # Chỉ tìm account picker — XPath từ bytecode gốc EXE
            result = driver.execute_script("""
                const FORBIDDEN = ["log in","login","sign up","sign in","đăng nhập","đăng ký",
                                   "recover","this isn't me","back to login","continue","tiếp tục"];
                const items = document.querySelectorAll("a[contains], div[role='button'], li");
                for (const el of items) {
                    const txt = (el.innerText||'').trim();
                    if (txt.length < 5 || txt.length > 80) continue;
                    const low = txt.toLowerCase();
                    if (FORBIDDEN.some(f => low.includes(f))) continue;
                    const rect = el.getBoundingClientRect();
                    if (rect.width===0||rect.height===0) continue;
                    if (rect.y < 150) continue;
                    el.click();
                    return txt;
                }
                return null;
            """)
            if result:
                self.callbacks["log"](self.email, f"[Account Select] Clicked: {result[:40]}")
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _click_recover_button(self, wait: WebDriverWait):
        """Click nút 'Recover' nằm TRONG CARD giữa trang — không phải header.
        Gốc từ bytecode: span[contains(text(),'Recover')]/ancestor::div[@role='none']
        """
        driver = self.driver
        time.sleep(2)

        # DOM-confirmed: <a aria-label="Recover"> — selector chính xác nhất
        try:
            for xpath in [
                '//a[@aria-label="Recover"]',
                '//a[@aria-label="Khôi phục"]',
            ]:
                els = driver.find_elements(By.XPATH, xpath)
                for el in els:
                    if el.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                        time.sleep(0.3)
                        el.click()
                        self.callbacks["log"](self.email, "[Recover] ✓ Clicked (aria-label)")
                        return
        except Exception:
            pass

        # JS: tìm nút Recover trong card — dùng y-position để phân biệt với header
        try:
            result = driver.execute_script("""
                const ALLOWED = ["Recover", "Khôi phục"];
                const FORBIDDEN = ["this isn't me","log in","login","back to login",
                                   "đây không phải tôi","forgotten account","sign up"];

                // Scan tất cả elements có text "Recover"
                const all = document.querySelectorAll("*");
                const candidates = [];
                for (const el of all) {
                    // Chỉ lấy leaf node có text đúng
                    if (el.children.length > 0) continue;
                    const txt = (el.innerText||el.textContent||'').trim();
                    if (!ALLOWED.includes(txt)) continue;
                    if (FORBIDDEN.some(f => txt.toLowerCase().includes(f))) continue;
                    const rect = el.getBoundingClientRect();
                    if (rect.width===0||rect.height===0) continue;
                    // Header thường y < 80px — bỏ qua
                    if (rect.y < 80) continue;
                    candidates.push({el, txt, y: rect.y});
                }

                if (candidates.length === 0) return null;

                // Lấy cái có y thấp nhất (trong card, không phải header)
                candidates.sort((a,b) => a.y - b.y);
                const {el, txt} = candidates[0];

                // Leo lên ancestor clickable
                let target = el;
                let p = el.parentElement;
                for (let i=0; i<8; i++) {
                    if (!p) break;
                    const role = p.getAttribute('role');
                    const tag = p.tagName;
                    if (role==='button'||role==='none'||tag==='A'||tag==='BUTTON') {
                        target = p; break;
                    }
                    p = p.parentElement;
                }
                target.scrollIntoView({block:'center'});
                target.click();
                return txt;
            """)
            if result:
                self.callbacks["log"](self.email, f"[Recover] ✓ Clicked (JS): '{result}'")
            else:
                self.callbacks["log"](self.email, "[Recover] ✗ Recover button not found")
        except Exception as exc:
            self.callbacks["log"](self.email, f"[Recover] Error: {exc}")

    # ------------------------------------------------------------------
    def _check_support_button(self) -> bool:
        driver = self.driver
        try:
            result = driver.execute_script(SUPPORT_JS)
            if result:
                self.callbacks["log"](
                    self.email, f"[Support] Found button: '{result}'"
                )
                return True
        except Exception as exc:
            self.callbacks["log"](self.email, f"[Support check] {exc}")
        return False


# ---------------------------------------------------------------------------
class FBHackedRecoveryTool(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FB Hacked Recovery Tool")
        self.geometry("1100x750")
        self.resizable(True, True)
        self.configure(bg="#1e1e2e")

        self._workers: list = []
        self._total_accounts = 0
        self._semaphore: threading.Semaphore = threading.Semaphore(5)
        self._success_emails: set = set()  # emails đã SUCCESS — Chrome giữ nguyên
        self._success_worker_info: dict = {}  # email → {driver, proxy, tunnel, url} — giữ sau STOP
        self._view_drivers: dict = {}  # email → selenium driver của Chrome view đang mở
        self._lock = threading.Lock()
        self._loop_active = False   # True khi đang chạy vòng lặp vô hạn
        self._loop_stop = threading.Event()  # set() để dừng vòng lặp

        # VPS list: list of dict {host, user, key, status}
        self._vps_list: list = []

        # Stats variables
        self._stats_vars = {
            "total": tk.StringVar(value="0"),
            "running": tk.StringVar(value="0"),
            "success": tk.StringVar(value="0"),
            "failed": tk.StringVar(value="0"),
            "pending": tk.StringVar(value="0"),
            "vps": tk.StringVar(value="0 servers"),
            "proxies": tk.StringVar(value="0 entries"),
        }

        # Result tracking for stats
        self._result_rows: dict = {}
        self._status_counts = {"running": 0, "success": 0, "failed": 0}

        self._build_ui()
        self._load_state()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # Kill orphan chromedriver processes (PPID=1) còn sót từ session cũ
        # Chúng spawn Chrome không headless → hiện Dock icon
        try:
            r = subprocess.run(
                ["pgrep", "-f", "chromedriver.*fb_recovery\|chromedriver.*fb_view"],
                capture_output=True, text=True
            )
            # Kill chromedriver orphan có PPID=1 (không còn parent)
            r2 = subprocess.run(["pgrep", "chromedriver"], capture_output=True, text=True)
            for pid in r2.stdout.strip().split():
                if pid:
                    ppid_r = subprocess.run(["ps", "-p", pid, "-o", "ppid="], capture_output=True, text=True)
                    ppid = ppid_r.stdout.strip()
                    if ppid == "1":  # orphan
                        subprocess.run(["kill", "-9", pid], capture_output=True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _kill_stale_view_chromes(self):
        """Kill Chrome processes dùng fb_view_ profiles còn sót từ session trước."""
        try:
            views_root = os.path.join(os.path.expanduser("~"), ".fb_recovery_views")
            if not os.path.isdir(views_root):
                return
            # Tìm Chrome process nào đang dùng profile trong .fb_recovery_views
            r = subprocess.run(
                ["pgrep", "-f", "fb_recovery_views"],
                capture_output=True, text=True
            )
            for pid in r.stdout.strip().split():
                if pid:
                    try:
                        subprocess.run(["kill", "-9", pid], capture_output=True)
                    except Exception:
                        pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "TLabel", background="#1e1e2e", foreground="#cdd6f4", font=("Helvetica", 11)
        )
        style.configure(
            "TButton",
            background="#a6e3a1",
            foreground="#1e1e2e",
            font=("Helvetica", 11, "bold"),
            padding=6,
        )
        style.map("TButton", background=[("active", "#94d38f")])
        style.configure(
            "Stop.TButton",
            background="#f38ba8",
            foreground="#1e1e2e",
            font=("Helvetica", 11, "bold"),
            padding=6,
        )
        style.map("Stop.TButton", background=[("active", "#e07a94")])

        # ----------------------------------------------------------------
        # TOP BAR: title + buttons
        # ----------------------------------------------------------------
        top_bar = tk.Frame(self, bg="#181825", pady=6, padx=12)
        top_bar.pack(fill="x")

        tk.Label(
            top_bar,
            text="🔒 FB Hacked Recovery Tool",
            bg="#181825",
            fg="#cba6f7",
            font=("Helvetica", 14, "bold"),
        ).pack(side="left")

        # Buttons on right side of top bar
        btn_frame = tk.Frame(top_bar, bg="#181825")
        btn_frame.pack(side="right")

        self.btn_stop = ttk.Button(
            btn_frame,
            text="STOP ALL",
            style="Stop.TButton",
            command=self.stop_all,
        )
        self.btn_stop.pack(side="right", padx=(4, 0))

        self.btn_start = ttk.Button(btn_frame, text="START", command=self.start_threads)
        self.btn_start.pack(side="right", padx=(0, 4))

        # Separator
        sep = tk.Frame(self, bg="#313244", height=1)
        sep.pack(fill="x")

        concurrent_row = tk.Frame(self, bg="#1e1e2e")
        concurrent_row.pack(fill="x", padx=16, pady=(2, 2))
        tk.Label(
            concurrent_row, text="Threads:",
            bg="#1e1e2e", fg="#cdd6f4", font=("Helvetica", 11)
        ).pack(side="left")
        self._max_concurrent_var = tk.IntVar(value=10)
        tk.Spinbox(
            concurrent_row,
            from_=1, to=50,
            textvariable=self._max_concurrent_var,
            width=4,
            bg="#313244", fg="#cdd6f4",
            buttonbackground="#45475a",
            font=("Helvetica", 11),
        ).pack(side="left", padx=(8, 0))

        # ----------------------------------------------------------------
        # THREE-PANEL INPUT ROW: Accounts | VPS Pool | Proxy Pool
        # ----------------------------------------------------------------
        input_row = tk.Frame(self, bg="#1e1e2e")
        input_row.pack(fill="both", expand=False, padx=0, pady=0)

        # --- Accounts panel ---
        acct_panel = tk.Frame(input_row, bg="#1e1e2e", padx=8, pady=6)
        acct_panel.pack(side="left", fill="both", expand=True)

        tk.Label(
            acct_panel,
            text="📋 ACCOUNTS",
            bg="#1e1e2e",
            fg="#cba6f7",
            font=("Helvetica", 10, "bold"),
        ).pack(anchor="w")
        tk.Label(
            acct_panel,
            text="(one per line)",
            bg="#1e1e2e",
            fg="#6c7086",
            font=("Helvetica", 9),
        ).pack(anchor="w")

        self.accounts_text = tk.Text(
            acct_panel,
            height=7,
            bg="#313244",
            fg="#cdd6f4",
            insertbackground="#cdd6f4",
            font=("Courier", 10),
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#313244",
            highlightcolor="#cba6f7",
        )
        self.accounts_text.pack(fill="both", expand=True, pady=(4, 0))
        self.accounts_text.insert(
            "1.0",
            "# Nhap email/phone moi dong\n"
            "# Lines bat dau # se bi bo qua\n",
        )

        # Vertical separator
        vsep1 = tk.Frame(input_row, bg="#313244", width=1)
        vsep1.pack(side="left", fill="y", pady=4)

        # --- VPS Pool panel (Termius-style) ---
        vps_panel = tk.Frame(input_row, bg="#1e1e2e", padx=8, pady=6)
        vps_panel.pack(side="left", fill="both", expand=True)

        tk.Label(
            vps_panel,
            text="🖥 VPS POOL",
            bg="#1e1e2e",
            fg="#cba6f7",
            font=("Helvetica", 10, "bold"),
        ).pack(anchor="w")
        tk.Label(
            vps_panel,
            text="Key tự động: ~/.ssh/vps_key_openssh hoặc ~/.ssh/id_rsa",
            bg="#1e1e2e",
            fg="#6c7086",
            font=("Helvetica", 9),
        ).pack(anchor="w")

        # Listbox container
        lb_frame = tk.Frame(vps_panel, bg="#181825", relief="flat",
                            highlightthickness=1, highlightbackground="#313244")
        lb_frame.pack(fill="both", expand=True, pady=(4, 2))

        lb_scroll = tk.Scrollbar(lb_frame, bg="#313244", troughcolor="#1e1e2e",
                                 relief="flat", width=8)
        lb_scroll.pack(side="right", fill="y")

        self._vps_listbox = tk.Listbox(
            lb_frame,
            bg="#181825",
            fg="#cdd6f4",
            selectbackground="#313244",
            selectforeground="#cdd6f4",
            font=("Courier", 9),
            relief="flat",
            bd=0,
            highlightthickness=0,
            activestyle="none",
            yscrollcommand=lb_scroll.set,
        )
        self._vps_listbox.pack(side="left", fill="both", expand=True)
        lb_scroll.config(command=self._vps_listbox.yview)

        # Input fields row
        vps_input_row = tk.Frame(vps_panel, bg="#1e1e2e")
        vps_input_row.pack(fill="x", pady=(2, 2))

        tk.Label(vps_input_row, text="IP/Host", bg="#1e1e2e", fg="#6c7086",
                 font=("Helvetica", 8)).grid(row=0, column=0, sticky="w", padx=(0, 2))
        tk.Label(vps_input_row, text="Username", bg="#1e1e2e", fg="#6c7086",
                 font=("Helvetica", 8)).grid(row=0, column=1, sticky="w", padx=(4, 0))

        self._vps_host_var = tk.StringVar()
        self._vps_user_var = tk.StringVar(value="root")

        vps_host_entry = tk.Entry(
            vps_input_row,
            textvariable=self._vps_host_var,
            bg="#313244", fg="#cdd6f4",
            insertbackground="#cdd6f4",
            relief="flat", bd=4,
            font=("Courier", 9),
        )
        vps_host_entry.grid(row=1, column=0, sticky="ew", padx=(0, 2))

        vps_user_entry = tk.Entry(
            vps_input_row,
            textvariable=self._vps_user_var,
            bg="#313244", fg="#cdd6f4",
            insertbackground="#cdd6f4",
            relief="flat", bd=4,
            font=("Courier", 9),
        )
        vps_user_entry.grid(row=1, column=1, sticky="ew", padx=(4, 0))

        vps_input_row.columnconfigure(0, weight=1)
        vps_input_row.columnconfigure(1, weight=1)

        # Buttons row
        vps_btn_row = tk.Frame(vps_panel, bg="#1e1e2e")
        vps_btn_row.pack(fill="x", pady=(0, 0))

        btn_add_vps = tk.Button(
            vps_btn_row, text="+ ADD VPS",
            bg="#a6e3a1", fg="#1e1e2e",
            font=("Helvetica", 8, "bold"),
            relief="flat", bd=0, padx=6, pady=3,
            activebackground="#94d38f", activeforeground="#1e1e2e",
            cursor="hand2",
            command=self._vps_add,
        )
        btn_add_vps.pack(side="left", padx=(0, 3))

        btn_rem_vps = tk.Button(
            vps_btn_row, text="- REMOVE",
            bg="#f38ba8", fg="#1e1e2e",
            font=("Helvetica", 8, "bold"),
            relief="flat", bd=0, padx=6, pady=3,
            activebackground="#e07a94", activeforeground="#1e1e2e",
            cursor="hand2",
            command=self._vps_remove,
        )
        btn_rem_vps.pack(side="left", padx=(0, 3))

        btn_test_vps = tk.Button(
            vps_btn_row, text="TEST",
            bg="#89b4fa", fg="#1e1e2e",
            font=("Helvetica", 8, "bold"),
            relief="flat", bd=0, padx=6, pady=3,
            activebackground="#74a0e8", activeforeground="#1e1e2e",
            cursor="hand2",
            command=self._vps_test,
        )
        btn_test_vps.pack(side="left")

        # Vertical separator
        vsep2 = tk.Frame(input_row, bg="#313244", width=1)
        vsep2.pack(side="left", fill="y", pady=4)

        # --- Proxy Pool panel ---
        proxy_panel = tk.Frame(input_row, bg="#1e1e2e", padx=8, pady=6)
        proxy_panel.pack(side="left", fill="both", expand=True)

        tk.Label(
            proxy_panel,
            text="🔗 PROXY POOL",
            bg="#1e1e2e",
            fg="#cba6f7",
            font=("Helvetica", 10, "bold"),
        ).pack(anchor="w")
        tk.Label(
            proxy_panel,
            text="http://ip:port  or  user:pass@ip:port",
            bg="#1e1e2e",
            fg="#6c7086",
            font=("Helvetica", 9),
        ).pack(anchor="w")

        self.proxy_entry = tk.Text(
            proxy_panel,
            height=7,
            bg="#313244",
            fg="#a6e3a1",
            insertbackground="#cdd6f4",
            font=("Courier", 10),
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#313244",
            highlightcolor="#cba6f7",
        )
        self.proxy_entry.pack(fill="both", expand=True, pady=(4, 0))
        self.proxy_entry.insert("1.0", "# ip:port  or  user:pass@ip:port\n")

        # Separator
        sep2 = tk.Frame(self, bg="#313244", height=1)
        sep2.pack(fill="x")

        # ----------------------------------------------------------------
        # MIDDLE ROW: Results (scrollable) + Stats panel
        # ----------------------------------------------------------------
        middle_row = tk.Frame(self, bg="#1e1e2e")
        middle_row.pack(fill="both", expand=True, padx=0, pady=0)

        # --- Results panel (left, scrollable) ---
        results_panel = tk.Frame(middle_row, bg="#1e1e2e", padx=8, pady=6)
        results_panel.pack(side="left", fill="both", expand=True)

        tk.Label(
            results_panel,
            text="📊 RESULTS",
            bg="#1e1e2e",
            fg="#cba6f7",
            font=("Helvetica", 10, "bold"),
        ).pack(anchor="w")

        # Scrollable results frame
        results_container = tk.Frame(results_panel, bg="#181825", relief="flat",
                                     highlightthickness=1, highlightbackground="#313244")
        results_container.pack(fill="both", expand=True, pady=(4, 0))

        results_scroll = tk.Scrollbar(results_container, bg="#313244", troughcolor="#1e1e2e",
                                      relief="flat", width=8)
        results_scroll.pack(side="right", fill="y")

        self.results_canvas = tk.Canvas(
            results_container,
            bg="#181825",
            highlightthickness=0,
            yscrollcommand=results_scroll.set,
        )
        self.results_canvas.pack(side="left", fill="both", expand=True)
        results_scroll.config(command=self.results_canvas.yview)

        self.results_frame = tk.Frame(self.results_canvas, bg="#181825")
        self._results_window = self.results_canvas.create_window(
            (0, 0), window=self.results_frame, anchor="nw"
        )
        self.results_canvas.bind(
            "<Configure>",
            lambda e: self.results_canvas.itemconfig(
                self._results_window, width=e.width
            )
        )
        # Mouse wheel scroll cho results panel
        def _scroll_results(e):
            # macOS: delta là pixels trực tiếp (trackpad), Windows: bội của 120
            delta = e.delta
            if abs(delta) >= 100:
                # Windows / macOS đơn vị lớn
                units = int(-1 * delta / 120)
            else:
                # macOS trackpad — delta nhỏ, dùng trực tiếp
                units = int(-1 * delta) if delta != 0 else 0
            if units != 0:
                self.results_canvas.yview_scroll(units, "units")

        def _results_enter(e):
            self.bind_all("<MouseWheel>", _scroll_results)

        def _results_leave(e):
            # Chỉ unbind nếu chuột thực sự ra ngoài vùng canvas
            rx = self.results_canvas.winfo_rootx()
            ry = self.results_canvas.winfo_rooty()
            rw = self.results_canvas.winfo_width()
            rh = self.results_canvas.winfo_height()
            mx, my = self.winfo_pointerx(), self.winfo_pointery()
            if not (rx <= mx <= rx + rw and ry <= my <= ry + rh):
                self.unbind_all("<MouseWheel>")

        self.results_canvas.bind("<Enter>", _results_enter)
        self.results_canvas.bind("<Leave>", _results_leave)
        self.results_frame.bind("<Enter>", _results_enter)

        # Bind scroll vào child widgets mới được thêm vào sau
        def _bind_children_scroll(widget):
            try:
                widget.bind("<Enter>", _results_enter)
                for c in widget.winfo_children():
                    _bind_children_scroll(c)
            except Exception:
                pass
        # Hook vào results_frame Configure để bind children khi row mới thêm vào
        self.results_frame.bind(
            "<Configure>",
            lambda e: (
                self.results_canvas.configure(scrollregion=self.results_canvas.bbox("all")),
                _bind_children_scroll(self.results_frame)
            )
        )

        # Header row in results
        hdr = tk.Frame(self.results_frame, bg="#181825")
        hdr.pack(fill="x", padx=4, pady=(4, 2))
        tk.Label(hdr, text="Email / Account", bg="#181825", fg="#6c7086",
                 font=("Courier", 9, "bold"), anchor="w").pack(side="left")
        tk.Label(hdr, text="Status", bg="#181825", fg="#6c7086",
                 font=("Courier", 9, "bold"), width=9, anchor="e").pack(side="right")

        # Vertical separator
        vsep3 = tk.Frame(middle_row, bg="#313244", width=1)
        vsep3.pack(side="left", fill="y", pady=4)

        # --- Stats panel (right, fixed 200px) ---
        stats_panel = tk.Frame(middle_row, bg="#1e1e2e", width=200, padx=10, pady=6)
        stats_panel.pack(side="right", fill="y")
        stats_panel.pack_propagate(False)

        tk.Label(
            stats_panel,
            text="📊 STATS",
            bg="#1e1e2e",
            fg="#cba6f7",
            font=("Helvetica", 12, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        stat_items = [
            ("Total:", "total", "#cdd6f4"),
            ("Running:", "running", "#fab387"),
            ("Success:", "success", "#a6e3a1"),
            ("Failed:", "failed", "#f38ba8"),
            ("Pending:", "pending", "#f9e2af"),
            ("VPS:", "vps", "#89dceb"),
            ("Proxies:", "proxies", "#89b4fa"),
        ]
        for label_text, key, color in stat_items:
            row = tk.Frame(stats_panel, bg="#1e1e2e")
            row.pack(fill="x", pady=3)
            tk.Label(
                row,
                text=label_text,
                bg="#1e1e2e",
                fg="#6c7086",
                font=("Helvetica", 10),
                anchor="w",
                width=10,
            ).pack(side="left")
            tk.Label(
                row,
                textvariable=self._stats_vars[key],
                bg="#1e1e2e",
                fg=color,
                font=("Helvetica", 13, "bold"),
                anchor="e",
            ).pack(side="right")

        # Separator
        sep3 = tk.Frame(self, bg="#313244", height=1)
        sep3.pack(fill="x")

        # ----------------------------------------------------------------
        # BOTTOM: Log panel
        # ----------------------------------------------------------------
        log_panel = tk.Frame(self, bg="#1e1e2e", padx=8, pady=6)
        log_panel.pack(fill="x", padx=0, pady=0)

        tk.Label(
            log_panel,
            text="📝 LOG",
            bg="#1e1e2e",
            fg="#cba6f7",
            font=("Helvetica", 10, "bold"),
        ).pack(anchor="w")

        self.log_box = scrolledtext.ScrolledText(
            log_panel,
            height=8,
            bg="#11111b",
            fg="#a6e3a1",
            font=("Courier", 9),
            state="disabled",
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#313244",
            insertbackground="#cdd6f4",
        )
        self.log_box.pack(fill="x", pady=(4, 0))

        # Khi hover log → unbind scroll results, để log tự scroll bình thường
        def _on_enter_log(e):
            self.unbind_all("<MouseWheel>")
        def _on_leave_log(e):
            pass  # results sẽ tự bind lại khi chuột vào
        self.log_box.bind("<Enter>", _on_enter_log)
        self.log_box.bind("<Leave>", _on_leave_log)

    # ------------------------------------------------------------------
    # VPS Panel methods (Termius-style)
    # ------------------------------------------------------------------
    def _vps_add(self):
        host = self._vps_host_var.get().strip()
        # Clean up http://, https://, trailing slashes
        host = host.replace("https://", "").replace("http://", "").rstrip("/")
        user = self._vps_user_var.get().strip() or "root"
        if not host:
            messagebox.showwarning("VPS", "Nhập IP/Host trước.")
            return
        # Tìm key mặc định
        default_key = ""
        for k in ["~/.ssh/vps_key_openssh", "~/.ssh/id_rsa", "~/.ssh/id_ed25519"]:
            expanded = os.path.expanduser(k)
            if os.path.isfile(expanded):
                default_key = expanded
                break
        entry = {"host": host, "user": user, "key": default_key, "status": ""}
        self._vps_list.append(entry)
        self._vps_refresh_listbox()
        self._vps_host_var.set("")
        self._vps_user_var.set("root")

    def _vps_remove(self):
        sel = self._vps_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if 0 <= idx < len(self._vps_list):
            self._vps_list.pop(idx)
            self._vps_refresh_listbox()

    def _vps_test(self):
        sel = self._vps_listbox.curselection()
        if not sel:
            messagebox.showwarning("VPS", "Chọn VPS cần test.")
            return
        idx = sel[0]
        if not (0 <= idx < len(self._vps_list)):
            return
        entry = self._vps_list[idx]
        self._vps_list[idx]["status"] = "..."
        self._vps_refresh_listbox()
        self._vps_listbox.selection_set(idx)

        def _do_test(entry=entry, idx=idx):
            host = entry["host"]
            user = entry["user"]
            key = entry.get("key", "")
            cmd = [
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=6",
                "-o", "BatchMode=yes",
            ]
            if key and os.path.isfile(key):
                cmd += ["-i", key]
            cmd += [f"{user}@{host}", "echo OK"]
            try:
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=10,
                )
                ok = result.returncode == 0 and b"OK" in result.stdout
            except Exception:
                ok = False
            status = "✅ OK" if ok else "❌ FAIL"
            if 0 <= idx < len(self._vps_list):
                self._vps_list[idx]["status"] = status
            self.after(0, self._vps_refresh_listbox)
            self.after(0, lambda: self._vps_listbox.selection_set(idx))

        threading.Thread(target=_do_test, daemon=True).start()

    def _vps_refresh_listbox(self):
        self._vps_listbox.delete(0, "end")
        for entry in self._vps_list:
            status = entry.get("status", "")
            line = f"{entry['host']:<20}  {entry['user']:<12}  {status}"
            self._vps_listbox.insert("end", line)
            # Color based on status
            last_idx = self._vps_listbox.size() - 1
            if "✅" in status:
                self._vps_listbox.itemconfig(last_idx, fg="#a6e3a1")
            elif "❌" in status:
                self._vps_listbox.itemconfig(last_idx, fg="#f38ba8")
            elif status == "...":
                self._vps_listbox.itemconfig(last_idx, fg="#fab387")
            else:
                self._vps_listbox.itemconfig(last_idx, fg="#89dceb")

    def _get_vps_list(self) -> list:
        """Return self._vps_list for use by start_threads."""
        # Tìm key mặc định
        default_key = ""
        for k in ["~/.ssh/vps_key_openssh", "~/.ssh/id_rsa", "~/.ssh/id_ed25519"]:
            expanded = os.path.expanduser(k)
            if os.path.isfile(expanded):
                default_key = expanded
                break
        return [
            {
                "host": e["host"],
                "user": e["user"],
                "key": e.get("key") or default_key,
                "port": e.get("port", 22),
            }
            for e in self._vps_list
        ]

    # ------------------------------------------------------------------
    # Stats management
    # ------------------------------------------------------------------
    def _update_stats(self):
        """Refresh all stats vars from current state."""
        # Tổng dựa trên accounts hiện tại trong textbox (bỏ qua những gì đã bị xóa)
        current_accounts = set(self._parse_accounts())
        # Chỉ đếm success emails vẫn còn trong danh sách
        active_success = self._success_emails & current_accounts if current_accounts else self._success_emails
        total = len(current_accounts) if current_accounts else (self._total_accounts or len(self._workers))

        with self._lock:
            running = sum(
                1 for w in self._workers
                if w.is_alive() and w.email not in self._success_emails
            )
            success = len(active_success)
            failed = sum(
                1 for w in self._workers
                if not w.is_alive() and w.email not in self._success_emails
                and w.email in current_accounts
            )

        pending = max(0, total - running - success - failed)
        self._stats_vars["total"].set(str(total))
        self._stats_vars["running"].set(str(running))
        self._stats_vars["success"].set(str(success))
        self._stats_vars["failed"].set(str(failed))
        self._stats_vars["pending"].set(str(pending))

        # VPS count
        vps_list = self._get_vps_list()
        self._stats_vars["vps"].set(f"{len(vps_list)} servers")

        # Proxy count
        proxy_raw = self._parse_proxies()
        pool = ProxyPool(proxy_raw)
        self._stats_vars["proxies"].set(f"{len(pool.proxies)} entries")

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------
    def _parse_accounts(self) -> list:
        raw = self.accounts_text.get("1.0", "end")
        accounts = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "Nhap email" in line or "Lines bat" in line:
                continue
            accounts.append(line)
        return accounts

    def _parse_proxies(self) -> str:
        raw = self.proxy_entry.get("1.0", "end").strip()
        if raw.startswith("# ip:port"):
            return ""
        return raw

    def _parse_vps(self) -> list:
        """Parse VPS textarea, return list of {"host": str, "user": str, "key": str}."""
        raw = self._vps_entry.get("1.0", "end")
        result = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 3:
                result.append({
                    "host": parts[0],
                    "user": parts[1],
                    "key": parts[2],
                })
            elif len(parts) == 2:
                result.append({
                    "host": parts[0],
                    "user": parts[1],
                    "key": "",
                })
            elif len(parts) == 1:
                result.append({
                    "host": parts[0],
                    "user": "root",
                    "key": "",
                })
        return result

    # ------------------------------------------------------------------
    def start_threads(self):
        accounts = self._parse_accounts()
        if not accounts:
            messagebox.showwarning("No accounts", "Nhap it nhat 1 account.")
            return
        self._total_accounts = len(accounts)

        # Clean up non-success workers — giữ nguyên SUCCESS tabs
        self._workers = [w for w in self._workers if w.email in self._success_emails]
        max_c = self._max_concurrent_var.get()
        self._semaphore = threading.Semaphore(max_c)
        self._log_append(f"[START] Max concurrent Chrome: {max_c}")
        # Reset result rows nhưng giữ SUCCESS entries
        for widget in self.results_frame.winfo_children():
            if isinstance(widget, tk.Frame):
                # Keep header row (first child)
                pass
        # Clear all non-header rows
        children = self.results_frame.winfo_children()
        for widget in children[1:]:  # skip header
            widget.destroy()
        self._result_rows = {}
        # Re-add SUCCESS rows
        for email in self._success_emails:
            self._add_result_row(email, "SUCCESS")
            self._update_result_row(email, "SUCCESS")

        proxy_raw = self._parse_proxies()
        pool = ProxyPool(proxy_raw)

        vps_list = self._get_vps_list()

        self._log_append(
            f"[START] {len(accounts)} accounts | "
            f"proxy pool: {len(pool.proxies)} entries | "
            f"vps pool: {len(vps_list)} servers"
        )

        # Xóa khỏi _success_emails những email không còn trong danh sách nữa
        accounts_set = set(accounts)
        removed = self._success_emails - accounts_set
        for em in removed:
            self._success_emails.discard(em)
            self._success_worker_info.pop(em, None)

        stop_event = threading.Event()

        for idx, email in enumerate(accounts):
            # Bỏ qua email đã SUCCESS — Chrome của họ vẫn đang mở, không được đụng vào
            if email in self._success_emails:
                continue
            self._add_result_row(email, "WAITING")
            w = AccountWorker(
                email=email,
                proxy=None,
                idx=idx,
                callbacks={
                    "log": self._cb_log,
                    "result": self._cb_result,
                    "success_keep": self._cb_success_keep,
                    "thumbnail": self._cb_thumbnail,
                },
                stop_event=stop_event,
                vps=None,
                semaphore=self._semaphore,
                vps_list=list(vps_list),
                proxy_list=list(pool.proxies),
            )
            self._workers.append(w)

        # Start all workers simultaneously — parallel Chrome
        for w in self._workers:
            if not w.is_alive():
                w.start()

        # Bật vòng lặp vô hạn
        self._loop_active = True
        self._loop_stop.clear()

        # Monitor completion in background
        threading.Thread(target=self._monitor, daemon=True).start()

        # Initial stats update
        self.after(100, self._update_stats)

    # ------------------------------------------------------------------
    def _monitor(self):
        """Chạy workers, khi xong tự restart nếu _loop_active=True."""
        while True:
            # Chờ tất cả workers kết thúc
            while any(w.is_alive() for w in self._workers):
                self.after(0, self._update_stats)
                time.sleep(1)
            self.after(0, self._update_stats)

            # Nếu user đã bấm STOP → thoát vòng lặp
            if not self._loop_active or self._loop_stop.is_set():
                break

            # Tự động restart: chờ 2s rồi start lại
            time.sleep(2)
            if not self._loop_active or self._loop_stop.is_set():
                break
            self.after(0, self._restart_round)

    # ------------------------------------------------------------------
    def _restart_round(self):
        """Gọi lại start_threads để chạy vòng mới — được gọi từ _monitor."""
        if self._loop_active and not self._loop_stop.is_set():
            self._log_append("[LOOP] Restarting round...")
            self.start_threads()

    # ------------------------------------------------------------------
    def stop_all(self):
        self._log_append("[STOP] Stopping all workers...")

        # Dừng vòng lặp auto-restart tạm thời trong khi reset
        self._loop_active = False
        self._loop_stop.set()

        for w in self._workers:
            w._stop.set()
            if w.email not in self._success_emails:
                w.quit_driver()  # chỉ đóng Chrome của non-SUCCESS

        # Giữ lại SUCCESS workers — Chrome của họ vẫn mở, không đụng
        self._workers = [w for w in self._workers if w.email in self._success_emails]
        self._log_append("[STOP] Done. SUCCESS kept. Press START to retry remaining accounts.")
        self.after(100, self._update_stats)

    # ------------------------------------------------------------------
    def _add_result_row(self, email: str, status: str):
        row = tk.Frame(self.results_frame, bg="#181825")
        row.pack(fill="x", padx=4, pady=1)

        icon_map = {
            "SUCCESS": "✅",
            "FAILED": "❌",
            "WAITING": "⏳",
            "RUNNING": "🔄",
        }
        icon = icon_map.get(status, "·")

        icon_lbl = tk.Label(
            row,
            text=icon,
            bg="#181825",
            fg="#cdd6f4",
            font=("Courier", 9),
            width=2,
        )
        icon_lbl.pack(side="left")

        tk.Label(
            row,
            text=email[:32],
            bg="#181825",
            fg="#cdd6f4",
            font=("Courier", 9),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        lbl = tk.Label(
            row,
            text=status,
            bg="#181825",
            fg="#6c7086",
            font=("Courier", 9, "bold"),
            width=9,
            anchor="e",
        )
        lbl.pack(side="right")

        # Thumbnail
        thumb_lbl = tk.Label(row, bg="#181825", width=20, height=5, cursor="hand2")
        thumb_lbl.pack(side="right", padx=(0, 4))
        thumb_lbl.bind("<Button-1>", lambda e, em=email: self._on_thumbnail_click(em))

        self._result_rows[email] = (lbl, icon_lbl, thumb_lbl)

    def _update_result_row(self, email: str, status: str):
        entry = self._result_rows.get(email)
        if not entry:
            return
        lbl, icon_lbl = entry[0], entry[1]
        color_map = {
            "SUCCESS": "#a6e3a1",
            "FAILED": "#f38ba8",
            "RUNNING": "#fab387",
            "WAITING": "#6c7086",
        }
        icon_map = {
            "SUCCESS": "✅",
            "FAILED": "❌",
            "WAITING": "⏳",
            "RUNNING": "🔄",
        }
        fg = color_map.get(status, "#cdd6f4")
        icon = icon_map.get(status, "·")
        lbl.configure(text=status, fg=fg)
        icon_lbl.configure(text=icon)
        # Cursor: chỉ SUCCESS mới hand2 (clickable)
        if len(entry) >= 3:
            entry[2].configure(cursor="hand2")  # tất cả đều clickable để xem Chrome

    # ------------------------------------------------------------------
    # Thread-safe callbacks via root.after(0, ...)
    def _cb_log(self, email: str, msg: str):
        line = f"[{email[:20]}] {msg}"
        self.after(0, lambda l=line: self._log_append(l))

    def _cb_result(self, email: str, status: str):
        self.after(0, lambda e=email, s=status: self._update_result_row(e, s))
        self.after(100, self._update_stats)

    def _cb_success_keep(self, email: str):
        self._success_emails.add(email)  # track để stop_all không đóng Chrome này
        # Lưu worker info để dùng khi click thumbnail sau STOP
        for w in self._workers:
            if w.email == email:
                self._success_worker_info[email] = {
                    "worker": w,
                    "proxy": w.proxy,
                    "tunnel": w._tunnel,
                }
                break
        line = f"[SUCCESS] {email} — Chrome kept open for manual action."
        self.after(0, lambda l=line: self._log_append(l))
        self.after(0, lambda e=email: self._update_result_row(e, "SUCCESS"))
        self.after(100, self._update_stats)

    def _cb_thumbnail(self, email: str, b64_data: str):
        if not HAS_PIL:
            return
        def _update():
            try:
                if email not in self._result_rows:
                    return
                row_data = self._result_rows[email]
                if len(row_data) < 3:
                    return
                thumb_lbl = row_data[2]
                import base64, io
                img_bytes = base64.b64decode(b64_data)
                img = Image.open(io.BytesIO(img_bytes))
                img = img.resize((160, 100), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                thumb_lbl.configure(image=photo, width=160, height=100)
                thumb_lbl.image = photo  # keep reference
            except Exception:
                pass
        self.after(0, _update)

    def _on_thumbnail_click(self, email: str):
        # Chống spam — mỗi email chỉ cho phép 1 Chrome view cùng lúc
        if not hasattr(self, '_view_opening'):
            self._view_opening: set = set()
        if email in self._view_opening:
            return
        self._view_opening.add(email)

        # Tìm worker — ưu tiên _workers đang chạy, fallback sang _success_worker_info
        target_worker = None
        for w in self._workers:
            if w.email == email and w.driver:
                target_worker = w
                break
        if target_worker is None and email in self._success_worker_info:
            target_worker = self._success_worker_info[email].get("worker")

        if not (target_worker and target_worker.driver):
            self._view_opening.discard(email)
            self._log_append(f"[Chrome] No active driver for {email[:25]}")
            return

        w = target_worker
        try:
            current_url = w.driver.current_url

            proxy_str = None
            if w._tunnel and w._tunnel._proc and w._tunnel._proc.poll() is None:
                proxy_str = w._tunnel.proxy_url()
            elif w.proxy:
                proxy_str = w.proxy

            # Lấy --user-data-dir của Chrome headless đang chạy
            profile_dir = None
            try:
                drv_pid = w.driver.service.process.pid
                r = subprocess.run(["pgrep", "-P", str(drv_pid)], capture_output=True, text=True)
                for cpid in r.stdout.strip().split():
                    pr = subprocess.run(["ps", "-p", cpid, "-o", "command="], capture_output=True, text=True)
                    for part in pr.stdout.split():
                        if part.startswith("--user-data-dir="):
                            profile_dir = part.split("=", 1)[1]
                            break
                    if profile_dir:
                        break
            except Exception:
                pass

            import threading, json as _json

            # Lưu session ra disk (email cố định) để restore sau nếu cần
            safe_name = "".join(c if c.isalnum() else "_" for c in email)
            save_dir = os.path.join(os.path.expanduser("~"), ".fb_recovery_views", safe_name)
            os.makedirs(save_dir, exist_ok=True)
            try:
                cookies = list(w.driver.get_cookies())
                with open(os.path.join(save_dir, "session.json"), "w", encoding="utf-8") as f:
                    _json.dump({"email": email, "url": current_url, "proxy": proxy_str, "cookies": cookies}, f, ensure_ascii=False, indent=2)
            except Exception:
                cookies = []

            def _show(url=current_url, px=proxy_str, cks=cookies, em=email, sdir=save_dir):
                try:
                    import tempfile as _tmp
                    from selenium import webdriver as wd
                    from selenium.webdriver.chrome.options import Options as COptions
                    from selenium.webdriver.chrome.service import Service as CService

                    # Kill Chrome view cũ của email này nếu còn mở
                    old_info = self._view_drivers.pop(em, None)
                    if old_info:
                        old_drv, old_dir = old_info if isinstance(old_info, tuple) else (old_info, None)
                        try:
                            old_drv.quit()
                        except Exception:
                            pass
                        # Xóa tmpdir cũ để không còn Chrome sót trong Dock
                        if old_dir and os.path.isdir(old_dir):
                            try:
                                import shutil as _sh
                                _sh.rmtree(old_dir, ignore_errors=True)
                            except Exception:
                                pass

                    # Profile sạch riêng cho Chrome view — KHÔNG dùng profile headless
                    view_dir = _tmp.mkdtemp(prefix="fb_view_")

                    opts = COptions()
                    opts.add_argument(f"--user-data-dir={view_dir}")
                    opts.add_argument("--no-first-run")
                    opts.add_argument("--no-default-browser-check")
                    opts.add_argument("--disable-blink-features=AutomationControlled")

                    if px:
                        if px.startswith("socks5://"):
                            opts.add_argument(f"--proxy-server={px}")
                        else:
                            ext_dir2 = w._make_proxy_extension(px) if hasattr(w, '_make_proxy_extension') else None
                            if ext_dir2:
                                opts.add_argument(f"--load-extension={ext_dir2}")
                            else:
                                opts.add_argument(f"--proxy-server={px}")

                    # Mở Chrome thường với profile sạch + proxy đúng
                    drv = wd.Chrome(service=CService(), options=opts)

                    # Inject cookies từ headless → Chrome view có cùng session
                    drv.get("https://www.facebook.com")
                    for ck in cks:
                        try:
                            ck2 = {k: v for k, v in ck.items()
                                   if k not in ("sameSite", "expiry")}
                            drv.add_cookie(ck2)
                        except Exception:
                            pass

                    # Navigate đến đúng URL — phiên hoàn toàn đồng bộ với headless
                    drv.get(url)

                    # Lưu (driver, view_dir) để kill + cleanup khi click lại
                    self._view_drivers[em] = (drv, view_dir)
                    # Chrome ở lại cho user — tool không can thiệp gì nữa

                except Exception as ex:
                    # Fallback: inject cookies vào profile cố định
                    try:
                        from selenium import webdriver as wd2
                        from selenium.webdriver.chrome.options import Options as COptions2
                        from selenium.webdriver.chrome.service import Service as CService2
                        opts2 = COptions2()
                        opts2.add_argument(f"--user-data-dir={sdir}")
                        opts2.add_argument("--no-first-run")
                        # detach removed
                        if px:
                            if px.startswith("socks5://"):
                                opts2.add_argument(f"--proxy-server={px}")
                            else:
                                e2 = w._make_proxy_extension(px) if hasattr(w, '_make_proxy_extension') else None
                                if e2:
                                    opts2.add_argument(f"--load-extension={e2}")
                        drv2 = wd2.Chrome(service=CService2(), options=opts2)
                        drv2.get("https://www.facebook.com")
                        for ck in cks:
                            try:
                                ck2 = {k: v for k, v in ck.items() if k not in ("sameSite", "expiry")}
                                drv2.add_cookie(ck2)
                            except Exception:
                                pass
                        drv2.get(url)
                    except Exception as ex2:
                        self._log_append(f"[Chrome] Fallback error: {ex2}")
                    self._log_append(f"[Chrome] Primary error: {ex}")
                finally:
                    self._view_opening.discard(em)

            threading.Thread(target=_show, daemon=True).start()
            self._log_append(f"[Chrome] Showing session: {email[:25]}")
        except Exception as e:
            self._view_opening.discard(email)
            self._log_append(f"[Chrome] Error: {e}")

    # ------------------------------------------------------------------
    _STATE_FILE = os.path.expanduser("~/.fb_recovery_state.json")

    def _save_state(self):
        try:
            state = {
                "accounts": self.accounts_text.get("1.0", "end").strip(),
                "proxy": self.proxy_entry.get("1.0", "end").strip(),
                "vps_list": getattr(self, '_vps_list', []),
                "max_concurrent": self._max_concurrent_var.get() if hasattr(self, '_max_concurrent_var') else 5,
            }
            with open(self._STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_state(self):
        try:
            if not os.path.isfile(self._STATE_FILE):
                return
            with open(self._STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            if state.get("accounts"):
                self.accounts_text.delete("1.0", "end")
                self.accounts_text.insert("1.0", state["accounts"])
            if state.get("proxy"):
                self.proxy_entry.delete("1.0", "end")
                self.proxy_entry.insert("1.0", state["proxy"])
            if state.get("vps_list"):
                self._vps_list = state["vps_list"]
                self._vps_refresh_listbox()
            if state.get("max_concurrent") and hasattr(self, '_max_concurrent_var'):
                self._max_concurrent_var.set(state["max_concurrent"])
        except Exception:
            pass

    def _on_close(self):
        self._save_state()
        self.destroy()

    # ------------------------------------------------------------------
    def _log_append(self, text: str):
        self.log_box.configure(state="normal")
        ts = time.strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{ts}] {text}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")


# ---------------------------------------------------------------------------
_app_ref = None

def _watch_and_reload():
    """Watch fb_recovery_mac.py, save state và restart khi file thay đổi."""
    import os, sys, time as _t, subprocess as _sp
    src = os.path.abspath(__file__)
    mtime = os.path.getmtime(src)
    while True:
        _t.sleep(1)
        try:
            new_mtime = os.path.getmtime(src)
        except OSError:
            continue
        if new_mtime != mtime:
            try:
                if _app_ref:
                    _app_ref._save_state()
            except Exception:
                pass
            _sp.Popen([sys.executable] + sys.argv)
            os._exit(0)

if __name__ == "__main__":
    import threading as _tw
    watcher = _tw.Thread(target=_watch_and_reload, daemon=True)
    watcher.start()
    app = FBHackedRecoveryTool()
    _app_ref = app
    app.mainloop()

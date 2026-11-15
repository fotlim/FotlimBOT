"""管理面板：标准库 http.server，绑 127.0.0.1，token 鉴权。支持测试发送文字/表情/图片。"""
from __future__ import annotations

import base64
import glob
import http.server
import json
import random
import threading
import time
import urllib.parse

from .store import Store
from .types import Outbound, Segment
from . import voice


class Admin:
    def __init__(self, host: str, port: int, token: str, store: Store, channel, brain,
                 started_at: float, sticker_dir: str = ""):
        self.host = host
        self.port = port
        self.token = token or ""
        self.store = store
        self.channel = channel
        self.brain = brain
        self.started_at = started_at
        self.sticker_dir = sticker_dir
        self._httpd = None

    def status(self) -> dict:
        return {
            "uptime_sec": int(time.time() - self.started_at),
            "channel": getattr(self.channel, "name", "?"),
            "channel_connected": bool(getattr(self.channel, "connected", False)),
            "model": getattr(getattr(self.brain, "llm", None), "model", "?"),
            "stats": self.store.stats(),
        }

    def _pick_sticker(self) -> str | None:
        if not self.sticker_dir:
            return None
        files = glob.glob(self.sticker_dir + "/*.png") + glob.glob(self.sticker_dir + "/*.jpg")
        if not files:
            return None
        try:
            with open(random.choice(files), "rb") as f:
                return "base64://" + base64.b64encode(f.read()).decode()
        except Exception:
            return None

    def _html(self) -> str:
        return (
            "<!doctype html><meta charset=utf-8><title>阿渔 · 控制台</title>"
            "<style>body{background:#0f1115;color:#d7dae0;font-family:system-ui;margin:0;padding:16px}"
            ".card{background:#171a21;border:1px solid #232733;border-radius:10px;padding:12px;margin-bottom:12px}"
            ".k{color:#7fd1b9}.r{color:#e0a86b}pre,div{white-space:pre-wrap;word-break:break-all}"
            "input{background:#0f1115;border:1px solid #2b3242;color:#d7dae0;border-radius:6px;padding:6px;margin:2px}"
            "button{background:#28648c;border:0;color:#fff;border-radius:6px;padding:6px 12px;cursor:pointer;margin:2px}</style>"
            "<h2>🐟 阿渔 · 核心状态</h2><div id=status class=card>loading…</div>"
            "<div class=card><b>最近消息（30）</b><div id=msgs></div></div>"
            "<div class=card><b>测试发送</b><br><input id=peer placeholder=QQ号 size=12>"
            "<input id=text placeholder=文字内容 size=34>"
            "<button onclick=doSend(false)>发文字</button><button onclick=doSend(true)>发个表情</button>"
            " <span id=sret class=r></span></div>"
            "<script>"
            "const T=new URLSearchParams(location.search).get('token')||'';"
            "async function j(u,o){const r=await fetch(u+'?token='+encodeURIComponent(T),o);return r.json()}"
            "async function tick(){try{const s=await j('/api/status');"
            "document.getElementById('status').innerHTML='<span class=k>运行</span> '+s.uptime_sec+'s · 通道 '+"
            "(s.channel_connected?'<span class=k>在线✅</span>':'<span class=r>离线❌</span>')+' · 模型 '+s.model+"
            "'<br>消息 '+s.stats.messages+'（今日 '+s.stats.today+'） · 对话者 '+s.stats.peers+"
            "' · 事实 '+s.stats.facts+' · 动作 '+s.stats.actions;"
            "const m=await j('/api/messages');document.getElementById('msgs').innerHTML=m.messages.map(x=>"
            "'<div><span class=k>['+x.scene+'] '+x.peer+'</span> '+x.role+': '+x.content+'</div>').join('')}catch(e){}}"
            "setInterval(tick,3000);tick();"
            "async function doSend(stk){const peer=document.getElementById('peer').value,text=document.getElementById('text').value;"
            "const r=await fetch('/api/send?token='+encodeURIComponent(T),{method:'POST',headers:{'Content-Type':'application/json'},"
            "body:JSON.stringify({peer,text,scene:'private',sticker:stk})});"
            "document.getElementById('sret').textContent=JSON.stringify(await r.json())}"
            "</script>"
        )

    def start(self) -> None:
        admin = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _auth(self) -> bool:
                q = urllib.parse.urlparse(self.path).query
                tok = urllib.parse.parse_qs(q).get("token", [""])[0]
                return tok == admin.token

            def _json(self, code, obj):
                b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                path = urllib.parse.urlparse(self.path).path
                if not self._auth():
                    self._json(403, {"error": "bad token"})
                    return
                if path == "/api/status":
                    self._json(200, admin.status())
                elif path == "/api/messages":
                    self._json(200, {"messages": admin.store.recent_messages(30)})
                elif path == "/":
                    b = admin._html().encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(b)))
                    self.end_headers()
                    self.wfile.write(b)
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                if not self._auth():
                    self._json(403, {"error": "bad token"})
                    return
                if self.path.split("?")[0] == "/api/send":
                    n = int(self.headers.get("Content-Length", "0") or 0)
                    try:
                        d = json.loads(self.rfile.read(n) or b"{}")
                    except Exception:
                        d = {}
                    peer = str(d.get("peer", ""))
                    text = d.get("text", "")
                    scene = d.get("scene", "private")
                    segs = []
                    if text:
                        segs.append(Segment.text(text))
                    if d.get("voice_text"):
                        vp = voice.synth(d["voice_text"])
                        if vp:
                            try:
                                vb = base64.b64encode(open(vp, "rb").read()).decode()
                                segs.append(Segment("record", {"file": "base64://" + vb}))
                            except Exception:
                                pass
                    if d.get("sticker"):
                        f = admin._pick_sticker()
                        if f:
                            segs.append(Segment("image", {"file": f}))
                    elif d.get("image_url"):
                        segs.append(Segment("image", {"file": d["image_url"]}))
                    ok = bool(segs) and admin.channel.send(Outbound(scene, peer, segs))
                    admin.store.log_action("manual_send", peer, (text or "[media]")[:50])
                    self._json(200, {"ok": ok})
                else:
                    self.send_response(404)
                    self.end_headers()

        self._httpd = http.server.ThreadingHTTPServer((self.host, self.port), H)
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        print(f"[admin] http://{self.host}:{self.port}/?token=***", flush=True)

"""管理面板：标准库 http.server，绑 127.0.0.1，token 鉴权。全能控制台。"""
from __future__ import annotations

import base64
import glob
import http.server
import json
import os
import random
import threading
import time
import urllib.parse

from .store import Store
from .types import Outbound, Segment
from . import voice


_HTML = r'''<!doctype html><html><head><meta charset="utf-8"><title>阿渔 · 控制台</title>
<style>
:root{color-scheme:dark}
body{background:#0f1115;color:#d7dae0;font-family:system-ui,sans-serif;margin:0;padding:14px}
h2{margin:6px 0 12px}
.card{background:#171a21;border:1px solid #232733;border-radius:10px;padding:12px;margin-bottom:12px}
.k{color:#7fd1b9}.r{color:#e0a86b}.dim{color:#8892a4}
.tabs button{background:#1d222c;border:1px solid #2b3242;color:#cbd3de;border-radius:8px;padding:7px 14px;cursor:pointer;margin:2px}
.tabs button.on{background:#28648c;border-color:#28648c;color:#fff}
input,textarea,select{background:#0f1115;border:1px solid #2b3242;color:#d7dae0;border-radius:6px;padding:6px;margin:3px}
button.act{background:#28648c;border:0;color:#fff;border-radius:6px;padding:6px 12px;cursor:pointer;margin:2px}
button.del{background:#8c3333}button.lock{background:#6a5a24}
table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #232733;padding:5px;text-align:left;font-size:13px;word-break:break-all}
div.msg{white-space:pre-wrap;word-break:break-all}
.tab{display:none}.tab.on{display:block}
</style></head><body>
<h2>🐟 阿渔 · 控制台</h2>
<div id="status" class="card">loading…</div>
<div class="tabs">
<button data-tab="status" class="on">状态</button>
<button data-tab="chat">对话</button>
<button data-tab="facts">记忆</button>
<button data-tab="actions">动作</button>
<button data-tab="send">发送</button>
<button data-tab="settings">设置/人设</button>
</div>

<div id="tab-status" class="tab on card">见上方状态栏（3 秒自动刷新）</div>

<div id="tab-chat" class="tab card">
 <b>对话者</b> <select id="peerSel" onchange="loadMsgs()"></select>
 <span class="dim">共 <span id="peerCnt">0</span> 人</span>
 <div id="msgs" style="margin-top:8px"></div>
</div>

<div id="tab-facts" class="tab card">
 <b>事实记忆</b>
 <div style="margin:6px 0">新增：<input id="fPeer" placeholder="QQ/peer" size=12><input id="fK" placeholder="类别(称呼/喜欢…)" size=12><input id="fV" placeholder="内容" size=24><button class="act" onclick="addFact()">+ 添加</button></div>
 <table><thead><tr><th>对象</th><th>类别</th><th>内容</th><th>置信</th><th>操作</th></tr></thead><tbody id="factRows"></tbody></table>
</div>

<div id="tab-actions" class="tab card"><b>最近动作</b><div id="actRows"></div></div>

<div id="tab-send" class="tab card">
 <b>发送测试</b><br>
 场景 <select id="sScene"><option value="private">私聊</option><option value="group">群聊</option></select>
 目标 <input id="sPeer" placeholder="QQ号或群号" size=14>
 <br><textarea id="sText" placeholder="文字内容" cols=60 rows=2></textarea>
 <br>图片URL <input id="sImg" placeholder="http(s) 图片地址" size=40>
 <br>TTS语音 <input id="sVoice" placeholder="输入文字→合成语音发送" size=40>
 <label><input type="checkbox" id="sSticker"> 附带一个表情</label>
 <br><button class="act" onclick="doSend()">发送</button> <span id="sRet" class="r"></span>
</div>

<div id="tab-settings" class="tab card">
 <b>运行设置</b><div id="settings"></div>
 <hr style="border-color:#232733">
 <b>人设 persona.txt</b> <button class="act" onclick="savePersona()">保存</button> <span id="pRet" class="r"></span>
 <br><textarea id="persona" cols=80 rows=10></textarea>
</div>

<script>
const T=new URLSearchParams(location.search).get('token')||'';
async function api(p,opt){const sep=p.includes('?')?'&':'?';const r=await fetch(p+sep+'token='+encodeURIComponent(T),opt||{});return r.json();}
function fmt(ts){try{return new Date(ts*1000).toLocaleString()}catch(e){return ts}}
async function refreshStatus(){try{const s=await api('/api/status');
 document.getElementById('status').innerHTML='<span class=k>运行</span> '+s.uptime_sec+'s · 通道 '+(s.channel_connected?'<span class=k>在线✅</span>':'<span class=r>离线❌</span>')+' · 模型 '+s.model+' · 主动'+(s.proactive?'开':'关')+'<br>消息 '+s.stats.messages+'（今日 '+s.stats.today+'） · 对话者 '+s.stats.peers+' · 事实 '+s.stats.facts+' · 动作 '+s.stats.actions;
}catch(e){}}
async function loadPeers(){const ps=await api('/api/peers');const sel=document.getElementById('peerSel');sel.innerHTML='';ps.peers.forEach(p=>{const o=document.createElement('option');o.value=p.peer_id;o.textContent=p.peer_id+' ('+p.count+'条)';sel.appendChild(o)});document.getElementById('peerCnt').textContent=ps.peers.length;if(ps.peers.length)loadMsgs();else document.getElementById('msgs').innerHTML='<span class=dim>暂无对话</span>'}
async function loadMsgs(){const peer=document.getElementById('peerSel').value;if(!peer)return;const m=await api('/api/messages?peer='+encodeURIComponent(peer));const el=document.getElementById('msgs');el.innerHTML=m.messages.map(x=>'<div class=msg><span class=dim>'+fmt(x.ts)+' </span><span class=k>'+(x.role==='assistant'?'阿渔':(x.name||x.role))+'</span>: '+x.content+'</div>').join('')}
async function loadFacts(){const f=await api('/api/facts');const tb=document.getElementById('factRows');tb.innerHTML=f.facts.map(x=>'<tr><td>'+x.peer+'</td><td>'+x.k+'</td><td>'+x.v+'</td><td>'+x.conf+'</td><td><button class="act del" onclick="delFact('+x.id+')">删</button><button class="act lock" onclick="lockFact('+x.id+','+(x.locked?'false':'true')+')">'+(x.locked?'已锁':'锁定')+'</button></td></tr>').join('')||'<tr><td colspan=5 class=dim>暂无事实</td></tr>'}
async function addFact(){const peer=document.getElementById('fPeer').value,k=document.getElementById('fK').value,v=document.getElementById('fV').value;if(!peer||!k||!v)return;await api('/api/facts/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({peer,k,v})});loadFacts()}
async function delFact(id){await api('/api/facts/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});loadFacts()}
async function lockFact(id,l){await api('/api/facts/lock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,locked:l})});loadFacts()}
async function loadActions(){const a=await api('/api/actions');document.getElementById('actRows').innerHTML=a.actions.map(x=>'<div class=msg><span class=dim>'+fmt(x.ts)+'</span> <span class=k>'+x.kind+'</span> '+x.peer+' '+x.detail+'</div>').join('')||'<span class=dim>暂无</span>'}
async function doSend(){const scene=document.getElementById('sScene').value,peer=document.getElementById('sPeer').value,text=document.getElementById('sText').value,image_url=document.getElementById('sImg').value,voice_text=document.getElementById('sVoice').value,sticker=document.getElementById('sSticker').checked;const r=await api('/api/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scene,peer,text,image_url,voice_text,sticker})});document.getElementById('sRet').textContent=JSON.stringify(r)}
async function loadSettings(){const s=await api('/api/settings');document.getElementById('settings').innerHTML='模型 '+s.model+' · 通道 '+s.channel+' · 表情包 '+s.sticker_count+' 张 · 静默 '+s.quiet_start+'-'+s.quiet_end+' · 表情概率 '+s.emoji_prob+'<br>主动发言：<b class='+(s.proactive?'k':'r')+'>'+(s.proactive?'开':'关')+'</b> <button class="act" onclick="toggleProactive('+(s.proactive?'false':'true')+')">'+(s.proactive?'关闭':'开启')+'</button>';const p=await api('/api/persona');document.getElementById('persona').value=p.text}
async function toggleProactive(v){await api('/api/settings/proactive',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:v})});loadSettings()}
async function savePersona(){const text=document.getElementById('persona').value;const r=await api('/api/persona',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});document.getElementById('pRet').textContent=JSON.stringify(r)}
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('on'));b.classList.add('on');document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));document.getElementById('tab-'+b.dataset.tab).classList.add('on');if(b.dataset.tab==='chat')loadPeers();if(b.dataset.tab==='facts')loadFacts();if(b.dataset.tab==='actions')loadActions();if(b.dataset.tab==='settings')loadSettings();});
setInterval(refreshStatus,3000);refreshStatus();loadPeers();
</script></body></html>'''


class Admin:
    def __init__(self, host: str, port: int, token: str, store: Store, channel, brain,
                 started_at: float, sticker_dir: str = "", scheduler=None, cfg=None):
        self.host = host
        self.port = port
        self.token = token or ""
        self.store = store
        self.channel = channel
        self.brain = brain
        self.started_at = started_at
        self.sticker_dir = sticker_dir
        self.scheduler = scheduler
        self.cfg = cfg
        self._httpd = None

    # ---------- helpers ----------
    def status(self) -> dict:
        return {
            "uptime_sec": int(time.time() - self.started_at),
            "channel": getattr(self.channel, "name", "?"),
            "channel_connected": bool(getattr(self.channel, "connected", False)),
            "model": getattr(getattr(self.brain, "llm", None), "model", "?"),
            "proactive": bool(getattr(self.scheduler, "enabled", False)),
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

    def _sticker_count(self) -> int:
        if not self.sticker_dir:
            return 0
        return len(glob.glob(self.sticker_dir + "/*.png") + glob.glob(self.sticker_dir + "/*.jpg"))

    def _settings(self) -> dict:
        c = self.cfg
        return {
            "model": getattr(getattr(self.brain, "llm", None), "model", "?"),
            "channel": getattr(self.channel, "name", "?"),
            "connected": bool(getattr(self.channel, "connected", False)),
            "quiet_start": getattr(c, "quiet_start", "?"),
            "quiet_end": getattr(c, "quiet_end", "?"),
            "emoji_prob": getattr(c, "emoji_prob", 0),
            "proactive": bool(getattr(self.scheduler, "enabled", False)),
            "sticker_count": self._sticker_count(),
            "persona_file": getattr(c, "persona_file", ""),
        }

    def _persona_path(self) -> str:
        return getattr(self.cfg, "persona_file", "") if self.cfg else ""

    def _build_out(self, d: dict) -> list[Segment]:
        segs = []
        text = d.get("text") or ""
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
            f = self._pick_sticker()
            if f:
                segs.append(Segment("image", {"file": f}))
        elif d.get("image_url"):
            segs.append(Segment("image", {"file": d["image_url"]}))
        if d.get("face"):
            segs.append(Segment("face", {"id": str(d["face"])}))
        return segs

    # ---------- http ----------
    def start(self) -> None:
        admin = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _auth(self) -> bool:
                q = urllib.parse.urlparse(self.path).query
                return urllib.parse.parse_qs(q).get("token", [""])[0] == admin.token

            def _json(self, code, obj):
                b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def _body(self) -> dict:
                try:
                    n = int(self.headers.get("Content-Length", "0") or 0)
                    return json.loads(self.rfile.read(n) or b"{}")
                except Exception:
                    return {}

            def do_GET(self):
                u = urllib.parse.urlparse(self.path)
                if not self._auth():
                    self._json(403, {"error": "bad token"})
                    return
                q = urllib.parse.parse_qs(u.query)
                p = u.path
                if p == "/":
                    b = _HTML.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(b)))
                    self.end_headers()
                    self.wfile.write(b)
                elif p == "/api/status":
                    self._json(200, admin.status())
                elif p == "/api/peers":
                    self._json(200, {"peers": admin.store.peers_with_stats()})
                elif p == "/api/messages":
                    peer = q.get("peer", [""])[0]
                    if peer:
                        self._json(200, {"messages": admin.store.messages_for_peer(peer, 100)})
                    else:
                        self._json(200, {"messages": admin.store.recent_messages(30)})
                elif p == "/api/facts":
                    self._json(200, {"facts": admin.store.all_facts()})
                elif p == "/api/actions":
                    self._json(200, {"actions": admin.store.actions_recent(50)})
                elif p == "/api/settings":
                    self._json(200, admin._settings())
                elif p == "/api/persona":
                    txt = ""
                    pp = admin._persona_path()
                    if pp and os.path.exists(pp):
                        try:
                            txt = open(pp, "r", encoding="utf-8").read()
                        except Exception:
                            txt = ""
                    self._json(200, {"text": txt})
                else:
                    self.send_response(404); self.end_headers()

            def do_POST(self):
                if not self._auth():
                    self._json(403, {"error": "bad token"}); return
                p = self.path.split("?")[0]
                d = self._body()
                if p == "/api/send":
                    peer = str(d.get("peer", "")); scene = d.get("scene", "private")
                    segs = admin._build_out(d)
                    ok = bool(segs) and admin.channel.send(Outbound(scene, peer, segs))
                    admin.store.log_action("manual_send", peer, (d.get("text") or "[media]")[:50])
                    self._json(200, {"ok": ok})
                elif p == "/api/facts/add":
                    admin.store.add_fact(str(d.get("peer", "")), str(d.get("k", "")), str(d.get("v", "")), 1.0, "manual")
                    self._json(200, {"ok": True})
                elif p == "/api/facts/delete":
                    admin.store.fact_delete(int(d.get("id", 0)))
                    self._json(200, {"ok": True})
                elif p == "/api/facts/lock":
                    admin.store.fact_set_locked(int(d.get("id", 0)), bool(d.get("locked")))
                    self._json(200, {"ok": True})
                elif p == "/api/settings/proactive":
                    if admin.scheduler is not None:
                        admin.scheduler.set_enabled(bool(d.get("enabled")))
                        self._json(200, {"ok": True, "proactive": admin.scheduler.enabled})
                    else:
                        self._json(200, {"ok": False})
                elif p == "/api/persona":
                    txt = d.get("text", "")
                    pp = admin._persona_path()
                    ok = False
                    if pp:
                        try:
                            with open(pp, "w", encoding="utf-8") as f:
                                f.write(txt)
                            admin.brain.persona = txt
                            ok = True
                        except Exception:
                            ok = False
                    self._json(200, {"ok": ok})
                else:
                    self.send_response(404); self.end_headers()

        self._httpd = http.server.ThreadingHTTPServer((self.host, self.port), H)
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        print(f"[admin] http://{self.host}:{self.port}/?token=***", flush=True)

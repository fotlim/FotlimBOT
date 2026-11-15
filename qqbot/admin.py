"""管理面板：标准库 http.server，绑 127.0.0.1，token 鉴权。全能控制台（参考 AstrBot/NapCat/Koishi）。"""
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
from . import logbus


_HTML = r'''<!doctype html><html><head><meta charset="utf-8"><title>阿渔 · 控制台</title>
<style>
:root{color-scheme:dark}
body{background:#0f1115;color:#d7dae0;font-family:system-ui,sans-serif;margin:0;padding:14px}
h2{margin:6px 0 12px}.card{background:#171a21;border:1px solid #232733;border-radius:10px;padding:12px;margin-bottom:12px}
.k{color:#7fd1b9}.r{color:#e0a86b}.dim{color:#8892a4}.b{font-weight:600}
.tabs button{background:#1d222c;border:1px solid #2b3242;color:#cbd3de;border-radius:8px;padding:7px 13px;cursor:pointer;margin:2px}
.tabs button.on{background:#28648c;border-color:#28648c;color:#fff}
input,textarea,select{background:#0f1115;border:1px solid #2b3242;color:#d7dae0;border-radius:6px;padding:6px;margin:3px}
button.act{background:#28648c;border:0;color:#fff;border-radius:6px;padding:6px 12px;cursor:pointer;margin:2px}
button.del{background:#8c3333}button.lock{background:#6a5a24}button.gray{background:#3a4150}
table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #232733;padding:5px;text-align:left;font-size:13px;word-break:break-all}
div.msg{white-space:pre-wrap;word-break:break-all;line-height:1.5}
.tab{display:none}.tab.on{display:block}
.bar{display:inline-block;background:#28648c;vertical-align:bottom;margin-right:4px;border-radius:3px 3px 0 0}
.mini{color:#8892a4;font-size:12px}
.row{display:flex;gap:16px;flex-wrap:wrap}.row>div{flex:1;min-width:220px}
.logbox{background:#0b0d11;border:1px solid #232733;border-radius:8px;padding:8px;height:360px;overflow:auto;font-family:ui-monospace,monospace;font-size:12px;white-space:pre-wrap}
</style></head><body>
<h2>🐟 阿渔 · 控制台</h2>
<div id="status" class="card">loading…</div>
<div class="tabs">
<button data-tab="dash" class="on">仪表盘</button>
<button data-tab="chat">对话</button>
<button data-tab="facts">记忆</button>
<button data-tab="modules">模块</button>
<button data-tab="acl">名单</button>
<button data-tab="logs">日志</button>
<button data-tab="settings">设置</button>
<button data-tab="send">发送</button>
</div>

<div id="tab-dash" class="tab on card">
 <div class="row">
  <div><b>系统资源</b><div id="res" class="mini">…</div></div>
  <div><b>消息统计</b><div id="dstats" class="mini">…</div></div>
  <div><b>模型</b><div id="dmodel" class="mini">…</div></div>
 </div>
 <hr style="border-color:#232733">
 <b>近 7 日消息</b><div id="chart" style="margin-top:8px"></div>
</div>

<div id="tab-chat" class="tab card">
 <b>对话者</b> <select id="peerSel" onchange="loadMsgs()"></select>
 <span class="mini">共 <span id="peerCnt">0</span> 人</span>
 <button class="act gray" onclick="exportPeer()">导出此对话</button>
 <button class="act del" onclick="delPeer()">删除此对话</button>
 <div id="msgs" style="margin-top:8px"></div>
</div>

<div id="tab-facts" class="tab card">
 <b>事实记忆</b>
 <div style="margin:6px 0">新增：<input id="fPeer" placeholder="QQ/peer" size=12><input id="fK" placeholder="类别(称呼/喜欢…)" size=12><input id="fV" placeholder="内容" size=22><button class="act" onclick="addFact()">+ 添加</button></div>
 <table><thead><tr><th>对象</th><th>类别</th><th>内容</th><th>置信</th><th>操作</th></tr></thead><tbody id="factRows"></tbody></table>
</div>

<div id="tab-modules" class="tab card"><b>功能模块开关（即时生效）</b><div id="modRows" style="margin-top:8px"></div></div>

<div id="tab-acl" class="tab card">
 <b>黑白名单</b> <span class="mini">每行一个 QQ 号/群号；白名单非空时只理白名单；黑名单永不理</span><br>
 <div class="row">
  <div><b>白名单</b><br><textarea id="white" cols=22 rows=8></textarea></div>
  <div><b>黑名单</b><br><textarea id="black" cols=22 rows=8></textarea></div>
 </div>
 <button class="act" onclick="saveAcl()">保存名单</button> <span id="aclRet" class="r"></span>
</div>

<div id="tab-logs" class="tab card"><b>运行日志</b> <button class="act gray" onclick="loadLogs()">刷新</button><div id="logbox" class="logbox"></div></div>

<div id="tab-settings" class="tab card">
 <b>模型提供商</b> <span id="modelRet" class="r"></span><br>
 Base <input id="mBase" size=34> Key <input id="mKey" size=14 placeholder="(不变则留空)">
 模型 <input id="mModel" size=30>
 <button class="act" onclick="saveModel()">保存(即时)</button> <button class="act gray" onclick="testModel()">测试连接</button>
 <hr style="border-color:#232733">
 <b>主动发言</b> <span id="proactiveBox"></span>
 <div class="mini">静默时段与表情概率见下</div><div id="settingsExtra" class="mini"></div>
 <hr style="border-color:#232733">
 <b>数据备份</b> <button class="act" onclick="doBackup()">立即快照</button> <span id="bakRet" class="r"></span><div id="baks" class="mini"></div>
 <hr style="border-color:#232733">
 <b>人设 persona.txt</b> <button class="act" onclick="savePersona()">保存</button> <span id="pRet" class="r"></span>
 <br><textarea id="persona" cols=90 rows=10></textarea>
</div>

<div id="tab-send" class="tab card">
 <b>发送测试</b><br>
 场景 <select id="sScene"><option value="private">私聊</option><option value="group">群聊</option></select>
 目标 <input id="sPeer" placeholder="QQ号或群号" size=14>
 <br><textarea id="sText" placeholder="文字内容" cols=64 rows=2></textarea>
 <br>图片URL <input id="sImg" placeholder="http(s) 图片地址" size=42>
 <br>TTS语音 <input id="sVoice" placeholder="文字→合成语音" size=42>
 <label><input type="checkbox" id="sSticker"> 附带表情</label>
 <br><button class="act" onclick="doSend()">发送</button> <span id="sRet" class="r"></span>
</div>

<script>
const T=new URLSearchParams(location.search).get('token')||'';
async function api(p,opt){const sep=p.includes('?')?'&':'?';const r=await fetch(p+sep+'token='+encodeURIComponent(T),opt||{});return r.json();}
function fmt(ts){try{return new Date(ts*1000).toLocaleString()}catch(e){return ts}}
async function refreshStatus(){try{const s=await api('/api/status');
 document.getElementById('status').innerHTML='<span class=k>● 运行</span> '+s.uptime_sec+'s · 通道 '+(s.channel_connected?'<span class=k>在线</span>':'<span class=r>离线</span>')+' · 模型 '+s.model+' · 主动'+(s.proactive?'开':'关')+'<br><span class=mini>消息 '+s.stats.messages+'（今日 '+s.stats.today+'）· 对话者 '+s.stats.peers+' · 事实 '+s.stats.facts+' · 动作 '+s.stats.actions+'</span>';
}catch(e){}}
async function loadDash(){const d=await api('/api/dashboard');
 document.getElementById('res').innerHTML='CPU 负载 '+d.cpu_load+'（'+d.cpu_pct+'%, '+d.cpu_count+'核）<br>内存 '+d.mem_used_mb+'/'+d.mem_total_mb+'MB（'+d.mem_pct+'%）<br>磁盘 '+d.disk.pct+'% 已用';
 document.getElementById('dstats').innerHTML='总消息 '+d.stats.messages+' · 今日 '+d.stats.today+'<br>私聊 '+(d.scenes.private||0)+' · 群聊 '+(d.scenes.group||0);
 document.getElementById('dmodel').innerHTML=d.model;
 const max=Math.max(1,...d.byday.map(x=>x.count));
 document.getElementById('chart').innerHTML=d.byday.map(x=>'<div style="display:inline-block;text-align:center;margin-right:10px"><div class=bar style="height:'+Math.round(x.count/max*100)+'px;width:34px"></div><div class=mini>'+x.day+'</div><div class=mini>'+x.count+'</div></div>').join('');
}
async function loadPeers(){const ps=await api('/api/peers');const sel=document.getElementById('peerSel');sel.innerHTML='';ps.peers.forEach(p=>{const o=document.createElement('option');o.value=p.peer_id;o.textContent=p.peer_id+' ('+p.count+'条)';sel.appendChild(o)});document.getElementById('peerCnt').textContent=ps.peers.length;if(ps.peers.length)loadMsgs();else document.getElementById('msgs').innerHTML='<span class=dim>暂无对话</span>'}
async function loadMsgs(){const peer=document.getElementById('peerSel').value;if(!peer)return;const m=await api('/api/messages?peer='+encodeURIComponent(peer));document.getElementById('msgs').innerHTML=m.messages.map(x=>'<div class=msg><span class=mini>'+fmt(x.ts)+' </span><span class=k>'+(x.role==='assistant'?'阿渔':(x.name||x.role))+'</span>: '+x.content+'</div>').join('')}
function exportPeer(){const peer=document.getElementById('peerSel').value;if(!peer)return;window.open('/api/export?peer='+encodeURIComponent(peer)+'&token='+encodeURIComponent(T),'_blank')}
async function delPeer(){const peer=document.getElementById('peerSel').value;if(!peer||!confirm('删除 '+peer+' 的对话记录？'))return;await api('/api/peer/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({peer})});loadPeers()}
async function loadFacts(){const f=await api('/api/facts');document.getElementById('factRows').innerHTML=f.facts.map(x=>'<tr><td>'+x.peer+'</td><td>'+x.k+'</td><td>'+x.v+'</td><td>'+x.conf+'</td><td><button class="act del" onclick="delFact('+x.id+')">删</button><button class="act lock" onclick="lockFact('+x.id+','+(x.locked?'false':'true')+')">'+(x.locked?'已锁':'锁定')+'</button></td></tr>').join('')||'<tr><td colspan=5 class=dim>暂无事实</td></tr>'}
async function addFact(){const peer=document.getElementById('fPeer').value,k=document.getElementById('fK').value,v=document.getElementById('fV').value;if(!peer||!k||!v)return;await api('/api/facts/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({peer,k,v})});loadFacts()}
async function delFact(id){await api('/api/facts/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});loadFacts()}
async function lockFact(id,l){await api('/api/facts/lock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,locked:l})});loadFacts()}
async function loadModules(){const m=await api('/api/modules');document.getElementById('modRows').innerHTML=m.modules.map(x=>'<div style="margin:6px 0"><b>'+x.label+'</b> <button class="act '+(x.enabled?'':'gray')+'" onclick="toggleMod(\''+x.key+'\','+(x.enabled?'false':'true')+')">'+(x.enabled?'已开启 · 点关闭':'已关闭 · 点开启')+'</button></div>').join('')}
async function toggleMod(k,e){await api('/api/modules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:k,enabled:e})});loadModules()}
async function loadAcl(){const a=await api('/api/acl');document.getElementById('white').value=(a.white||[]).join('\n');document.getElementById('black').value=(a.black||[]).join('\n')}
async function saveAcl(){const white=document.getElementById('white').value.split('\n').map(s=>s.trim()).filter(Boolean),black=document.getElementById('black').value.split('\n').map(s=>s.trim()).filter(Boolean);const r=await api('/api/acl',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({white,black})});document.getElementById('aclRet').textContent=JSON.stringify(r)}
async function loadLogs(){const l=await api('/api/logs');const box=document.getElementById('logbox');box.textContent=(l.lines||[]).join('\n');box.scrollTop=box.scrollHeight}
async function loadSettings(){const m=await api('/api/model');document.getElementById('mBase').value=m.base;document.getElementById('mModel').value=m.model;document.getElementById('mKey').placeholder=m.key_set?'(已设置，留空不改)':'(未设置)';
 const s=await api('/api/settings');document.getElementById('proactiveBox').innerHTML='<b class='+(s.proactive?'k':'r')+'>'+(s.proactive?'开启':'关闭')+'</b> <button class="act" onclick="toggleProactive('+(s.proactive?'false':'true')+')">'+(s.proactive?'关闭':'开启')+'</button>';document.getElementById('settingsExtra').innerHTML='静默 '+s.quiet_start+'-'+s.quiet_end+' · 表情概率 '+s.emoji_prob+' · 表情包 '+s.sticker_count+' 张';
 const bs=await api('/api/backups');document.getElementById('baks').innerHTML='备份：'+((bs.backups||[]).map(b=>b.name+' ('+b.size_kb+'KB)').join(' · ')||'无');
 const p=await api('/api/persona');document.getElementById('persona').value=p.text}
async function saveModel(){const base=document.getElementById('mBase').value,model=document.getElementById('mModel').value,key=document.getElementById('mKey').value;const r=await api('/api/model',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({base,model,key})});document.getElementById('modelRet').textContent=JSON.stringify(r)}
async function testModel(){document.getElementById('modelRet').textContent='测试中…';const r=await api('/api/model/test',{method:'POST'});document.getElementById('modelRet').textContent=JSON.stringify(r)}
async function toggleProactive(v){await api('/api/settings/proactive',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:v})});loadSettings()}
async function doBackup(){const r=await api('/api/backup',{method:'POST'});document.getElementById('bakRet').textContent=JSON.stringify(r);loadSettings()}
async function savePersona(){const text=document.getElementById('persona').value;const r=await api('/api/persona',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});document.getElementById('pRet').textContent=JSON.stringify(r)}
async function doSend(){const scene=document.getElementById('sScene').value,peer=document.getElementById('sPeer').value,text=document.getElementById('sText').value,image_url=document.getElementById('sImg').value,voice_text=document.getElementById('sVoice').value,sticker=document.getElementById('sSticker').checked;const r=await api('/api/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scene,peer,text,image_url,voice_text,sticker})});document.getElementById('sRet').textContent=JSON.stringify(r)}
const loaders={dash:loadDash,chat:loadPeers,facts:loadFacts,modules:loadModules,acl:loadAcl,logs:loadLogs,settings:loadSettings};
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('on'));b.classList.add('on');document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));document.getElementById('tab-'+b.dataset.tab).classList.add('on');if(loaders[b.dataset.tab])loaders[b.dataset.tab]()});
setInterval(refreshStatus,3000);refreshStatus();loadDash();
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

    # ---------- builders ----------
    def status(self) -> dict:
        return {
            "uptime_sec": int(time.time() - self.started_at),
            "channel": getattr(self.channel, "name", "?"),
            "channel_connected": bool(getattr(self.channel, "connected", False)),
            "model": getattr(getattr(self.brain, "llm", None), "model", "?"),
            "proactive": bool(getattr(self.scheduler, "enabled", False)),
            "stats": self.store.stats(),
        }

    def dashboard(self) -> dict:
        import shutil
        try:
            load = os.getloadavg()[0]
        except Exception:
            load = 0.0
        cpu = os.cpu_count() or 1
        mem = {}
        try:
            with open("/proc/meminfo") as f:
                for ln in f:
                    parts = ln.split(":")
                    if len(parts) == 2:
                        mem[parts[0]] = int(parts[1].split()[0])
        except Exception:
            pass
        total = mem.get("MemTotal", 0)
        avail = mem.get("MemAvailable", 0)
        mem_pct = round((total - avail) / total * 100, 1) if total else 0
        try:
            du = shutil.disk_usage("/")
            disk = {"total_gb": round(du.total / 1e9, 1), "used_gb": round(du.used / 1e9, 1), "pct": round(du.used / du.total * 100, 1)}
        except Exception:
            disk = {"pct": 0}
        return {"cpu_load": round(load, 2), "cpu_count": cpu, "cpu_pct": round(load / cpu * 100, 1),
                "mem_total_mb": round(total / 1024), "mem_used_mb": round((total - avail) / 1024), "mem_pct": mem_pct,
                "disk": disk, "stats": self.store.stats(), "byday": self.store.stats_by_day(7),
                "scenes": self.store.scene_stats(), "model": getattr(getattr(self.brain, "llm", None), "model", "?")}

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
        return {"model": getattr(getattr(self.brain, "llm", None), "model", "?"),
                "channel": getattr(self.channel, "name", "?"),
                "connected": bool(getattr(self.channel, "connected", False)),
                "quiet_start": getattr(c, "quiet_start", "?"), "quiet_end": getattr(c, "quiet_end", "?"),
                "emoji_prob": getattr(c, "emoji_prob", 0),
                "proactive": bool(getattr(self.scheduler, "enabled", False)),
                "sticker_count": self._sticker_count(), "persona_file": getattr(c, "persona_file", "")}

    def _modules(self) -> list[dict]:
        defs = [("memory", "长期记忆（事实+检索）"), ("vision", "看图（视觉理解）"),
                ("emoji", "自动表情"), ("voice", "语音（TTS 发送）"), ("proactive", "主动发言")]
        out = []
        for key, label in defs:
            if key == "proactive":
                en = bool(getattr(self.scheduler, "enabled", False))
            else:
                en = self.store.flag("flag:" + key, True)
            out.append({"key": key, "label": label, "enabled": en})
        return out

    def _persona_path(self) -> str:
        return getattr(self.cfg, "persona_file", "") if self.cfg else ""

    def _backup_dir(self) -> str:
        return os.path.join(getattr(self.cfg, "data_dir", "."), "backup")

    def _build_out(self, d: dict) -> list[Segment]:
        segs = []
        text = d.get("text") or ""
        if text:
            segs.append(Segment.text(text))
        if d.get("voice_text") and self.store.flag("flag:voice", True):
            vp = voice.synth(d["voice_text"])
            if vp:
                try:
                    vb = base64.b64encode(open(vp, "rb").read()).decode()
                    segs.append(Segment("record", {"file": "base64://" + vb}))
                except Exception:
                    pass
        if d.get("sticker") and self.store.flag("flag:emoji", True):
            f = self._pick_sticker()
            if f:
                segs.append(Segment("image", {"file": f}))
        elif d.get("image_url"):
            segs.append(Segment("image", {"file": d["image_url"]}))
        if d.get("face"):
            segs.append(Segment("face", {"id": str(d["face"])}))
        return segs

    def start(self) -> None:
        admin = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _auth(self):
                q = urllib.parse.urlparse(self.path).query
                return urllib.parse.parse_qs(q).get("token", [""])[0] == admin.token

            def _json(self, code, obj):
                b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

            def _text(self, code, text, fname=None):
                b = text.encode("utf-8")
                self.send_response(code); self.send_header("Content-Type", "text/plain; charset=utf-8")
                if fname:
                    self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

            def _body(self):
                try:
                    n = int(self.headers.get("Content-Length", "0") or 0)
                    return json.loads(self.rfile.read(n) or b"{}")
                except Exception:
                    return {}

            def do_GET(self):
                u = urllib.parse.urlparse(self.path)
                if not self._auth():
                    self._json(403, {"error": "bad token"}); return
                p = u.path; q = urllib.parse.parse_qs(u.query)
                if p == "/":
                    b = _HTML.encode("utf-8"); self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
                elif p == "/api/status": self._json(200, admin.status())
                elif p == "/api/dashboard": self._json(200, admin.dashboard())
                elif p == "/api/peers": self._json(200, {"peers": admin.store.peers_with_stats()})
                elif p == "/api/messages":
                    peer = q.get("peer", [""])[0]
                    self._json(200, {"messages": admin.store.messages_for_peer(peer, 200) if peer else admin.store.recent_messages(30)})
                elif p == "/api/export":
                    peer = q.get("peer", [""])[0]
                    rows = admin.store.messages_for_peer(peer, 1000)
                    txt = "\n".join(f"[{time.strftime('%Y-%m-%d %H:%M', time.localtime(r['ts']))}] {r['role']}: {r['content']}" for r in rows)
                    self._text(200, txt or "（无记录）", f"chat-{peer}.txt")
                elif p == "/api/facts": self._json(200, {"facts": admin.store.all_facts()})
                elif p == "/api/actions": self._json(200, {"actions": admin.store.actions_recent(50)})
                elif p == "/api/modules": self._json(200, {"modules": admin._modules()})
                elif p == "/api/acl": self._json(200, {"white": admin.store.kv_list_get("acl:white"), "black": admin.store.kv_list_get("acl:black")})
                elif p == "/api/logs": self._json(200, {"lines": logbus.lines(300)})
                elif p == "/api/model":
                    llm = admin.brain.llm
                    self._json(200, {"base": getattr(llm, "base", ""), "model": getattr(llm, "model", ""), "key_set": bool(getattr(llm, "key", ""))})
                elif p == "/api/settings": self._json(200, admin._settings())
                elif p == "/api/persona":
                    txt = ""
                    pp = admin._persona_path()
                    if pp and os.path.exists(pp):
                        try: txt = open(pp, "r", encoding="utf-8").read()
                        except Exception: txt = ""
                    self._json(200, {"text": txt})
                elif p == "/api/backups": self._json(200, {"backups": admin.store.list_backups(admin._backup_dir())})
                else:
                    self.send_response(404); self.end_headers()

            def do_POST(self):
                if not self._auth():
                    self._json(403, {"error": "bad token"}); return
                p = self.path.split("?")[0]; d = self._body()
                if p == "/api/send":
                    peer = str(d.get("peer", "")); scene = d.get("scene", "private")
                    segs = admin._build_out(d)
                    ok = bool(segs) and admin.channel.send(Outbound(scene, peer, segs))
                    admin.store.log_action("manual_send", peer, (d.get("text") or "[media]")[:50])
                    self._json(200, {"ok": ok})
                elif p == "/api/facts/add":
                    admin.store.add_fact(str(d.get("peer", "")), str(d.get("k", "")), str(d.get("v", "")), 1.0, "manual"); self._json(200, {"ok": True})
                elif p == "/api/facts/delete":
                    admin.store.fact_delete(int(d.get("id", 0))); self._json(200, {"ok": True})
                elif p == "/api/facts/lock":
                    admin.store.fact_set_locked(int(d.get("id", 0)), bool(d.get("locked"))); self._json(200, {"ok": True})
                elif p == "/api/modules":
                    name = str(d.get("name", "")); en = bool(d.get("enabled"))
                    if name == "proactive" and admin.scheduler is not None:
                        admin.scheduler.set_enabled(en)
                    else:
                        admin.store.flag_set("flag:" + name, en)
                    self._json(200, {"ok": True})
                elif p == "/api/acl":
                    admin.store.kv_list_set("acl:white", [str(x) for x in (d.get("white") or [])])
                    admin.store.kv_list_set("acl:black", [str(x) for x in (d.get("black") or [])])
                    self._json(200, {"ok": True, "white": len(d.get("white") or []), "black": len(d.get("black") or [])})
                elif p == "/api/model":
                    llm = admin.brain.llm
                    if d.get("base"): llm.base = d["base"]
                    if d.get("model"): llm.model = d["model"]
                    if d.get("key"): llm.key = d["key"]
                    self._json(200, {"ok": True, "note": "已即时生效（重启后请改 .env 持久化）"})
                elif p == "/api/model/test":
                    t0 = time.time()
                    try:
                        out = admin.brain.llm.chat([{"role": "user", "content": "ping"}], max_tokens=8)
                        self._json(200, {"ok": True, "latency_ms": int((time.time() - t0) * 1000), "sample": (out or "")[:60]})
                    except Exception as e:
                        self._json(200, {"ok": False, "error": str(e)[:200]})
                elif p == "/api/settings/proactive":
                    if admin.scheduler is not None:
                        admin.scheduler.set_enabled(bool(d.get("enabled")))
                        self._json(200, {"ok": True, "proactive": admin.scheduler.enabled})
                    else:
                        self._json(200, {"ok": False})
                elif p == "/api/backup":
                    try:
                        path = admin.store.backup(admin._backup_dir())
                        admin.store.log_action("backup", "", os.path.basename(path))
                        self._json(200, {"ok": True, "file": os.path.basename(path)})
                    except Exception as e:
                        self._json(200, {"ok": False, "error": str(e)[:200]})
                elif p == "/api/peer/delete":
                    admin.store.delete_peer(str(d.get("peer", ""))); self._json(200, {"ok": True})
                elif p == "/api/persona":
                    txt = d.get("text", ""); pp = admin._persona_path(); ok = False
                    if pp:
                        try:
                            with open(pp, "w", encoding="utf-8") as f: f.write(txt)
                            admin.brain.persona = txt; ok = True
                        except Exception:
                            ok = False
                    self._json(200, {"ok": ok})
                else:
                    self.send_response(404); self.end_headers()

        self._httpd = http.server.ThreadingHTTPServer((self.host, self.port), H)
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        print(f"[admin] http://{self.host}:{self.port}/?token=***", flush=True)

"""管理面板：标准库 http.server，绑 127.0.0.1，token 鉴权。现代侧边栏控制台。"""
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
from . import emotion
from . import actions


_HTML = r'''<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>阿渔 · 控制台</title>
<style>
*{box-sizing:border-box}
:root{--bg:#0b0e14;--side:#0e131b;--card:#121722;--card2:#151b27;--line:#1e2633;--tx:#dbe2ec;--dim:#8b95a7;--acc:#3b82f6;--acc2:#22d3ee;--ok:#34d399;--warn:#fbbf24;--bad:#f87171}
body{margin:0;background:var(--bg);color:var(--tx);font-family:system-ui,-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}
.app{display:flex;min-height:100vh}
.side{width:220px;flex:0 0 220px;background:var(--side);border-right:1px solid var(--line);padding:18px 12px;position:sticky;top:0;height:100vh;overflow:auto}
.brand{display:flex;align-items:center;gap:10px;padding:6px 10px 18px;font-size:18px;font-weight:700}
.brand .logo{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,#3b82f6,#22d3ee);display:flex;align-items:center;justify-content:center;font-size:19px}
.nav-item{display:flex;align-items:center;gap:11px;padding:10px 12px;border-radius:10px;color:var(--dim);cursor:pointer;font-size:14px;margin:2px 0;transition:.15s;user-select:none}
.nav-item:hover{background:#151b27;color:var(--tx)}
.nav-item.on{background:linear-gradient(90deg,rgba(59,130,246,.22),rgba(34,211,238,.10));color:#fff;box-shadow:inset 0 0 0 1px rgba(59,130,246,.35)}
.nav-item .ic{width:20px;text-align:center}
.main{flex:1;min-width:0;padding:22px 26px}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:20px;flex-wrap:wrap}
.topbar h1{font-size:20px;margin:0;font-weight:700}
.pill{display:inline-flex;align-items:center;gap:9px;background:var(--card);border:1px solid var(--line);border-radius:999px;padding:9px 16px;font-size:13px;color:var(--dim)}
.dot{width:9px;height:9px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 0 rgba(52,211,153,.5);animation:pulse 2s infinite}
.dot.off{background:var(--bad);animation:none}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(52,211,153,.45)}70%{box-shadow:0 0 0 8px rgba(52,211,153,0)}100%{box-shadow:0 0 0 0 rgba(52,211,153,0)}}
.page{display:none;animation:fade .2s ease}
.page.on{display:block}
@keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:16px;box-shadow:0 4px 14px rgba(0,0,0,.18)}
.card h3{margin:0 0 12px;font-size:15px;font-weight:600;color:#e8edf5;display:flex;align-items:center;gap:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px}
.kpi .lab{color:var(--dim);font-size:12px;letter-spacing:.3px}
.kpi .num{font-size:24px;font-weight:700;margin-top:6px;background:linear-gradient(90deg,#e8edf5,#9fb4d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.kpi .sub{color:var(--dim);font-size:12px;margin-top:4px}
.k{color:var(--acc2)}.r{color:var(--warn)}.ok{color:var(--ok)}.bad{color:var(--bad)}.dim{color:var(--dim)}
.mini{color:var(--dim);font-size:12px}
input,textarea,select{background:#0d121b;border:1px solid var(--line);color:var(--tx);border-radius:9px;padding:8px 10px;margin:3px;font-size:13px;outline:none;transition:.15s}
input:focus,textarea:focus,select:focus{border-color:var(--acc);box-shadow:0 0 0 3px rgba(59,130,246,.15)}
textarea{resize:vertical}
button.act{background:linear-gradient(180deg,#3b82f6,#2563eb);border:0;color:#fff;border-radius:9px;padding:8px 14px;cursor:pointer;margin:3px;font-size:13px;font-weight:600;transition:.15s}
button.act:hover{filter:brightness(1.1)}
button.gray{background:#2a3342}button.del{background:#b23b3b}button.lock{background:#8a6d1f}
table{width:100%;border-collapse:collapse}
th,td{border-bottom:1px solid var(--line);padding:9px 8px;text-align:left;font-size:13px;word-break:break-all}
th{color:var(--dim);font-weight:600;font-size:12px;letter-spacing:.3px}
tbody tr:hover{background:#161d29}
.chatbox{height:460px;overflow:auto;padding:6px;background:#0d121b;border-radius:12px;border:1px solid var(--line);margin-top:10px}
.msgrow{display:flex;margin:7px 0}
.msgrow.right{justify-content:flex-end}.msgrow.left{justify-content:flex-start}
.bubble{max-width:72%;padding:9px 13px;border-radius:13px;font-size:13.5px;line-height:1.55;white-space:pre-wrap;word-break:break-word}
.bubble.me{background:#243b55;border-bottom-right-radius:4px}
.bubble.bot{background:#1a2230;border-bottom-left-radius:4px}
.bar{display:inline-block;background:linear-gradient(180deg,#3b82f6,#22d3ee);vertical-align:bottom;margin-right:10px;border-radius:4px 4px 0 0;min-height:3px}
.logbox{background:#080a0f;border:1px solid var(--line);border-radius:12px;padding:12px;height:420px;overflow:auto;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;white-space:pre-wrap;color:#a9b6c9}
.logbox::-webkit-scrollbar,.chatbox::-webkit-scrollbar,.side::-webkit-scrollbar{width:8px}
.logbox::-webkit-scrollbar-thumb,.chatbox::-webkit-scrollbar-thumb,.side::-webkit-scrollbar-thumb{background:#243040;border-radius:8px}
.row{display:flex;gap:22px;flex-wrap:wrap}
.toolbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px}
hr{border:0;border-top:1px solid var(--line);margin:16px 0}
.tag{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;background:#1c2635;color:var(--dim)}
@media(max-width:820px){.app{flex-direction:column}.side{width:auto;flex:none;height:auto;position:static;display:flex;gap:6px;overflow-x:auto;border-right:0;border-bottom:1px solid var(--line)}.brand{padding:4px 8px}.nav-item{white-space:nowrap}.main{padding:14px}}
</style></head><body>
<div class="app">
<aside class="side">
  <div class="brand"><span class="logo">🐟</span><span>阿渔</span></div>
  <div class="nav-item on" data-tab="dash"><span class="ic">📊</span>仪表盘</div>
  <div class="nav-item" data-tab="chat"><span class="ic">💬</span>对话</div>
  <div class="nav-item" data-tab="facts"><span class="ic">🧠</span>记忆</div>
  <div class="nav-item" data-tab="modules"><span class="ic">🧩</span>模块</div>
  <div class="nav-item" data-tab="acl"><span class="ic">🛡️</span>名单</div>
  <div class="nav-item" data-tab="logs"><span class="ic">📜</span>日志</div>
  <div class="nav-item" data-tab="settings"><span class="ic">⚙️</span>设置</div>
  <div class="nav-item" data-tab="emotions"><span class="ic">💗</span>情绪</div>
  <div class="nav-item" data-tab="caps"><span class="ic">🛠️</span>能力</div>
  <div class="nav-item" data-tab="send"><span class="ic">✉️</span>发送</div>
</aside>
<main class="main">
  <div class="topbar">
    <h1 id="pageTitle">仪表盘</h1>
    <div id="status" class="pill">连接中…</div>
  </div>

  <section id="tab-dash" class="page on">
    <div class="grid">
      <div class="card kpi"><div class="lab">系统资源</div><div id="res" class="sub">…</div></div>
      <div class="card kpi"><div class="lab">消息统计</div><div id="dstats" class="sub">…</div></div>
      <div class="card kpi"><div class="lab">当前模型</div><div id="dmodel" class="num" style="font-size:15px">…</div></div>
    </div>
    <div class="card"><h3>近 7 日消息量</h3><div id="chart"></div></div>
  </section>

  <section id="tab-chat" class="page">
    <div class="card">
      <div class="toolbar">
        <b>对话者</b> <select id="peerSel" onchange="loadMsgs()"></select>
        <span class="mini">共 <span id="peerCnt">0</span> 人</span>
        <button class="act gray" onclick="exportPeer()">导出</button>
        <button class="act del" onclick="delPeer()">删除对话</button>
      </div>
      <div id="msgs" class="chatbox"></div>
    </div>
  </section>

  <section id="tab-emotions" class="page">
    <div class="card"><h3>情绪状态（PAD 情绪场 · 好感 · 精力）</h3>
      <table><thead><tr><th>对话者</th><th>心情</th><th>好感</th><th>愉悦P</th><th>唤醒A</th><th>掌控D</th><th>精力</th><th>操作</th></tr></thead><tbody id="emoRows"></tbody></table>
      <div class="toolbar" style="margin-top:12px">手动设置：<input id="ePeer" placeholder="QQ/peer" size="12"> 心情 <input id="eMood" placeholder="开心/害羞/难过/生气" size="10"> 好感 <input id="eAff" type="number" step="any" placeholder="0-100" size="6"><button class="act" onclick="setEmotion()">应用</button> <span id="eRet" class="r"></span></div>
    </div>
  </section>

  <section id="tab-facts" class="page">
    <div class="card">
      <h3>事实记忆</h3>
      <div class="toolbar">新增：<input id="fPeer" placeholder="QQ/peer" size="12"><input id="fK" placeholder="类别(称呼/喜欢…)" size="12"><input id="fV" placeholder="内容" size="22"><button class="act" onclick="addFact()">+ 添加</button></div>
      <table><thead><tr><th>对象</th><th>类别</th><th>内容</th><th>置信</th><th>操作</th></tr></thead><tbody id="factRows"></tbody></table>
    </div>
  </section>

  <section id="tab-modules" class="page">
    <div class="card"><h3>模块 · 功能设置（即时生效）</h3><div id="modEditor"></div><div style="margin-top:10px"><button class="act" onclick="saveSettingsFull()">保存全部设置</button> <span id="modRet" class="r"></span></div></div>
  </section>

  <section id="tab-acl" class="page">
    <div class="card">
      <h3>黑白名单</h3>
      <div class="mini" style="margin-bottom:10px">每行一个 QQ 号/群号；白名单非空时只理白名单；黑名单永不理。</div>
      <div class="row">
        <div style="flex:1"><b>白名单</b><br><textarea id="white" cols="24" rows="9"></textarea></div>
        <div style="flex:1"><b>黑名单</b><br><textarea id="black" cols="24" rows="9"></textarea></div>
      </div>
      <button class="act" onclick="saveAcl()">保存名单</button> <span id="aclRet" class="r"></span>
    </div>
  </section>

  <section id="tab-logs" class="page">
    <div class="card"><h3>运行日志 <button class="act gray" style="margin-left:auto" onclick="loadLogs()">刷新</button></h3><div id="logbox" class="logbox"></div></div>
  </section>

  <section id="tab-settings" class="page">
    <div class="card">
      <h3>模型提供商 <span id="modelRet" class="r mini"></span></h3>
      <div class="toolbar">Base <input id="mBase" size="34"> Key <input id="mKey" size="14" placeholder="(留空不改)"> 模型 <input id="mModel" size="30"></div>
      <button class="act" onclick="saveModel()">保存(即时)</button><button class="act gray" onclick="testModel()">测试连接</button>
    </div>
    <div class="card"><h3>主动发言</h3><span id="proactiveBox"></span><div id="settingsExtra" class="mini" style="margin-top:8px"></div></div>
    <div class="card"><h3>数据备份 <span id="bakRet" class="r mini"></span></h3><button class="act" onclick="doBackup()">立即快照</button><div id="baks" class="mini" style="margin-top:8px"></div></div>
    <div class="card"><h3>人设 persona.txt <button class="act" style="margin-left:auto" onclick="savePersona()">保存</button> <span id="pRet" class="r mini"></span></h3><textarea id="persona" cols="90" rows="11" style="width:100%"></textarea></div>
  </section>

  <section id="tab-send" class="page">
    <div class="card">
      <h3>发送测试</h3>
      <div class="toolbar">场景 <select id="sScene"><option value="private">私聊</option><option value="group">群聊</option></select> 目标 <input id="sPeer" placeholder="QQ号或群号" size="14"></div>
      <div style="margin:6px 0"><textarea id="sText" placeholder="文字内容" cols="64" rows="2" style="width:100%"></textarea></div>
      <div class="toolbar">图片URL <input id="sImg" placeholder="http(s) 图片地址" size="42"> TTS语音 <input id="sVoice" placeholder="文字→合成语音" size="42"></div>
      <label class="mini"><input type="checkbox" id="sSticker"> 附带表情</label>
      <div style="margin-top:10px"><button class="act" onclick="doSend()">发送</button> <span id="sRet" class="r"></span></div>
    </div>
  </section>
  <section id="tab-caps" class="page">
    <div class="card"><h3>① 昵称 / 签名</h3>
      <div class="toolbar">昵称 <input id="capNick" size="16" placeholder="新昵称"><button class="act" onclick="doNick()">改昵称</button> 签名 <input id="capSign" size="20" placeholder="个性签名"><button class="act" onclick="doSign()">改签名</button> <span id="capRet" class="r"></span></div>
      <div class="mini">当前昵称：<span id="curNick">?</span></div>
    </div>
    <div class="card"><h3>② 换头像</h3>
      <div class="toolbar">图片URL/路径 <input id="capAvatar" size="46" placeholder="http(s):// 或本地路径"><button class="act" onclick="doAvatar()">换头像</button> <span id="avatarRet" class="r"></span></div>
    </div>
    <div class="card"><h3>③ QQ空间</h3>
      <div class="toolbar"><textarea id="qzText" placeholder="要发的说说…" cols="60" rows="2"></textarea><button class="act" onclick="doQzonePost()">发说说</button> <span id="qzRet" class="r"></span></div>
      <div class="toolbar"><button class="act gray" onclick="loadFeeds()">拉取好友动态</button><span class="mini">点「赞」给好友说说点赞</span></div>
      <table><thead><tr><th>昵称</th><th>内容</th><th>tid</th><th>操作</th></tr></thead><tbody id="feedRows"></tbody></table>
    </div>
  </section>
</main></div>

<script>
const T=new URLSearchParams(location.search).get('token')||'';
async function api(p,opt){const sep=p.includes('?')?'&':'?';const r=await fetch(p+sep+'token='+encodeURIComponent(T),opt||{});return r.json();}
function fmt(ts){try{return new Date(ts*1000).toLocaleString()}catch(e){return ts}}
async function refreshStatus(){try{const s=await api('/api/status');const on=s.channel_connected;
 document.getElementById('status').innerHTML='<span class="dot '+(on?'':'off')+'"></span>'+(on?'在线':'离线')+' · '+s.uptime_sec+'s · '+(s.proactive?'主动开':'主动关')+' · '+(s.stats.messages)+' 条消息';
}catch(e){document.getElementById('status').textContent='连接断开'}}
async function loadDash(){const d=await api('/api/dashboard');
 document.getElementById('res').innerHTML='CPU '+d.cpu_load+'（'+d.cpu_pct+'% / '+d.cpu_count+'核）<div class="mini">内存 '+d.mem_used_mb+'/'+d.mem_total_mb+' MB（'+d.mem_pct+'%）· 磁盘 '+d.disk.pct+'%</div>';
 document.getElementById('dstats').innerHTML='共 '+d.stats.messages+' · 今日 '+d.stats.today+'<div class="mini">私聊 '+(d.scenes.private||0)+' · 群聊 '+(d.scenes.group||0)+' · 对话者 '+d.stats.peers+'</div>';
 document.getElementById('dmodel').textContent=d.model;
 const max=Math.max(1,...d.byday.map(x=>x.count));
 document.getElementById('chart').innerHTML=d.byday.map(x=>'<div style="display:inline-block;text-align:center;margin-right:14px"><div class="bar" style="height:'+Math.round(x.count/max*120)+'px;width:36px"></div><div class="mini">'+x.day+'</div><div class="mini">'+x.count+'</div></div>').join('');
}
async function loadPeers(){const ps=await api('/api/peers');const sel=document.getElementById('peerSel');sel.innerHTML='';ps.peers.forEach(p=>{const o=document.createElement('option');o.value=p.peer_id;o.textContent=p.peer_id+' ('+p.count+'条)';sel.appendChild(o)});document.getElementById('peerCnt').textContent=ps.peers.length;if(ps.peers.length)loadMsgs();else document.getElementById('msgs').innerHTML='<span class=dim>暂无对话</span>'}
async function loadMsgs(){const peer=document.getElementById('peerSel').value;if(!peer)return;const m=await api('/api/messages?peer='+encodeURIComponent(peer));document.getElementById('msgs').innerHTML=m.messages.map(x=>'<div class="msgrow '+(x.role==='assistant'?'right':'left')+'"><div class="bubble '+(x.role==='assistant'?'bot':'me')+'"><div class="mini">'+fmt(x.ts)+(x.role==='assistant'?' · 阿渔':(' · '+(x.name||x.role)))+'</div>'+x.content+'</div></div>').join('')}
function exportPeer(){const peer=document.getElementById('peerSel').value;if(!peer)return;window.open('/api/export?peer='+encodeURIComponent(peer)+'&token='+encodeURIComponent(T),'_blank')}
async function delPeer(){const peer=document.getElementById('peerSel').value;if(!peer||!confirm('删除 '+peer+' 的对话记录？'))return;await api('/api/peer/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({peer})});loadPeers()}
async function loadFacts(){const f=await api('/api/facts');document.getElementById('factRows').innerHTML=f.facts.map(x=>'<tr><td>'+x.peer+'</td><td><span class=tag>'+x.k+'</span></td><td>'+x.v+'</td><td>'+x.conf+'</td><td><button class="act del" onclick="delFact('+x.id+')">删</button><button class="act lock" onclick="lockFact('+x.id+','+(x.locked?'false':'true')+')">'+(x.locked?'已锁':'锁定')+'</button></td></tr>').join('')||'<tr><td colspan=5 class=dim>暂无事实</td></tr>'}
async function addFact(){const peer=document.getElementById('fPeer').value,k=document.getElementById('fK').value,v=document.getElementById('fV').value;if(!peer||!k||!v)return;await api('/api/facts/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({peer,k,v})});loadFacts()}
async function delFact(id){await api('/api/facts/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});loadFacts()}
async function lockFact(id,l){await api('/api/facts/lock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,locked:l})});loadFacts()}
const MSCHEMA={memory:{t:'长期记忆',f:[['enabled','bool','启用'],['retrieve','num','检索条数']]},vision:{t:'看图（视觉）',f:[['enabled','bool','启用']]},emoji:{t:'自动表情',f:[['enabled','bool','启用'],['prob','num','概率0-1']]},voice:{t:'语音TTS',f:[['enabled','bool','启用'],['voice','text','音色']]},proactive:{t:'主动发言',f:[['enabled','bool','启用'],['quiet_start','text','静默开始'],['quiet_end','text','静默结束'],['min_idle_h','num','最小空闲h']]},reply:{t:'回复',f:[['max_tokens','num','最大tokens'],['history','num','上下文条数'],['reasoning','sel:none low medium high','推理强度'],['bubble_len','num','每句字数']]},rate:{t:'频率',f:[['qpm','num','每分钟上限']]},emotion:{t:'情绪/好感',f:[['enabled','bool','启用'],['use_llm','bool','LLM评估(慢)'],['decay_per_hour','num','每小时衰减'],['baseline_affinity','num','初始好感']]},moderation:{t:'屏蔽词',f:[['enabled','bool','启用'],['words','text','词库(逗号分隔)'],['action','sel:skip mask','命中处理']]},autonomy:{t:'自主行为',f:[['enabled','bool','启用'],['allow_like','bool','自主点赞'],['allow_qzone_post','bool','自主发说说'],['allow_nickname','bool','自主改昵称'],['min_interval_hours','num','最短间隔(小时)'],['allow_avatar','bool','自主换头像(未启用)']]},humanize:{t:'拟人化(分条/延迟)',f:[['enabled','bool','启用'],['read_min_ms','num','读延迟下限ms'],['read_max_ms','num','读延迟上限ms'],['per_char_ms','num','每字ms'],['bubble_gap_min_ms','num','气泡间隔下限ms'],['bubble_gap_max_ms','num','气泡间隔上限ms']]}};
let _s={};
async function loadModules(){_s=await api('/api/settings_full');let h='';for(const sec in MSCHEMA){const def=MSCHEMA[sec];h+='<div class="card" style="margin:0 0 10px;padding:13px"><b>'+def.t+'</b><div class="toolbar" style="margin-top:8px">';for(const fld of def.f){const k=fld[0],ty=fld[1],lab=fld[2],v=_s[sec][k];if(ty==='bool'){h+='<label class="mini"><input type="checkbox" id="set_'+sec+'_'+k+'" '+(v?'checked':'')+'> '+lab+'</label>';}else if(ty.indexOf('sel:')===0){const opts=ty.slice(4).split(' ');h+=lab+' <select id="set_'+sec+'_'+k+'">'+opts.map(o=>'<option '+(o===v?'selected':'')+'>'+o+'</option>').join('')+'</select>';}else{const t2=ty==='num'?'number':'text';h+=lab+' <input type="'+t2+'" '+(ty==='num'?'step=any ':'')+'id="set_'+sec+'_'+k+'" value="'+v+'" size="'+(ty==='num'?'6':'10')+'">';}}h+='</div></div>';}document.getElementById('modEditor').innerHTML=h}
async function saveSettingsFull(){const patch={};for(const sec in MSCHEMA){patch[sec]={};for(const fld of MSCHEMA[sec].f){const k=fld[0],ty=fld[1];const el=document.getElementById('set_'+sec+'_'+k);patch[sec][k]=ty==='bool'?el.checked:(ty==='num'?parseFloat(el.value):el.value);}}const r=await api('/api/settings_full',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(patch)});document.getElementById('modRet').textContent=r.ok?'已保存并生效':'保存失败'}
async function loadAcl(){const a=await api('/api/acl');document.getElementById('white').value=(a.white||[]).join('\n');document.getElementById('black').value=(a.black||[]).join('\n')}
async function saveAcl(){const white=document.getElementById('white').value.split('\n').map(s=>s.trim()).filter(Boolean),black=document.getElementById('black').value.split('\n').map(s=>s.trim()).filter(Boolean);const r=await api('/api/acl',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({white,black})});document.getElementById('aclRet').textContent='已保存 白'+r.white+'/黑'+r.black}
async function loadLogs(){const l=await api('/api/logs');const box=document.getElementById('logbox');box.textContent=(l.lines||[]).join('\n');box.scrollTop=box.scrollHeight}
async function loadEmotions(){const e=await api('/api/emotions');document.getElementById('emoRows').innerHTML=(e.emotions||[]).map(x=>'<tr><td>'+x.peer_id+'</td><td><span class=tag>'+x.mood+'</span></td><td>'+x.affinity+'</td><td>'+x.p+'</td><td>'+x.a+'</td><td>'+x.d+'</td><td>'+x.energy+'</td><td><button class="act lock" onclick="document.getElementById(\'ePeer\').value=\''+x.peer_id+'\';document.getElementById(\'eAff\').value=\''+x.affinity+'\'">选中</button></td></tr>').join('')||'<tr><td colspan=8 class=dim>暂无情绪记录（聊两句就有了）</td></tr>'}
async function setEmotion(){const peer=document.getElementById('ePeer').value,mood=document.getElementById('eMood').value,aff=document.getElementById('eAff').value;if(!peer)return;const body={peer};if(mood)body.mood=mood;if(aff!=='')body.affinity=parseFloat(aff);const r=await api('/api/emotion/set',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});document.getElementById('eRet').textContent=r.ok?'已更新':'失败';loadEmotions()}
async function loadCaps(){try{const r=await api('/api/cap/whoami');if(r&&r.nickname)document.getElementById('curNick').textContent=r.nickname}catch(e){}}
async function doNick(){const nickname=document.getElementById('capNick').value;if(!nickname)return;const r=await api('/api/cap/nickname',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nickname})});document.getElementById('capRet').textContent=r.ok?'已改':'失败';loadCaps()}
async function doSign(){const text=document.getElementById('capSign').value;if(!text)return;const r=await api('/api/cap/sign',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});document.getElementById('capRet').textContent=r.ok?'已改':'失败'}
async function doAvatar(){const file=document.getElementById('capAvatar').value;if(!file)return;const r=await api('/api/cap/avatar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file})});document.getElementById('avatarRet').textContent=r.ok?'已提交':('失败:'+(r.msg||''))}
async function doQzonePost(){const content=document.getElementById('qzText').value;if(!content)return;const r=await api('/api/qzone/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content})});document.getElementById('qzRet').textContent=r.ok?'已发':('失败:'+(r.msg||''))}
async function loadFeeds(){const r=await api('/api/qzone/feeds');document.getElementById('feedRows').innerHTML=(r.feeds||[]).map(f=>'<tr><td>'+f.nick+'</td><td>'+f.content+'</td><td class="mini">'+f.tid+'</td><td><button class="act lock" onclick="likeTid(\''+f.tid+'\')">赞</button><button class="act del" onclick="delTid(\''+f.tid+'\')">删</button></td></tr>').join('')||'<tr><td colspan=4 class=dim>无动态</td></tr>'}
async function likeTid(tid){const r=await api('/api/qzone/like',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tid})});alert(r.ok?'点赞成功':('失败:'+(r.msg||'')))}
async function delTid(tid){if(!confirm('删除这条说说？'))return;const r=await api('/api/qzone/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tid})});alert(r.ok?'已删':('失败:'+(r.msg||'')))}
async function loadSettings(){const m=await api('/api/model');document.getElementById('mBase').value=m.base;document.getElementById('mModel').value=m.model;document.getElementById('mKey').placeholder=m.key_set?'(已设置,留空不改)':'(未设置)';
 const s=await api('/api/settings');document.getElementById('proactiveBox').innerHTML='当前 <b class="'+(s.proactive?'ok':'bad')+'">'+(s.proactive?'开启':'关闭')+'</b> <button class="act" onclick="toggleProactive('+(s.proactive?'false':'true')+')">'+(s.proactive?'关闭':'开启')+'</button>';document.getElementById('settingsExtra').innerHTML='静默 '+s.quiet_start+'-'+s.quiet_end+' · 表情概率 '+s.emoji_prob+' · 表情包 '+s.sticker_count+' 张';
 const bs=await api('/api/backups');document.getElementById('baks').innerHTML='备份：'+((bs.backups||[]).map(b=>b.name+' ('+b.size_kb+'KB)').join(' · ')||'无');
 const p=await api('/api/persona');document.getElementById('persona').value=p.text}
async function saveModel(){const base=document.getElementById('mBase').value,model=document.getElementById('mModel').value,key=document.getElementById('mKey').value;const r=await api('/api/model',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({base,model,key})});document.getElementById('modelRet').textContent=r.note||'已保存'}
async function testModel(){document.getElementById('modelRet').textContent='测试中…';const r=await api('/api/model/test',{method:'POST'});document.getElementById('modelRet').textContent=r.ok?('连通 '+r.latency_ms+'ms'):('失败: '+(r.error||''))}
async function toggleProactive(v){await api('/api/settings/proactive',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:v})});loadSettings()}
async function doBackup(){const r=await api('/api/backup',{method:'POST'});document.getElementById('bakRet').textContent=r.ok?('已备份 '+r.file):('失败 '+(r.error||''));loadSettings()}
async function savePersona(){const text=document.getElementById('persona').value;const r=await api('/api/persona',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});document.getElementById('pRet').textContent=r.ok?'已保存':('失败')}
async function doSend(){const scene=document.getElementById('sScene').value,peer=document.getElementById('sPeer').value,text=document.getElementById('sText').value,image_url=document.getElementById('sImg').value,voice_text=document.getElementById('sVoice').value,sticker=document.getElementById('sSticker').checked;const r=await api('/api/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scene,peer,text,image_url,voice_text,sticker})});document.getElementById('sRet').textContent=JSON.stringify(r)}
const TITLES={dash:'仪表盘',chat:'对话',facts:'记忆',modules:'模块',acl:'名单',logs:'日志',settings:'设置',send:'发送',emotions:'情绪',caps:'能力'};
const loaders={dash:loadDash,chat:loadPeers,facts:loadFacts,modules:loadModules,acl:loadAcl,logs:loadLogs,settings:loadSettings,emotions:loadEmotions,caps:loadCaps};
document.querySelectorAll('.nav-item').forEach(b=>b.onclick=()=>{document.querySelectorAll('.nav-item').forEach(x=>x.classList.remove('on'));b.classList.add('on');document.querySelectorAll('.page').forEach(t=>t.classList.remove('on'));document.getElementById('tab-'+b.dataset.tab).classList.add('on');document.getElementById('pageTitle').textContent=TITLES[b.dataset.tab]||'';if(loaders[b.dataset.tab])loaders[b.dataset.tab]()});
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

    def status(self) -> dict:
        return {"uptime_sec": int(time.time() - self.started_at),
                "channel": getattr(self.channel, "name", "?"),
                "channel_connected": bool(getattr(self.channel, "connected", False)),
                "model": getattr(getattr(self.brain, "llm", None), "model", "?"),
                "proactive": bool(getattr(self.scheduler, "enabled", False)),
                "stats": self.store.stats()}

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
        s = self.store.get_settings()
        defs = [("memory", "长期记忆（事实+检索）"), ("vision", "看图（视觉理解）"),
                ("emoji", "自动表情"), ("voice", "语音（TTS 发送）"), ("proactive", "主动发言")]
        return [{"key": k, "label": lab, "enabled": bool(s[k]["enabled"])} for k, lab in defs]

    def _persona_path(self) -> str:
        return getattr(self.cfg, "persona_file", "") if self.cfg else ""

    def _backup_dir(self) -> str:
        return os.path.join(getattr(self.cfg, "data_dir", "."), "backup")

    def _build_out(self, d: dict) -> list[Segment]:
        st = self.store.get_settings()
        segs = []
        text = d.get("text") or ""
        if text:
            segs.append(Segment.text(text))
        if d.get("voice_text") and st["voice"].get("enabled", True):
            vp = voice.synth(d["voice_text"], st["voice"].get("voice") or voice.DEFAULT_VOICE)
            if vp:
                try:
                    vb = base64.b64encode(open(vp, "rb").read()).decode()
                    segs.append(Segment("record", {"file": "base64://" + vb}))
                except Exception:
                    pass
        if d.get("sticker") and st["emoji"].get("enabled", True):
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
                elif p == "/api/emotions": self._json(200, {"emotions": emotion.snapshot(admin.store, admin.store.get_settings())})
                elif p == "/api/cap/whoami":
                    r = admin.channel.call_action("get_login_info") if hasattr(admin.channel, "call_action") else None
                    nick = ((r or {}).get("data") or {}).get("nickname", "")
                    self._json(200, {"nickname": nick})
                elif p == "/api/qzone/feeds":
                    self._json(200, {"feeds": actions.simplify_feeds(actions.qzone_feeds(admin.channel))})
                elif p == "/api/model":
                    llm = admin.brain.llm
                    self._json(200, {"base": getattr(llm, "base", ""), "model": getattr(llm, "model", ""), "key_set": bool(getattr(llm, "key", ""))})
                elif p == "/api/settings": self._json(200, admin._settings())
                elif p == "/api/settings_full": self._json(200, admin.store.get_settings())
                elif p == "/api/persona":
                    txt = ""; pp = admin._persona_path()
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
                elif p == "/api/emotion/set":
                    peer = str(d.get("peer", ""))
                    st = admin.store.emotion_get_raw(peer) or emotion.new_state(admin.store.get_settings())
                    st = emotion.relax(st, admin.store.get_settings())
                    if d.get("mood"):
                        st["mood"] = str(d["mood"])
                    if d.get("affinity") not in (None, ""):
                        st["affinity"] = max(0.0, min(100.0, float(d["affinity"])))
                    for k in ("p", "a", "d"):
                        if d.get(k) not in (None, ""):
                            st[k] = max(0.0, min(1.0, float(d[k])))
                    st["updated"] = time.time()
                    admin.store.emotion_save(peer, st)
                    self._json(200, {"ok": True})
                elif p == "/api/cap/avatar":
                    r = actions.set_avatar(admin.channel, str(d.get("file", "")))
                    self._json(200, {"ok": bool(r and r.get("status") == "ok"), "msg": (r or {}).get("message", "")})
                elif p == "/api/cap/nickname":
                    r = actions.set_nickname(admin.channel, str(d.get("nickname", "")))
                    self._json(200, {"ok": bool(r and r.get("status") == "ok"), "msg": (r or {}).get("message", "")})
                elif p == "/api/cap/sign":
                    r = actions.set_sign(admin.channel, str(d.get("text", "")))
                    self._json(200, {"ok": bool(r and r.get("status") == "ok"), "msg": (r or {}).get("message", "")})
                elif p == "/api/qzone/post":
                    r = actions.qzone_publish(admin.channel, str(d.get("content", "")))
                    self._json(200, {"ok": bool(r and r.get("status") == "ok"), "msg": (r or {}).get("message", "")})
                elif p == "/api/qzone/like":
                    r = actions.qzone_like(admin.channel, str(d.get("tid", "")))
                    self._json(200, {"ok": bool(r and r.get("status") == "ok"), "msg": (r or {}).get("message", "")})
                elif p == "/api/qzone/delete":
                    r = actions.qzone_delete(admin.channel, str(d.get("tid", "")))
                    self._json(200, {"ok": bool(r and r.get("status") == "ok"), "msg": (r or {}).get("message", "")})
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
                        admin.store.set_settings({name: {"enabled": en}})
                    self._json(200, {"ok": True})
                elif p == "/api/acl":
                    admin.store.kv_list_set("acl:white", [str(x) for x in (d.get("white") or [])])
                    admin.store.kv_list_set("acl:black", [str(x) for x in (d.get("black") or [])])
                    self._json(200, {"ok": True, "white": len(d.get("white") or []), "black": len(d.get("black") or [])})
                elif p == "/api/settings_full":
                    merged = admin.store.set_settings(d)
                    if admin.scheduler is not None and isinstance(d.get("proactive"), dict) and "enabled" in d["proactive"]:
                        admin.scheduler.enabled = bool(merged["proactive"]["enabled"])
                    self._json(200, {"ok": True, "settings": merged})
                elif p == "/api/model":
                    llm = admin.brain.llm
                    if d.get("base"): llm.base = d["base"]
                    if d.get("model"): llm.model = d["model"]
                    if d.get("key"): llm.key = d["key"]
                    self._json(200, {"ok": True, "note": "已即时生效（重启后请改 .env 持久化）"})
                elif p == "/api/model/test":
                    t0 = time.time()
                    try:
                        _r = admin.store.get_settings()["reply"].get("reasoning")
                        out = admin.brain.llm.chat([{"role": "user", "content": "ping"}], max_tokens=16, reasoning=_r)
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

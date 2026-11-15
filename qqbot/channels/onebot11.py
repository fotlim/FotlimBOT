"""OneBot v11 通道（LLBot / NapCat / SnowCat 通用）。

- 同步实现（websocket-client），配合同步 core，零 asyncio 心智负担。
- 只负责：WS 连协议端、事件→Inbound、Outbound→send_msg。
- 不 import 任何 core 内部实现，只依赖 types + brain.respond 这一张脸。
"""
from __future__ import annotations

import json
import time
import websocket  # pip: websocket-client

from ..brain import Brain
from ..types import Capabilities, Inbound, Outbound, Segment

CAPS = Capabilities(
    send_text=True, send_image=True, send_voice=True, send_file=True,
    mention=True, reply=True, recall=True, emoji_react=True, poke=True,
    forward=True, group_history=True, proactive=True,
)


def _to_inbound(ev: dict) -> Inbound | None:
    if ev.get("post_type") != "message":
        return None
    scene = "group" if ev.get("message_type") == "group" else "private"
    peer = str(ev.get("group_id")) if scene == "group" else str(ev.get("user_id"))
    segs: list[Segment] = []
    for m in ev.get("message", []) or []:
        t = m.get("type")
        d = m.get("data", {}) or {}
        if t == "text":
            segs.append(Segment("text", {"text": d.get("text", "")}))
        elif t == "at":
            segs.append(Segment("at", {"uid": str(d.get("qq", ""))}))
        elif t == "image":
            segs.append(Segment("image", {"url": d.get("url") or d.get("file", "")}))
    sender = ev.get("sender") or {}
    return Inbound(
        channel="onebot11",
        scene=scene,
        peer_id=peer,
        sender_id=str(ev.get("user_id", "")),
        sender_name=sender.get("card") or sender.get("nickname") or "",
        segments=segs,
        message_id=str(ev.get("message_id", "")),
        ts=time.time(),
        raw=ev,
    )


def _send(ws, out: Outbound) -> None:
    msg = [
        {"type": "text", "data": {"text": s.data.get("text", "")}}
        for s in out.segments
        if s.type == "text"
    ]
    if not msg:
        return
    if out.scene == "group":
        params = {"message_type": "group", "group_id": int(out.peer_id), "message": msg}
    else:
        params = {"message_type": "private", "user_id": int(out.peer_id), "message": msg}
    ws.send(json.dumps({"action": "send_msg", "params": params, "echo": "send"}))


def run(brain: Brain, ws_url: str) -> None:
    print(f"[onebot11] connecting {ws_url}", flush=True)
    while True:
        ws = None
        try:
            ws = websocket.create_connection(ws_url, timeout=30, max_size=None)
            print("[onebot11] connected", flush=True)
            while True:
                raw = ws.recv()
                if not raw:
                    continue
                try:
                    ev = json.loads(raw)
                except Exception:
                    continue
                if "post_type" not in ev:  # action 的 echo 回执，忽略
                    continue
                inbound = _to_inbound(ev)
                if inbound is None:
                    continue
                out = brain.respond(inbound, CAPS)
                if out is not None:
                    _send(ws, out)
                    print(f"[onebot11] replied to {inbound.scene}:{inbound.peer_id}", flush=True)
        except Exception as e:  # 断线重连，绝不静默退出
            print(f"[onebot11] disconnected: {e!r}; retry in 3s", flush=True)
            try:
                if ws:
                    ws.close()
            except Exception:
                pass
            time.sleep(3)

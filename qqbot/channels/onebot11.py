"""OneBot v11 通道（类）：断线重连 + 供调度器主动 send。"""
from __future__ import annotations

import json
import threading
import time

import websocket  # websocket-client

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
        elif t == "face":
            segs.append(Segment("face", {"id": d.get("id", "")}))
        elif t == "record":
            segs.append(Segment("voice", {"file": d.get("file", "")}))
    sender = ev.get("sender") or {}
    return Inbound(
        channel="onebot11", scene=scene, peer_id=peer,
        sender_id=str(ev.get("user_id", "")),
        sender_name=sender.get("card") or sender.get("nickname") or "",
        segments=segs, message_id=str(ev.get("message_id", "")), ts=time.time(), raw=ev,
    )


def _build_message(out: Outbound) -> list[dict]:
    msg = []
    for s in out.segments:
        if s.type == "text" and s.data.get("text"):
            msg.append({"type": "text", "data": {"text": s.data["text"]}})
        elif s.type == "image" and s.data.get("file"):
            msg.append({"type": "image", "data": {"file": s.data["file"]}})
        elif s.type == "face" and s.data.get("id"):
            msg.append({"type": "face", "data": {"id": str(s.data["id"])}})
        elif s.type == "record" and s.data.get("file"):
            msg.append({"type": "record", "data": {"file": s.data["file"]}})
    return msg


class OneBot11Channel:
    name = "onebot11"
    caps = CAPS

    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws = None
        self.connected = False
        self._send_lock = threading.Lock()

    def send(self, out: Outbound) -> bool:
        msg = _build_message(out)
        if not msg:
            return False
        if out.scene == "group":
            params = {"message_type": "group", "group_id": int(out.peer_id), "message": msg}
        else:
            params = {"message_type": "private", "user_id": int(out.peer_id), "message": msg}
        with self._send_lock:
            if not self.ws or not self.connected:
                return False
            try:
                self.ws.send(json.dumps({"action": "send_msg", "params": params, "echo": "send"}))
                return True
            except Exception:
                return False

    def run(self, brain: Brain) -> None:
        print(f"[onebot11] connecting {self.ws_url}", flush=True)
        while True:
            try:
                self.ws = websocket.create_connection(self.ws_url, timeout=30, max_size=None)
                self.connected = True
                print("[onebot11] connected", flush=True)
                while True:
                    raw = self.ws.recv()
                    if not raw:
                        continue
                    try:
                        ev = json.loads(raw)
                    except Exception:
                        continue
                    if not isinstance(ev, dict) or "post_type" not in ev:
                        continue
                    inbound = _to_inbound(ev)
                    if inbound is None:
                        continue
                    out = brain.respond(inbound, CAPS)
                    if out is not None and self.send(out):
                        print(f"[onebot11] replied {inbound.scene}:{inbound.peer_id}", flush=True)
            except Exception as e:
                self.connected = False
                print(f"[onebot11] disconnected: {e!r}; retry 3s", flush=True)
                try:
                    if self.ws:
                        self.ws.close()
                except Exception:
                    pass
                time.sleep(3)

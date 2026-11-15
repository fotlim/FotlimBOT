"""OneBot v11 通道（类）：断线重连 + 线程池并发 + 通用 call_action + 供调度器主动 send。"""
from __future__ import annotations

import itertools
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import websocket  # websocket-client

from ..brain import Brain
from ..types import Capabilities, Inbound, Outbound, Segment

CAPS = Capabilities(
    send_text=True, send_image=True, send_voice=True, send_file=True,
    mention=True, reply=True, recall=True, emoji_react=True, poke=True,
    forward=True, group_history=True, proactive=True,
)


def _to_inbound(ev: dict):
    if ev.get("post_type") != "message":
        return None
    scene = "group" if ev.get("message_type") == "group" else "private"
    peer = str(ev.get("group_id")) if scene == "group" else str(ev.get("user_id"))
    segs: list[Segment] = []
    for m in ev.get("message", []) or []:
        t = m.get("type"); d = m.get("data", {}) or {}
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
    return Inbound(channel="onebot11", scene=scene, peer_id=peer, sender_id=str(ev.get("user_id", "")),
                   sender_name=sender.get("card") or sender.get("nickname") or "", segments=segs,
                   message_id=str(ev.get("message_id", "")), ts=time.time(), raw=ev)


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
        self._pool = ThreadPoolExecutor(max_workers=6)
        self._pending = {}
        self._pend_lock = threading.Lock()
        self._seq = itertools.count(1)
        self.store = None

    def _send_one(self, out: Outbound, seg) -> None:
        msg = _build_message(Outbound(out.scene, out.peer_id, [seg]))
        if not msg:
            return
        params = ({"message_type": "group", "group_id": int(out.peer_id)} if out.scene == "group"
                  else {"message_type": "private", "user_id": int(out.peer_id)})
        params["message"] = msg
        with self._send_lock:
            if self.ws and self.connected:
                self.ws.send(json.dumps({"action": "send_msg", "params": params, "echo": "send"}))

    def send(self, out: Outbound) -> bool:
        if not out.segments or not self.ws or not self.connected:
            return False
        import random as _r
        hz = {}
        try:
            if self.store is not None:
                hz = self.store.get_settings().get("humanize", {})
        except Exception:
            hz = {}
        enabled = bool(hz.get("enabled", True))
        items = []
        for s in out.segments:
            if s.type == "text" and s.data.get("text"):
                items.append(s)
            elif s.type == "image" and s.data.get("file"):
                items.append(s)
            elif s.type == "record" and s.data.get("file"):
                items.append(s)
            elif s.type == "face" and s.data.get("id"):
                items.append(s)
        if not items:
            return False
        try:
            if enabled:
                time.sleep(_r.uniform(hz.get("read_min_ms", 600), hz.get("read_max_ms", 1600)) / 1000.0)
            for i, s in enumerate(items):
                if i > 0 and enabled:
                    gap = _r.uniform(hz.get("bubble_gap_min_ms", 500), hz.get("bubble_gap_max_ms", 1400)) / 1000.0
                    per = (len(s.data.get("text", "")) * hz.get("per_char_ms", 35) / 1000.0) if s.type == "text" else 0.0
                    time.sleep(gap + per)
                self._send_one(out, s)
            return True
        except Exception:
            return False

    def call_action(self, action: str, params: dict | None = None, timeout: int = 20):
        if not self.ws or not self.connected:
            return None
        echo = "a" + str(next(self._seq))
        slot = {"ev": threading.Event(), "r": None}
        with self._pend_lock:
            self._pending[echo] = slot
        try:
            with self._send_lock:
                self.ws.send(json.dumps({"action": action, "params": params or {}, "echo": echo}))
            if slot["ev"].wait(timeout):
                return slot["r"]
            return None
        except Exception:
            return None
        finally:
            with self._pend_lock:
                self._pending.pop(echo, None)

    def _resolve(self, ev: dict) -> bool:
        echo = ev.get("echo")
        if echo is None:
            return False
        with self._pend_lock:
            slot = self._pending.get(echo)
        if slot:
            slot["r"] = ev
            slot["ev"].set()
            return True
        return False

    def _handle(self, inbound, brain: Brain) -> None:
        try:
            out = brain.respond(inbound, CAPS)
            if out is not None and self.send(out):
                log_print(f"[onebot11] replied {inbound.scene}:{inbound.peer_id}")
        except Exception as e:
            log_print(f"[onebot11] handle err {e!r}")

    def run(self, brain: Brain) -> None:
        log_print(f"[onebot11] connecting {self.ws_url}")
        while True:
            try:
                self.ws = websocket.create_connection(self.ws_url, timeout=30, max_size=None)
                self.connected = True
                log_print("[onebot11] connected")
                while True:
                    raw = self.ws.recv()
                    if not raw:
                        continue
                    try:
                        ev = json.loads(raw)
                    except Exception:
                        continue
                    if not isinstance(ev, dict):
                        continue
                    if "post_type" not in ev:
                        self._resolve(ev)
                        continue
                    inbound = _to_inbound(ev)
                    if inbound is None:
                        continue
                    self._pool.submit(self._handle, inbound, brain)
            except Exception as e:
                self.connected = False
                log_print(f"[onebot11] disconnected: {e!r}; retry 3s")
                try:
                    if self.ws:
                        self.ws.close()
                except Exception:
                    pass
                time.sleep(3)


def log_print(msg: str) -> None:
    try:
        print(msg, flush=True)
    except Exception:
        pass

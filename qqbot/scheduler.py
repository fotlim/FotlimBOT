"""调度器：主动发言 + 定时（设置驱动，运行时可开关）。"""
from __future__ import annotations

import datetime
import threading
import time

from .brain import Brain
from .store import Store


def _hm(s: str) -> int:
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


class Scheduler:
    def __init__(self, brain: Brain, channel, store: Store, cfg):
        self.brain = brain
        self.channel = channel
        self.store = store
        self.cfg = cfg
        self.enabled = bool(store.get_settings()["proactive"].get("enabled", True))

    def set_enabled(self, v: bool) -> None:
        self.enabled = bool(v)
        self.store.set_settings({"proactive": {"enabled": bool(v)}})

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()
        print(f"[sched] started (enabled={self.enabled})", flush=True)

    def _in_quiet(self, now, qs, qe):
        cur = now.hour * 60 + now.minute
        return (qs <= cur < qe) if qs <= qe else (cur >= qs or cur < qe)

    def _loop(self) -> None:
        time.sleep(30)
        while True:
            try:
                self._tick()
            except Exception as e:
                print("[sched] err", repr(e), flush=True)
            time.sleep(120)

    def _tick(self) -> None:
        if not self.enabled or not getattr(self.channel, "connected", False):
            return
        cfgp = self.store.get_settings()["proactive"]
        now = datetime.datetime.now()
        if self._in_quiet(now, _hm(cfgp.get("quiet_start", "22:30")), _hm(cfgp.get("quiet_end", "08:00"))):
            return
        min_idle = float(cfgp.get("min_idle_h", 2))
        date = now.strftime("%Y-%m-%d")
        for p in self.store.recent_peers(days=3):
            peer = p["peer_id"]
            idle = (time.time() - p["last"]) / 3600.0
            slot = hint = None
            if 8 <= now.hour < 11 and idle >= min_idle:
                slot, hint = "am", "上午好，用一句轻快简短的话跟对方打个招呼，关心下今天。"
            elif 20 <= now.hour < 22 and idle >= min_idle:
                slot, hint = "pm", "晚上了，语气温柔点，问问对方今天过得怎么样，别太长。"
            elif 13 <= now.hour < 18 and idle >= min_idle + 1:
                slot, hint = "mid", "下午了，随口关心一句，自然点，不黏人。"
            if not hint:
                continue
            key = f"proactive:{peer}:{date}:{slot}"
            if self.store.kv_get(key):
                continue
            out = self.brain.generate_proactive(peer, "private", hint)
            if self.channel.send(out):
                self.store.kv_set(key, "1")
                self.store.log_action("proactive", peer, hint)
                print("[sched] proactive ->", peer, flush=True)
                time.sleep(2)

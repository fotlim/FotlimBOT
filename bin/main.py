#!/usr/bin/env python3
"""入口：装配 存储 + 大脑 + 通道 + 调度 + 管理面板。"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qqbot import config as cfgmod
from qqbot import persona as persona_mod
from qqbot import logbus
from qqbot.admin import Admin
from qqbot.brain import Brain
from qqbot.llm import LLMClient
from qqbot.scheduler import Scheduler
from qqbot.store import Store


class _NullChannel:
    name = "mock"
    connected = False

    def send(self, out):
        return False


def main() -> int:
    logbus.install()
    cfg = cfgmod.load()
    print(f"[boot] channel={cfg.channel} model={cfg.llm_model} base={cfg.llm_base} proactive={cfg.proactive} emoji_prob={cfg.emoji_prob}", flush=True)
    store = Store(os.path.join(cfg.data_dir, "qqbot.db"))
    brain = Brain(llm=LLMClient(cfg.llm_base, cfg.llm_key, cfg.llm_model),
                  persona=persona_mod.load(cfg.persona_file), store=store,
                  emoji_prob=cfg.emoji_prob, sticker_dir=cfg.sticker_dir, persona_file=cfg.persona_file)
    brain.meme_dir = cfg.meme_dir
    brain.memory_dir = cfg.memory_dir
    try:
        from qqbot import meme as mememod
        if mememod.count(store) == 0:
            mememod.seed_from_dir(store, cfg.sticker_dir, cfg.meme_dir, pack="default")
        mememod.scan(store, cfg.meme_dir)
        print(f"[meme] library count={mememod.count(store)}", flush=True)
    except Exception as e:
        print("[meme] init skip:", repr(e), flush=True)
    try:
        from qqbot import profile as profilemod
        if not profilemod.list_profiles(cfg.memory_dir):
            for _p in store.peers_with_stats():
                for _m in store.messages_for_peer(_p["peer_id"], 500):
                    if _m.get("role") == "user":
                        profilemod.append_speech(cfg.memory_dir, _p.get("scene") or "private",
                                                 _p["peer_id"], _m.get("name") or _p["peer_id"],
                                                 _m.get("content", ""), _m.get("ts"))
            print(f"[profile] backfilled {len(profilemod.list_profiles(cfg.memory_dir))}", flush=True)
    except Exception as e:
        print("[profile] backfill skip:", repr(e), flush=True)
    try:
        from qqbot import rag as ragmod
        import threading as _th
        _th.Thread(target=lambda: print("[rag] backfilled", ragmod.backfill(store, 1200), flush=True), daemon=True).start()
    except Exception as e:
        print("[rag] skip:", repr(e), flush=True)

    if cfg.channel == "mock":
        from qqbot.channels.mock import run_demo
        sched = Scheduler(brain, _NullChannel(), store, cfg)
        try:
            Admin(cfg.admin_host, cfg.admin_port, cfg.admin_token, store, _NullChannel(), brain,
                  time.time(), sticker_dir=cfg.sticker_dir, scheduler=sched, cfg=cfg).start()
        except Exception as e:
            print("[admin] skip:", repr(e), flush=True)
        run_demo(brain)
        time.sleep(3600)
        return 0

    if cfg.channel == "onebot11":
        from qqbot.channels.onebot11 import OneBot11Channel
        ch = OneBot11Channel(cfg.onebot_ws)
        try:
            from qqbot.astrbot_host import AstrBotHost
            _sample = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "astrbot_plugins")
            _host = AstrBotHost(cfg.plugins_dir, _sample)
            _host.load()
            ch.host = _host
        except Exception as e:
            print("[astr] host skip:", repr(e), flush=True)
        brain.channel = ch
        ch.store = store
        sched = Scheduler(brain, ch, store, cfg)
        Admin(cfg.admin_host, cfg.admin_port, cfg.admin_token, store, ch, brain,
              time.time(), sticker_dir=cfg.sticker_dir, scheduler=sched, cfg=cfg).start()
        sched.start()
        ch.run(brain)
        return 0

    print(f"[boot] 未知 CHANNEL={cfg.channel}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

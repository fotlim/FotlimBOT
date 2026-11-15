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

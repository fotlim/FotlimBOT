#!/usr/bin/env python3
"""入口：按配置装配通道 + 大脑，跑起来。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qqbot import config as cfgmod
from qqbot import persona as persona_mod
from qqbot.brain import Brain
from qqbot.llm import LLMClient


def main() -> int:
    cfg = cfgmod.load()
    print(f"[boot] channel={cfg.channel} model={cfg.llm_model} base={cfg.llm_base}", flush=True)
    brain = Brain(
        llm=LLMClient(cfg.llm_base, cfg.llm_key, cfg.llm_model),
        persona=persona_mod.load(cfg.persona_file),
    )

    if cfg.channel == "mock":
        from qqbot.channels.mock import run_demo
        run_demo(brain)
        return 0

    if cfg.channel == "onebot11":
        from qqbot.channels.onebot11 import run
        run(brain, cfg.onebot_ws)
        return 0

    if cfg.channel == "milky":
        print("[boot] milky 通道尚未接入（可用 onebot11 先跑）", flush=True)
        return 2

    print(f"[boot] 未知 CHANNEL={cfg.channel}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

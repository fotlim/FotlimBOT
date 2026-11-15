from __future__ import annotations


def load(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "你是对方的QQ好友，说话短、口语化、有温度，不要像客服。"

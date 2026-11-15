from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(v, default=False) -> bool:
    if v is None:
        return default
    return str(v).lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    llm_base: str
    llm_key: str
    llm_model: str
    persona_file: str
    channel: str
    onebot_ws: str
    milky_ws: str
    data_dir: str
    admin_host: str
    admin_port: int
    admin_token: str
    proactive: bool
    quiet_start: str
    quiet_end: str
    emoji_prob: float
    sticker_dir: str


def _root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load() -> Config:
    root = _root()
    data_dir = os.getenv("DATA_DIR", os.path.join(root, "data"))
    return Config(
        llm_base=os.getenv("LLM_BASE_URL", "http://10.42.0.44:3426/v1"),
        llm_key=os.getenv("LLM_API_KEY", "magpie"),
        llm_model=os.getenv("LLM_MODEL", "raccoon/sn-deepseek-v4-1-flash-1017-p"),
        persona_file=os.getenv("PERSONA_FILE", os.path.join(root, "persona.txt")),
        channel=os.getenv("CHANNEL", "mock"),
        onebot_ws=os.getenv("ONEBOT_WS", "ws://127.0.0.1:3001"),
        milky_ws=os.getenv("MILKY_WS", "ws://127.0.0.1:3010/"),
        data_dir=data_dir,
        admin_host=os.getenv("ADMIN_HOST", "127.0.0.1"),
        admin_port=int(os.getenv("ADMIN_PORT", "3703")),
        admin_token=os.getenv("ADMIN_TOKEN", ""),
        proactive=_bool(os.getenv("PROACTIVE"), True),
        quiet_start=os.getenv("QUIET_START", "22:30"),
        quiet_end=os.getenv("QUIET_END", "08:00"),
        emoji_prob=float(os.getenv("EMOJI_PROB", "0.18")),
        sticker_dir=os.getenv("STICKER_DIR", os.path.join(data_dir, "stickers")),
    )

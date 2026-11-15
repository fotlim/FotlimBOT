"""TTS：edge-tts 合成 + 音色列表 + 试听。"""
from __future__ import annotations

import base64
import os
import subprocess
import sys
import tempfile
import uuid

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

FALLBACK_VOICES = [
    ("zh-CN-XiaoxiaoNeural", "Female", "zh-CN"),
    ("zh-CN-XiaoyiNeural", "Female", "zh-CN"),
    ("zh-CN-YunjianNeural", "Male", "zh-CN"),
    ("zh-CN-YunxiNeural", "Male", "zh-CN"),
    ("zh-CN-YunxiaNeural", "Male", "zh-CN"),
    ("zh-CN-YunyangNeural", "Male", "zh-CN"),
    ("zh-CN-liaoning-XiaobeiNeural", "Female", "zh-CN"),
    ("zh-CN-shaanxi-XiaoniNeural", "Female", "zh-CN"),
    ("zh-HK-HiuGaaiNeural", "Female", "zh-HK"),
    ("zh-TW-HsiaoChenNeural", "Female", "zh-TW"),
]


def _exe() -> str:
    p = os.path.join(os.path.dirname(sys.executable), "edge-tts")
    return p if os.path.exists(p) else "edge-tts"


def list_voices(zh_only: bool = True) -> list[dict]:
    out = []
    try:
        p = subprocess.run([_exe(), "--list-voices"], capture_output=True, text=True, timeout=25)
        for line in p.stdout.splitlines():
            toks = line.split()
            if not toks or "-Neural" not in toks[0]:
                continue
            name = toks[0]
            gender = "Female" if "Female" in line else ("Male" if "Male" in line else "?")
            locale = "-".join(name.split("-")[:2])
            out.append({"name": name, "gender": gender, "locale": locale})
    except Exception:
        out = []
    if not out:
        out = [{"name": n, "gender": g, "locale": l} for n, g, l in FALLBACK_VOICES]
    if zh_only:
        out = [v for v in out if v["name"].startswith("zh")]
    return out


def synth(text: str, voice: str = DEFAULT_VOICE) -> str | None:
    if not text or not text.strip():
        return None
    out = os.path.join(tempfile.gettempdir(), f"bot_{uuid.uuid4().hex}.mp3")
    try:
        subprocess.run(
            [_exe(), "--text", text, "--voice", voice, "--write-media", out],
            check=True, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return out if os.path.exists(out) and os.path.getsize(out) > 0 else None
    except Exception:
        return None


def preview_b64(text: str, voice: str = DEFAULT_VOICE) -> str | None:
    p = synth(text, voice)
    if not p:
        return None
    try:
        with open(p, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None

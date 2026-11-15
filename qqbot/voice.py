"""TTS：edge-tts 合成语音（返回 mp3 路径）。失败返回 None。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"


def synth(text: str, voice: str = DEFAULT_VOICE) -> str | None:
    if not text or not text.strip():
        return None
    out = os.path.join(tempfile.gettempdir(), f"ayu_{uuid.uuid4().hex}.mp3")
    exe = os.path.join(os.path.dirname(sys.executable), "edge-tts")
    if not os.path.exists(exe):
        exe = "edge-tts"
    try:
        subprocess.run(
            [exe, "--text", text, "--voice", voice, "--write-media", out],
            check=True, timeout=30,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return out if os.path.exists(out) and os.path.getsize(out) > 0 else None
    except Exception:
        return None

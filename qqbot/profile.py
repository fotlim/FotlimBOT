"""人物分析：按 场景/群/对话者昵称 存档对方发言 + 性格分析。
文件：<base>/<scene>__<peer>__<昵称>.txt（发言）、同名 .analysis.txt（分析）。"""
from __future__ import annotations

import os
import re
import time

_SAFE = re.compile(r'[\\/:*?"<>|\s]+')


def _safe(s: str) -> str:
    return (_SAFE.sub("_", str(s or "")).strip("_") or "unknown")[:40]


def _paths(base: str, scene: str, peer: str, nick: str):
    os.makedirs(base, exist_ok=True)
    stem = f"{scene}__{peer}__{_safe(nick)}"
    return (os.path.join(base, stem + ".txt"),
            os.path.join(base, stem + ".analysis.txt"),
            stem)


def append_speech(base: str, scene: str, peer: str, nick: str, text: str, ts: float | None = None) -> None:
    if not text:
        return
    fp, _, _ = _paths(base, scene, peer, nick)
    line = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts or time.time())) + " | " + text.replace("\n", " ")[:500] + "\n"
    try:
        with open(fp, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def read_speech(base: str, scene: str, peer: str, nick: str, max_chars: int = 2500) -> str:
    fp, _, _ = _paths(base, scene, peer, nick)
    try:
        with open(fp, "r", encoding="utf-8") as f:
            return f.read()[-max_chars:]
    except Exception:
        return ""


def read_analysis(base: str, scene: str, peer: str, nick: str) -> str:
    _, ap, _ = _paths(base, scene, peer, nick)
    try:
        with open(ap, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def write_analysis(base: str, scene: str, peer: str, nick: str, text: str) -> None:
    _, ap, _ = _paths(base, scene, peer, nick)
    try:
        with open(ap, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def analyze(base: str, scene: str, peer: str, nick: str, llm) -> str | None:
    speech = read_speech(base, scene, peer, nick, max_chars=4000)
    if not speech.strip():
        return None
    sys_p = ("根据下面这个人过往的发言，分析 ta 的性格、说话风格、情绪倾向、兴趣点，"
             "并给一句“和 ta 聊天该怎么接”的建议。用简洁中文，分点不超过 6 条，不要编造。")
    try:
        out = llm.chat([{"role": "system", "content": sys_p},
                        {"role": "user", "content": speech}], max_tokens=700, reasoning="none")
    except Exception:
        return None
    out = (out or "").strip()
    if out:
        write_analysis(base, scene, peer, nick, out)
    return out


def clear_all(base: str) -> None:
    if not os.path.isdir(base):
        return
    for fn in os.listdir(base):
        if fn.endswith(".txt"):
            try:
                os.remove(os.path.join(base, fn))
            except Exception:
                pass


def clear_peer(base: str, peer: str) -> None:
    if not os.path.isdir(base):
        return
    for fn in os.listdir(base):
        if fn.endswith(".txt") and ("__" + str(peer) + "__") in fn:
            try:
                os.remove(os.path.join(base, fn))
            except Exception:
                pass


def list_profiles(base: str) -> list[dict]:
    out = []
    if not os.path.isdir(base):
        return out
    for fn in os.listdir(base):
        if not fn.endswith(".txt") or fn.endswith(".analysis.txt"):
            continue
        stem = fn[:-4]
        parts = stem.split("__")
        if len(parts) < 3:
            continue
        scene, peer, nick = parts[0], parts[1], "__".join(parts[2:])
        fp = os.path.join(base, fn)
        ap = fp[:-4] + ".analysis.txt"
        try:
            with open(fp, "r", encoding="utf-8") as f:
                lines = sum(1 for _ in f)
        except Exception:
            lines = 0
        ana = ""
        if os.path.exists(ap):
            try:
                with open(ap, "r", encoding="utf-8") as f:
                    ana = f.read()[:300]
            except Exception:
                ana = ""
        out.append({"scene": scene, "peer": peer, "nickname": nick, "lines": lines, "analysis": ana})
    out.sort(key=lambda x: -x["lines"])
    return out

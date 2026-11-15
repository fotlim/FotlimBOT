"""只观察学习：群里未被叫到时静默记录群友用词/梗，供回复时自然借鉴。"""
from __future__ import annotations

import json
import re

SLANG = ["草", "绝了", "栓Q", "蚌埠住了", "绷不住", "破防", "芜湖", "好家伙", "笑死", "哈哈哈哈",
         "笑不活了", "yyds", "xswl", "666", "awsl", "emo", "摆烂", "内卷", "躺平", "泪目",
         "寄了", "开摆", "乐", "整活", "抽象", "真香", "破大防", "拍一拍"]


def _tokens(text: str) -> list[str]:
    t = text or ""
    toks = re.findall(r"[A-Za-z0-9]{2,6}", t)
    cjk = re.findall(r"[\u4e00-\u9fff]", t)
    toks += [cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1)]
    for s in SLANG:
        if s in t:
            toks.append(s)
    return toks


def learn(store, gid: str, text: str) -> None:
    if not store or not text or len(text.strip()) < 2:
        return
    key = "style:" + str(gid)
    try:
        d = json.loads(store.kv_get(key) or "{}")
    except Exception:
        d = {}
    words = d.get("words") or {}
    for tk in _tokens(text):
        if len(tk) >= 2 or tk in SLANG:
            words[tk] = words.get(tk, 0) + 1
    if len(words) > 400:
        words = dict(sorted(words.items(), key=lambda x: -x[1])[:250])
    d["words"] = words
    d["n"] = int(d.get("n", 0)) + 1
    samples = d.get("samples") or []
    samples.append((text or "")[:40])
    d["samples"] = samples[-20:]
    try:
        store.kv_set(key, json.dumps(d, ensure_ascii=False))
    except Exception:
        pass


def context(store, gid: str, limit: int = 10) -> str:
    try:
        d = json.loads(store.kv_get("style:" + str(gid)) or "{}")
    except Exception:
        return ""
    words = d.get("words") or {}
    if not words:
        return ""
    top = [w for w, c in sorted(words.items(), key=lambda x: -x[1])[:limit] if len(w) >= 2]
    if not top:
        return ""
    return ("（本群网友交流风格参考：常出现「" + "」「".join(top) + "」这类说法/梗，语气偏轻松口语。"
            "你可以自然借鉴这种风格，但不要生硬堆砌，仍保持自己的人设与分寸。）")


def stats(store, gid: str) -> dict:
    try:
        d = json.loads(store.kv_get("style:" + str(gid)) or "{}")
    except Exception:
        d = {}
    words = d.get("words") or {}
    top = [{"w": w, "c": c} for w, c in sorted(words.items(), key=lambda x: -x[1])[:20]]
    return {"observed": d.get("n", 0), "top": top, "samples": d.get("samples", [])[-5:]}

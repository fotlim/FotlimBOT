"""轻量向量检索（RAG）：字符 n-gram 哈希 embedding + 余弦。可选外部 embedding API。"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.request

DIM = 256


def _tokens(text: str) -> list[str]:
    t = (text or "").lower()
    toks = re.findall(r"[a-z0-9]+", t)
    cjk = re.findall(r"[\u4e00-\u9fff]", t)
    toks += cjk
    toks += [cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1)]
    return toks


def local_embed(text: str, dim: int = DIM) -> list[float]:
    v = [0.0] * dim
    for tok in _tokens(text):
        h = hashlib.md5(tok.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "little") % dim
        sign = 1.0 if (h[4] & 1) else -1.0
        v[idx] += sign
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _api_embed(text: str):
    base = os.getenv("EMBED_BASE_URL")
    model = os.getenv("EMBED_MODEL")
    if not base or not model:
        return None
    try:
        body = json.dumps({"model": model, "input": text}).encode()
        req = urllib.request.Request(base.rstrip("/") + "/embeddings", data=body,
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer " + os.getenv("EMBED_API_KEY", "")})
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.load(r)
        return (d.get("data") or [{}])[0].get("embedding")
    except Exception:
        return None


def embed(text: str) -> list[float]:
    e = _api_embed(text)
    return e if e else local_embed(text)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def index(store, msg_id: int, peer_id: str, text: str) -> None:
    if not text:
        return
    try:
        vec = embed(text)
        store.vec_upsert(int(msg_id), peer_id, json.dumps(vec), text[:200], __import__("time").time())
    except Exception:
        pass


def search(store, peer_id: str, query: str, k: int = 4) -> list[str]:
    if not query:
        return []
    q = embed(query)
    cands = store.vec_for_peer(peer_id, 500)
    scored = []
    for c in cands:
        try:
            s = _dot(q, json.loads(c["v"]))
        except Exception:
            continue
        scored.append((s, c["content"]))
    scored.sort(key=lambda x: -x[0])
    return [c for s, c in scored if s >= 0.12][:k]


def backfill(store, batch: int = 800) -> int:
    n = 0
    for m in store.messages_missing_vec(batch):
        try:
            index(store, m["id"], m["peer_id"], m["content"])
            n += 1
        except Exception:
            pass
    return n

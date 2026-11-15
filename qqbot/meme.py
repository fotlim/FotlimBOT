"""表情包图库（参考 dsh-meme）：包 / 情绪标签 / 描述 / 关键词；扫描、导入ZIP、按情绪抽图。
图片文件放 data/memes/<pack>/<...>.png，元数据进 SQLite memes 表。"""
from __future__ import annotations

import io
import os
import urllib.request
import zipfile

IMG_EXT = (".png", ".jpg", ".jpeg", ".gif")


def _iter_files(base):
    for root, _, files in os.walk(base):
        for f in files:
            if f.lower().endswith(IMG_EXT):
                yield os.path.join(root, f)


def scan(store, base: str) -> int:
    base = os.path.abspath(base)
    os.makedirs(base, exist_ok=True)
    for p in _iter_files(base):
        rel = os.path.relpath(p, base)
        parts = rel.split(os.sep)
        pack = parts[0] if len(parts) > 1 else "default"
        tag = parts[1] if len(parts) > 2 else "misc"
        caption = os.path.splitext(parts[-1])[0]
        store.meme_upsert(pack, tag, caption, "", p)
    return store.meme_count()


def add_bytes(store, data: bytes, filename: str, base: str, pack: str = "import", tag: str = "misc", caption: str = "") -> str:
    d = os.path.join(base, pack, tag) if tag and tag != "misc" else os.path.join(base, pack)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, filename)
    with open(p, "wb") as f:
        f.write(data)
    store.meme_upsert(pack, tag, caption or os.path.splitext(filename)[0], "", p)
    return p


def seed_from_dir(store, src_dir: str, base: str, pack: str = "default") -> int:
    if not src_dir or not os.path.isdir(src_dir):
        return 0
    n = 0
    for p in _iter_files(src_dir):
        try:
            name = os.path.basename(p)
            with open(p, "rb") as f:
                add_bytes(store, f.read(), name, base, pack=pack, tag=os.path.splitext(name)[0])
            n += 1
        except Exception:
            pass
    return n


def import_zip(store, src: str, base: str, pack: str = "import") -> int:
    data = None
    if os.path.isfile(src):
        with open(src, "rb") as f:
            data = f.read()
    else:
        url = src
        if "github.com" in url and "ghfast.top" not in url and "/releases/download/" in url:
            url = "https://ghfast.top/" + url
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=40) as r:
            data = r.read(80_000_000)
    n = 0
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if name.endswith("/") or not name.lower().endswith(IMG_EXT):
                continue
            try:
                b = zf.read(name)
                if len(b) > 8_000_000:
                    continue
                add_bytes(store, b, os.path.basename(name), base, pack=pack,
                          tag=os.path.splitext(os.path.basename(name))[0])
                n += 1
            except Exception:
                pass
    return n


def pick(store, tag: str | None = None):
    return store.meme_pick(tag)


def count(store) -> int:
    return store.meme_count()

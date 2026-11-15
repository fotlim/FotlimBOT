"""NapCat 能力封装：头像 / 昵称 / 签名 / QQ空间。channel 需提供 call_action()."""
from __future__ import annotations

import json


def _r(channel, action, params=None, timeout=20):
    if channel is None or not getattr(channel, "connected", False):
        return None
    try:
        return channel.call_action(action, params or {}, timeout)
    except Exception:
        return None


def set_avatar(channel, file: str):
    return _r(channel, "set_qq_avatar", {"file": file})


def set_nickname(channel, nickname: str):
    return _r(channel, "set_qq_profile", {"nickname": nickname})


def set_sign(channel, text: str):
    return _r(channel, "set_self_longnick", {"longNick": text})


def qzone_publish(channel, content: str, images=None):
    p = {"content": content}
    if images:
        p["images"] = images
    return _r(channel, "send_qzone_msg", p)


def qzone_feeds(channel):
    return _r(channel, "get_qzone_feeds", {})


def qzone_like(channel, tid):
    return _r(channel, "like_qzone", {"tid": tid})


def qzone_delete(channel, tid):
    return _r(channel, "delete_qzone_msg", {"tid": tid})


def simplify_feeds(resp) -> list[dict]:
    out = []
    data = (resp or {}).get("data") or {}
    for f in (data.get("feeds") or []):
        if not isinstance(f, dict):
            continue
        tid = f.get("tid") or f.get("cellid") or f.get("id") or f.get("feedid") or ""
        nick = f.get("nickname") or f.get("nick") or (f.get("user") or {}).get("nickname") or ""
        content = f.get("content") or f.get("text") or f.get("summary") or ""
        if not content:
            content = json.dumps(f, ensure_ascii=False)
        out.append({"tid": str(tid), "nick": str(nick), "content": str(content)[:200]})
    return out

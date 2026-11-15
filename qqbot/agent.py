"""轻量多步 agent：读群聊/群成员/搜索 → 规划 → 调工具 → 汇报（仅主人，最多 4 步）。"""
from __future__ import annotations

import json

from .types import Outbound, Segment
from . import tools_router as tr

READ_DEFS = [
    {"type": "function", "function": {"name": "read_recent_messages", "description": "读取当前群/私聊最近的消息",
     "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "group_members", "description": "获取本群成员列表（昵称+QQ号）",
     "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}}},
]
ALL_DEFS = tr.TOOL_DEFS + READ_DEFS
MAX_STEPS = 4


def _read_recent(brain, inbound, limit=20):
    try:
        rows = brain.store.messages_for_peer(inbound.peer_id, int(limit))
    except Exception:
        rows = []
    if not rows:
        return "（没有历史消息）"
    out = []
    for m in rows[-int(limit):]:
        role = "我" if m.get("role") == "assistant" else (m.get("sender_name") or "对方")
        out.append("%s：%s" % (role, (m.get("content") or "")[:80]))
    return "最近消息：\n" + "\n".join(out)


def _group_members(brain, inbound, limit=30):
    gid = inbound.peer_id if inbound.scene == "group" else None
    if not gid:
        return "私聊没有群成员"
    try:
        r = brain.channel.call_action("get_group_member_list", {"group_id": int(gid)}, timeout=10)
        data = (r or {}).get("data") or []
        names = ["%s(%s)" % ((m.get("card") or m.get("nickname") or ""), m.get("user_id")) for m in data[:int(limit)]]
        return "群成员(%d)：%s" % (len(data), "、".join(names))
    except Exception:
        return "取群成员失败（可能需要权限）"


def _exec(name, args, brain, inbound):
    if name == "read_recent_messages":
        return _read_recent(brain, inbound, args.get("limit", 20))
    if name == "group_members":
        return _group_members(brain, inbound, args.get("limit", 30))
    okk, payload = tr._ex(name, args, brain, inbound)
    if isinstance(payload, tuple) and payload[0] == "__IMG__":
        return payload
    return payload if okk else ("失败：" + str(payload))


def run(inbound, brain):
    llm = getattr(brain, "llm", None)
    ch = getattr(brain, "channel", None)
    if llm is None or ch is None or not getattr(ch, "connected", False):
        return None
    ats = [str(s.data.get("uid")) for s in inbound.segments if s.type == "at" and str(s.data.get("uid")) != "all"]
    ctx = ("场景：%s；群号：%s；说话人：%s(%s)；被@的人QQ：%s" % (
        "群聊" if inbound.scene == "group" else "私聊",
        inbound.peer_id if inbound.scene == "group" else "-",
        inbound.sender_name, inbound.sender_id, ",".join(ats) or "无"))
    sys_p = ("你是一个轻量 agent，能分步调用工具帮主人完成任务。上下文：" + ctx +
             "。规则：需要信息就先调只读工具（read_recent_messages 读最近消息 / group_members 群成员 / web_search 联网），"
             "看到结果再决定下一步；写操作（改昵称/禁言/发公告/踢人等）仅在主人明确要求时才执行。"
             "最多 4 步，完成后用中文简短汇报结果；如果只是闲聊就不要调用任何工具。")
    messages = [{"role": "system", "content": sys_p}, {"role": "user", "content": inbound.text}]
    pending_img = None
    for _ in range(MAX_STEPS):
        try:
            msg = llm.chat_tools(messages, ALL_DEFS, tool_choice="auto", max_tokens=400, reasoning="none")
        except Exception:
            return None
        calls = msg.get("tool_calls") or []
        if calls:
            messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        else:
            messages.append({"role": "assistant", "content": msg.get("content") or ""})
            content = (msg.get("content") or "").strip()
            if not content:
                return None
            segs = [Segment.text(content)]
            if pending_img:
                segs.append(Segment("image", {"file": pending_img}))
            return Outbound(inbound.scene, inbound.peer_id, segs, reply_to=inbound.message_id or None)
        for c in calls:
            fn = c.get("function") or {}
            name = fn.get("name") or ""
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            res = _exec(name, args, brain, inbound)
            if isinstance(res, tuple) and res[0] == "__IMG__":
                pending_img = res[1]
                res = "（已获取一张图片，将在最终回复中发送）"
            messages.append({"role": "tool", "tool_call_id": c.get("id"), "content": str(res)[:1500]})
    last = ""
    for m in reversed(messages):
        if m.get("role") == "assistant" and m.get("content"):
            last = m["content"]
            break
    return Outbound(inbound.scene, inbound.peer_id, [Segment.text(last or "步骤有点多，我先停一下～")],
                    reply_to=inbound.message_id or None)

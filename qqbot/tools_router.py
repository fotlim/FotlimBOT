"""自然语言指令路由：让模型自己决定调用哪条 QQ 操作（仅主人）。"""
from __future__ import annotations

import json
import re

from .types import Outbound, Segment

TOOL_DEFS = [
    {"type": "function", "function": {"name": "change_nickname", "description": "修改机器人QQ昵称",
     "parameters": {"type": "object", "properties": {"nickname": {"type": "string"}}, "required": ["nickname"]}}},
    {"type": "function", "function": {"name": "change_sign", "description": "修改个签",
     "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}}},
    {"type": "function", "function": {"name": "change_avatar", "description": "换头像（可不给url，按人设联网找）",
     "parameters": {"type": "object", "properties": {"url": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "set_group_card", "description": "改本群群名片",
     "parameters": {"type": "object", "properties": {"card": {"type": "string"}}, "required": ["card"]}}},
    {"type": "function", "function": {"name": "post_qzone", "description": "发QQ空间说说",
     "parameters": {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]}}},
    {"type": "function", "function": {"name": "like_qzone", "description": "给好友说说点赞",
     "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "mute_member", "description": "禁言群成员",
     "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}, "minutes": {"type": "integer"}}, "required": ["user_id"]}}},
    {"type": "function", "function": {"name": "unmute_member", "description": "解除禁言",
     "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}}},
    {"type": "function", "function": {"name": "whole_ban", "description": "全体禁言开/关",
     "parameters": {"type": "object", "properties": {"enable": {"type": "boolean"}}}}},
    {"type": "function", "function": {"name": "kick_member", "description": "踢出群成员",
     "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}}},
    {"type": "function", "function": {"name": "group_notice", "description": "发群公告",
     "parameters": {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]}}},
    {"type": "function", "function": {"name": "set_group_name", "description": "改群名",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "set_special_title", "description": "设置群成员头衔",
     "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}, "title": {"type": "string"}}, "required": ["user_id"]}}},
    {"type": "function", "function": {"name": "poke_member", "description": "戳一戳某人",
     "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}}},
    {"type": "function", "function": {"name": "send_like", "description": "给某人资料卡点赞",
     "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}}},
    {"type": "function", "function": {"name": "send_private", "description": "私聊给指定QQ发消息",
     "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}, "text": {"type": "string"}}, "required": ["user_id", "text"]}}},
    {"type": "function", "function": {"name": "web_search", "description": "联网搜索",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "image_search", "description": "联网找图并发送",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "clear_conversation", "description": "清空与当前对话者的记录",
     "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "status", "description": "查看运行状态",
     "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "view_affinity", "description": "查看好感度",
     "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}}}},
]

_TASK_RE = re.compile(
    r"(禁言|解禁|踢人|踢出|踢了|撤回|公告|群名|头衔|戳一戳|戳一下|点赞|赞我|私聊|发消息|发条消息|"
    r"换头像|换个头像|换张头像|改昵称|改名|换个名|签名|群名片|说说|动态|清空对话|清空记忆|状态|看好感|好感|"
    r"帮我|给我|帮我弄|把.{0,8}(改|换|设|发|删|禁|踢)|去.{0,6}(发|改|点赞)|搜一下|搜一搜|找图|找张图|查一下)")


def looks_like_task(text: str) -> bool:
    return bool(text) and bool(_TASK_RE.search(text))


def _ex(name, a, brain, inbound):
    from . import actions, web, emotion
    ch = brain.channel
    gid = inbound.peer_id if inbound.scene == "group" else None

    def ok(r):
        return bool(r and r.get("status") == "ok")

    if name == "change_nickname":
        nick = str(a.get("nickname", ""))[:20]
        return ok(actions.set_nickname(ch, nick)), "昵称改成「%s」啦（客户端可能缓存）" % nick
    if name == "change_sign":
        return ok(actions.set_sign(ch, str(a.get("text", ""))[:60])), "签名改好了"
    if name == "change_avatar":
        url = a.get("url") or ""
        if not url:
            nm = brain._self_name() if hasattr(brain, "_self_name") else "FotlimBOT"
            kw = ""
            m = re.search(r"外貌[：:]\s*(.+)", brain._current_persona())
            if m:
                kw = " ".join([x for x in re.split(r"[、，,。]", m.group(1)) if x][:2])
            urls = web.image_search((nm + " 二次元 头像 " + kw).strip(), 6)
            url = urls[0] if urls else ""
        if not url:
            return False, "没搜到头像图"
        return ok(actions.set_avatar(ch, url)), "头像换好啦"
    if name == "set_group_card":
        if not gid:
            return False, "群聊里才能改群名片"
        li = actions.get_login_info(ch)
        uid = ((li or {}).get("data") or {}).get("user_id")
        return ok(actions.set_group_card(ch, gid, uid, str(a.get("card", ""))[:20])), "群名片改好啦"
    if name == "post_qzone":
        return ok(actions.qzone_publish(ch, str(a.get("content", ""))[:400])), "说说发出去了"
    if name == "like_qzone":
        import random
        feeds = [f for f in actions.simplify_feeds(actions.qzone_feeds(ch)) if f.get("tid")]
        if not feeds:
            return False, "没有可点赞的动态"
        f = random.choice(feeds)
        return ok(actions.qzone_like(ch, f["tid"])), "给%s点了赞" % f.get("nick")
    if name == "mute_member":
        if not gid:
            return False, "群聊里才能禁言"
        mins = int(a.get("minutes") or 10)
        return ok(actions.set_group_ban(ch, gid, a.get("user_id"), mins * 60)), "禁言 %d 分钟" % mins
    if name == "unmute_member":
        if not gid:
            return False, "群聊"
        return ok(actions.set_group_ban(ch, gid, a.get("user_id"), 0)), "已解禁"
    if name == "whole_ban":
        if not gid:
            return False, "群聊"
        en = bool(a.get("enable", True))
        return ok(actions.set_group_whole_ban(ch, gid, en)), ("已开启全体禁言" if en else "已解除全体禁言")
    if name == "kick_member":
        if not gid:
            return False, "群聊"
        return ok(actions.set_group_kick(ch, gid, a.get("user_id"))), "已踢出"
    if name == "group_notice":
        if not gid:
            return False, "群聊"
        return ok(actions.send_group_notice(ch, gid, str(a.get("content", ""))[:400])), "群公告已发"
    if name == "set_group_name":
        if not gid:
            return False, "群聊"
        return ok(actions.set_group_name(ch, gid, str(a.get("name", ""))[:30])), "群名改好了"
    if name == "set_special_title":
        if not gid:
            return False, "群聊"
        return ok(actions.set_group_special_title(ch, gid, a.get("user_id"), str(a.get("title", "常驻")))), "头衔已设置"
    if name == "poke_member":
        return ok(actions.send_poke(ch, a.get("user_id"), gid)), "戳了一下"
    if name == "send_like":
        return ok(actions.send_like(ch, a.get("user_id") or inbound.sender_id, 10)), "点赞啦"
    if name == "send_private":
        return ok(actions.send_private_msg(ch, a.get("user_id"), str(a.get("text", "")))), "已私聊发送"
    if name == "web_search":
        rs = web.search(str(a.get("query", "")), 5)
        if not rs:
            return False, "没搜到"
        return True, "搜索结果：\n" + "\n".join("%d. %s：%s" % (i + 1, x["title"], x["snippet"][:60]) for i, x in enumerate(rs))
    if name == "image_search":
        urls = web.image_search(str(a.get("query", "")), 6)
        b64 = web.fetch_b64(urls[0]) if urls else None
        if not b64:
            return False, "没找到图"
        return True, ("__IMG__", "base64://" + b64)
    if name == "clear_conversation":
        brain.store.clear_peer(inbound.peer_id)
        return True, "对话已清空"
    if name == "status":
        st = brain.store.stats()
        return True, "在线 · 消息%d · 对话者%d · 事实%d" % (st["messages"], st["peers"], st["facts"])
    if name == "view_affinity":
        snap = emotion.snapshot(brain.store, brain.store.get_settings())
        uid = str(a.get("user_id") or inbound.peer_id)
        row = next((x for x in snap if str(x["peer_id"]) == uid), None)
        if not row:
            return False, "没有好感记录"
        return True, "好感 %s/100，心情 %s" % (row["affinity"], row["mood"])
    return False, "未知操作"


def route(inbound, brain):
    llm = getattr(brain, "llm", None)
    ch = getattr(brain, "channel", None)
    if llm is None or ch is None or not getattr(ch, "connected", False):
        return None
    ats = [str(s.data.get("uid")) for s in inbound.segments if s.type == "at" and str(s.data.get("uid")) != "all"]
    ctx = ("场景：%s；群号：%s；说话人：%s(%s)；被@的人QQ：%s" % (
        "群聊" if inbound.scene == "group" else "私聊",
        inbound.peer_id if inbound.scene == "group" else "-",
        inbound.sender_name, inbound.sender_id, ",".join(ats) or "无"))
    sys_p = ("你是指令路由器。根据主人（只有主人会这样用）的话，判断是否要调用工具去操作QQ。上下文：" + ctx +
             "。只在主人明确要求执行某操作时调用对应工具；只是闲聊/提问就不要调用任何工具。"
             "参数从话里提取：@到的人用其QQ号填 user_id；群操作默认用上面的群号。")
    try:
        msg = llm.chat_tools([{"role": "system", "content": sys_p}, {"role": "user", "content": inbound.text}],
                             TOOL_DEFS, tool_choice="auto", max_tokens=200, reasoning="none")
    except Exception:
        return None
    calls = msg.get("tool_calls") or []
    if not calls:
        return None
    fn = calls[0].get("function") or {}
    name = fn.get("name") or ""
    try:
        args = json.loads(fn.get("arguments") or "{}")
    except Exception:
        args = {}
    okk, payload = _ex(name, args, brain, inbound)
    if isinstance(payload, tuple) and payload[0] == "__IMG__":
        return Outbound(inbound.scene, inbound.peer_id,
                        [Segment.text("喏，给你找的～"), Segment("image", {"file": payload[1]})],
                        reply_to=inbound.message_id or None)
    text = payload if okk else ("失败：" + str(payload))
    return Outbound(inbound.scene, inbound.peer_id, [Segment.text(text)], reply_to=inbound.message_id or None)

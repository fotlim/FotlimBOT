"""主人指令路由：在 QQ 里用自然语言下指令，bot 自己执行（仅 owner）。"""
from __future__ import annotations

import base64
import random
import re

from .types import Outbound, Segment

HELP = ("我可以听你的指令（仅主人）：\n"
        "· 换头像 / 换头像 <图片URL>\n· 改昵称 <名字>\n· 改签名 <内容>\n· 群名片改名 <内容>（群）\n"
        "· 发说说：<内容>\n· 去QQ空间点赞\n· 发个表情 [关键词]\n· 搜一下 <关键词>\n· 找图 <关键词>\n· 换音色 <关键词>\n"
        "· 禁言 @人 [分钟] / 解禁 @人 / 全体禁言 / 解除全体禁言\n· 踢 @人\n· 戳一戳 @人\n· 撤回（回复那条消息）\n"
        "· 群公告 <内容> / 群名改成 <名字> / 头衔 @人 <内容>\n· 点赞 @人 / 赞我\n· 私聊 <QQ号> <内容>\n"
        "· 状态 / 看好感 / 清空对话")


def _ok(r) -> bool:
    return bool(r and r.get("status") == "ok")


def _at_uid(inbound):
    for s in inbound.segments:
        if s.type == "at":
            u = str(s.data.get("uid", ""))
            if u and u != "all":
                return u
    return None


def is_owner(store, inbound) -> bool:
    try:
        ids = store.get_settings().get("owner", {}).get("ids", [])
    except Exception:
        ids = []
    return str(inbound.sender_id) in [str(x) for x in ids]


def _rep(inbound, texts, segs=None):
    s = [Segment.text(t) for t in texts if t]
    if segs:
        s += segs
    return Outbound(inbound.scene, inbound.peer_id, s, reply_to=inbound.message_id or None)


def handle(inbound, brain):
    from . import actions, web as webmod
    ch = getattr(brain, "channel", None)
    store = brain.store
    if not is_owner(store, inbound):
        return None
    t = (inbound.text or "").strip()

    if re.match(r"^(帮助|help|指令|命令|你能做什么|你会什么)[。！!？?]*$", t):
        return _rep(inbound, [HELP])

    if re.search(r"^(状态|运行状态|报一下状态)", t):
        st = store.stats()
        conn = bool(getattr(ch, "connected", False))
        model = getattr(getattr(brain, "llm", None), "model", "?")
        return _rep(inbound, [f"状态：{'在线' if conn else '离线'} · 模型 {model}\n消息 {st['messages']}（今日 {st['today']}）· 对话者 {st['peers']} · 事实 {st['facts']}"])

    m = re.match(r"^(?:把)?头像(?:换成|改为|改成|换|改)?\s*(.*)$", t)
    if m and "头像" in t:
        arg = m.group(1).strip()
        url = arg if arg.startswith("http") else None
        if not url:
            name = brain._self_name() if hasattr(brain, "_self_name") else "FotlimBOT"
            kw = ""
            pm = re.search(r"外貌[：:]\s*(.+)", brain._current_persona())
            if pm:
                kw = " ".join([x for x in re.split(r"[、，,。]", pm.group(1)) if x][:2])
            urls = webmod.image_search((name + " 二次元 头像 " + kw).strip(), 8)
            url = urls[0] if urls else None
        if not url:
            return _rep(inbound, ["没搜到合适的头像图，给我个图片 URL 吧～"])
        r = actions.set_avatar(ch, url)
        return _rep(inbound, ["头像换好啦～" if (r and r.get("status") == "ok") else ("换头像失败：" + str((r or {}).get("message", ""))[:60])])

    m = re.match(r"^(?:改昵称|昵称改成|昵称改为|改名)\s*[:：]?\s*(.+)$", t)
    if m:
        nick = m.group(1).strip()[:20]
        r = actions.set_nickname(ch, nick)
        return _rep(inbound, [("昵称改成「%s」啦（QQ 可能缓存一会儿才显示）" % nick) if (r and r.get("status") == "ok") else "改昵称失败"])

    m = re.match(r"^(?:改签名|签名改成|签名改为)\s*[:：]?\s*(.+)$", t)
    if m:
        r = actions.set_sign(ch, m.group(1).strip()[:60])
        return _rep(inbound, ["签名改好啦" if (r and r.get("status") == "ok") else "改签名失败"])

    if inbound.scene == "group":
        m = re.match(r"^(?:群名片改名|改群名片|群昵称改成)\s*[:：]?\s*(.+)$", t)
        if m:
            li = actions.get_login_info(ch)
            uid = ((li or {}).get("data") or {}).get("user_id")
            r = actions.set_group_card(ch, inbound.peer_id, uid, m.group(1).strip()[:20])
            return _rep(inbound, ["本群名片改好啦" if (r and r.get("status") == "ok") else "改群名片失败"])

    m = re.match(r"^(?:发说说|发条说说|发个说说|发动态)\s*[:：]?\s*(.+)$", t)
    if m:
        r = actions.qzone_publish(ch, m.group(1).strip()[:400])
        return _rep(inbound, ["说说发出去啦～" if (r and r.get("status") == "ok") else "发说说失败"])

    if re.search(r"(去)?QQ?空间点赞|点赞一下|帮我点赞", t):
        feeds = [f for f in actions.simplify_feeds(actions.qzone_feeds(ch)) if f.get("tid")]
        if not feeds:
            return _rep(inbound, ["现在没有好友动态可点赞～"])
        f = random.choice(feeds)
        r = actions.qzone_like(ch, f["tid"])
        return _rep(inbound, [("给「%s」的说说点赞啦" % f.get("nick")) if (r and r.get("status") == "ok") else "点赞失败"])

    m = re.match(r"^(?:发个表情|来张表情|发表情|发个图|来张图)\s*(.*)$", t)
    if m:
        kw = m.group(1).strip()
        path = None
        try:
            if kw:
                rows = store.meme_list(q=kw)
                if rows:
                    path = rows[0]["path"]
            if not path:
                path = store.meme_pick(None)
        except Exception:
            path = None
        if not path:
            return _rep(inbound, ["图库空空的，先给我导入点表情吧～"])
        b64 = base64.b64encode(open(path, "rb").read()).decode()
        return _rep(inbound, [], [Segment("image", {"file": "base64://" + b64})])

    m = re.match(r"^(?:搜一下|查一下|搜|查)\s*[:：]?\s*(.+)$", t)
    if m:
        rs = webmod.search(m.group(1).strip(), 5)
        if not rs:
            return _rep(inbound, ["没搜到结果呢"])
        lines = ["搜到这些："] + [f"{i+1}. {x['title']}：{x['snippet'][:60]}" for i, x in enumerate(rs)]
        return _rep(inbound, ["\n".join(lines)[:900]])

    m = re.match(r"^(?:找图|找张图|搜图|来张)\s*[:：]?\s*(.+)$", t)
    if m:
        urls = webmod.image_search(m.group(1).strip(), 6)
        b64 = webmod.fetch_b64(urls[0]) if urls else None
        if not b64:
            return _rep(inbound, ["没找到合适的图～"])
        return _rep(inbound, ["喏，给你找的～"], [Segment("image", {"file": "base64://" + b64})])

    m = re.match(r"^(?:换音色|音色改成|音色改为|用音色)\s*[:：]?\s*(.+)$", t)
    if m:
        kw = m.group(1).strip()
        from . import voice
        vs = voice.list_voices(zh_only=True)
        hit = next((v["name"] for v in vs if kw in v["name"] or kw in v["name"].split("-")[-1]), None)
        if not hit:
            return _rep(inbound, ["没找到这个音色，可用：" + "、".join(v["name"] for v in vs[:8])])
        store.set_settings({"voice": {"voice": hit}})
        return _rep(inbound, ["音色换成 " + hit + " 啦"])

    if re.match(r"^(看|查)?(好感|好感度)", t):
        from . import emotion
        snap = emotion.snapshot(store, store.get_settings())
        row = next((x for x in snap if str(x["peer_id"]) == str(inbound.peer_id)), None)
        if not row:
            return _rep(inbound, ["还没什么好感记录，多聊几句吧～"])
        return _rep(inbound, [f"我对你的好感度 {row['affinity']}/100，心情 {row['mood']}，精力 {row['energy']}"])

    # ---- QQ 控制类（仅主人；需有权限才会成功）----
    if inbound.scene == "group":
        if re.match(r"^全体禁言$", t):
            r = actions.set_group_whole_ban(ch, inbound.peer_id, True)
            return _rep(inbound, ["已开启全体禁言" if _ok(r) else "操作失败（可能需要管理员）"])
        if re.match(r"^(解除|关闭)全体禁言$", t):
            r = actions.set_group_whole_ban(ch, inbound.peer_id, False)
            return _rep(inbound, ["已解除全体禁言" if _ok(r) else "操作失败"])
        if t.startswith("禁言"):
            uid = _at_uid(inbound)
            if not uid:
                return _rep(inbound, ["要 @ 一个人才能禁言哦"])
            mm = re.search(r"(\d+)\s*(分钟|秒|min|s)?", re.sub(r"@\S+|\d{5,}", "", t))
            val = int(mm.group(1)) if mm else 10
            unit = (mm.group(2) if mm else "分钟") or "分钟"
            sec = val if unit in ("秒", "s") else val * 60
            r = actions.set_group_ban(ch, inbound.peer_id, uid, sec)
            return _rep(inbound, ["已禁言 %d 秒" % sec if _ok(r) else "禁言失败（需要管理员）"])
        if t.startswith("解禁"):
            uid = _at_uid(inbound)
            if not uid:
                return _rep(inbound, ["要 @ 一个人"])
            r = actions.set_group_ban(ch, inbound.peer_id, uid, 0)
            return _rep(inbound, ["已解禁" if _ok(r) else "解禁失败"])
        if t.startswith("踢"):
            uid = _at_uid(inbound)
            if not uid:
                return _rep(inbound, ["要 @ 一个人才能踢"])
            r = actions.set_group_kick(ch, inbound.peer_id, uid)
            return _rep(inbound, ["已踢出" if _ok(r) else "踢出失败（需要管理员）"])
        if t.startswith("头衔"):
            uid = _at_uid(inbound)
            if not uid:
                return _rep(inbound, ["要 @ 一个人"])
            title = re.sub(r"@\S+", "", t).replace("头衔", "").strip() or "常驻"
            r = actions.set_group_special_title(ch, inbound.peer_id, uid, title)
            return _rep(inbound, ["头衔请求已发送" if _ok(r) else "设置失败（需要群主）"])
        m = re.match(r"^(?:群公告|发公告)\s*[:：]?\s*(.+)$", t)
        if m:
            r = actions.send_group_notice(ch, inbound.peer_id, m.group(1).strip())
            return _rep(inbound, ["群公告已发" if _ok(r) else "发公告失败（需要管理员）"])
        m = re.match(r"^群名改成\s*[:：]?\s*(.+)$", t)
        if m:
            r = actions.set_group_name(ch, inbound.peer_id, m.group(1).strip()[:30])
            return _rep(inbound, ["群名改好啦" if _ok(r) else "改群名失败（需要群主）"])
        if re.match(r"^(撤回|撤一下)", t):
            mid = None
            raw = getattr(inbound, "raw", None) or {}
            for mm2 in raw.get("message", []) or []:
                if mm2.get("type") == "reply":
                    mid = (mm2.get("data") or {}).get("id")
            if not mid:
                return _rep(inbound, ["回复要撤回的那条消息再说「撤回」"])
            r = actions.delete_msg(ch, mid)
            return _rep(inbound, ["撤回啦" if _ok(r) else "撤回失败（需要管理员/已超时）"])

    if t.startswith("戳一戳") or t == "戳":
        uid = _at_uid(inbound) or (inbound.peer_id if inbound.scene == "private" else None)
        if not uid:
            return _rep(inbound, ["要 @ 一个人"])
        r = actions.send_poke(ch, uid, inbound.peer_id if inbound.scene == "group" else None)
        return _rep(inbound, ["戳啦～"])

    if t.startswith("点赞") or t == "赞我":
        uid = _at_uid(inbound) or str(inbound.sender_id)
        r = actions.send_like(ch, uid, 10)
        return _rep(inbound, ["点赞啦" if _ok(r) else "点赞失败"])

    m = re.match(r"^(?:私聊|发消息)\s*(\d{5,12})\s+([\s\S]+)$", t)
    if m:
        r = actions.send_private_msg(ch, m.group(1), m.group(2).strip())
        return _rep(inbound, ["已私聊发送" if _ok(r) else "发送失败"])

    if re.match(r"^(清空对话|清空记忆|忘掉之前)", t):
        store.clear_peer(inbound.peer_id)
        try:
            from . import profile as profilemod
            profilemod.clear_peer(getattr(brain, "memory_dir", ""), inbound.peer_id)
        except Exception:
            pass
        return _rep(inbound, ["好，我把我们之前的对话清掉啦～"])

    return None

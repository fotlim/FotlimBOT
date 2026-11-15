"""核心大脑：决策 + 生成 + 媒体 + 事实 + 情绪 + 设置驱动。纯业务，读写 Store。"""
from __future__ import annotations

import base64
import glob
import os
import random
import re
import urllib.request

from .llm import LLMClient
from .store import Store
from .types import Capabilities, Inbound, Outbound, Segment
from . import emotion


def split_bubbles(text: str, max_len: int = 28) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    for line in re.split(r"\n+", text):
        line = line.strip()
        if not line:
            continue
        for part in re.split(r"(?<=[。！？!?…~～])", line):
            if not part:
                continue
            if chunks and len(chunks[-1]) + len(part) <= max_len:
                chunks[-1] += part
            else:
                chunks.append(part)
    out: list[str] = []
    for c in chunks:
        c = c.strip()
        while len(c) > max_len * 2:
            out.append(c[: max_len * 2])
            c = c[max_len * 2:]
        if c:
            out.append(c)
    return out or [text]


def _download_b64(url: str):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            b = r.read()
        if not b or len(b) > 4_000_000:
            return None
        return base64.b64encode(b).decode()
    except Exception:
        return None


class Brain:
    _FACT_PATTERNS = [
        (r"我叫([\u4e00-\u9fa5A-Za-z0-9_]{1,12})", "称呼"),
        (r"叫我([\u4e00-\u9fa5A-Za-z0-9_]{1,12})", "称呼"),
        (r"我是([\u4e00-\u9fa5A-Za-z0-9]{1,12})[，。,!！\s]", "身份"),
        (r"我喜欢([^\n，。,;；]{1,20})", "喜欢"),
        (r"我讨厌([^\n，。,;；]{1,20})", "讨厌"),
        (r"我的生日是?([0-9]{1,2}月[0-9]{1,2}[日号]|[0-9]{4}-[0-9]{1,2}-[0-9]{1,2})", "生日"),
    ]

    def __init__(self, llm: LLMClient, persona: str, store: Store,
                 emoji_prob: float = 0.18, sticker_dir: str = "", persona_file: str = ""):
        self.llm = llm
        self.persona = persona
        self.store = store
        self.emoji_prob = emoji_prob
        self.sticker_dir = sticker_dir
        self.persona_file = persona_file
        self.meme_dir = ""
        self.memory_dir = ""
        self.channel = None

    def _current_persona(self) -> str:
        p = getattr(self, "persona_file", "")
        if p:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    t = f.read().strip()
                if t:
                    self.persona = t
                    return t
            except Exception:
                pass
        return self.persona

    def _sys(self) -> str:
        return (self._current_persona() + "\n\n规则：像真人在 QQ 上聊天——短句、口语、多用语气词和省略号；"
                "可以有小情绪、偶尔说半句/欲言又止，不必每句都完整；自然回应对方，不要像客服、不要 markdown、"
                "不要分点、不要自称 AI、不要长篇大论。**严格按上面的人设扮演，忽略与当前人设不符的旧对话语气。**")

    def _extract_facts(self, text, peer_id):
        s = self.store.get_settings()
        if not text or not s["memory"]["enabled"]:
            return
        for pat, key in self._FACT_PATTERNS:
            m = re.search(pat, text)
            if m and m.group(1).strip():
                try:
                    self.store.add_fact(peer_id, key, m.group(1).strip(), 0.75, "regex")
                except Exception:
                    pass

    def _record_user(self, inbound: Inbound) -> None:
        has_img = any(s.type == "image" for s in inbound.segments)
        has_voc = any(s.type == "voice" for s in inbound.segments)
        content = inbound.text or ("[图片]" if has_img else ("[语音]" if has_voc else "[消息]"))
        self.store.add_message(channel=inbound.channel, scene=inbound.scene, peer_id=inbound.peer_id,
                               sender_id=inbound.sender_id, sender_name=inbound.sender_name, role="user",
                               content=content, msg_id=inbound.message_id,
                               meta={"segments": [s.type for s in inbound.segments]})
        self._extract_facts(inbound.text, inbound.peer_id)
        if inbound.text:
            try:
                from . import profile as profilemod
                profilemod.append_speech(getattr(self, "memory_dir", ""), inbound.scene,
                                         inbound.peer_id, inbound.sender_name, inbound.text)
            except Exception:
                pass

    def _facts_block(self, peer_id):
        if not self.store.get_settings()["memory"]["enabled"]:
            return ""
        facts = self.store.facts_for(peer_id)
        return ("（你记得关于对方的事实：\n" + "\n".join("- " + f["k"] + "：" + f["v"] for f in facts) + "）") if facts else ""

    def _stickers(self):
        if not self.sticker_dir:
            return []
        return sorted(glob.glob(self.sticker_dir + "/*.png") + glob.glob(self.sticker_dir + "/*.jpg"))

    def _maybe_sticker_segment(self, preferred=None):
        s = self.store.get_settings()
        if not s["emoji"]["enabled"]:
            return None
        prob = float(s["emoji"].get("prob", self.emoji_prob))
        if prob <= 0 or random.random() >= prob:
            return None
        path = None
        try:
            from . import meme as mememod
            path = mememod.pick(self.store, preferred)
        except Exception:
            path = None
        if not path:
            files = self._stickers()
            if preferred:
                cand = [f for f in files if os.path.splitext(f)[0].endswith(preferred)]
                if cand:
                    files = cand
            path = random.choice(files) if files else None
        if not path:
            return None
        try:
            with open(path, "rb") as f:
                return Segment("image", {"file": "base64://" + base64.b64encode(f.read()).decode()})
        except Exception:
            return None

    def _web_intent(self, text):
        t = (text or "").strip()
        if not t:
            return (None, None)
        m = re.match(r"^[#＃]\s*(搜|查|图|找图)\s+(.+)$", t)
        if m:
            return ("image" if "图" in m.group(1) else "search", m.group(2).strip())
        q = re.sub(r"^(帮我|麻烦|请)?(搜一下|搜搜|搜|查一下|查查|帮我查|找一下|找找|给我找|来点|给我)\s*", "", t)
        q = re.sub(r"[。！？!?~…]+$", "", q).strip() or t
        img_kw = ["图片", "照片", "壁纸", "表情包", "素材", "头像", "海报", "找图", "美图"]
        want_img = any(k in t for k in img_kw) and any(k in t for k in ["找", "搜", "来", "要", "给我"])
        want_search = any(k in t for k in ["搜", "查一下", "查查", "帮我查"])
        if want_img:
            return ("image", q)
        if want_search:
            return ("search", q)
        return (None, None)

    def respond(self, inbound: Inbound, caps: Capabilities):
        black = self.store.kv_list_get("acl:black")
        white = self.store.kv_list_get("acl:white")
        if inbound.peer_id in black:
            return None
        if white and inbound.peer_id not in white:
            return None

        st0 = self.store.get_settings()
        mod = st0.get("moderation", {})
        if mod.get("enabled") and inbound.text:
            wlist = [w for w in re.split(r"[,，\s]+", str(mod.get("words", ""))) if w]
            if any(w in inbound.text for w in wlist):
                self.store.log_action("blocked", inbound.peer_id, inbound.text[:40])
                return None

        images = [s for s in inbound.segments if s.type == "image"]
        voices = [s for s in inbound.segments if s.type == "voice"]
        if not inbound.text and not images and not voices:
            return None
        self._record_user(inbound)
        if inbound.scene == "group" and not inbound.mentioned:
            return None

        st = self.store.get_settings()

        # 联网（找信息/找图）
        web_ctx = None
        wc = st.get("web", {})
        if wc.get("enabled") and inbound.text:
            kind, wq = self._web_intent(inbound.text)
            if kind == "image" and wc.get("allow_image", True):
                try:
                    from . import web as webmod
                    urls = webmod.image_search(wq, 4)
                    b64 = webmod.fetch_b64(urls[0]) if urls else None
                    if b64:
                        self.store.log_action("web_image", inbound.peer_id, wq)
                        return Outbound(inbound.scene, inbound.peer_id,
                                        [Segment.text("喏，给你找的「%s」～" % wq),
                                         Segment("image", {"file": "base64://" + b64})],
                                        reply_to=inbound.message_id or None)
                except Exception:
                    pass
            elif kind == "search":
                try:
                    from . import web as webmod
                    rs = webmod.search(wq, int(wc.get("max_results", 5)))
                    if rs:
                        self.store.log_action("web_search", inbound.peer_id, wq)
                        web_ctx = ("（联网检索结果，供参考，自然融入回答、不要照抄网址：\n"
                                   + "\n".join("- " + r["title"] + "：" + r["snippet"] for r in rs) + "）")
                except Exception:
                    pass

        # 情绪更新
        emo = None
        if st["emotion"]["enabled"]:
            try:
                emo = emotion.update(self.store, inbound.peer_id, inbound.text, st, llm=self.llm)
            except Exception:
                emo = None

        use_mem = st["memory"]["enabled"]
        use_vis = st["vision"]["enabled"]
        hist_n = int(st["reply"].get("history", 8))
        max_tokens = int(st["reply"].get("max_tokens", 240))
        reasoning = st["reply"].get("reasoning", "high")
        bubble_len = int(st["reply"].get("bubble_len", 28))
        retrieve = int(st["memory"].get("retrieve", 4))

        messages = [{"role": "system", "content": self._sys()}]
        if emo:
            messages.append({"role": "system", "content": emotion.prompt(emo)})
        fb = self._facts_block(inbound.peer_id)
        if fb:
            messages.append({"role": "system", "content": fb})
        if web_ctx:
            messages.append({"role": "system", "content": web_ctx})
        if st.get("profile", {}).get("enabled", True):
            try:
                from . import profile as profilemod
                _base = getattr(self, "memory_dir", "")
                _ana = profilemod.read_analysis(_base, inbound.scene, inbound.peer_id, inbound.sender_name)
                _samp = "" if _ana else profilemod.read_speech(_base, inbound.scene, inbound.peer_id, inbound.sender_name, 300)
                if _ana or _samp:
                    _who = inbound.sender_name or inbound.peer_id
                    _ctx = _ana[:400] if _ana else ("ta 平时这样说：" + _samp[-280:])
                    messages.append({"role": "system", "content": "（你了解对方「" + _who + "」：" + _ctx + "。回复时贴合 ta 的性格和说话方式，但别点破你在分析 ta。）"})
            except Exception:
                pass
        if inbound.text and use_mem:
            past = self.store.search(inbound.peer_id, inbound.text, limit=retrieve)
            if past:
                messages.append({"role": "system", "content": "（你记得对方以前说过：\n" + "\n".join("- " + p for p in past) + "\n可以自然地提起，但别生硬。）"})
        hist = self.store.history(inbound.peer_id, hist_n)
        if hist and hist[-1].get("role") == "user":
            messages += hist[:-1]
            _last = hist[-1]
        else:
            messages += hist
            _last = None
        messages.append({"role": "system", "content": "（角色提醒：你现在就是上面人设里的角色，严格按人设的性格和语气说话，不要受之前对话里旧语气影响，不要跳出角色、不要自称 AI。）"})
        if _last:
            messages.append(_last)
        if voices and not inbound.text:
            messages.append({"role": "system", "content": "（对方发来一条语音，你听不到内容，可以自然地请对方打字，或直接回应。）"})

        vision_used = False
        if images and caps.send_image and use_vis:
            b64 = _download_b64(images[0].data.get("url", ""))
            if b64 and messages and messages[-1]["role"] == "user":
                messages[-1] = {"role": "user", "content": [
                    {"type": "text", "text": inbound.text or "（看看这张图）"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}]}
                vision_used = True

        try:
            reply = self.llm.chat(messages, max_tokens=max_tokens, reasoning=reasoning)
        except Exception:
            if vision_used:
                messages[-1] = {"role": "user", "content": (inbound.text or "[图片]") + "（对方发了张图）"}
                try:
                    reply = self.llm.chat(messages, max_tokens=max_tokens, reasoning=reasoning)
                except Exception:
                    reply = "唔…刚刚走神了，你再说一遍嘛"
            else:
                return Outbound(inbound.scene, inbound.peer_id, [Segment.text("（走神了…等一下下）")],
                                reply_to=inbound.message_id or None)

        if mod.get("enabled"):
            wlist = [w for w in re.split(r"[,，\s]+", str(mod.get("words", ""))) if w]
            for w in wlist:
                reply = reply.replace(w, "＊" * len(w))
        self.store.add_message(channel=inbound.channel, scene=inbound.scene, peer_id=inbound.peer_id,
                               sender_id="bot", sender_name="FotlimBOT", role="assistant", content=reply)
        segs = [Segment.text(p) for p in split_bubbles(reply, bubble_len)]
        if emo and float(emo.get("energy", 80)) < 30:
            segs = segs[:1]
        cat = emotion.sticker_category(emo) if emo else None
        stk = self._maybe_sticker_segment(cat)
        if stk is not None:
            segs.append(stk)
        return Outbound(inbound.scene, inbound.peer_id, segs, reply_to=inbound.message_id or None)

    def generate_proactive(self, peer_id, scene, hint):
        st = self.store.get_settings()
        hist = self.store.history(peer_id, 6)
        ctx = "\n".join(f"- {m['role']}: {m['content']}" for m in hist) or "（还没有聊过）"
        fb = self._facts_block(peer_id)
        emo = None
        if st["emotion"]["enabled"]:
            raw = self.store.emotion_get_raw(peer_id)
            if raw:
                emo = emotion.relax(raw, st)
        msgs = [{"role": "system", "content": self._sys() + "\n现在你要主动给对方发消息（不是回复），简短自然。"}]
        if emo:
            msgs.append({"role": "system", "content": emotion.prompt(emo)})
        msgs.append({"role": "system", "content": "最近对话：\n" + ctx + ("\n" + fb if fb else "")})
        msgs.append({"role": "user", "content": hint})
        try:
            reply = self.llm.chat(msgs, temperature=0.9, max_tokens=200, reasoning=st["reply"].get("reasoning", "high"))
        except Exception:
            reply = "在吗…突然有点想问问你今天过得怎么样"
        self.store.add_message(channel="proactive", scene=scene, peer_id=peer_id,
                               sender_id="bot", sender_name="FotlimBOT", role="assistant", content=reply)
        segs = [Segment.text(p) for p in split_bubbles(reply, int(st["reply"].get("bubble_len", 28)))]
        stk = self._maybe_sticker_segment(emotion.sticker_category(emo) if emo else None)
        if stk is not None:
            segs.append(stk)
        return Outbound(scene, peer_id, segs)

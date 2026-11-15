"""核心大脑：决策 + 生成 + 媒体 + 事实 + 情绪 + 设置驱动。纯业务，读写 Store。"""
from __future__ import annotations

import base64
import glob
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
        return (self._current_persona() + "\n\n规则：像真人聊 QQ，短句口语，多用语气词；"
                "不要 markdown、不要分点、不要自称 AI、不要长篇大论。")

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
        files = self._stickers()
        if not files:
            return None
        if preferred:
            cand = [f for f in files if f[:-4].endswith(preferred)]
            if cand:
                files = cand
        try:
            with open(random.choice(files), "rb") as f:
                return Segment("image", {"file": "base64://" + base64.b64encode(f.read()).decode()})
        except Exception:
            return None

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
        if inbound.text and use_mem:
            past = self.store.search(inbound.peer_id, inbound.text, limit=retrieve)
            if past:
                messages.append({"role": "system", "content": "（你记得对方以前说过：\n" + "\n".join("- " + p for p in past) + "\n可以自然地提起，但别生硬。）"})
        messages += self.store.history(inbound.peer_id, hist_n)
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
                return Outbound(inbound.scene, inbound.peer_id, [Segment.text("（阿渔走神了…等一下下）")],
                                reply_to=inbound.message_id or None)

        if mod.get("enabled"):
            wlist = [w for w in re.split(r"[,，\s]+", str(mod.get("words", ""))) if w]
            for w in wlist:
                reply = reply.replace(w, "＊" * len(w))
        self.store.add_message(channel=inbound.channel, scene=inbound.scene, peer_id=inbound.peer_id,
                               sender_id="bot", sender_name="阿渔", role="assistant", content=reply)
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
                               sender_id="bot", sender_name="阿渔", role="assistant", content=reply)
        segs = [Segment.text(p) for p in split_bubbles(reply, int(st["reply"].get("bubble_len", 28)))]
        stk = self._maybe_sticker_segment(emotion.sticker_category(emo) if emo else None)
        if stk is not None:
            segs.append(stk)
        return Outbound(scene, peer_id, segs)

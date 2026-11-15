"""核心大脑：决策 + 生成 + 媒体（看图 / 发表情）。纯业务，读写 Store。"""
from __future__ import annotations

import base64
import glob
import random
import re
import urllib.request

from .llm import LLMClient
from .store import Store
from .types import Capabilities, Inbound, Outbound, Segment


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


def _download_b64(url: str) -> str | None:
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
    def __init__(self, llm: LLMClient, persona: str, store: Store,
                 emoji_prob: float = 0.18, sticker_dir: str = ""):
        self.llm = llm
        self.persona = persona
        self.store = store
        self.emoji_prob = emoji_prob
        self.sticker_dir = sticker_dir

    def _sys(self) -> str:
        return (
            self.persona
            + "\n\n规则：像真人聊 QQ，短句口语，多用语气词；"
            "不要 markdown、不要分点、不要自称 AI、不要长篇大论。"
        )

    def _record_user(self, inbound: Inbound) -> None:
        self.store.add_message(
            channel=inbound.channel, scene=inbound.scene, peer_id=inbound.peer_id,
            sender_id=inbound.sender_id, sender_name=inbound.sender_name,
            role="user", content=inbound.text or "[图片]", msg_id=inbound.message_id,
            meta={"segments": [s.type for s in inbound.segments]},
        )

    def _stickers(self) -> list[str]:
        if not self.sticker_dir:
            return []
        return sorted(glob.glob(self.sticker_dir + "/*.png") + glob.glob(self.sticker_dir + "/*.jpg"))

    def _maybe_sticker_segment(self) -> Segment | None:
        if self.emoji_prob <= 0 or random.random() >= self.emoji_prob:
            return None
        files = self._stickers()
        if not files:
            return None
        try:
            with open(random.choice(files), "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            return Segment("image", {"file": "base64://" + b64})
        except Exception:
            return None

    def respond(self, inbound: Inbound, caps: Capabilities) -> Outbound | None:
        images = [s for s in inbound.segments if s.type == "image"]
        if not inbound.text and not images:
            return None
        self._record_user(inbound)
        if inbound.scene == "group" and not inbound.mentioned:
            return None

        messages = [{"role": "system", "content": self._sys()}]
        if inbound.text:
            past = self.store.search(inbound.peer_id, inbound.text, limit=4)
            if past:
                messages.append({
                    "role": "system",
                    "content": "（你记得对方以前说过：\n" + "\n".join("- " + p for p in past)
                               + "\n可以自然地提起，但别生硬。）",
                })
        messages += self.store.history(inbound.peer_id, 12)

        # 图片：尝试视觉理解（把图片塞进最后一条 user 的 content 里）
        vision_used = False
        if images and caps.send_image:
            b64 = _download_b64(images[0].data.get("url", ""))
            if b64 and messages and messages[-1]["role"] == "user":
                messages[-1] = {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": inbound.text or "（看看这张图）"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
                    ],
                }
                vision_used = True

        try:
            reply = self.llm.chat(messages)
        except Exception:
            if vision_used:  # 模型不支持视觉时回退纯文本
                messages[-1] = {"role": "user", "content": (inbound.text or "[图片]") + "（对方发了张图）"}
                try:
                    reply = self.llm.chat(messages)
                except Exception:
                    reply = "唔…刚刚走神了，你再说一遍嘛"
            else:
                return Outbound(inbound.scene, inbound.peer_id,
                                [Segment.text("（阿渔走神了…等一下下）")],
                                reply_to=inbound.message_id or None)

        self.store.add_message(
            channel=inbound.channel, scene=inbound.scene, peer_id=inbound.peer_id,
            sender_id="bot", sender_name="阿渔", role="assistant", content=reply,
        )
        segs = [Segment.text(p) for p in split_bubbles(reply)]
        st = self._maybe_sticker_segment()
        if st is not None:
            segs.append(st)
        return Outbound(inbound.scene, inbound.peer_id, segs, reply_to=inbound.message_id or None)

    def generate_proactive(self, peer_id: str, scene: str, hint: str) -> Outbound:
        hist = self.store.history(peer_id, 6)
        ctx = "\n".join(f"- {m['role']}: {m['content']}" for m in hist) or "（还没有聊过）"
        messages = [
            {"role": "system", "content": self._sys() + "\n现在你要主动给对方发消息（不是回复），简短自然。"},
            {"role": "system", "content": "最近对话：\n" + ctx},
            {"role": "user", "content": hint},
        ]
        try:
            reply = self.llm.chat(messages, temperature=0.9, max_tokens=200)
        except Exception:
            reply = "在吗…突然有点想问问你今天过得怎么样"
        self.store.add_message(
            channel="proactive", scene=scene, peer_id=peer_id,
            sender_id="bot", sender_name="阿渔", role="assistant", content=reply,
        )
        segs = [Segment.text(p) for p in split_bubbles(reply)]
        st = self._maybe_sticker_segment()
        if st is not None:
            segs.append(st)
        return Outbound(scene, peer_id, segs)

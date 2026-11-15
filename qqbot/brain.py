"""核心大脑：决策 + 生成。纯业务，不 import 任何协议/框架。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .llm import LLMClient
from .types import Capabilities, Inbound, Outbound, Segment


def split_bubbles(text: str, max_len: int = 28) -> list[str]:
    """把一段回复切成像真人连发的短消息。"""
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
            c = c[max_len * 2 :]
        if c:
            out.append(c)
    return out or [text]


@dataclass
class Brain:
    llm: LLMClient
    persona: str
    history: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    max_history: int = 12

    def respond(self, inbound: Inbound, caps: Capabilities) -> Outbound | None:
        # 群聊：没被 @ 就（M0）不插话；M3 换成分寸模型
        if inbound.scene == "group" and not inbound.mentioned:
            return None
        if not inbound.text:
            return None

        hist = self.history.setdefault(inbound.peer_id, [])
        sys_prompt = (
            self.persona
            + "\n\n规则：像真人聊 QQ，短句口语，多用语气词；"
            "不要 markdown、不要分点、不要自称 AI、不要长篇大论。"
        )
        messages = [{"role": "system", "content": sys_prompt}]
        messages += hist[-self.max_history :]
        messages.append({"role": "user", "content": inbound.text})

        try:
            reply = self.llm.chat(messages)
        except Exception as e:  # 大脑挂了也要有兜底，不能静默
            return Outbound(
                inbound.scene,
                inbound.peer_id,
                [Segment.text("（阿渔走神了…等一下下）")],
                reply_to=inbound.message_id or None,
            )

        hist.append({"role": "user", "content": inbound.text})
        hist.append({"role": "assistant", "content": reply})
        del hist[: max(0, len(hist) - self.max_history * 2)]

        parts = split_bubbles(reply)
        segments = [Segment.text(p) for p in parts]
        if not caps.send_text:
            return None
        return Outbound(
            inbound.scene, inbound.peer_id, segments, reply_to=inbound.message_id or None
        )

"""契约层：core 只认识这些类型，不认识 QQ / OneBot / Milky。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Scene = Literal["private", "group"]


@dataclass(frozen=True)
class Segment:
    """归一化消息段。type: text | image | at | voice | face | reply"""
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def text(s: str) -> "Segment":
        return Segment("text", {"text": s})

    @staticmethod
    def at(uid: str) -> "Segment":
        return Segment("at", {"uid": uid})


@dataclass
class Inbound:
    channel: str
    scene: Scene
    peer_id: str
    sender_id: str
    sender_name: str
    segments: list[Segment]
    message_id: str = ""
    ts: float = 0.0
    raw: Any = None  # 原始事件，仅供调试；core 严禁依赖

    @property
    def text(self) -> str:
        return "".join(
            s.data.get("text", "") for s in self.segments if s.type == "text"
        ).strip()

    @property
    def mentioned(self) -> bool:
        return any(s.type == "at" for s in self.segments)


@dataclass
class Outbound:
    scene: Scene
    peer_id: str
    segments: list[Segment]
    reply_to: str | None = None

    def as_text(self) -> str:
        return " / ".join(s.data.get("text", "") for s in self.segments)


@dataclass(frozen=True)
class RateLimit:
    qpm: int = 20
    per_group_daily: int = 1000
    passive_window_sec: int = 300


@dataclass(frozen=True)
class Capabilities:
    """通道能力矩阵：core 按此降级，而不是抛异常。"""
    send_text: bool = True
    send_image: bool = True
    send_voice: bool = False
    send_file: bool = False
    mention: bool = True
    reply: bool = True
    recall: bool = True
    emoji_react: bool = False
    poke: bool = False
    forward: bool = False
    group_history: bool = True
    proactive: bool = False
    rate: RateLimit = field(default_factory=RateLimit)

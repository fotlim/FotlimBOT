"""Mock 通道：无需 QQ，用脚本脚本化对话验证 核心→LLM→出站 全链路。"""
from __future__ import annotations

from ..brain import Brain
from ..types import Capabilities, Inbound, Segment


def run_demo(brain: Brain) -> None:
    caps = Capabilities()  # 全功能通道
    scripted = [
        Inbound("mock", "private", "u1001", "u1001", "小林",
                [Segment.text("在吗，今天有点累，不太想说话")], "m1"),
        Inbound("mock", "private", "u1001", "u1001", "小林",
                [Segment.text("你还记得我上次说要去面试吗")], "m2"),
        Inbound("mock", "group", "g2002", "u1003", "老王",
                [Segment.at("bot"), Segment.text("阿渔你在不在，聊两句")], "m3"),
        Inbound("mock", "group", "g2002", "u1004", "路人",
                [Segment.text("（群里在聊别的，没叫阿渔）")], "m4"),
    ]
    for msg in scripted:
        print(f"\n[{msg.scene}] {msg.sender_name}: {msg.text}")
        out = brain.respond(msg, caps)
        if out is None:
            print("  (未插话 / 静默 —— 这是设计，不是故障)")
            continue
        for seg in out.segments:
            print(f"  阿渔 → {seg.data.get('text','')}")

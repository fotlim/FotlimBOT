"""astrbot.api.event 兼容：filter 装饰器 + AstrMessageEvent + MessageEventResult。"""
from __future__ import annotations

from .message_components import Plain


class MessageEventResult:
    def __init__(self, chain=None):
        self.chain = list(chain or [])

    def plain(self, text):
        self.chain.append(Plain(text))
        return self

    def message(self, seg):
        self.chain.append(seg)
        return self


class _Filter:
    def __init__(self):
        self.handlers = []

    def command(self, name):
        def deco(fn):
            fn.__astrbot_kind__ = "command"
            fn.__astrbot_cmd__ = name
            self.handlers.append(fn)
            return fn
        return deco

    def on_message(self, *a, **k):
        def deco(fn):
            fn.__astrbot_kind__ = "message"
            fn.__astrbot_cmd__ = None
            self.handlers.append(fn)
            return fn
        return deco

    # 常见别名（不精确实现，仅占位，避免 import 失败）
    def command_group(self, *a, **k):
        return lambda fn: fn

    def event_message_type(self, *a, **k):
        return lambda fn: fn


filter = _Filter()


class AstrMessageEvent:
    def __init__(self, message_str, sender_name="", sender_id="", group_id="", message_id=""):
        self.message_str = message_str or ""
        self._sender_name = sender_name
        self._sender_id = str(sender_id)
        self.group_id = group_id or ""
        self.message_id = message_id or ""
        self.message_chain = [Plain(self.message_str)]

    def get_sender_name(self):
        return self._sender_name

    def get_sender_id(self):
        return self._sender_id

    def get_group_id(self):
        return self.group_id

    def get_messages(self):
        return self.message_chain

    def plain_result(self, text):
        return MessageEventResult([Plain(text)])

    async def reply(self, chain):
        if isinstance(chain, list):
            return MessageEventResult(chain)
        return MessageEventResult([Plain(str(chain))])

    async def send(self, chain):
        return await self.reply(chain)

    def is_private_chat(self):
        return not self.group_id

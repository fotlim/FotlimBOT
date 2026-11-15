"""AstrBot 插件宿主：加载 data/astrbot_plugins/*/main.py，把入站消息分发给插件指令。"""
from __future__ import annotations

import asyncio
import importlib.util
import inspect
import os
import shutil
import sys

_SHIM = os.path.join(os.path.dirname(__file__), "astrbot_shim")
if _SHIM not in sys.path:
    sys.path.insert(0, _SHIM)

from astrbot.api.star import REGISTRY, Context  # noqa: E402
from astrbot.api.event import AstrMessageEvent, MessageEventResult  # noqa: E402
from astrbot.api.message_components import Plain, At, Image, Record, Face  # noqa: E402


def _segments_from_chain(chain):
    """把 AstrBot 消息组件转成我们的 Segment 列表（延迟 import 防循环）。"""
    from .types import Segment
    segs = []
    for it in chain:
        cls = type(it).__name__
        if cls == "Plain":
            segs.append(Segment.text(it.text))
        elif cls == "At":
            segs.append(Segment("at", {"uid": str(it.qq)}))
        elif cls == "Image":
            segs.append(Segment("image", {"file": it.url or it.file or ""}))
        elif cls == "Record":
            segs.append(Segment("record", {"file": it.file or ""}))
        elif cls == "Face":
            segs.append(Segment("face", {"id": str(it.id)}))
    return segs


class AstrBotHost:
    def __init__(self, plugins_dir: str, sample_dir: str = ""):
        self.plugins_dir = plugins_dir
        self.sample_dir = sample_dir
        self.context = Context()
        self.plugins = []
        self.metas = []

    def _seed(self):
        try:
            os.makedirs(self.plugins_dir, exist_ok=True)
            if not os.listdir(self.plugins_dir) and self.sample_dir and os.path.isdir(self.sample_dir):
                shutil.copytree(self.sample_dir, self.plugins_dir, dirs_exist_ok=True)
        except Exception as e:
            print("[astr] seed err", repr(e), flush=True)

    def load(self) -> None:
        self._seed()
        REGISTRY.clear()
        if not os.path.isdir(self.plugins_dir):
            return
        for name in sorted(os.listdir(self.plugins_dir)):
            main = os.path.join(self.plugins_dir, name, "main.py")
            if not os.path.isfile(main):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"astrbot_plugin_{name}", main)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            except Exception as e:
                print("[astr] load err", name, repr(e), flush=True)
        for cls in REGISTRY:
            try:
                inst = cls(self.context)
                self.plugins.append(inst)
                meta = dict(getattr(cls, "__astrbot_meta__", {}))
                meta["class"] = cls.__name__
                self.metas.append(meta)
            except Exception as e:
                print("[astr] init err", cls, repr(e), flush=True)
        print(f"[astr] plugins loaded: {[m.get('name') for m in self.metas]}", flush=True)

    def reload(self) -> None:
        self.plugins = []
        self.metas = []
        try:
            for m in list(sys.modules.keys()):
                if m.startswith("astrbot_plugin_"):
                    del sys.modules[m]
        except Exception:
            pass
        self.load()

    def list(self):
        return self.metas

    def _handlers(self):
        for p in self.plugins:
            for attr in dir(p):
                try:
                    fn = getattr(p, attr)
                except Exception:
                    continue
                if callable(fn) and getattr(fn, "__astrbot_kind__", None):
                    yield fn

    def try_handle(self, inbound):
        """若有插件指令命中，返回 (Segment列表, 插件meta)；否则 None。"""
        cmd_text = (inbound.text or "").strip()
        if not cmd_text.startswith("/"):
            # 只对指令消息走插件，避免把普通聊天抢占
            return None
        ev = AstrMessageEvent(cmd_text, inbound.sender_name, inbound.sender_id,
                              group_id=(inbound.peer_id if inbound.scene == "group" else ""),
                              message_id=inbound.message_id)
        for fn in self._handlers():
            kind = getattr(fn, "__astrbot_kind__")
            cmd = getattr(fn, "__astrbot_cmd__", None)
            if kind == "command":
                tok = cmd_text.split()[0]
                if tok != "/" + str(cmd):
                    continue
            elif kind == "message":
                continue  # 不主动抢普通消息
            else:
                continue
            try:
                res = fn(ev)
                if inspect.isasyncgen(res):
                    async def collect(ag):
                        out = []
                        async for x in ag:
                            out.append(x)
                        return out
                    results = asyncio.run(collect(res))
                elif inspect.iscoroutine(res):
                    results = asyncio.run(res)
                else:
                    results = res
            except Exception as e:
                print("[astr] handle err", repr(e), flush=True)
                return None
            return (self._collect(results), {"plugin": getattr(fn, "__self__", None).__class__.__name__ if getattr(fn, "__self__", None) else "?"})

    def _collect(self, results):
        if results is None:
            return None
        if isinstance(results, MessageEventResult):
            results = [results]
        if not isinstance(results, list):
            results = [results]
        chain = []
        for r in results:
            if isinstance(r, MessageEventResult):
                chain.extend(r.chain)
            elif isinstance(r, str):
                chain.append(Plain(r))
        return chain or None

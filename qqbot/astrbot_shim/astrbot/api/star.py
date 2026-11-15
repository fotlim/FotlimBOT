"""astrbot.api.star 兼容：Star / Context / register。"""
from __future__ import annotations

REGISTRY = []


class _Metadata:
    async def get_plugin_config(self):
        return {}

    async def save_plugin_config(self, *a, **k):
        return None


class Context:
    def __init__(self):
        self.metadata = _Metadata()

    class _DB:
        async def get(self, *a, **k):
            return None

        async def set(self, *a, **k):
            return None

    @property
    def db(self):
        return Context._DB()


class Star:
    def __init__(self, context=None, config=None):
        self.context = context or Context()
        self.config = config or {}

    async def initialize(self):
        pass

    async def terminate(self):
        pass


def register(name, author="", desc="", version="1.0.0", repo=""):
    def deco(cls):
        cls.__astrbot_meta__ = {"name": name, "author": author, "desc": desc, "version": version}
        REGISTRY.append(cls)
        return cls
    return deco

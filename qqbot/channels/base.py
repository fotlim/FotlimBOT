"""通道抽象：所有协议实现都继承它。core 只见这张脸。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..types import Capabilities


class Channel(ABC):
    name: str = "base"
    caps: Capabilities = Capabilities()

    @abstractmethod
    def start(self) -> None:
        """阻塞运行，收到消息就交给 brain，并把 Outbound 发出去。"""
        raise NotImplementedError

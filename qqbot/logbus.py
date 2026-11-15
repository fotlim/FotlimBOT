"""stdout tee -> 环形缓冲，供控制台查看日志。"""
from __future__ import annotations

import collections
import sys
import threading


class _Tee:
    def __init__(self, real):
        self.real = real
        self.buf = collections.deque(maxlen=800)
        self.lock = threading.Lock()
        self.partial = ""

    def write(self, s):
        try:
            self.real.write(s)
        except Exception:
            pass
        with self.lock:
            self.partial += s
            while "\n" in self.partial:
                line, self.partial = self.partial.split("\n", 1)
                if line:
                    self.buf.append(line)
        return len(s)

    def flush(self):
        try:
            self.real.flush()
        except Exception:
            pass

    def lines(self, n: int = 200) -> list[str]:
        with self.lock:
            return list(self.buf)[-n:]


_tee: _Tee | None = None


def install() -> _Tee:
    global _tee
    if _tee is None:
        _tee = _Tee(sys.stdout)
        sys.stdout = _tee
        sys.stderr = _tee
    return _tee


def lines(n: int = 200) -> list[str]:
    return _tee.lines(n) if _tee is not None else []

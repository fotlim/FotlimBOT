"""OpenAI 兼容客户端（仅标准库），支持 reasoning_effort 提速。"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMClient:
    base: str
    key: str
    model: str
    timeout: int = 90

    def chat(self, messages, temperature: float = 0.85, max_tokens: int = 240,
             reasoning: str | None = None) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if reasoning:
            payload["reasoning_effort"] = reasoning
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base.rstrip("/") + "/chat/completions", data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                d: Any = json.load(r)
            return (d["choices"][0]["message"]["content"] or "").strip()
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:400]
            except Exception:
                pass
            raise RuntimeError(f"LLM HTTP {e.code}: {detail}") from e

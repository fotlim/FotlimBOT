"""联网通道：网页搜索 / 图片搜索 / 抓正文（Bing，国内可达）。仅标准库。"""
from __future__ import annotations

import base64
import html
import json
import re
import urllib.parse
import urllib.request

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def _get(url, timeout=12, max_bytes=1_500_000):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(max_bytes)


def _text(url, timeout=12):
    d = _get(url, timeout)
    try:
        return d.decode("utf-8", "replace")
    except Exception:
        return d.decode("gbk", "replace")


def search(query: str, n: int = 6) -> list[dict]:
    url = "https://cn.bing.com/search?" + urllib.parse.urlencode({"q": query, "setlang": "zh-CN"})
    h = _text(url)
    items = []
    for m in re.finditer(r'<li class="b_algo".*?</li>', h, re.S):
        block = m.group(0)
        t = re.search(r'<h2[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not t:
            continue
        link = html.unescape(t.group(1))
        title = re.sub(r"<[^>]+>", "", html.unescape(t.group(2))).strip()
        sn = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
        snippet = re.sub(r"<[^>]+>", "", html.unescape(sn.group(1))).strip() if sn else ""
        items.append({"title": title, "url": link, "snippet": snippet[:200]})
        if len(items) >= n:
            break
    return items


def image_search(query: str, n: int = 8) -> list[str]:
    url = "https://cn.bing.com/images/search?" + urllib.parse.urlencode({"q": query, "form": "HDRSC2"})
    h = _text(url)
    urls = []
    for m in re.finditer(r'm="(\{[^"]*?\})"', h):
        try:
            obj = json.loads(html.unescape(m.group(1)))
        except Exception:
            continue
        u = obj.get("murl")
        if u:
            urls.append(u)
        if len(urls) >= n:
            break
    return urls


def fetch_text(url: str, max_chars: int = 4000, timeout: int = 12) -> str:
    try:
        h = _text(url, timeout)
    except Exception:
        return ""
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h)
    txt = re.sub(r"(?s)<[^>]+>", " ", h)
    txt = html.unescape(txt)
    txt = re.sub(r"\s+", " ", txt)
    return txt[:max_chars]


def fetch_b64(url: str, max_bytes: int = 4_000_000, timeout: int = 15) -> str | None:
    try:
        return base64.b64encode(_get(url, timeout, max_bytes)).decode()
    except Exception:
        return None

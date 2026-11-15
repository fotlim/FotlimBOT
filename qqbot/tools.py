"""工具层 + 第一批零依赖插件（计算/天气/报时/骰子/硬币/运势/一言/笑话/古诗/密码/颜色/摩斯/进制/单位/备忘/记账/签到/群资料）。
dispatch(inbound, brain) 命中意图就执行并返回 Outbound，否则 None。"""
from __future__ import annotations

import datetime
import hashlib
import json
import random
import re
import urllib.parse
import urllib.request

from .types import Outbound, Segment

UA = {"User-Agent": "Mozilla/5.0"}

TOOLS = [
    {"name": "calc", "desc": "算术计算", "eg": "算 1+2*3"},
    {"name": "weather", "desc": "查天气", "eg": "天气 北京"},
    {"name": "clock", "desc": "报时", "eg": "现在几点"},
    {"name": "coin", "desc": "抛硬币", "eg": "抛硬币"},
    {"name": "dice", "desc": "掷骰子", "eg": "骰子 2d6"},
    {"name": "fortune", "desc": "今日运势", "eg": "今日运势"},
    {"name": "hitokoto", "desc": "一言", "eg": "来句一言"},
    {"name": "joke", "desc": "冷笑话", "eg": "讲个笑话"},
    {"name": "poem", "desc": "古诗", "eg": "来首古诗"},
    {"name": "passgen", "desc": "生成密码", "eg": "密码 16"},
    {"name": "color", "desc": "随机颜色", "eg": "随机颜色"},
    {"name": "morse", "desc": "摩斯电码", "eg": "摩斯 hello"},
    {"name": "baseconv", "desc": "进制转换", "eg": "进制 255 16"},
    {"name": "unit", "desc": "单位换算", "eg": "换算 5 km m"},
    {"name": "memo", "desc": "群备忘", "eg": "备忘 明天交报告 / 看备忘"},
    {"name": "ledger", "desc": "群记账", "eg": "记账 15 午饭 / 看账本"},
    {"name": "signin", "desc": "群签到", "eg": "签到"},
    {"name": "group_info", "desc": "群资料", "eg": "群资料"},
]


def _get(url, timeout=10):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _json(url, timeout=10):
    return json.loads(_get(url, timeout).decode("utf-8", "replace"))


def _rep(inbound, text):
    return Outbound(inbound.scene, inbound.peer_id, [Segment.text(text)], reply_to=inbound.message_id or None)


WCODE = {0: "晴", 1: "多云", 2: "多云", 3: "阴", 45: "雾", 48: "雾", 51: "小雨", 53: "小雨", 55: "中雨",
         61: "小雨", 63: "中雨", 65: "大雨", 71: "小雪", 73: "中雪", 75: "大雪", 80: "阵雨", 81: "阵雨",
         82: "强阵雨", 95: "雷阵雨", 96: "雷阵雨", 99: "雷暴"}


def t_weather(city):
    g = _json("https://geocoding-api.open-meteo.com/v1/search?" +
              urllib.parse.urlencode({"name": city, "count": 1, "language": "zh"}))
    res = g.get("results")
    if not res:
        return "没找到「%s」这个城市" % city
    loc = res[0]
    w = _json("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": loc["latitude"], "longitude": loc["longitude"],
        "current": "temperature_2m,weather_code", "daily": "temperature_2m_max,temperature_2m_min",
        "timezone": "auto", "forecast_days": 1}))
    cur = w.get("current") or {}
    d = w.get("daily") or {}
    tmax = (d.get("temperature_2m_max") or ["?"])[0]
    tmin = (d.get("temperature_2m_min") or ["?"])[0]
    desc = WCODE.get(cur.get("weather_code"), "未知")
    return "%s：现在 %s℃，今天 %s~%s℃，%s" % (loc.get("name", city), cur.get("temperature_2m"), tmin, tmax, desc)


JOKES = ["为什么程序员分不清万圣节和圣诞节？因为 Oct 31 == Dec 25。",
         "我减肥了，减掉了一斤……好吧其实是秤坏了。",
         "鱼为什么不上岸？因为岸上有猫。",
         "有人问我：你帅吗？我说：我这叫耐看。"]
POEMS = ["床前明月光，疑是地上霜。——李白《静夜思》",
         "海上生明月，天涯共此时。——张九龄《望月怀远》",
         "山有木兮木有枝，心悦君兮君不知。——《越人歌》",
         "落霞与孤鹜齐飞，秋水共长天一色。——王勃《滕王阁序》"]
FOR = ["诸事顺遂，宜出门", "小有波折，但能化解", "贵人相助，大胆一点", "适合安静待着，少惹事", "财运一般，别乱花钱"]
HITO_FALLBACK = ["生活不止眼前的苟且，还有诗和远方。", "愿你熬过万丈孤独，藏下星辰大海。"]


def t_calc(expr):
    if not re.fullmatch(r"[0-9\.\+\-\*/%\(\)\s]+", expr or ""):
        return "算式里有不支持的字符（只支持数字和 + - * / % ( )）"
    try:
        val = eval(expr, {"__builtins__": {}}, {})
    except Exception:
        return "这个算式算不出来，检查一下～"
    return "%s = %s" % (expr.strip(), val)


def t_dice(arg):
    m = re.match(r"^(\d*)d(\d+)$", (arg or "").strip().lower())
    if m:
        n = int(m.group(1) or 1); sides = int(m.group(2))
    elif (arg or "").strip().isdigit():
        n, sides = 1, int(arg.strip())
    else:
        n, sides = 1, 6
    n = max(1, min(20, n)); sides = max(2, min(1000, sides))
    rolls = [random.randint(1, sides) for _ in range(n)]
    return "掷 %dd%d：%s（合计 %d）" % (n, sides, "、".join(map(str, rolls)), sum(rolls))


MORSE = {'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.', 'G': '--.', 'H': '....',
         'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..', 'M': '--', 'N': '-.', 'O': '---', 'P': '.--.',
         'Q': '--.-', 'R': '.-.', 'S': '...', 'T': '-', 'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-',
         'Y': '-.--', 'Z': '--..', '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-',
         '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.'}


def t_morse(text):
    out = []
    for ch in text.upper():
        if ch == ' ':
            out.append('/')
        elif ch in MORSE:
            out.append(MORSE[ch])
    return " ".join(out) or "（没有可转换的字符）"


UNITS = {"km": ("len", 1000.0), "m": ("len", 1.0), "cm": ("len", 0.01), "mm": ("len", 0.001),
         "kg": ("w", 1000.0), "g": ("w", 1.0), "t": ("w", 1000000.0)}


def t_unit(arg):
    m = re.match(r"^([\d\.]+)\s*([a-zA-Z]+)\s*(?:->|to|转|=|成)?\s*([a-zA-Z]+)$", (arg or "").strip())
    if not m:
        return "格式：换算 5 km m（长度 km/m/cm/mm、重量 kg/g/t）"
    v = float(m.group(1)); a = m.group(2).lower(); b = m.group(3).lower()
    if a in ("c", "f") or b in ("c", "f"):
        if a == "c" and b == "f":
            return "%g℃ = %g℉" % (v, v * 9 / 5 + 32)
        if a == "f" and b == "c":
            return "%g℉ = %g℃" % (v, (v - 32) * 5 / 9)
    if a in UNITS and b in UNITS and UNITS[a][0] == UNITS[b][0]:
        r = v * UNITS[a][1] / UNITS[b][1]
        return "%g %s = %g %s" % (v, a, r, b)
    return "这两个单位我换算不了～"


def t_baseconv(arg):
    parts = (arg or "").split()
    try:
        if len(parts) == 3:
            s, frm, to = parts[0], int(parts[1]), int(parts[2])
        elif len(parts) == 2:
            s, to = parts[0], int(parts[1]); frm = 10
        else:
            return "格式：进制 255 16（10进制→16进制）或 进制 ff 16 10（16进制→10进制）"
        n = int(s, frm)
        digits = "0123456789abcdefghijklmnopqrstuvwxyz"
        if not (2 <= to <= 36) or not (2 <= frm <= 36):
            return "进制支持 2~36"
        if n == 0:
            out = "0"
        else:
            out = ""
            while n:
                out = digits[n % to] + out
                n //= to
        return "%s（%d进制）= %s（%d进制）" % (s, frm, out, to)
    except Exception:
        return "转换失败，检查输入"


def t_hitokoto():
    try:
        d = _json("https://v1.hitokoto.cn/")
        return d.get("hitokoto") or random.choice(HITO_FALLBACK)
    except Exception:
        return random.choice(HITO_FALLBACK)


def _kv_list(store, key):
    try:
        return json.loads(store.kv_get(key) or "[]")
    except Exception:
        return []


def _kv_set(store, key, val):
    store.kv_set(key, json.dumps(val, ensure_ascii=False))


def dispatch(inbound, brain):
    t = (inbound.text or "").strip()
    if not t:
        return None
    store = brain.store
    gid = inbound.peer_id if inbound.scene == "group" else ""

    m = re.match(r"^(?:算一下|计算|算)\s*(.+)$", t)
    if m:
        return _rep(inbound, t_calc(m.group(1)))

    m = re.match(r"^(?:查?天气)\s+(.+)$", t) or re.match(r"^(.+?)(?:的)?天气(?:怎么样|如何)?[。！!？?]*$", t)
    if m:
        return _rep(inbound, t_weather(m.group(1).strip()))

    if re.search(r"^(现在几点|几点了|报时|现在时间)", t):
        return _rep(inbound, "现在时间：" + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    if re.match(r"^(抛硬币|硬币|coin)", t, re.I):
        return _rep(inbound, "抛硬币：" + random.choice(["正面", "反面"]))

    m = re.match(r"^(?:骰子|掷骰子|roll)\s*([0-9dD]*)$", t, re.I)
    if m:
        return _rep(inbound, t_dice(m.group(1)))

    if re.match(r"^(今日运势|运势|抽个运势|看看运势)", t):
        seed = int(hashlib.md5((datetime.date.today().isoformat() + str(inbound.sender_id)).encode()).hexdigest(), 16)
        score = seed % 101
        return _rep(inbound, "今日运势 %d/100：%s" % (score, FOR[seed % len(FOR)]))

    if re.match(r"^(来句一言|一言|一言以蔽之)", t):
        return _rep(inbound, t_hitokoto())

    if re.match(r"^(讲个笑话|冷笑话|来个笑话|笑话)", t):
        return _rep(inbound, random.choice(JOKES))

    if re.match(r"^(来首古诗|背首诗|古诗|来句诗)", t):
        return _rep(inbound, random.choice(POEMS))

    m = re.match(r"^(?:生成)?密码\s*(\d+)?$", t)
    if m:
        n = int(m.group(1) or 16); n = max(6, min(64, n))
        chars = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%"
        return _rep(inbound, "随机密码（%d位）：%s" % (n, "".join(random.choice(chars) for _ in range(n))))

    if re.match(r"^(随机颜色|颜色|color)$", t, re.I):
        c = "#%06x" % random.randint(0, 0xFFFFFF)
        return _rep(inbound, "随机颜色：%s" % c)

    m = re.match(r"^(?:摩斯|转摩斯|摩斯电码)\s+(.+)$", t)
    if m:
        return _rep(inbound, t_morse(m.group(1)))

    m = re.match(r"^(?:进制|转换进制)\s+(.+)$", t)
    if m:
        return _rep(inbound, t_baseconv(m.group(1)))

    m = re.match(r"^(?:单位换算|换算)\s+(.+)$", t)
    if m:
        return _rep(inbound, t_unit(m.group(1)))

    if inbound.scene == "group":
        m = re.match(r"^备忘\s+(.+)$", t)
        if m:
            key = "memo:" + gid
            arr = _kv_list(store, key); arr.append({"t": datetime.datetime.now().strftime("%m-%d %H:%M"), "c": m.group(1)[:200]})
            _kv_set(store, key, arr[-50:])
            return _rep(inbound, "记下了备忘：" + m.group(1)[:60])
        if re.match(r"^(看备忘|备忘列表|查备忘)$", t):
            arr = _kv_list(store, "memo:" + gid)
            if not arr:
                return _rep(inbound, "本群还没有备忘～")
            return _rep(inbound, "本群备忘：\n" + "\n".join("- [%s] %s" % (x["t"], x["c"]) for x in arr[-15:]))

        m = re.match(r"^记账\s+([\d\.]+)\s*(.*)$", t)
        if m:
            key = "ledger:" + gid
            arr = _kv_list(store, key)
            arr.append({"who": str(inbound.sender_name or inbound.sender_id), "amt": float(m.group(1)),
                        "note": (m.group(2) or "").strip()[:40], "t": datetime.datetime.now().strftime("%m-%d %H:%M")})
            _kv_set(store, key, arr[-500:])
            total = sum(x["amt"] for x in arr)
            return _rep(inbound, "记一笔 %g 元 %s，本群累计 %.2f 元" % (float(m.group(1)), m.group(2), total))
        if re.match(r"^(看账本|账本|查账本)$", t):
            arr = _kv_list(store, "ledger:" + gid)
            if not arr:
                return _rep(inbound, "本群还没记账～")
            total = sum(x["amt"] for x in arr)
            recent = "\n".join("- %s %g元 %s" % (x["who"], x["amt"], x["note"]) for x in arr[-10:])
            return _rep(inbound, "本群累计 %.2f 元，最近记录：\n%s" % (total, recent))

        if re.match(r"^签到$", t):
            key = "signin:" + gid
            data = {}
            try:
                data = json.loads(store.kv_get(key) or "{}")
            except Exception:
                data = {}
            uid = str(inbound.sender_id); today = datetime.date.today().isoformat()
            rec = data.get(uid) or {"last": "", "points": 0, "days": 0}
            if rec.get("last") == today:
                return _rep(inbound, "你今天已经签到过啦，当前 %d 分" % rec["points"])
            rec["points"] += random.randint(1, 5); rec["days"] += 1; rec["last"] = today
            data[uid] = rec; store.kv_set(key, json.dumps(data, ensure_ascii=False))
            return _rep(inbound, "签到成功！+积分，你现在 %d 分（连续 %d 天）" % (rec["points"], rec["days"]))

        if re.match(r"^(群资料|群信息|本群信息)$", t):
            ch = getattr(brain, "channel", None)
            try:
                info = ch.call_action("get_group_info", {"group_id": int(gid)}, timeout=8) if ch else None
                mem = ch.call_action("get_group_member_list", {"group_id": int(gid)}, timeout=8) if ch else None
                d = (info or {}).get("data") or {}
                cnt = len((mem or {}).get("data") or [])
                return _rep(inbound, "本群：%s｜成员约 %d 人" % (d.get("group_name", gid), cnt))
            except Exception:
                return _rep(inbound, "拿不到群资料（可能需要权限或协议端未开）")

    return None

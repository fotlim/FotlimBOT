"""情绪引擎：PAD 三维情绪场 + 好感度 + 精力 + 弛豫 + 评估 + 注入文案。
参考 AstrBot BioCore / EmotionAI Pro / dsh-emotion-memory 的思路。"""
from __future__ import annotations

import json
import re
import time

POS = ["谢谢", "喜欢", "爱你", "开心", "哈哈", "么么", "抱抱", "好棒", "厉害", "想你", "可爱", "乖", "宝贝", "亲", "赞", "辛苦", "好听"]
NEG = ["讨厌", "滚", "烦", "闭嘴", "垃圾", "笨", "傻", "恨", "丑", "恶心", "别烦", "生气", "去死"]
APO = ["对不起", "抱歉", "我错", "别生气", "原谅", "不好意思"]
SAD = ["累", "难过", "难受", "不开心", "委屈", "压力", "烦死"]
LOVE = ["想你", "喜欢你", "爱你", "抱抱", "么么"]

MOOD2CAT = {"开心": "happy", "兴奋": "happy", "喜欢": "love", "害羞": "shy",
            "难过": "sad", "委屈": "sad", "生气": "angry", "平静": "speechless"}


def _clamp(x, a, b):
    return max(a, min(b, x))


DEFAULT_LEVELS = [[0, "陌生"], [20, "认识"], [40, "朋友"], [62, "好友"], [80, "挚友"]]


def level_of(aff: float, settings) -> str:
    e = settings.get("emotion", {}) or {}
    if all(k in e for k in ("lv_acquaint", "lv_friend", "lv_close", "lv_best")):
        levels = [[0, "陌生"], [float(e["lv_acquaint"]), "认识"], [float(e["lv_friend"]), "朋友"],
                  [float(e["lv_close"]), "好友"], [float(e["lv_best"]), "挚友"]]
    else:
        levels = e.get("affinity_levels") or DEFAULT_LEVELS
    levels = sorted(levels, key=lambda x: float(x[0]))
    name = levels[0][1]
    try:
        for mn, nm in levels:
            if aff >= float(mn):
                name = nm
    except Exception:
        pass
    return name


def new_state(settings) -> dict:
    e = settings.get("emotion", {})
    return {"p": float(e.get("baseline_p", 0.6)), "a": float(e.get("baseline_a", 0.35)),
            "d": float(e.get("baseline_d", 0.6)), "affinity": float(e.get("baseline_affinity", 50.0)),
            "energy": 80.0, "mood": "平静", "intensity": 0.3, "events": [], "updated": time.time()}


def relax(state: dict, settings) -> dict:
    e = settings.get("emotion", {})
    now = time.time()
    dt = max(0.0, (now - state.get("updated", now)) / 3600.0)
    if dt > 0:
        k = min(1.0, dt * float(e.get("decay_per_hour", 3.0)) / 10.0)
        for dim, bkey in (("p", "baseline_p"), ("a", "baseline_a"), ("d", "baseline_d")):
            base = float(e.get(bkey, state[dim]))
            state[dim] = _clamp(state[dim] + (base - state[dim]) * k, 0, 1)
        baf = float(e.get("baseline_affinity", 50.0))
        state["affinity"] = _clamp(state["affinity"] + (baf - state["affinity"]) * k * 0.5, 0, 100)
        state["energy"] = _clamp(state.get("energy", 80) + dt * 10, 0, 100)
        state["updated"] = now
    return state


def appraise_heuristic(text: str):
    t = text or ""
    dp = da = dd = daff = 0.0
    ev = []
    for w in POS:
        if w in t:
            dp += 0.08; da += 0.03; daff += 3; ev.append("夸赞")
    for w in NEG:
        if w in t:
            dp -= 0.20; da += 0.12; dd -= 0.05; daff -= 7; ev.append("冒犯")
    if any(w in t for w in APO):
        dp += 0.06; da -= 0.12; daff += 2; ev.append("道歉")
    if any(w in t for w in SAD):
        dp -= 0.05; da += 0.03; ev.append("对方低落")
    if any(w in t for w in LOVE):
        dp += 0.05; daff += 5; ev.append("亲昵")
    if ("?" in t) or ("？" in t) or any(w in t for w in ["在吗", "怎么了", "为什么", "吗"]):
        da += 0.02; ev.append("询问")
    if not ev:
        ev.append("平常")
    dp = _clamp(dp, -0.3, 0.3); da = _clamp(da, -0.3, 0.3); dd = _clamp(dd, -0.3, 0.3); daff = _clamp(daff, -30, 30)
    return dp, da, dd, daff, ev


def appraise_llm(llm, text: str):
    sys_p = ('你在为角色"FotlimBOT"评估用户这句话的情绪影响。只输出一行 JSON：'
             '{"d_pleasure":数,"d_arousal":数,"d_dominance":数,"d_affinity":数,"event":"标签"}，'
             '各 d 值范围 -0.2~0.2（d_affinity -10~10）。')
    try:
        out = llm.chat([{"role": "system", "content": sys_p}, {"role": "user", "content": text}],
                       max_tokens=120, reasoning="none")
        m = re.search(r"\{.*\}", out, re.S)
        d = json.loads(m.group(0))
        return (float(d.get("d_pleasure", 0)), float(d.get("d_arousal", 0)),
                float(d.get("d_dominance", 0)), float(d.get("d_affinity", 0)), [str(d.get("event", "事件"))])
    except Exception:
        return None


def derive_mood(st: dict):
    p, a, d, aff = st["p"], st["a"], st["d"], st["affinity"]
    if aff >= 78 and p > 0.55:
        label = "喜欢"
    elif p > 0.66:
        label = "兴奋" if a > 0.6 else "开心"
    elif p < 0.50 and a >= 0.55:
        label = "生气"
    elif p < 0.32:
        label = "难过"
    elif d < 0.4 and p < 0.5:
        label = "委屈"
    elif a < 0.3 and p >= 0.55:
        label = "害羞" if d < 0.55 else "平静"
    else:
        label = "平静"
    intensity = round(_clamp(abs(p - 0.55) * 1.6 + abs(a - 0.35) * 0.8, 0, 1), 2)
    return label, intensity


def update(store, peer_id: str, text: str, settings, llm=None, scene: str = "private") -> dict:
    st = store.emotion_get_raw(peer_id) or new_state(settings)
    st = relax(st, settings)
    ap = appraise_llm(llm, text) if (settings["emotion"].get("use_llm") and llm is not None) else None
    if ap is None:
        dp, da, dd, daff, ev = appraise_heuristic(text)
    else:
        dp, da, dd, daff, ev = ap
    st["p"] = _clamp(st["p"] + dp, 0, 1)
    st["a"] = _clamp(st["a"] + da, 0, 1)
    st["d"] = _clamp(st["d"] + dd, 0, 1)
    st["affinity"] = _clamp(st["affinity"] + daff, 0, 100)
    if scene == "group":
        cap = float(settings["emotion"].get("group_affinity_cap", 60))
        st["affinity"] = min(st["affinity"], cap)
    evs = (st.get("events") or [])[-9:] + list(ev)
    st["events"] = evs
    st["energy"] = _clamp(st.get("energy", 80) - 1.5, 0, 100)
    label, inten = derive_mood(st)
    st["mood"] = label
    st["intensity"] = inten
    st["updated"] = time.time()
    store.emotion_save(peer_id, st)
    return st


def prompt(st: dict, scene: str = "private", settings=None) -> str:
    settings = settings or {"emotion": {}}
    aff = st["affinity"]
    if scene == "group":
        cap = float(settings.get("emotion", {}).get("group_affinity_cap", 60))
        aff = min(aff, cap)
    tier = level_of(aff, settings)
    energy = "充足" if st["energy"] > 60 else ("一般" if st["energy"] > 30 else "有点累")
    extra = ""
    if scene == "group":
        extra = ("（注意：这是群聊，你和对方只是普通朋友/群友关系，必须保持分寸和礼貌，"
                 "不要暧昧、不要撒娇过度、不要表达任何超出朋友的亲密或占有欲。）")
    return (f"（你此刻心情：{st['mood']}（强度 {st['intensity']}），精力{energy}；对对方好感度：{tier}。"
            f"请让语气自然贴合当前情绪，但不要直接说出这些数值或设定。{extra}）")


def sticker_category(st: dict):
    return MOOD2CAT.get(st.get("mood", ""), None)


def snapshot(store, settings) -> list[dict]:
    out = []
    for st in store.emotion_all_raw():
        st = relax(st, settings)
        out.append({"peer_id": st.get("peer_id"), "p": round(st["p"], 2), "a": round(st["a"], 2),
                    "d": round(st["d"], 2), "affinity": round(st["affinity"], 1),
                    "energy": round(st["energy"], 0), "mood": st["mood"], "intensity": st["intensity"],
                    "events": st.get("events", [])[-5:]})
    return out

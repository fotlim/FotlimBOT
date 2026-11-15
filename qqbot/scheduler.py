"""调度器：主动发言 + 自主行为（独立开关，可手动试跑）。"""
from __future__ import annotations

import datetime
import random
import threading
import time

from .brain import Brain
from .store import Store


def _hm(s: str) -> int:
    try:
        h, m = s.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


class Scheduler:
    def __init__(self, brain: Brain, channel, store: Store, cfg):
        self.brain = brain
        self.channel = channel
        self.store = store
        self.cfg = cfg
        self.enabled = bool(store.get_settings()["proactive"].get("enabled", True))

    def set_enabled(self, v: bool) -> None:
        self.enabled = bool(v)
        self.store.set_settings({"proactive": {"enabled": bool(v)}})

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()
        print(f"[sched] started (enabled={self.enabled})", flush=True)

    def _in_quiet(self, now, qs, qe):
        cur = now.hour * 60 + now.minute
        return (qs <= cur < qe) if qs <= qe else (cur >= qs or cur < qe)

    def _loop(self) -> None:
        time.sleep(30)
        while True:
            try:
                self._tick()
            except Exception as e:
                print("[sched] err", repr(e), flush=True)
            time.sleep(120)

    def _tick(self) -> None:
        if not getattr(self.channel, "connected", False):
            return
        try:
            if self.enabled:
                self._proactive()
        except Exception as e:
            print("[sched] proactive err", repr(e), flush=True)
        try:
            r = self._autonomy()
            if r.get("ok"):
                print("[sched] autonomy ->", r.get("act"), flush=True)
        except Exception as e:
            print("[sched] autonomy err", repr(e), flush=True)

    def _proactive(self) -> None:
        cfgp = self.store.get_settings()["proactive"]
        now = datetime.datetime.now()
        if self._in_quiet(now, _hm(cfgp.get("quiet_start", "22:30")), _hm(cfgp.get("quiet_end", "08:00"))):
            return
        min_idle = float(cfgp.get("min_idle_h", 2))
        date = now.strftime("%Y-%m-%d")
        for p in self.store.recent_peers(days=3):
            peer = p["peer_id"]
            idle = (time.time() - p["last"]) / 3600.0
            slot = hint = None
            if 8 <= now.hour < 11 and idle >= min_idle:
                slot, hint = "am", "上午好，用一句轻快简短的话跟对方打个招呼，关心下今天。"
            elif 20 <= now.hour < 22 and idle >= min_idle:
                slot, hint = "pm", "晚上了，语气温柔点，问问对方今天过得怎么样，别太长。"
            elif 13 <= now.hour < 18 and idle >= min_idle + 1:
                slot, hint = "mid", "下午了，随口关心一句，自然点，不黏人。"
            if not hint:
                continue
            key = f"proactive:{peer}:{date}:{slot}"
            if self.store.kv_get(key):
                continue
            out = self.brain.generate_proactive(peer, "private", hint)
            if self.channel.send(out):
                self.store.kv_set(key, "1")
                self.store.log_action("proactive", peer, hint)
                print("[sched] proactive ->", peer, flush=True)
                time.sleep(2)

    def _autonomy(self, force: bool = False) -> dict:
        a = self.store.get_settings().get("autonomy", {})
        if not force and not a.get("enabled"):
            return {"ok": False, "detail": "自主行为未启用"}
        if not getattr(self.channel, "connected", False):
            return {"ok": False, "detail": "通道未连接"}
        now = time.time()
        if not force and (now - float(self.store.kv_get("autonomy:last", 0) or 0) < float(a.get("min_interval_hours", 6)) * 3600):
            return {"ok": False, "detail": "未到最小间隔"}
        acts = [k for k, flag in (("like", a.get("allow_like")), ("qzone", a.get("allow_qzone_post")),
                                  ("nick", a.get("allow_nickname")), ("avatar", a.get("allow_avatar"))) if flag]
        if not acts:
            return {"ok": False, "detail": "未勾选任何自主动作"}
        act = random.choice(acts)
        from . import actions
        detail = ""
        ok = False
        try:
            if act == "like":
                feeds = [f for f in actions.simplify_feeds(actions.qzone_feeds(self.channel)) if f.get("tid")]
                if not feeds:
                    return {"ok": False, "act": act, "detail": "好友动态为空"}
                f = random.choice(feeds)
                r = actions.qzone_like(self.channel, f["tid"])
                ok = bool(r and r.get("status") == "ok")
                detail = f"赞了 {f.get('nick')} 的说说"
            elif act == "qzone":
                txt = self.brain.llm.chat(
                    [{"role": "system", "content": "你是FotlimBOT，用一句简短治愈的话发QQ空间说说，不加话题"},
                     {"role": "user", "content": "写一句今天的心情"}], max_tokens=50, reasoning="none")
                r = actions.qzone_publish(self.channel, (txt or "今天也是想你的一天").strip())
                ok = bool(r and r.get("status") == "ok")
                detail = "发了条说说"
            elif act == "nick":
                name = self.brain._self_name() if hasattr(self.brain, "_self_name") else "FotlimBOT"
                try:
                    _p = self.brain._current_persona()[:900]
                    nn = self.brain.llm.chat(
                        [{"role": "system", "content": "这是你的角色人设，请给自己起一个【完全符合该人设】的 QQ 昵称（贴合角色身份与气质，6 字以内），只输出昵称本身，不要引号不要解释：\n" + _p},
                         {"role": "user", "content": "起个符合人设的新昵称"}], max_tokens=40, reasoning="low")
                except Exception:
                    nn = ""
                nick = (nn or "").strip().replace('"', "").splitlines()[0][:16] if (nn or "").strip() else ""
                if not nick:
                    nick = name
                r = actions.set_nickname(self.channel, nick)
                ok = bool(r and r.get("status") == "ok")
                detail = "改昵称为 " + nick
                try:
                    li = actions.get_login_info(self.channel)
                    uid = ((li or {}).get("data") or {}).get("user_id")
                    gl = actions.get_group_list(self.channel)
                    groups = ((gl or {}).get("data") or [])
                    if uid:
                        for g in groups[:5]:
                            gid = g.get("group_id")
                            if gid:
                                actions.set_group_card(self.channel, gid, uid, nick)
                except Exception:
                    pass
            elif act == "avatar":
                ok = False
                detail = ""
                name = self.brain._self_name() if hasattr(self.brain, "_self_name") else "FotlimBOT"
                kw = ""
                try:
                    import re as _re
                    p = self.brain._current_persona()
                    m = _re.search(r"外貌[：:]\s*(.+)", p)
                    if m:
                        kw = " ".join([x.strip() for x in _re.split(r"[、，,。]", m.group(1)) if x.strip()][:2])
                except Exception:
                    pass
                query = (name + " 二次元 头像 " + kw).strip()
                try:
                    from . import web as webmod
                    urls = webmod.image_search(query, 8)
                    url = next((u for u in urls if u), None)
                    if url:
                        r = actions.set_avatar(self.channel, url)
                        ok = bool(r and r.get("status") == "ok")
                        detail = "换了符合人设的头像（" + name + "·网络图）"
                except Exception:
                    ok = False
                if not ok:
                    p2 = self.store.meme_pick(None)
                    if p2:
                        import base64 as _b64
                        data = _b64.b64encode(open(p2, "rb").read()).decode()
                        r = actions.set_avatar(self.channel, "base64://" + data)
                        ok = bool(r and r.get("status") == "ok")
                        detail = "换了头像（图库兜底）"
                if not ok:
                    return {"ok": False, "act": act, "detail": "换头像失败（网络搜图与图库都不可用）"}
        except Exception as e:
            return {"ok": False, "act": act, "detail": repr(e)[:120]}
        if ok:
            self.store.kv_set("autonomy:last", str(now))
            self.store.log_action("autonomy", act, detail)
            if act == "avatar":
                try:
                    self.store.kv_set("self:avatar_desc", detail or "二次元风格头像")
                except Exception:
                    pass
        return {"ok": ok, "act": act, "detail": detail or ("成功" if ok else "执行失败")}

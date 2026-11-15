"""SQLite 持久状态：消息、事实、键值、动作、备份、设置。唯一真相来源。"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL, channel TEXT, scene TEXT, peer_id TEXT, sender_id TEXT,
  sender_name TEXT, role TEXT, content TEXT, msg_id TEXT, meta TEXT
);
CREATE INDEX IF NOT EXISTS idx_msg_peer ON messages(peer_id, ts);
CREATE TABLE IF NOT EXISTS facts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT, skey TEXT, svalue TEXT,
  confidence REAL DEFAULT 0.6, status TEXT DEFAULT 'active', locked INTEGER DEFAULT 0,
  source TEXT, ts REAL
);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS actions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, kind TEXT, peer_id TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS emotions(
  peer_id TEXT PRIMARY KEY, js TEXT, updated REAL
);
CREATE TABLE IF NOT EXISTS memes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, pack TEXT, tag TEXT, caption TEXT,
  keywords TEXT, path TEXT UNIQUE, added REAL
);
CREATE TABLE IF NOT EXISTS vecs(
  msg_id INTEGER PRIMARY KEY, peer_id TEXT, v TEXT, content TEXT, ts REAL
);
"""

DEFAULT_SETTINGS = {
    "memory": {"enabled": True, "retrieve": 4, "use_facts": True, "use_profile": True, "use_summary": True, "use_rag": True},
    "vision": {"enabled": True},
    "emoji": {"enabled": True, "prob": 0.18},
    "voice": {"enabled": True, "voice": "zh-CN-XiaoxiaoNeural"},
    "proactive": {"enabled": True, "quiet_start": "22:30", "quiet_end": "08:00", "min_idle_h": 2},
    "reply": {"max_tokens": 240, "history": 8, "reasoning": "high", "bubble_len": 28},
    "rate": {"qpm": 20},
    "emotion": {"enabled": True, "use_llm": False, "decay_per_hour": 3.0,
                "baseline_affinity": 50.0, "baseline_p": 0.6, "baseline_a": 0.35, "baseline_d": 0.6},
    "moderation": {"enabled": True, "words": "傻逼,操你,去死,滚蛋,妈的,煞笔,贱", "action": "skip"},
    "autonomy": {"enabled": True, "allow_like": True, "allow_qzone_post": False,
                 "allow_nickname": False, "allow_avatar": False, "min_interval_hours": 6},
    "humanize": {"enabled": True, "read_min_ms": 600, "read_max_ms": 1600, "per_char_ms": 35,
                 "bubble_gap_min_ms": 500, "bubble_gap_max_ms": 1400},
    "web": {"enabled": True, "max_results": 5, "allow_image": True},
    "security": {"persona_lock": True, "block_jailbreak": True},
}


def _deep_merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Store:
    def __init__(self, path: str):
        d = os.path.dirname(path)
        self.path = path
        if d:
            os.makedirs(d, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def add_message(self, *, channel, scene, peer_id, sender_id, sender_name,
                    role, content, msg_id="", meta=None) -> int:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO messages(ts,channel,scene,peer_id,sender_id,sender_name,role,content,msg_id,meta) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (time.time(), channel, scene, peer_id, sender_id, sender_name,
                 role, content, msg_id, json.dumps(meta or {}, ensure_ascii=False)),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def history(self, peer_id: str, limit: int = 16) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT role,content FROM messages WHERE peer_id=? ORDER BY id DESC LIMIT ?",
                (peer_id, limit),
            ).fetchall()
        return [{"role": r, "content": c} for r, c in reversed(rows)]

    def search(self, peer_id: str, query: str, limit: int = 4) -> list[str]:
        kws = [w for w in re.split(r"\W+", query or "") if len(w) >= 2][:6]
        if not kws:
            return []
        like = " OR ".join(["content LIKE ?"] * len(kws))
        args = [f"%{w}%" for w in kws] + [peer_id, limit]
        with self._lock:
            rows = self.conn.execute(
                f"SELECT content FROM messages WHERE ({like}) AND peer_id=? AND role='user' "
                "ORDER BY id DESC LIMIT ?", args,
            ).fetchall()
        return [r[0] for r in rows if r[0]]

    def kv_get(self, k: str, default=None):
        with self._lock:
            r = self.conn.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return r[0] if r else default

    def kv_set(self, k: str, v) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v))
            )
            self.conn.commit()

    def recent_peers(self, days: int = 3) -> list[dict]:
        cut = time.time() - days * 86400
        with self._lock:
            rows = self.conn.execute(
                "SELECT peer_id, MAX(ts) t FROM messages WHERE ts>? GROUP BY peer_id ORDER BY t DESC", (cut,)
            ).fetchall()
        return [{"peer_id": p, "last": t} for p, t in rows]

    def recent_messages(self, limit: int = 30) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT ts,scene,peer_id,role,content FROM messages ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{"ts": ts, "scene": s, "peer": p, "role": r, "content": c} for ts, s, p, r, c in reversed(rows)]

    def stats(self) -> dict:
        day_start = int(time.time() // 86400) * 86400
        with self._lock:
            total = self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            today = self.conn.execute("SELECT COUNT(*) FROM messages WHERE ts>=?", (day_start,)).fetchone()[0]
            peers = self.conn.execute("SELECT COUNT(DISTINCT peer_id) FROM messages").fetchone()[0]
            facts = self.conn.execute("SELECT COUNT(*) FROM facts WHERE status='active'").fetchone()[0]
            actions = self.conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
        return {"messages": total, "today": today, "peers": peers, "facts": facts, "actions": actions}

    def log_action(self, kind: str, peer_id: str, detail: str = "") -> None:
        with self._lock:
            self.conn.execute("INSERT INTO actions(ts,kind,peer_id,detail) VALUES(?,?,?,?)",
                              (time.time(), kind, peer_id, detail))
            self.conn.commit()

    def add_fact(self, subject: str, skey: str, svalue: str, confidence: float = 0.7, source: str = "auto") -> None:
        svalue = (svalue or "").strip()
        if not svalue:
            return
        with self._lock:
            row = self.conn.execute(
                "SELECT id, locked FROM facts WHERE subject=? AND skey=? AND status='active'", (subject, skey)
            ).fetchone()
            if row:
                if row[1]:
                    return
                self.conn.execute("UPDATE facts SET svalue=?,confidence=?,ts=? WHERE id=?",
                                  (svalue, confidence, time.time(), row[0]))
            else:
                self.conn.execute(
                    "INSERT INTO facts(subject,skey,svalue,confidence,status,locked,source,ts) "
                    "VALUES(?,?,?,?,'active',0,?,?)", (subject, skey, svalue, confidence, source, time.time()))
            self.conn.commit()

    def facts_for(self, subject: str, limit: int = 10) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT skey,svalue FROM facts WHERE subject=? AND status='active' ORDER BY id DESC LIMIT ?",
                (subject, limit)).fetchall()
        return [{"k": k, "v": v} for k, v in rows]

    def all_facts(self, limit: int = 200) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT id,subject,skey,svalue,confidence,locked FROM facts WHERE status='active' ORDER BY id DESC LIMIT ?",
                (limit,)).fetchall()
        return [{"id": i, "peer": s, "k": k, "v": v, "conf": cf, "locked": bool(l)} for i, s, k, v, cf, l in rows]

    def fact_delete(self, fid: int) -> None:
        with self._lock:
            self.conn.execute("UPDATE facts SET status='deleted' WHERE id=?", (fid,))
            self.conn.commit()

    def fact_set_locked(self, fid: int, locked: bool) -> None:
        with self._lock:
            self.conn.execute("UPDATE facts SET locked=? WHERE id=?", (1 if locked else 0, fid))
            self.conn.commit()

    def peers_with_stats(self) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT peer_id, COUNT(*) c, MAX(ts) t, MAX(scene) FROM messages GROUP BY peer_id ORDER BY t DESC"
            ).fetchall()
        return [{"peer_id": p, "count": c, "last": t, "scene": s} for p, c, t, s in rows]

    def messages_for_peer(self, peer_id: str, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT ts,role,sender_name,content FROM messages WHERE peer_id=? ORDER BY id DESC LIMIT ?",
                (peer_id, limit)).fetchall()
        return [{"ts": t, "role": r, "name": n, "content": c} for t, r, n, c in reversed(rows)]

    def actions_recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT ts,kind,peer_id,detail FROM actions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"ts": t, "kind": k, "peer": p, "detail": d} for t, k, p, d in rows]

    def stats_by_day(self, days: int = 7) -> list[dict]:
        now = int(time.time() // 86400) * 86400
        out = []
        with self._lock:
            for i in range(days - 1, -1, -1):
                start = now - i * 86400
                c = self.conn.execute("SELECT COUNT(*) FROM messages WHERE ts>=? AND ts<?", (start, start + 86400)).fetchone()[0]
                out.append({"day": time.strftime("%m-%d", time.localtime(start)), "count": c})
        return out

    def scene_stats(self) -> dict:
        with self._lock:
            rows = self.conn.execute("SELECT scene,COUNT(*) FROM messages GROUP BY scene").fetchall()
        return {s: c for s, c in rows}

    def kv_list_get(self, k: str) -> list:
        v = self.kv_get(k)
        if not v:
            return []
        try:
            return json.loads(v)
        except Exception:
            return []

    def kv_list_set(self, k: str, arr: list) -> None:
        self.kv_set(k, json.dumps(arr, ensure_ascii=False))

    def delete_peer(self, peer: str) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM messages WHERE peer_id=?", (peer,))
            self.conn.commit()

    def backup(self, backup_dir: str) -> str:
        os.makedirs(backup_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        dst = os.path.join(backup_dir, f"qqbot-{ts}.db")
        with self._lock:
            try:
                self.conn.execute("PRAGMA wal_checkpoint(FULL)")
            except Exception:
                pass
            dest = sqlite3.connect(dst)
            self.conn.backup(dest)
            dest.close()
        return dst

    def list_backups(self, backup_dir: str) -> list[dict]:
        import glob as _g
        rows = []
        for p in sorted(_g.glob(os.path.join(backup_dir, "qqbot-*.db")), reverse=True)[:50]:
            try:
                rows.append({"name": os.path.basename(p), "size_kb": int(os.path.getsize(p) / 1024)})
            except Exception:
                pass
        return rows

    # ---- 设置（模块功能参数，实时生效）----
    def get_settings(self) -> dict:
        raw = self.kv_get("settings_json")
        try:
            cur = json.loads(raw) if raw else {}
        except Exception:
            cur = {}
        return _deep_merge(DEFAULT_SETTINGS, cur)

    def set_settings(self, patch: dict) -> dict:
        merged = _deep_merge(self.get_settings(), patch or {})
        self.kv_set("settings_json", json.dumps(merged, ensure_ascii=False))
        return merged

    # ---- 情绪状态存储（PAD + 好感 + 精力）----
    def emotion_get_raw(self, peer_id: str):
        with self._lock:
            r = self.conn.execute("SELECT js FROM emotions WHERE peer_id=?", (peer_id,)).fetchone()
        if not r:
            return None
        try:
            return json.loads(r[0])
        except Exception:
            return None

    def emotion_save(self, peer_id: str, state: dict) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO emotions(peer_id,js,updated) VALUES(?,?,?) "
                "ON CONFLICT(peer_id) DO UPDATE SET js=excluded.js, updated=excluded.updated",
                (peer_id, json.dumps(state, ensure_ascii=False), time.time()))
            self.conn.commit()

    def emotion_all_raw(self) -> list[dict]:
        with self._lock:
            rows = self.conn.execute("SELECT peer_id,js FROM emotions ORDER BY updated DESC").fetchall()
        out = []
        for p, js in rows:
            try:
                st = json.loads(js)
                st["peer_id"] = p
                out.append(st)
            except Exception:
                pass
        return out

    # ---- 表情包图库 ----
    def meme_upsert(self, pack, tag, caption, keywords, path):
        with self._lock:
            self.conn.execute(
                "INSERT INTO memes(pack,tag,caption,keywords,path,added) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(path) DO UPDATE SET pack=excluded.pack, tag=excluded.tag, "
                "caption=excluded.caption, keywords=excluded.keywords",
                (pack, tag, caption, keywords, path, time.time()))
            self.conn.commit()

    def meme_list(self, pack=None, tag=None, q=None, limit=300):
        sql = "SELECT id,pack,tag,caption,keywords,path FROM memes WHERE 1=1"
        args = []
        if pack:
            sql += " AND pack=?"; args.append(pack)
        if tag:
            sql += " AND tag=?"; args.append(tag)
        if q:
            sql += " AND (caption LIKE ? OR keywords LIKE ? OR tag LIKE ?)"
            args += [f"%{q}%", f"%{q}%", f"%{q}%"]
        sql += " ORDER BY id DESC LIMIT ?"; args.append(limit)
        with self._lock:
            rows = self.conn.execute(sql, args).fetchall()
        return [{"id": i, "pack": p, "tag": t, "caption": c, "keywords": k, "path": path}
                for i, p, t, c, k, path in rows]

    def meme_pick(self, tag=None):
        with self._lock:
            if tag:
                r = self.conn.execute("SELECT path FROM memes WHERE tag=? ORDER BY RANDOM() LIMIT 1", (tag,)).fetchone()
                if r:
                    return r[0]
            r = self.conn.execute("SELECT path FROM memes ORDER BY RANDOM() LIMIT 1").fetchone()
        return r[0] if r else None

    def meme_get(self, mid):
        with self._lock:
            r = self.conn.execute("SELECT id,pack,tag,caption,keywords,path FROM memes WHERE id=?", (mid,)).fetchone()
        return {"id": r[0], "pack": r[1], "tag": r[2], "caption": r[3], "keywords": r[4], "path": r[5]} if r else None

    def meme_delete(self, mid):
        with self._lock:
            r = self.conn.execute("SELECT path FROM memes WHERE id=?", (mid,)).fetchone()
            self.conn.execute("DELETE FROM memes WHERE id=?", (mid,))
            self.conn.commit()
        try:
            if r and os.path.exists(r[0]):
                os.remove(r[0])
        except Exception:
            pass

    def meme_update(self, mid, tag=None, caption=None, keywords=None):
        with self._lock:
            if tag is not None:
                self.conn.execute("UPDATE memes SET tag=? WHERE id=?", (tag, mid))
            if caption is not None:
                self.conn.execute("UPDATE memes SET caption=? WHERE id=?", (caption, mid))
            if keywords is not None:
                self.conn.execute("UPDATE memes SET keywords=? WHERE id=?", (keywords, mid))
            self.conn.commit()

    def meme_count(self):
        with self._lock:
            return self.conn.execute("SELECT COUNT(*) FROM memes").fetchone()[0]

    # ---- 长期记忆：滚动摘要 ----
    def summary_get(self, peer_id: str):
        v = self.kv_get("summary:" + peer_id)
        if not v:
            return None
        try:
            return json.loads(v)
        except Exception:
            return None

    def summary_set(self, peer_id: str, summary: str, last_msg_id: int) -> None:
        self.kv_set("summary:" + peer_id, json.dumps({"summary": summary, "last_msg_id": int(last_msg_id)}, ensure_ascii=False))

    def messages_since(self, peer_id: str, after_id: int, limit: int = 80) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT id,role,content FROM messages WHERE peer_id=? AND id>? ORDER BY id ASC LIMIT ?",
                (peer_id, int(after_id), limit)).fetchall()
        return [{"id": i, "role": r, "content": c} for i, r, c in rows]

    # ---- 向量检索（RAG）----
    def vec_upsert(self, msg_id: int, peer_id: str, v: str, content: str, ts: float) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO vecs(msg_id,peer_id,v,content,ts) VALUES(?,?,?,?,?) "
                "ON CONFLICT(msg_id) DO UPDATE SET v=excluded.v, content=excluded.content",
                (msg_id, peer_id, v, content, ts))
            self.conn.commit()

    def vec_for_peer(self, peer_id: str, limit: int = 500) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT v,content FROM vecs WHERE peer_id=? ORDER BY ts DESC LIMIT ?", (peer_id, limit)).fetchall()
        return [{"v": v, "content": c} for v, c in rows]

    def messages_missing_vec(self, limit: int = 800) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT m.id,m.peer_id,m.content FROM messages m LEFT JOIN vecs v ON v.msg_id=m.id "
                "WHERE v.msg_id IS NULL AND m.content<>'' ORDER BY m.id ASC LIMIT ?", (limit,)).fetchall()
        return [{"id": i, "peer_id": p, "content": c} for i, p, c in rows]

"""SQLite 持久状态：消息、事实、键值、动作日志。唯一真相来源。"""
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
"""


class Store:
    def __init__(self, path: str):
        d = os.path.dirname(path)
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
                "ORDER BY id DESC LIMIT ?",
                args,
            ).fetchall()
        return [r[0] for r in rows if r[0]]

    def kv_get(self, k: str, default=None):
        with self._lock:
            r = self.conn.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return r[0] if r else default

    def kv_set(self, k: str, v) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                (k, str(v)),
            )
            self.conn.commit()

    def recent_peers(self, days: int = 3) -> list[dict]:
        cut = time.time() - days * 86400
        with self._lock:
            rows = self.conn.execute(
                "SELECT peer_id, MAX(ts) t FROM messages WHERE ts>? GROUP BY peer_id ORDER BY t DESC",
                (cut,),
            ).fetchall()
        return [{"peer_id": p, "last": t} for p, t in rows]

    def recent_messages(self, limit: int = 30) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT ts,scene,peer_id,role,content FROM messages ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [{"ts": ts, "scene": s, "peer": p, "role": r, "content": c}
                for ts, s, p, r, c in reversed(rows)]

    def stats(self) -> dict:
        day_start = int(time.time() // 86400) * 86400
        with self._lock:
            total = self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            today = self.conn.execute(
                "SELECT COUNT(*) FROM messages WHERE ts>=?", (day_start,)
            ).fetchone()[0]
            peers = self.conn.execute("SELECT COUNT(DISTINCT peer_id) FROM messages").fetchone()[0]
            facts = self.conn.execute("SELECT COUNT(*) FROM facts WHERE status='active'").fetchone()[0]
            actions = self.conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
        return {"messages": total, "today": today, "peers": peers, "facts": facts, "actions": actions}

    def log_action(self, kind: str, peer_id: str, detail: str = "") -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO actions(ts,kind,peer_id,detail) VALUES(?,?,?,?)",
                (time.time(), kind, peer_id, detail),
            )
            self.conn.commit()

    def add_fact(self, subject: str, skey: str, svalue: str, confidence: float = 0.7, source: str = "auto") -> None:
        svalue = (svalue or "").strip()
        if not svalue:
            return
        with self._lock:
            row = self.conn.execute(
                "SELECT id, locked FROM facts WHERE subject=? AND skey=? AND status='active'",
                (subject, skey),
            ).fetchone()
            if row:
                if row[1]:
                    return
                self.conn.execute(
                    "UPDATE facts SET svalue=?,confidence=?,ts=? WHERE id=?",
                    (svalue, confidence, time.time(), row[0]),
                )
            else:
                self.conn.execute(
                    "INSERT INTO facts(subject,skey,svalue,confidence,status,locked,source,ts) "
                    "VALUES(?,?,?,?,'active',0,?,?)",
                    (subject, skey, svalue, confidence, source, time.time()),
                )
            self.conn.commit()

    def facts_for(self, subject: str, limit: int = 10) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT skey,svalue FROM facts WHERE subject=? AND status='active' ORDER BY id DESC LIMIT ?",
                (subject, limit),
            ).fetchall()
        return [{"k": k, "v": v} for k, v in rows]

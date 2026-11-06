"""
memory.py — persistent per-user memory for the assistant.

Three tables:
  messages — rolling conversation history per user (for short-term context)
  facts    — durable facts learned about a user (for long-term memory)
  actions  — a log of actions the assistant has taken (alarms, reminders, etc.)

This is intentionally simple (SQLite, no vector search) so it runs anywhere
with zero setup. Swap in Postgres + pgvector later if you want semantic
recall over long histories instead of just "most recent N messages".
"""

import sqlite3
import json
import time
import threading


class MemoryStore:
    def __init__(self, path: str = "memory.db"):
        self.path = path
        self.lock = threading.Lock()
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self.path)

    def _init_db(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    user_id TEXT, role TEXT, content TEXT, ts REAL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    user_id TEXT, fact TEXT, ts REAL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS actions (
                    user_id TEXT, type TEXT, data TEXT, ts REAL
                )
            """)

    # ---- conversation history ----
    def add_message(self, user_id: str, role: str, content: str):
        with self.lock, self._conn() as c:
            c.execute(
                "INSERT INTO messages VALUES (?,?,?,?)",
                (user_id, role, content, time.time()),
            )

    def get_recent_messages(self, user_id: str, limit: int = 20):
        with self._conn() as c:
            rows = c.execute(
                "SELECT role, content FROM messages WHERE user_id=? "
                "ORDER BY ts DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        rows.reverse()
        return [{"role": r, "content": ct} for r, ct in rows]

    # ---- long-term facts ----
    def add_fact(self, user_id: str, fact: str):
        with self.lock, self._conn() as c:
            c.execute(
                "INSERT INTO facts VALUES (?,?,?)", (user_id, fact, time.time())
            )

    def get_facts(self, user_id: str) -> str:
        with self._conn() as c:
            rows = c.execute(
                "SELECT fact FROM facts WHERE user_id=?", (user_id,)
            ).fetchall()
        return "\n".join(r[0] for r in rows) if rows else "(nothing known yet)"

    # ---- action log ----
    def add_action(self, user_id: str, type_: str, data: dict):
        with self.lock, self._conn() as c:
            c.execute(
                "INSERT INTO actions VALUES (?,?,?,?)",
                (user_id, type_, json.dumps(data), time.time()),
            )

    def get_recent_actions(self, user_id: str, limit: int = 10):
        with self._conn() as c:
            rows = c.execute(
                "SELECT type, data, ts FROM actions WHERE user_id=? "
                "ORDER BY ts DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [
            {"type": t, "data": json.loads(d), "ts": ts} for t, d, ts in rows
        ]

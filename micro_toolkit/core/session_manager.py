from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class SessionManager:
    """Tracks tool execution history in the application database."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    details TEXT
                )
                """
            )

    def log_run(self, tool_id: str, status: str, details: str = "") -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO sessions (tool_id, status, timestamp, details) VALUES (?, ?, ?, ?)",
                    (tool_id, status, time.time(), details),
                )
        except Exception as exc:
            print(f"Database logging failed: {exc}")

    def get_history(self, limit: int = 50):
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "SELECT id, tool_id, status, timestamp, details FROM sessions ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                )
                return cursor.fetchall()
        except Exception:
            return []

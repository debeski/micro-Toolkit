from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ClipboardEntry:
    entry_id: int
    content: str
    content_type: str
    label: str
    created_at: str


URL_PREFIXES = ("http://", "https://")


def detect_content_type(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped:
        return "text"
    if stripped.startswith(URL_PREFIXES):
        return "url"
    if "\t" in stripped and stripped.count("\t") >= 2:
        return "table"
    if stripped.startswith("<") and ("</html>" in stripped.lower() or "</div>" in stripped.lower()):
        return "rich_text"
    if any(token in stripped for token in ("def ", "class ", "import ", "const ", "let ", "=>", "{", "}")):
        return "code"
    if stripped.startswith("/") or stripped.startswith("\\") or ":/" in stripped or ":\\" in stripped:
        return "file_path"
    return "text"


class ClipboardStore:
    def __init__(self, db_path: Path, max_history: int = 400):
        self.db_path = Path(db_path)
        self.max_history = max_history
        self._init_db()

    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS clipboard_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    content_hash TEXT UNIQUE NOT NULL,
                    content_type TEXT NOT NULL DEFAULT 'text',
                    label TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS clipboard_labels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                )
                """
            )

    def add_entry(self, content: str, content_type: str | None = None) -> bool:
        normalized = (content or "").strip()
        if not normalized:
            return False
        entry_type = content_type or detect_content_type(normalized)
        content_hash = hashlib.md5(normalized.encode("utf-8", errors="replace")).hexdigest()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO clipboard_entries (content, content_hash, content_type)
                VALUES (?, ?, ?)
                """,
                (normalized, content_hash, entry_type),
            )
            inserted = cursor.rowcount > 0
            if inserted:
                self._trim_history(connection)
            return inserted

    def _trim_history(self, connection: sqlite3.Connection) -> None:
        count = connection.execute("SELECT COUNT(*) FROM clipboard_entries").fetchone()[0]
        overflow = count - self.max_history
        if overflow > 0:
            connection.execute(
                """
                DELETE FROM clipboard_entries
                WHERE id IN (
                    SELECT id FROM clipboard_entries
                    ORDER BY id ASC
                    LIMIT ?
                )
                """,
                (overflow,),
            )

    def list_entries(self, *, search: str = "", content_type: str = "ALL", label: str = "") -> list[ClipboardEntry]:
        query = "SELECT id, content, content_type, label, created_at FROM clipboard_entries"
        conditions = []
        params = []
        if content_type and content_type != "ALL":
            conditions.append("content_type = ?")
            params.append(content_type)
        if label:
            conditions.append("label = ?")
            params.append(label)
        if search:
            conditions.append("content LIKE ?")
            params.append(f"%{search}%")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id DESC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            ClipboardEntry(
                entry_id=row["id"],
                content=row["content"],
                content_type=row["content_type"],
                label=row["label"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def update_label(self, entry_id: int, label: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE clipboard_entries SET label = ? WHERE id = ?",
                (label.strip(), entry_id),
            )

    def delete_entry(self, entry_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM clipboard_entries WHERE id = ?", (entry_id,))

    def clear_entries(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM clipboard_entries")

    def list_labels(self) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute("SELECT name FROM clipboard_labels ORDER BY name").fetchall()
        return [row["name"] for row in rows]

    def add_label(self, label: str) -> None:
        normalized = label.strip()
        if not normalized:
            return
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO clipboard_labels (name) VALUES (?)",
                (normalized,),
            )

    def delete_label(self, label: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM clipboard_labels WHERE name = ?", (label,))
            connection.execute("UPDATE clipboard_entries SET label = '' WHERE label = ?", (label,))

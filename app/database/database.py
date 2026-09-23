from __future__ import annotations

import sqlite3
from pathlib import Path


class VaultDatabase:
    def __init__(self, vault_path: str | Path) -> None:
        self.vault_path = Path(vault_path)
        self.db_path = self.vault_path / ".knowledge_vault.db"
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE,
                    title TEXT,
                    content TEXT,
                    modified_time REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS links (
                    source_path TEXT,
                    target_path TEXT,
                    target_title TEXT,
                    resolved INTEGER DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tags (
                    path TEXT,
                    tag TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_notes_path ON notes(path)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_links_source ON links(source_path)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tags_path ON tags(path)")

            try:
                conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(path, title, content, tags, tokenize='porter unicode61')"
                )
            except sqlite3.DatabaseError:
                pass

            conn.commit()

    def rebuild(self, notes: list[dict[str, object]]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM notes")
            conn.execute("DELETE FROM links")
            conn.execute("DELETE FROM tags")
            try:
                conn.execute("DELETE FROM notes_fts")
            except sqlite3.DatabaseError:
                pass
            for note in notes:
                conn.execute(
                    "INSERT INTO notes(path, title, content, modified_time) VALUES (?, ?, ?, ?)",
                    (
                        note["path"],
                        note["title"],
                        note["content"],
                        note["modified_time"],
                    ),
                )
                try:
                    conn.execute(
                        "INSERT INTO notes_fts(path, title, content, tags) VALUES (?, ?, ?, ?)",
                        (
                            note["path"],
                            note["title"],
                            note["content"],
                            ", ".join(note.get("tags", [])),
                        ),
                    )
                except sqlite3.DatabaseError:
                    pass
                for tag in note.get("tags", []):
                    conn.execute("INSERT INTO tags(path, tag) VALUES (?, ?)", (note["path"], tag))
                for link in note.get("links", []):
                    conn.execute(
                        "INSERT INTO links(source_path, target_path, target_title, resolved) VALUES (?, ?, ?, ?)",
                        (note["path"], link["target_path"], link["target_title"], 1 if link["resolved"] else 0),
                    )
            conn.commit()

    def search(self, query: str) -> list[dict[str, str]]:
        with sqlite3.connect(self.db_path) as conn:
            if query.strip():
                try:
                    rows = conn.execute(
                        "SELECT path, title, content FROM notes_fts WHERE notes_fts MATCH ? ORDER BY rank",
                        (query,),
                    ).fetchall()
                    if rows:
                        return [
                            {"path": path, "title": title, "snippet": content[:160]}
                            for path, title, content in rows
                        ]
                except sqlite3.DatabaseError:
                    pass

            rows = conn.execute(
                "SELECT path, title, content FROM notes WHERE lower(title) LIKE ? OR lower(content) LIKE ? ORDER BY title",
                (f"%{query.lower()}%", f"%{query.lower()}%"),
            ).fetchall()
            return [{"path": path, "title": title, "snippet": content[:160]} for path, title, content in rows]

    def count_notes(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]

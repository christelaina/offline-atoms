from __future__ import annotations

import sqlite3
from pathlib import Path

from rapidfuzz import process


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

    def search(
        self, query: str, tag: str = "", path: str = ""
    ) -> list[dict[str, str]]:
        filters, filter_values = self._filters(tag, path)
        with sqlite3.connect(self.db_path) as conn:
            if query.strip():
                try:
                    clauses = ["notes_fts MATCH ?", *filters]
                    values = [query, *filter_values]
                    rows = conn.execute(
                        "SELECT notes.path, notes.title, notes.content "
                        "FROM notes_fts JOIN notes ON notes.path = notes_fts.path "
                        f"WHERE {' AND '.join(clauses)} ORDER BY rank",
                        values,
                    ).fetchall()
                    if rows:
                        return [
                            {"path": path, "title": title, "snippet": content[:160]}
                            for path, title, content in rows
                        ]
                except sqlite3.DatabaseError:
                    pass

            clauses = list(filters)
            values = list(filter_values)
            if query.strip():
                clauses.append(
                    "(lower(notes.title) LIKE ? OR lower(notes.content) LIKE ? "
                    "OR EXISTS (SELECT 1 FROM tags AS query_tags "
                    "WHERE query_tags.path = notes.path AND lower(query_tags.tag) LIKE ?))"
                )
                query_pattern = f"%{query.lower()}%"
                values.extend((query_pattern, query_pattern, query_pattern))
            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = conn.execute(
                f"SELECT notes.path, notes.title, notes.content FROM notes{where} ORDER BY title",
                values,
            ).fetchall()
            return [{"path": path, "title": title, "snippet": content[:160]} for path, title, content in rows]

    def suggest(
        self, query: str, limit: int = 10, tag: str = "", path: str = ""
    ) -> list[dict[str, str]]:
        filters, filter_values = self._filters(tag, path)
        where = f" WHERE {' AND '.join(filters)}" if filters else ""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT notes.path, notes.title, notes.content FROM notes" + where,
                filter_values,
            ).fetchall()

        records = [
            {"path": note_path, "title": title, "snippet": content[:160]}
            for note_path, title, content in rows
        ]
        if not query.strip():
            return sorted(records, key=lambda record: record["title"].lower())[:limit]
        if not records:
            return []
        matches = process.extract(
            query, [record["title"] for record in records], limit=limit
        )
        return [records[index] for _, _, index in matches]

    @staticmethod
    def _filters(tag: str, path: str) -> tuple[list[str], list[str]]:
        clauses: list[str] = []
        values: list[str] = []
        if tag:
            clauses.append(
                "EXISTS (SELECT 1 FROM tags AS filter_tags "
                "WHERE filter_tags.path = notes.path AND lower(filter_tags.tag) = lower(?))"
            )
            values.append(tag)
        if path:
            normalized_path = path.strip("/").replace("\\", "/")
            clauses.append(
                "(notes.path = ? OR substr(notes.path, 1, length(?) + 1) = ? || '/')"
            )
            values.extend((normalized_path, normalized_path, normalized_path))
        return clauses, values

    def count_notes(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]

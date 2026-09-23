from __future__ import annotations

import sqlite3
from pathlib import Path

from rapidfuzz import process

from app.core.markdown import extract_tags
from app.core.vault import Vault


def _sqlite_available() -> bool:
    try:
        with sqlite3.connect(":memory:") as conn:
            conn.execute("SELECT 1 FROM sqlite_master")
        return True
    except Exception:
        return False


def _search_sqlite(vault_path: str | Path, query: str) -> list[dict[str, str]]:
    vault = Vault(vault_path)
    vault.refresh()
    if not query.strip():
        return [{"path": key, "title": note.title, "snippet": note.content[:120]} for key, note in sorted(vault.notes.items())]

    lowered = query.lower()
    matches: list[dict[str, str]] = []
    for relative_path, note in vault.notes.items():
        haystack = " ".join([
            note.title,
            note.content,
            " ".join(note.headings),
            " ".join(note.tags),
            " ".join(note.wikilinks),
        ]).lower()
        if lowered in haystack:
            snippet = note.content[:160].replace("\n", " ").strip()
            matches.append({"path": relative_path, "title": note.title, "snippet": snippet})
    return matches


def search_notes(vault_path: str | Path, query: str) -> list[dict[str, str]]:
    return _search_sqlite(vault_path, query)


def fuzzy_note_suggestions(vault_path: str | Path, query: str, limit: int = 10) -> list[str]:
    vault = Vault(vault_path)
    vault.refresh()
    if not query.strip():
        return [note.title for note in sorted(vault.notes.values(), key=lambda n: n.title)]

    choices = [note.title for note in vault.notes.values()]
    if not choices:
        return []
    results = process.extract(query, choices, limit=limit)
    return [title for title, _, _ in results]

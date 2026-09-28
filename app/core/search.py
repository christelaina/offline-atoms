from __future__ import annotations

from pathlib import Path

from app.core.vault import Vault
from app.database.database import VaultDatabase


def refresh_search_index(
    vault_path: str | Path, vault: Vault | None = None
) -> VaultDatabase:
    if vault is None:
        vault = Vault(vault_path)
        vault.refresh()

    records: list[dict[str, object]] = []
    for relative_path, note in vault.notes.items():
        try:
            modified_time = note.path.stat().st_mtime
        except OSError:
            modified_time = 0.0
        records.append(
            {
                "path": relative_path,
                "title": note.title,
                "content": note.content,
                "modified_time": modified_time,
                "tags": note.tags,
                "links": [
                    {
                        "target_path": target,
                        "target_title": Path(target).stem,
                        "resolved": True,
                    }
                    for target in note.outgoing_links
                ],
            }
        )

    database = VaultDatabase(vault_path)
    database.rebuild(records)
    return database


def _database_for_vault(vault_path: str | Path) -> VaultDatabase:
    database = VaultDatabase(vault_path)
    if database.count_notes() == 0:
        vault = Vault(vault_path)
        vault.refresh()
        if vault.notes:
            database = refresh_search_index(vault_path, vault)
    return database


def search_notes(
    vault_path: str | Path,
    query: str,
    tag: str = "",
    path: str = "",
) -> list[dict[str, str]]:
    database = _database_for_vault(vault_path)
    return database.search(query, tag=tag, path=path)


def fuzzy_note_results(
    vault_path: str | Path,
    query: str,
    limit: int = 10,
    tag: str = "",
    path: str = "",
) -> list[dict[str, str]]:
    database = _database_for_vault(vault_path)
    return database.suggest(query, limit=limit, tag=tag, path=path)


def fuzzy_note_suggestions(
    vault_path: str | Path, query: str, limit: int = 10
) -> list[str]:
    return [
        result["title"]
        for result in fuzzy_note_results(vault_path, query, limit=limit)
    ]

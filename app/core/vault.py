from __future__ import annotations

from pathlib import Path

from app.core.markdown import read_note
from app.models.note import Note


class Vault:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.notes: dict[str, Note] = {}

    def refresh(self) -> None:
        self.notes = {}
        if not self.path.exists():
            return
        for file_path in sorted(self.path.rglob("*.md")):
            if file_path.is_file():
                note = self._load_note(file_path)
                self.notes[str(file_path.relative_to(self.path).as_posix())] = note

    def _load_note(self, file_path: Path) -> Note:
        title, frontmatter, body, headings, tags, wikilinks = read_note(file_path)
        return Note(
            path=file_path,
            title=title,
            content=body,
            headings=headings,
            tags=tags,
            wikilinks=wikilinks,
            frontmatter=frontmatter,
        )

    def get_note_by_relative_path(self, relative_path: str) -> Note | None:
        return self.notes.get(relative_path)

    def get_all_titles(self) -> list[str]:
        return [note.title for note in self.notes.values()]

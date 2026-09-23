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
        self._rebuild_links()

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

    def _rebuild_links(self) -> None:
        for note in self.notes.values():
            note.outgoing_links = []
            note.backlinks = []
            note.unresolved_links = []

        for relative_path, note in self.notes.items():
            for target in note.wikilinks:
                resolved = self.resolve_reference(target)
                if resolved is None:
                    note.unresolved_links.append(target)
                    continue
                note.outgoing_links.append(resolved)

                source_note = self.notes.get(relative_path)
                if source_note is not None:
                    target_note = self.notes.get(resolved)
                    if target_note is not None:
                        if relative_path not in target_note.backlinks:
                            target_note.backlinks.append(relative_path)

    def resolve_reference(self, link: str) -> str | None:
        target = link.strip()
        if not target:
            return None

        if "#" in target:
            target = target.split("#", 1)[0]

        if not target:
            return None

        normalized_name = target.strip()
        normalized_without_ext = normalized_name[:-3] if normalized_name.lower().endswith(".md") else normalized_name

        exact_candidates = [
            key for key in self.notes if key.lower() == normalized_name.lower() or key.lower() == f"{normalized_name}.md".lower()
        ]
        if exact_candidates:
            return exact_candidates[0]

        stem_matches = [
            key for key in self.notes if key.lower().removesuffix(".md") == normalized_without_ext.lower()
        ]
        if stem_matches:
            return stem_matches[0]

        for key in self.notes:
            if key.lower().removesuffix(".md") == normalized_without_ext.lower().replace(" ", "-"):
                return key

        for key in self.notes:
            if normalized_without_ext.lower() in key.lower().removesuffix(".md"):
                return key

        return None

    def get_note_by_relative_path(self, relative_path: str) -> Note | None:
        return self.notes.get(relative_path)

    def get_all_titles(self) -> list[str]:
        return [note.title for note in self.notes.values()]

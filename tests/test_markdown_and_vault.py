from __future__ import annotations

from pathlib import Path

from app.core.markdown import extract_frontmatter, extract_tags, extract_title, extract_wikilinks
from app.core.vault import Vault


def test_markdown_extracts_frontmatter_and_tags(tmp_path: Path):
    note = tmp_path / "Note.md"
    note.write_text(
        "---\ntitle: Gradient Descent\ntags:\n  - machine-learning\n---\n\n# Gradient Descent\n\nSee [[Optimization]] and #python\n",
        encoding="utf-8",
    )

    metadata, body = extract_frontmatter(note.read_text(encoding="utf-8"))
    assert metadata["title"] == "Gradient Descent"
    assert "machine-learning" in [tag.strip() for tag in metadata["tags"].splitlines() if tag.strip()]
    assert extract_title(body, "Fallback") == "Gradient Descent"
    assert "python" in extract_tags(body)
    assert "Optimization" in extract_wikilinks(body)


def test_vault_scans_markdown_notes(tmp_path: Path):
    notes_dir = tmp_path / "vault"
    notes_dir.mkdir()
    (notes_dir / "Alpha.md").write_text("# Alpha\n\n[[Beta]]\n", encoding="utf-8")
    (notes_dir / "Beta.md").write_text("# Beta\n\n[[Alpha|Alpha Page]]\n#project\n", encoding="utf-8")

    vault = Vault(notes_dir)
    vault.refresh()

    assert set(vault.notes) == {"Alpha.md", "Beta.md"}
    assert vault.notes["Alpha.md"].wikilinks == ["Beta"]
    assert vault.notes["Beta.md"].tags == ["project"]

from __future__ import annotations

import os
import sys

from PySide6 import QtWidgets

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ui.main_window import MainWindow


def test_note_tree_and_note_opening(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow()
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    (vault_dir / "Alpha.md").write_text("# Alpha\n\nSome content\n", encoding="utf-8")
    (vault_dir / "Beta.md").write_text("# Beta\n\nAnother note\n", encoding="utf-8")

    window._vault_path = vault_dir
    window.vault = __import__("app.core.vault", fromlist=["Vault"]).Vault(vault_dir)
    window.vault.refresh()
    window.populate_note_tree()

    assert window.note_tree.topLevelItem(0).text(0) == "vault"
    assert window.note_tree.topLevelItem(0).childCount() == 2


def test_preview_renders_markdown():
    from app.core.markdown import render_markdown_to_html

    html = render_markdown_to_html("# Title\n\n**bold** and [[Note]]")
    assert "<h1>Title</h1>" in html
    assert "<strong>bold</strong>" in html

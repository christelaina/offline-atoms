from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.markdown import render_markdown_to_html
from app.core.search import fuzzy_note_suggestions, search_notes
from app.core.vault import Vault


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Local Knowledge Vault")
        self.resize(1400, 900)
        self.setStyleSheet(
            """
            QMainWindow {
                background: #121212;
                color: #e6e6e6;
            }
            QWidget {
                background: #121212;
                color: #e6e6e6;
            }
            QSplitter::handle {
                background: #1f1f1f;
                border: 1px solid #2b2b2b;
            }
            QLabel {
                color: #d8d8d8;
            }
            QLineEdit,
            QTextEdit,
            QTextBrowser,
            QListWidget,
            QTreeWidget,
            QPushButton {
                background: #1d1d1d;
                color: #f0f0f0;
                border: 1px solid #2d2d2d;
                border-radius: 8px;
                padding: 6px 8px;
            }
            QLineEdit:focus,
            QTextEdit:focus,
            QTextBrowser:focus,
            QListWidget:focus,
            QTreeWidget:focus {
                border-color: #7b6ee6;
            }
            QPushButton {
                background: #202020;
                border: 1px solid #3a3a3a;
                padding: 7px 12px;
            }
            QPushButton:hover {
                background: #2b2b2b;
            }
            QPushButton:pressed {
                background: #323232;
            }
            QTreeWidget::item,
            QListWidget::item {
                border-radius: 6px;
                padding: 4px 6px;
            }
            QTreeWidget::item:selected,
            QListWidget::item:selected {
                background: rgba(122, 108, 233, 0.28);
                color: #ffffff;
            }
            QTreeWidget::item:hover,
            QListWidget::item:hover {
                background: rgba(255, 255, 255, 0.04);
            }
            QTreeWidget,
            QListWidget {
                border: 1px solid #2a2a2a;
                background: #171717;
            }
            QTextEdit,
            QTextBrowser {
                background: #171717;
                border: 1px solid #2a2a2a;
                selection-background-color: rgba(123, 110, 230, 0.5);
            }
            QHeaderView::section {
                background: #1b1b1b;
                color: #d0d0d0;
                border: 0;
                padding: 6px;
            }
            """
        )

        self._vault_path: Path | None = None
        self.vault: Vault | None = None
        self.current_note_path: Path | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        self.taskbar = QWidget()
        self.taskbar.setFixedWidth(92)
        self.taskbar.setStyleSheet(
            """
            QWidget#taskbar {
                background: #171717;
                border: 1px solid #2a2a2a;
                border-radius: 10px;
            }
            """
        )
        self.taskbar.setObjectName("taskbar")
        taskbar_layout = QVBoxLayout(self.taskbar)
        taskbar_layout.setContentsMargins(8, 12, 8, 12)
        taskbar_layout.setSpacing(10)

        self.select_vault_button = QPushButton("Vault")
        self.select_vault_button.clicked.connect(self.select_vault)
        self.new_note_button = QPushButton("New")
        self.new_note_button.clicked.connect(self.new_note)
        self.toggle_note_tree_button = QPushButton("Notes")
        self.toggle_note_tree_button.clicked.connect(self._toggle_note_tree)
        self.toggle_search_button = QPushButton("Search")
        self.toggle_search_button.clicked.connect(self._toggle_search)
        self.save_note_button = QPushButton("Save")
        self.save_note_button.clicked.connect(self.save_current_note)

        for button in (
            self.select_vault_button,
            self.new_note_button,
            self.toggle_note_tree_button,
            self.toggle_search_button,
            self.save_note_button,
        ):
            button.setStyleSheet(
                """
                QPushButton {
                    background: #202020;
                    border: 1px solid #363636;
                    border-radius: 8px;
                    min-height: 42px;
                    font-size: 11px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: #2a2a2a;
                }
                QPushButton:pressed {
                    background: #323232;
                }
                """
            )
            taskbar_layout.addWidget(button)

        taskbar_layout.addStretch()
        root_layout.addWidget(self.taskbar)

        main_panel = QWidget()
        main_layout = QVBoxLayout(main_panel)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)

        header = QHBoxLayout()
        self.vault_label = QLabel("No vault selected")
        self.vault_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.vault_label.setWordWrap(True)
        header.addWidget(self.vault_label)
        header.addStretch()
        main_layout.addLayout(header)

        self.search_panel = QWidget()
        self.search_layout = QVBoxLayout(self.search_panel)
        self.search_layout.setContentsMargins(0, 0, 0, 0)
        self.search_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search notes or titles...")
        self.search_input.setStyleSheet("QLineEdit { padding: 8px 10px; }")
        self.search_input.textChanged.connect(self.perform_search)

        self.search_results = QListWidget()
        self.search_results.itemClicked.connect(self._on_search_result_clicked)
        self.search_results.setMinimumHeight(160)
        self.search_results.setAlternatingRowColors(False)

        self.suggested_titles: list[str] = []

        self.search_layout.addWidget(self.search_input)
        self.search_layout.addWidget(self.search_results)
        self.search_panel.setVisible(False)
        main_layout.addWidget(self.search_panel)

        splitter = QSplitter(Qt.Horizontal)
        self.note_tree_container = QWidget()
        left_layout = QVBoxLayout(self.note_tree_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.note_tree = QTreeWidget()
        self.note_tree.setHeaderLabel("Notes")
        self.note_tree.itemClicked.connect(self._on_tree_item_clicked)
        left_layout.addWidget(self.note_tree)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Markdown title is derived from # heading")
        self.title_input.setVisible(False)

        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Write a note in Markdown...")
        self.editor.setMinimumHeight(340)
        self.editor.setStyleSheet(
            """
            QTextEdit {
                font-family: Consolas, 'Segoe UI', sans-serif;
                font-size: 13px;
                line-height: 1.6;
                padding: 14px 16px;
            }
            """
        )
        self.editor.textChanged.connect(self._refresh_preview)

        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(False)
        self.preview.anchorClicked.connect(self._on_preview_link_clicked)
        self.preview.setHtml("<p>Preview will appear here.</p>")
        self.preview.setMinimumHeight(220)
        self.preview.setStyleSheet(
            """
            QTextBrowser {
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
                line-height: 1.7;
                padding: 14px 16px;
            }
            QTextBrowser h1 { color: #f3f3f3; font-size: 2em; margin-top: 0; margin-bottom: 14px; }
            QTextBrowser h2 { color: #f3f3f3; font-size: 1.5em; margin-top: 16px; margin-bottom: 10px; }
            QTextBrowser h3 { color: #f3f3f3; font-size: 1.2em; margin-top: 12px; margin-bottom: 8px; }
            QTextBrowser p { margin: 8px 0; color: #e5e5e5; }
            QTextBrowser a { color: #9bb8ff; text-decoration: none; }
            QTextBrowser strong { color: #ffffff; }
            QTextBrowser em { color: #d5d5d5; }
            """
        )

        self.backlinks_list = QListWidget()
        self.backlinks_list.setMinimumHeight(100)
        self.backlinks_list.itemDoubleClicked.connect(self._on_list_item_open)

        self.outgoing_list = QListWidget()
        self.outgoing_list.setMinimumHeight(100)
        self.outgoing_list.itemDoubleClicked.connect(self._on_list_item_open)

        self.backlinks_label = QLabel("Backlinks")
        self.backlinks_label.setStyleSheet("QLabel { color: #a9a9a9; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }")
        self.outgoing_label = QLabel("Outgoing")
        self.outgoing_label.setStyleSheet("QLabel { color: #a9a9a9; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }")

        right_layout.addWidget(self.title_input)
        right_layout.addWidget(self.editor, 2)
        right_layout.addWidget(self.preview, 1)
        right_layout.addWidget(self.backlinks_label)
        right_layout.addWidget(self.backlinks_list)
        right_layout.addWidget(self.outgoing_label)
        right_layout.addWidget(self.outgoing_list)

        splitter.addWidget(self.note_tree_container)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        main_layout.addWidget(splitter)

        self.status_label = QLabel("Phase 4: local search and fuzzy lookup ready")
        main_layout.addWidget(self.status_label)

        root_layout.addWidget(main_panel)
        self._setup_shortcuts()

    def _toggle_note_tree(self) -> None:
        if hasattr(self, "note_tree_container"):
            self.note_tree_container.setVisible(not self.note_tree_container.isVisible())

    def _toggle_search(self) -> None:
        if hasattr(self, "search_panel"):
            self.search_panel.setVisible(not self.search_panel.isVisible())

    def perform_search(self) -> None:
        query = self.search_input.text().strip()
        self.search_results.clear()
        if self.vault is None:
            return

        if not query:
            self.search_results.clear()
            return

        self.suggested_titles = fuzzy_note_suggestions(self.vault.path, query)
        matches = search_notes(self.vault.path, query)

        for result in matches:
            title = result.get("title", "Untitled")
            path = result.get("path", "")
            snippet = result.get("snippet", "")
            item_text = f"{title}\n{path}\n{snippet}"
            self.search_results.addItem(item_text)

        if self.search_results.count() == 0:
            self.search_results.addItem(f"No results for: {query}")

    def _on_search_result_clicked(self, item: QListWidgetItem) -> None:
        text = item.text()
        if not text or text.startswith("No results"):
            return
        lines = text.splitlines()
        if len(lines) < 2:
            return
        path = lines[1].strip()
        if self.vault is not None:
            self._open_note_file(self.vault.path / path)

    def _setup_shortcuts(self) -> None:
        open_vault_action = QAction("Open Vault", self)
        open_vault_action.setShortcut(QKeySequence("Ctrl+O"))
        open_vault_action.triggered.connect(self.select_vault)
        self.addAction(open_vault_action)

        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self.save_current_note)
        self.addAction(save_action)

        new_note_action = QAction("New Note", self)
        new_note_action.setShortcut(QKeySequence("Ctrl+N"))
        new_note_action.triggered.connect(self.new_note)
        self.addAction(new_note_action)

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        relative_path = item.data(0, Qt.UserRole)
        if not relative_path or self.vault is None:
            return
        self._open_note_file(self.vault.path / relative_path)

    def populate_note_tree(self) -> None:
        self.note_tree.clear()
        if self.vault is None:
            return

        root_item = QTreeWidgetItem([self.vault.path.name])
        root_item.setData(0, Qt.UserRole, "")
        self.note_tree.addTopLevelItem(root_item)

        for raw_path in sorted(self.vault.notes.keys()):
            parts = raw_path.split("/")
            current_item = root_item
            for part in parts[:-1]:
                child_match = None
                for index in range(current_item.childCount()):
                    candidate = current_item.child(index)
                    if candidate.text(0) == part:
                        child_match = candidate
                        break
                if child_match is None:
                    child_match = QTreeWidgetItem([part])
                    child_match.setData(0, Qt.UserRole, "")
                    current_item.addChild(child_match)
                current_item = child_match

            file_item = QTreeWidgetItem([parts[-1]])
            file_item.setData(0, Qt.UserRole, raw_path)
            current_item.addChild(file_item)

        self.note_tree.expandAll()

    def _open_note_file(self, file_path: Path) -> None:
        if not file_path.exists():
            QMessageBox.warning(self, "Missing note", f"The note was not found: {file_path}")
            return

        self.current_note_path = file_path
        content = file_path.read_text(encoding="utf-8", errors="replace")
        self.editor.setPlainText(content)
        if self.vault is not None:
            note = self.vault.notes.get(file_path.relative_to(self.vault.path).as_posix())
            if note is not None:
                self.title_input.setText(note.title)
        self._refresh_preview()
        self._refresh_related_lists()
        rel_path = file_path.relative_to(self.vault.path).as_posix() if self.vault else file_path.name
        self.status_label.setText(f"Open note: {rel_path}")

    def _refresh_related_lists(self) -> None:
        if self.vault is None or self.current_note_path is None:
            return

        rel_path = self.current_note_path.relative_to(self.vault.path).as_posix()
        note = self.vault.notes.get(rel_path)
        if note is None:
            return

        self.backlinks_list.clear()
        self.outgoing_list.clear()

        for backlink in note.backlinks:
            self.backlinks_list.addItem(backlink)
        for outgoing in note.outgoing_links:
            self.outgoing_list.addItem(outgoing)

        if self.backlinks_list.count() == 0:
            self.backlinks_list.addItem("No backlinks")
        if self.outgoing_list.count() == 0:
            self.outgoing_list.addItem("No outgoing links")

    def _on_list_item_open(self, item) -> None:
        text = item.text()
        if not text or text.startswith("No "):
            return
        self._open_note_from_reference(text)

    def _on_preview_link_clicked(self, url: QUrl) -> None:
        target = unquote(url.toString())
        self._open_note_from_reference(target)

    def _open_note_from_reference(self, reference: str) -> None:
        if self.vault is None:
            return
        target = reference.strip()
        if not target:
            return
        if "#" in target:
            target = target.split("#", 1)[0]
        resolved = self.vault.resolve_reference(target)
        if resolved is None:
            QMessageBox.information(self, "Missing note", f"No note matches: {target}")
            return
        self._open_note_file(self.vault.path / resolved)

    def _refresh_preview(self) -> None:
        content = self.editor.toPlainText()
        self.preview.setHtml(render_markdown_to_html(content))

    def _rewrite_wikilink_references(self, old_name: str, new_name: str, content: str) -> str:
        pattern = re.compile(r"\[\[([^\]|#]+?)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]")

        def replace(match: re.Match[str]) -> str:
            target = match.group(1).strip()
            heading = match.group(2)
            alias = match.group(3)
            candidate_names = {old_name, f"{old_name}.md", old_name.replace(" ", "-")}
            if target in candidate_names:
                target = new_name
            elif target.endswith(".md") and target[:-3] in candidate_names:
                target = f"{new_name}.md"
            replacement = f"[[{target}"
            if heading:
                replacement += f"#{heading}"
            if alias is not None:
                replacement += f"|{alias}"
            replacement += "]]"
            return replacement

        return pattern.sub(replace, content)

    def _rename_note_file_if_needed(self) -> None:
        if self.current_note_path is None or self.vault is None:
            return

        content = self.editor.toPlainText()
        lines = content.splitlines()
        desired_title = ""
        for line in lines:
            if line.startswith("# "):
                desired_title = line[2:].strip()
                break
        if not desired_title:
            return

        current_name = self.current_note_path.name
        old_note_name = self.current_note_path.stem
        safe_name = f"{desired_title}.md"
        if safe_name == current_name:
            return

        destination = self.current_note_path.with_name(safe_name)
        if destination.exists() and destination != self.current_note_path:
            QMessageBox.warning(self, "Name conflict", f"A note named '{safe_name}' already exists in this folder.")
            return

        for relative_path, note in list(self.vault.notes.items()):
            if relative_path == self.current_note_path.relative_to(self.vault.path).as_posix():
                continue
            updated_content = self._rewrite_wikilink_references(old_note_name, desired_title, note.content)
            if updated_content != note.content:
                path = self.vault.path / relative_path
                path.write_text(updated_content, encoding="utf-8")

        self.current_note_path.rename(destination)
        self.current_note_path = destination

        if lines and lines[0].startswith("# "):
            lines[0] = f"# {desired_title}"
            self.editor.setPlainText("\n".join(lines))

    def save_current_note(self) -> None:
        if self.current_note_path is None:
            QMessageBox.information(self, "No note selected", "Select or create a note before saving.")
            return

        self._rename_note_file_if_needed()
        self.current_note_path.write_text(self.editor.toPlainText(), encoding="utf-8")
        self.status_label.setText(f"Saved: {self.current_note_path.name}")
        if self.vault is not None:
            self.vault.refresh()
            self.populate_note_tree()
            self._open_note_file(self.current_note_path)

    def new_note(self) -> None:
        if self.vault is None:
            QMessageBox.warning(self, "No vault", "Select a vault before creating a note.")
            return

        base_name = "Untitled.md"
        candidate = self.vault.path / base_name
        index = 1
        while candidate.exists():
            candidate = self.vault.path / f"Untitled_{index}.md"
            index += 1

        candidate.write_text("# Untitled\n\n", encoding="utf-8")
        self.vault.refresh()
        self.populate_note_tree()
        self._open_note_file(candidate)

    def select_vault(self) -> None:
        vault_dir = QFileDialog.getExistingDirectory(
            self,
            "Select vault folder",
            str(Path.home()),
        )
        if not vault_dir:
            return

        self._vault_path = Path(vault_dir)
        self.vault = Vault(self._vault_path)
        self.vault.refresh()
        self.vault_label.setText(f"Vault: {self._vault_path}")
        self.populate_note_tree()
        self.status_label.setText(f"Vault selected: {self._vault_path.name}")

        if self.vault.notes:
            first_note = sorted(self.vault.notes)[0]
            self._open_note_file(self._vault_path / first_note)
        else:
            self.editor.clear()
            self.preview.setHtml("<p>No notes yet. Create one with Ctrl+N or the New Note button.</p>")

        QMessageBox.information(
            self,
            "Vault selected",
            f"Selected vault: {self._vault_path}\n\nNotes folder loaded and ready for editing.",
        )

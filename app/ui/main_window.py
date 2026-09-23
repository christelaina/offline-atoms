from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
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
from app.core.vault import Vault


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Local Knowledge Vault")
        self.resize(1400, 900)

        self._vault_path: Path | None = None
        self.vault: Vault | None = None
        self.current_note_path: Path | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)

        header = QHBoxLayout()
        self.vault_label = QLabel("No vault selected")
        self.vault_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.vault_label.setWordWrap(True)

        self.select_vault_button = QPushButton("Open Vault")
        self.select_vault_button.clicked.connect(self.select_vault)
        self.new_note_button = QPushButton("New Note")
        self.new_note_button.clicked.connect(self.new_note)
        self.save_note_button = QPushButton("Save")
        self.save_note_button.clicked.connect(self.save_current_note)

        header.addWidget(self.vault_label)
        header.addWidget(self.select_vault_button)
        header.addWidget(self.new_note_button)
        header.addWidget(self.save_note_button)
        root_layout.addLayout(header)

        splitter = QSplitter(Qt.Horizontal)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        self.note_tree = QTreeWidget()
        self.note_tree.setHeaderLabel("Notes")
        self.note_tree.itemClicked.connect(self._on_tree_item_clicked)
        left_layout.addWidget(self.note_tree)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Write a note in Markdown...")
        self.editor.setMinimumHeight(340)
        self.editor.textChanged.connect(self._refresh_preview)

        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(False)
        self.preview.setHtml("<p>Preview will appear here.</p>")
        self.preview.setMinimumHeight(220)

        right_layout.addWidget(self.editor, 2)
        right_layout.addWidget(self.preview, 1)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        root_layout.addWidget(splitter)

        self.status_label = QLabel("Phase 2: markdown notes and vault explorer ready")
        root_layout.addWidget(self.status_label)

        self._setup_shortcuts()

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
        self._refresh_preview()
        rel_path = file_path.relative_to(self.vault.path).as_posix() if self.vault else file_path.name
        self.status_label.setText(f"Open note: {rel_path}")

    def _refresh_preview(self) -> None:
        content = self.editor.toPlainText()
        self.preview.setHtml(render_markdown_to_html(content))

    def save_current_note(self) -> None:
        if self.current_note_path is None:
            QMessageBox.information(self, "No note selected", "Select or create a note before saving.")
            return

        self.current_note_path.write_text(self.editor.toPlainText(), encoding="utf-8")
        self.status_label.setText(f"Saved: {self.current_note_path.name}")
        if self.vault is not None:
            self.vault.refresh()
            self.populate_note_tree()

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

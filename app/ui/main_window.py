from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QGraphicsEllipseItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
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
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class GraphNodeItem(QGraphicsEllipseItem):
    def __init__(self, label: str, reference: str, on_open) -> None:
        super().__init__(-48, -22, 96, 44)
        self.reference = reference
        self.on_open = on_open
        self.setBrush(QBrush(QColor("#25233b")))
        self.setPen(QPen(QColor("#8176e8"), 2))
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable, True)

        text = QGraphicsTextItem(label, self)
        text.setDefaultTextColor(QColor("#f1f0ff"))
        text.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        text.setTextWidth(84)
        text.setPos(-42, -10)

    def mousePressEvent(self, event) -> None:
        self.on_open(self.reference)
        super().mousePressEvent(event)

    def hoverEnterEvent(self, event) -> None:
        self.setBrush(QBrush(QColor("#3b3560")))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self.setBrush(QBrush(QColor("#25233b")))
        super().hoverLeaveEvent(event)


class VaultFileWatcher(FileSystemEventHandler):
    def __init__(self, window: "MainWindow") -> None:
        self.window = window

    def on_any_event(self, event) -> None:
        if getattr(event, "is_directory", False):
            return

        src = getattr(event, "src_path", "")
        if not src:
            return

        try:
            event_path = Path(src).resolve()
            vault_root = self.window._vault_path.resolve() if self.window._vault_path else None
        except (OSError, RuntimeError):
            event_path = None
            vault_root = None

        if vault_root is not None and event_path is not None:
            if event_path == vault_root or vault_root in event_path.parents:
                QTimer.singleShot(150, self.window._handle_watched_event)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Local Knowledge Vault")
        self.resize(1400, 900)
        self._vault_path: Path | None = None
        self.vault: Vault | None = None
        self.current_note_path: Path | None = None
        self._observer: Observer | None = None
        self._watcher: VaultFileWatcher | None = None
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
        self._init_ui()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._stop_vault_watcher()
        super().closeEvent(event)

    def _apply_toggle_state(self, button: QPushButton, active: bool) -> None:
        button.setProperty("active", active)
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def _sync_toggle_state(self) -> None:
        if hasattr(self, "toggle_note_tree_button"):
            self._apply_toggle_state(
                self.toggle_note_tree_button,
                bool(getattr(self, "note_tree_container", None)) and self.note_tree_container.isVisible(),
            )
        if hasattr(self, "toggle_search_button"):
            self._apply_toggle_state(
                self.toggle_search_button,
                bool(getattr(self, "search_panel", None)) and self.search_panel.isVisible(),
            )
        if hasattr(self, "toggle_backlinks_button"):
            self._apply_toggle_state(
                self.toggle_backlinks_button,
                bool(getattr(self, "backlinks_panel", None)) and self.backlinks_panel.isVisible(),
            )
        if hasattr(self, "toggle_connected_button"):
            self._apply_toggle_state(
                self.toggle_connected_button,
                bool(getattr(self, "connected_panel", None)) and self.connected_panel.isVisible(),
            )

    def _start_vault_watcher(self) -> None:
        if self._vault_path is None or not self._vault_path.exists():
            return

        self._stop_vault_watcher()
        self._watcher = VaultFileWatcher(self)
        self._observer = Observer()
        self._observer.schedule(self._watcher, str(self._vault_path), recursive=True)
        self._observer.start()

    def _stop_vault_watcher(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None
        self._watcher = None

    def _handle_watched_event(self, _event=None) -> None:
        self._refresh_vault_from_disk()

    def _init_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        self.taskbar = QWidget()
        self.taskbar.setFixedWidth(80)
        self.taskbar.setStyleSheet(
            """
            QWidget#taskbar {
                background: #171717;
                border: 1px solid #2a2a2a;
                border-radius: 12px;
            }
            QPushButton {
                min-height: 42px;
                min-width: 42px;
                font-size: 18px;
                border-radius: 10px;
            }
            QPushButton[active="true"] {
                background: #2a2a2a;
                border: 1px solid #7b6ee6;
                color: #f3f2ff;
            }
            """
        )
        self.taskbar.setObjectName("taskbar")
        taskbar_layout = QVBoxLayout(self.taskbar)
        taskbar_layout.setContentsMargins(8, 10, 8, 10)
        taskbar_layout.setSpacing(8)

        self.select_vault_button = QPushButton("🗂")
        self.select_vault_button.clicked.connect(self.select_vault)
        self.new_note_button = QPushButton("＋")
        self.new_note_button.clicked.connect(self.new_note)
        self.toggle_note_tree_button = QPushButton("🗃")
        self.toggle_note_tree_button.clicked.connect(self._toggle_note_tree)
        self.toggle_search_button = QPushButton("⌕")
        self.toggle_search_button.clicked.connect(self._toggle_search)
        self.toggle_backlinks_button = QPushButton("↔")
        self.toggle_backlinks_button.clicked.connect(self._toggle_backlinks_panel)
        self.toggle_connected_button = QPushButton("◎")
        self.toggle_connected_button.clicked.connect(self._toggle_connected_panel)
        self.save_note_button = QPushButton("💾")
        self.save_note_button.clicked.connect(self.save_current_note)

        for button in (
            self.select_vault_button,
            self.new_note_button,
            self.toggle_note_tree_button,
            self.toggle_search_button,
            self.toggle_backlinks_button,
            self.toggle_connected_button,
            self.save_note_button,
        ):
            button.setToolTip(button.text())
            button.setFixedWidth(54)
            button.setFixedHeight(42)
            button.setProperty("active", False)
            button.setStyleSheet(
                """
                QPushButton {
                    background: #202020;
                    border: 1px solid #363636;
                    border-radius: 10px;
                    min-height: 42px;
                    min-width: 42px;
                    font-size: 18px;
                    font-weight: 600;
                    padding: 0;
                }
                QPushButton:hover {
                    background: #2a2a2a;
                }
                QPushButton:pressed {
                    background: #323232;
                }
                QPushButton[active="true"] {
                    background: #2f2a42;
                    border: 1px solid #7b6ee6;
                    color: #f3f2ff;
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
        self.search_panel.setObjectName("drawer")
        self.search_panel.setStyleSheet(
            """
            QWidget#drawer {
                background: #171717;
                border: 1px solid #2a2a2a;
                border-radius: 10px;
            }
            """
        )
        self.search_layout = QVBoxLayout(self.search_panel)
        self.search_layout.setContentsMargins(10, 10, 10, 10)
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
        self._sync_toggle_state()

        splitter = QSplitter(Qt.Horizontal)
        self.note_tree_container = QWidget()
        self.note_tree_container.setObjectName("drawer")
        self.note_tree_container.setFixedWidth(220)
        self.note_tree_container.setStyleSheet(
            """
            QWidget#drawer {
                background: #171717;
                border: 1px solid #2a2a2a;
                border-radius: 10px;
            }
            """
        )
        left_layout = QVBoxLayout(self.note_tree_container)
        left_layout.setContentsMargins(10, 10, 10, 10)
        self.note_tree = QTreeWidget()
        self.note_tree.setHeaderLabel("Notes")
        self.note_tree.itemClicked.connect(self._on_tree_item_clicked)
        left_layout.addWidget(self.note_tree)

        self.sidebar_panel = QWidget()
        self.sidebar_panel.setFixedWidth(220)
        self.sidebar_panel.setObjectName("drawer")
        self.sidebar_panel.setStyleSheet(
            """
            QWidget#drawer {
                background: #171717;
                border: 1px solid #2a2a2a;
                border-radius: 10px;
            }
            """
        )
        self.sidebar_layout = QVBoxLayout(self.sidebar_panel)
        self.sidebar_layout.setContentsMargins(10, 10, 10, 10)
        self.sidebar_layout.setSpacing(8)

        self.backlinks_panel = QWidget()
        self.backlinks_panel.setObjectName("drawer")
        self.backlinks_layout = QVBoxLayout(self.backlinks_panel)
        self.backlinks_layout.setContentsMargins(0, 0, 0, 0)
        self.backlinks_list = QListWidget()
        self.backlinks_list.setMinimumHeight(100)
        self.backlinks_list.itemDoubleClicked.connect(self._on_list_item_open)
        self.backlinks_label = QLabel("Backlinks")
        self.backlinks_label.setStyleSheet("QLabel { color: #a9a9a9; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }")
        self.backlinks_layout.addWidget(self.backlinks_label)
        self.backlinks_layout.addWidget(self.backlinks_list)
        self.backlinks_panel.setVisible(False)

        self.connected_panel = QWidget()
        self.connected_panel.setObjectName("drawer")
        self.connected_layout = QVBoxLayout(self.connected_panel)
        self.connected_layout.setContentsMargins(0, 0, 0, 0)
        self.connected_layout.setSpacing(8)
        self.outgoing_list = QListWidget()
        self.outgoing_list.setMinimumHeight(100)
        self.outgoing_list.itemDoubleClicked.connect(self._on_list_item_open)
        self.graph_view = QGraphicsView()
        self.graph_scene = QGraphicsScene(self)
        self.graph_view.setScene(self.graph_scene)
        self.graph_view.setMinimumHeight(210)
        self.graph_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.graph_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.graph_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.graph_view.setStyleSheet(
            "QGraphicsView { background: #14141b; border: 1px solid #2a2a3a; border-radius: 8px; }"
        )
        self.graph_list = QListWidget()
        self.graph_list.setVisible(False)
        self.graph_list.itemDoubleClicked.connect(self._on_list_item_open)
        self.outgoing_label = QLabel("Outgoing")
        self.outgoing_label.setStyleSheet("QLabel { color: #a9a9a9; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }")
        self.graph_label = QLabel("Connected Notes")
        self.graph_label.setStyleSheet("QLabel { color: #a9a9a9; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }")
        self.connected_layout.addWidget(self.outgoing_label)
        self.connected_layout.addWidget(self.outgoing_list)
        self.connected_layout.addWidget(self.graph_label)
        self.connected_layout.addWidget(self.graph_view)
        self.connected_layout.addWidget(self.graph_list)
        self.connected_panel.setVisible(False)

        self.tag_panel = QWidget()
        self.tag_panel.setObjectName("drawer")
        self.tag_layout = QVBoxLayout(self.tag_panel)
        self.tag_layout.setContentsMargins(0, 0, 0, 0)
        self.tag_list = QListWidget()
        self.tag_list.setMinimumHeight(80)
        self.tag_list.itemDoubleClicked.connect(self._on_tag_clicked)
        self.tags_label = QLabel("Tags")
        self.tags_label.setStyleSheet("QLabel { color: #a9a9a9; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }")
        self.tag_layout.addWidget(self.tags_label)
        self.tag_layout.addWidget(self.tag_list)
        self.tag_panel.setVisible(False)

        self.sidebar_layout.addWidget(self.backlinks_panel)
        self.sidebar_layout.addWidget(self.connected_panel)
        self.sidebar_layout.addWidget(self.tag_panel)

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

        right_layout.addWidget(self.title_input)
        right_layout.addWidget(self.editor, 2)
        right_layout.addWidget(self.preview, 1)

        splitter.addWidget(self.note_tree_container)
        splitter.addWidget(self.sidebar_panel)
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
            self._sync_toggle_state()

    def _toggle_search(self) -> None:
        if hasattr(self, "search_panel"):
            self.search_panel.setVisible(not self.search_panel.isVisible())
            self._sync_toggle_state()

    def _toggle_backlinks_panel(self) -> None:
        if hasattr(self, "backlinks_panel"):
            self.backlinks_panel.setVisible(not self.backlinks_panel.isVisible())
            self._sync_toggle_state()

    def _toggle_connected_panel(self) -> None:
        if hasattr(self, "connected_panel"):
            self.connected_panel.setVisible(not self.connected_panel.isVisible())
            self._sync_toggle_state()

    def _refresh_vault_from_disk(self) -> None:
        if self.vault is None:
            return
        self.vault.refresh()
        self.populate_note_tree()
        if self.current_note_path is not None and self.current_note_path.exists():
            self._open_note_file(self.current_note_path)

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
        self.graph_list.clear()
        self.tag_list.clear()
        self._refresh_graph(note.title, note.backlinks, note.outgoing_links)

        for backlink in note.backlinks:
            self.backlinks_list.addItem(backlink)
        for outgoing in note.outgoing_links:
            self.outgoing_list.addItem(outgoing)

        connected: list[str] = []
        for item in note.backlinks + note.outgoing_links:
            if item not in connected:
                connected.append(item)
        for related in connected:
            self.graph_list.addItem(related)

        if note.tags:
            for tag in note.tags:
                self.tag_list.addItem(f"#{tag}")
        else:
            self.tag_list.addItem("No tags")

        if self.backlinks_list.count() == 0:
            self.backlinks_list.addItem("No backlinks")
        if self.outgoing_list.count() == 0:
            self.outgoing_list.addItem("No outgoing links")
        if self.graph_list.count() == 0:
            self.graph_list.addItem("No connected notes")

    def _refresh_graph(self, title: str, backlinks: list[str], outgoing: list[str]) -> None:
        self.graph_scene.clear()
        center = self.graph_scene.addEllipse(
            -58,
            -28,
            116,
            56,
            QPen(QColor("#d7a84b"), 2),
            QBrush(QColor("#4b3920")),
        )
        center.setZValue(2)
        center_label = self.graph_scene.addText(title, QFont("Segoe UI", 10, QFont.Weight.Bold))
        center_label.setDefaultTextColor(QColor("#fff4d1"))
        center_label.setTextWidth(104)
        center_label.setPos(-52, -10)
        center_label.setZValue(3)

        related: list[tuple[str, str, QColor]] = []
        for reference in backlinks:
            related.append((reference, "backlink", QColor("#62b6cb")))
        for reference in outgoing:
            if reference not in {item[0] for item in related}:
                related.append((reference, "outgoing", QColor("#c77dff")))

        if not related:
            empty_label = self.graph_scene.addText("No connected notes", QFont("Segoe UI", 9))
            empty_label.setDefaultTextColor(QColor("#89899a"))
            empty_label.setPos(-58, 58)
            self.graph_scene.setSceneRect(-120, -90, 240, 180)
            self.graph_view.fitInView(self.graph_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            return

        radius = 82
        import math

        for index, (reference, _kind, color) in enumerate(related):
            angle = (2 * math.pi * index / len(related)) - math.pi / 2
            x = math.cos(angle) * radius
            y = math.sin(angle) * radius
            edge = self.graph_scene.addLine(0, 0, x, y, QPen(color, 2))
            edge.setZValue(0)
            node = GraphNodeItem(Path(reference).stem, reference, self._open_note_from_reference)
            node.setPen(QPen(color, 2))
            node.setPos(x, y)
            node.setZValue(2)
            self.graph_scene.addItem(node)

        self.graph_scene.setSceneRect(-150, -145, 300, 290)
        self.graph_view.fitInView(self.graph_scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _on_list_item_open(self, item) -> None:
        text = item.text()
        if not text or text.startswith("No "):
            return
        self._open_note_from_reference(text)

    def _on_preview_link_clicked(self, url: QUrl) -> None:
        target = unquote(url.toString())
        self._open_note_from_reference(target)

    def _on_tag_clicked(self, item) -> None:
        text = item.text()
        if not text or text == "No tags":
            return
        self.search_input.setText(text)
        self.perform_search()

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
        self._start_vault_watcher()
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

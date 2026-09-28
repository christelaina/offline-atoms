from __future__ import annotations

import re
import shutil
from datetime import date, datetime
from pathlib import Path

import networkx as nx
from PySide6.QtCore import QEvent, QPoint, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QCursor, QFont, QFontMetrics, QIcon, QKeySequence, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QMenu,
    QPushButton,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHeaderView,
    QSplitter,
    QTabBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app.core.markdown import extract_frontmatter, set_frontmatter
from app.core.search import fuzzy_note_results, refresh_search_index, search_notes
from app.core.vault import Vault
from app.ui.markdown_editor import MarkdownEditor
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


DAILY_NOTES_FOLDER = "Daily Notes"
TEMPLATES_FOLDER = "Templates"


def _sidebar_action_icon(kind: str) -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#c4c0c9"), 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    if kind == "vault":
        path = QPainterPath()
        path.moveTo(3, 8)
        path.lineTo(9, 8)
        path.lineTo(11, 10)
        path.lineTo(21, 10)
        path.lineTo(18, 18)
        path.lineTo(3, 18)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(3, 10, 20, 10)
        painter.drawLine(8, 13, 14, 13)
    elif kind == "note":
        path = QPainterPath()
        path.moveTo(7, 3)
        path.lineTo(14, 3)
        path.lineTo(18, 7)
        path.lineTo(18, 20)
        path.lineTo(6, 20)
        path.lineTo(6, 4)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(14, 3, 14, 7)
        painter.drawLine(14, 7, 18, 7)
        painter.drawLine(9, 12, 15, 12)
        painter.drawLine(9, 15, 15, 15)
    elif kind == "folder":
        path = QPainterPath()
        path.moveTo(3, 7)
        path.lineTo(9, 7)
        path.lineTo(11, 9)
        path.lineTo(20, 9)
        path.lineTo(20, 18)
        path.lineTo(3, 18)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(12, 11, 12, 16)
        painter.drawLine(9.5, 13.5, 14.5, 13.5)
    elif kind == "save":
        path = QPainterPath()
        path.moveTo(5, 3)
        path.lineTo(17, 3)
        path.lineTo(20, 6)
        path.lineTo(20, 20)
        path.lineTo(4, 20)
        path.lineTo(4, 4)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawRect(8, 4, 8, 5)
        painter.drawRect(7, 13, 10, 7)
    elif kind == "settings":
        painter.drawLine(12, 2, 12, 5)
        painter.drawLine(12, 19, 12, 22)
        painter.drawLine(2, 12, 5, 12)
        painter.drawLine(19, 12, 22, 12)
        painter.drawLine(5, 5, 7, 7)
        painter.drawLine(17, 17, 19, 19)
        painter.drawLine(19, 5, 17, 7)
        painter.drawLine(7, 17, 5, 19)
        painter.drawEllipse(6, 6, 12, 12)
        painter.drawEllipse(10, 10, 4, 4)
    elif kind == "close":
        painter.drawLine(6, 6, 18, 18)
        painter.drawLine(18, 6, 6, 18)
    elif kind == "calendar":
        painter.drawRect(4, 5, 16, 16)
        painter.drawLine(4, 9, 20, 9)
        painter.drawLine(8, 3, 8, 7)
        painter.drawLine(16, 3, 16, 7)
        painter.drawLine(8, 12, 8, 12)
        painter.drawLine(12, 12, 12, 12)
        painter.drawLine(16, 12, 16, 12)
    elif kind == "template":
        path = QPainterPath()
        path.moveTo(6, 3)
        path.lineTo(14, 3)
        path.lineTo(19, 8)
        path.lineTo(19, 21)
        path.lineTo(6, 21)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(14, 3, 14, 8)
        painter.drawLine(14, 8, 19, 8)
        painter.drawLine(9, 12, 16, 12)
        painter.drawLine(9, 16, 16, 16)

    painter.end()
    return QIcon(pixmap)


class GraphNodeItem(QGraphicsEllipseItem):
    """Draggable, hoverable graph node; open-on-click, drag-to-reposition."""

    CLICK_DRAG_THRESHOLD = 4.0

    def __init__(
        self,
        label: str,
        reference: str,
        on_open,
        on_hover=None,
        on_drag_end=None,
        radius: float = 16.0,
        base_color: QColor = QColor("#25233b"),
        hover_color: QColor = QColor("#3b3560"),
        border_color: QColor = QColor("#8176e8"),
        text_color: QColor = QColor("#d7d4dc"),
    ) -> None:
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.reference = reference
        self.on_open = on_open
        self.on_hover = on_hover
        self.on_drag_end = on_drag_end
        self.edges: list["GraphEdgeItem"] = []
        self.vx = 0.0
        self.vy = 0.0
        self.pinned = False
        self._base_color = base_color
        self._hover_color = hover_color
        self._press_pos = None
        self.setBrush(QBrush(base_color))
        self.setPen(QPen(border_color, 2))
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        label_font = QFont("Segoe UI", 8, QFont.Weight.DemiBold)
        metrics = QFontMetrics(label_font)
        text_width = metrics.horizontalAdvance(label) + 10
        text_height = metrics.height() + 4

        label_background = QGraphicsRectItem(-text_width / 2, radius + 3, text_width, text_height, self)
        label_background.setBrush(QBrush(QColor(0, 0, 0, 150)))
        label_background.setPen(QPen(Qt.PenStyle.NoPen))
        label_background.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        label_background.setZValue(0)

        text = QGraphicsTextItem(label, self)
        text.setDefaultTextColor(text_color)
        text.setFont(label_font)
        text.setPos(-text_width / 2 + 5, radius + 3)
        text.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        text.setZValue(1)

    def itemChange(self, change, value):  # noqa: N802 - Qt API
        if change == QGraphicsEllipseItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in self.edges:
                edge.update_position()
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:
        self._press_pos = event.scenePos()
        self.pinned = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self.pinned = False
        moved = self._press_pos is not None and (
            (event.scenePos() - self._press_pos).manhattanLength() > self.CLICK_DRAG_THRESHOLD
        )
        self._press_pos = None
        if moved:
            if self.on_drag_end is not None:
                self.on_drag_end()
        else:
            self.on_open(self.reference)

    def hoverEnterEvent(self, event) -> None:
        self.setBrush(QBrush(self._hover_color))
        if self.on_hover is not None:
            self.on_hover(self, True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self.setBrush(QBrush(self._base_color))
        if self.on_hover is not None:
            self.on_hover(self, False)
        super().hoverLeaveEvent(event)


class GraphEdgeItem(QGraphicsLineItem):
    """Line between two graph nodes that follows them as they move."""

    def __init__(self, source: GraphNodeItem, target: GraphNodeItem, pen: QPen) -> None:
        super().__init__()
        self.source = source
        self.target = target
        self.setPen(pen)
        self.update_position()

    def update_position(self) -> None:
        self.setLine(self.source.x(), self.source.y(), self.target.x(), self.target.y())


class GraphForceSimulation:
    """Force-directed layout that settles on load and reheats when a node is dragged."""

    TICK_INTERVAL_MS = 16
    SETTLE_TICKS = 200
    WAKE_TICKS = 90

    def __init__(self, timer_parent) -> None:
        self.nodes: list[GraphNodeItem] = []
        self.edges: list[GraphEdgeItem] = []
        self._timer = QTimer(timer_parent)
        self._timer.timeout.connect(self._tick)
        self._remaining_ticks = 0

    def set_graph(self, nodes: list[GraphNodeItem], edges: list[GraphEdgeItem]) -> None:
        self.stop()
        self.nodes = nodes
        self.edges = edges
        for node in nodes:
            node.vx = 0.0
            node.vy = 0.0
        self.wake(self.SETTLE_TICKS)

    def wake(self, ticks: int = WAKE_TICKS) -> None:
        self._remaining_ticks = max(self._remaining_ticks, ticks)
        if self.nodes and not self._timer.isActive():
            self._timer.start(self.TICK_INTERVAL_MS)

    def stop(self) -> None:
        self._timer.stop()
        self._remaining_ticks = 0
        self.nodes = []
        self.edges = []

    def _tick(self) -> None:
        if self._remaining_ticks <= 0 or len(self.nodes) < 2:
            self._timer.stop()
            return
        self._remaining_ticks -= 1

        repulsion = 14000.0
        spring_length = 150.0
        spring_strength = 0.02
        damping = 0.82
        center_pull = 0.002

        forces = {node: [0.0, 0.0] for node in self.nodes}
        for index, node_a in enumerate(self.nodes):
            for node_b in self.nodes[index + 1 :]:
                dx = node_a.x() - node_b.x()
                dy = node_a.y() - node_b.y()
                distance_sq = max(dx * dx + dy * dy, 1.0)
                distance = distance_sq ** 0.5
                force = repulsion / distance_sq
                fx = force * dx / distance
                fy = force * dy / distance
                forces[node_a][0] += fx
                forces[node_a][1] += fy
                forces[node_b][0] -= fx
                forces[node_b][1] -= fy

        for edge in self.edges:
            dx = edge.target.x() - edge.source.x()
            dy = edge.target.y() - edge.source.y()
            distance = max((dx * dx + dy * dy) ** 0.5, 1.0)
            displacement = distance - spring_length
            fx = spring_strength * displacement * dx / distance
            fy = spring_strength * displacement * dy / distance
            forces[edge.source][0] += fx
            forces[edge.source][1] += fy
            forces[edge.target][0] -= fx
            forces[edge.target][1] -= fy

        still_moving = False
        for node in self.nodes:
            if node.pinned:
                node.vx = 0.0
                node.vy = 0.0
                continue
            fx, fy = forces[node]
            fx -= node.x() * center_pull
            fy -= node.y() * center_pull
            node.vx = (node.vx + fx) * damping
            node.vy = (node.vy + fy) * damping
            if abs(node.vx) > 0.05 or abs(node.vy) > 0.05:
                node.setPos(node.x() + node.vx, node.y() + node.vy)
                still_moving = True

        if not still_moving:
            self._remaining_ticks = 0


class VaultGraphView(QGraphicsView):
    """Graphics view supporting click-drag panning and wheel-zoom for graph navigation."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API
        zoom_factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(zoom_factor, zoom_factor)


class GraphSurface:
    """Bundles a graph's scene, view, and physics so multiple graphs can render independently."""

    def __init__(self, scene: QGraphicsScene, view: VaultGraphView, simulation: "GraphForceSimulation") -> None:
        self.scene = scene
        self.view = view
        self.simulation = simulation
        self.nodes: dict[str, GraphNodeItem] = {}
        self.edges: list[GraphEdgeItem] = []


class GraphTabWidget(QWidget):
    """Full-vault graph shown as its own note-editor tab, like Obsidian's graph view."""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self.window = window

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        title = QLabel("Full Vault Graph")
        title.setStyleSheet("QLabel { color: #8f8991; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }")
        self.tag_filter = QComboBox()
        self.tag_filter.setToolTip("Filter the graph by tag")
        self.tag_filter.addItem("All tags", "")
        self.tag_filter.currentIndexChanged.connect(self.refresh)
        self.path_filter = QComboBox()
        self.path_filter.setToolTip("Filter the graph by folder")
        self.path_filter.addItem("All paths", "")
        self.path_filter.currentIndexChanged.connect(self.refresh)
        controls.addWidget(title)
        controls.addStretch()
        controls.addWidget(self.tag_filter)
        controls.addWidget(self.path_filter)
        layout.addLayout(controls)

        self.view = VaultGraphView()
        self.scene = QGraphicsScene(self)
        self.view.setScene(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setStyleSheet(
            "QGraphicsView { background: #1f1f1f; border: 1px solid #454047; border-radius: 6px; }"
        )
        layout.addWidget(self.view, 1)

        self.simulation = GraphForceSimulation(self.view)
        self.surface = GraphSurface(self.scene, self.view, self.simulation)

    def refresh(self, _index: int = -1) -> None:
        self.window._render_full_vault_graph_into(self)

    def stop(self) -> None:
        self.simulation.stop()


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
                if not self.window._closing:
                    self.window._vault_refresh_requested.emit()


class VaultTreeWidget(QTreeWidget):
    IS_DIRECTORY_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(self, on_move_requested) -> None:
        super().__init__()
        self._on_move_requested = on_move_requested
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def dropEvent(self, event) -> None:
        source_item = self.currentItem()
        target_item = self.itemAt(event.position().toPoint())
        if source_item is None or target_item is None or source_item is target_item:
            event.ignore()
            return

        source_path = source_item.data(0, Qt.ItemDataRole.UserRole) or ""
        if not source_path:
            event.ignore()
            return

        target_path = target_item.data(0, Qt.ItemDataRole.UserRole) or ""
        target_is_directory = bool(target_item.data(0, self.IS_DIRECTORY_ROLE))
        if not target_is_directory:
            target_path = str(Path(target_path).parent).replace("\\", "/")
            if target_path == ".":
                target_path = ""

        moved = self._on_move_requested(source_path, target_path)
        if moved:
            event.accept()
        else:
            event.ignore()


class MainWindow(QMainWindow):
    _vault_refresh_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Local Knowledge Vault")
        self.resize(1400, 900)
        self._vault_path: Path | None = None
        self.vault: Vault | None = None
        self.current_note_path: Path | None = None
        self._note_history: list[str] = []
        self._note_history_index = -1
        self._history_navigation = False
        self._selected_folder_path: Path | None = None
        self._graph_tab_page: GraphTabWidget | None = None
        self._observer: Observer | None = None
        self._watcher: VaultFileWatcher | None = None
        self._closing = False
        self._vault_refresh_requested.connect(
            self._schedule_vault_refresh, Qt.ConnectionType.QueuedConnection
        )
        self._vault_refresh_timer = QTimer(self)
        self._vault_refresh_timer.setSingleShot(True)
        self._vault_refresh_timer.timeout.connect(self._handle_watched_event)
        self.setStyleSheet(
            """
            QMainWindow {
                background: #202020;
                color: #d6d3d1;
            }
            QWidget {
                background: #202020;
                color: #d6d3d1;
            }
            QSplitter::handle {
                background: #171717;
                border: 0;
            }
            QLabel {
                color: #a8a29e;
            }
            QLineEdit,
            QTextEdit,
            QListWidget,
            QTreeWidget,
            QPushButton {
                background: #262626;
                color: #e7e5e4;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 6px 8px;
            }
            QLineEdit:focus,
            QTextEdit:focus,
            QListWidget:focus,
            QTreeWidget:focus {
                border-color: #7c6bd6;
            }
            QPushButton {
                background: #2b2b2b;
                border: 1px solid #454047;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background: #343039;
            }
            QPushButton:pressed {
                background: #40394a;
            }
            QPushButton[active="true"] {
                background: #3d3552;
                border: 1px solid #6555a3;
                color: #c4b5fd;
            }
            QTreeWidget::item,
            QListWidget::item {
                border-radius: 5px;
                padding: 4px 6px;
            }
            QTreeWidget::item:selected,
            QListWidget::item:selected {
                background: #3d3552;
                color: #e9d5ff;
            }
            QTreeWidget::item:hover,
            QListWidget::item:hover {
                background: #302d33;
            }
            QTreeWidget::item:focus {
                outline: none;
                border: 0;
            }
            QTreeWidget,
            QListWidget {
                border: 0;
                background: #242424;
            }
            QTextEdit {
                background: #262626;
                border: 0;
                selection-background-color: #5a4b80;
            }
            QHeaderView::section {
                background: #2b292c;
                color: #a8a29e;
                border: 0;
                padding: 6px;
            }
            QScrollBar:vertical {
                background: #242424;
                width: 10px;
                margin: 2px 2px 2px 0;
                border-radius: 5px;
            }
            QScrollBar:horizontal {
                background: #242424;
                height: 10px;
                margin: 0 2px 2px 2px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical,
            QScrollBar::handle:horizontal {
                background: #51466f;
                border-radius: 5px;
                min-height: 28px;
                min-width: 28px;
            }
            QScrollBar::handle:hover {
                background: #7564a6;
            }
            QScrollBar::add-line,
            QScrollBar::sub-line,
            QScrollBar::add-page,
            QScrollBar::sub-page {
                background: transparent;
                border: 0;
            }
            QTabWidget::pane {
                border: 1px solid #454047;
                background: #262626;
                border-radius: 8px;
            }
            QTabBar::tab {
                background: #2b292c;
                color: #a8a29e;
                border: 1px solid #454047;
                border-bottom: 0;
                padding: 6px 12px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #262626;
                color: #e9d5ff;
                border-color: #6555a3;
            }
            """
        )
        self._init_ui()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._closing = True
        self._stop_vault_watcher()
        self._vault_refresh_timer.stop()
        super().closeEvent(event)

    def _apply_toggle_state(self, button: QPushButton, active: bool) -> None:
        button.setProperty("active", active)
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def _sync_toggle_state(self) -> None:
        notes_visible = bool(getattr(self, "note_tree_container", None)) and not self.note_tree_container.isHidden()
        if hasattr(self, "toggle_note_tree_button"):
            self._apply_toggle_state(
                self.toggle_note_tree_button,
                notes_visible,
            )
        if hasattr(self, "notes_toggle_button"):
            self._apply_toggle_state(self.notes_toggle_button, notes_visible)
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
        if hasattr(self, "_vault_refresh_timer"):
            self._vault_refresh_timer.stop()

    def _schedule_vault_refresh(self) -> None:
        if not self._closing:
            self._vault_refresh_timer.start(150)

    def _handle_watched_event(self, _event=None) -> None:
        if not self._closing:
            self._refresh_vault_from_disk()

    def _position_search_results(self) -> None:
        if not hasattr(self, "search_results"):
            return
        position = self.search_input.mapTo(self, QPoint(0, self.search_input.height()))
        self.search_results.setGeometry(
            position.x(),
            position.y(),
            self.search_input.width(),
            min(180, max(40, self.search_results.sizeHintForRow(0) * self.search_results.count() + 8)),
        )

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if hasattr(self, "search_results") and not self.search_results.isHidden():
            self._position_search_results()

    def moveEvent(self, event) -> None:  # type: ignore[override]
        super().moveEvent(event)
        if hasattr(self, "search_results") and not self.search_results.isHidden():
            self._position_search_results()

    def _init_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.top_bar = QWidget()
        self.top_bar.setObjectName("topBar")
        self.top_bar.setStyleSheet(
            """
            QWidget#topBar {
                background: #242424;
                border-bottom: 1px solid #353238;
            }
            QPushButton {
                background: #2b2b2b;
                border: 1px solid #454047;
                border-radius: 5px;
                padding: 5px 10px;
                color: #d6d3d1;
                min-height: 28px;
            }
            QPushButton:hover {
                background: #39343f;
            }
            QLineEdit {
                background: #1f1f1f;
                border: 1px solid #3f3b44;
                border-radius: 6px;
                padding: 7px 11px;
                min-height: 30px;
            }
            QLabel {
                color: #a8a29e;
            }
            """
        )
        top_bar_layout = QHBoxLayout(self.top_bar)
        top_bar_layout.setContentsMargins(14, 7, 14, 7)
        top_bar_layout.setSpacing(10)

        self.vault_controls = QWidget()
        vault_controls_layout = QHBoxLayout(self.vault_controls)
        vault_controls_layout.setContentsMargins(0, 0, 0, 0)
        vault_controls_layout.setSpacing(8)

        self.select_vault_button = QPushButton("Open vault")
        self.select_vault_button.clicked.connect(self.select_vault)
        self.select_vault_button.setFixedHeight(32)

        self.vault_label = QLabel("No vault selected")
        self.vault_label.setStyleSheet("QLabel { font-weight: 600; color: #e7e5e4; }")
        self.vault_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.breadcrumb_label = QLabel("")
        self.breadcrumb_label.setStyleSheet("QLabel { color: #8f8991; font-size: 12px; }")
        self.breadcrumb_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        vault_controls_layout.addWidget(self.vault_label)

        self.search_panel = QWidget()
        self.search_panel.setMinimumWidth(320)
        self.search_panel.setMaximumWidth(520)
        search_layout = QVBoxLayout(self.search_panel)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(4)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search notes or switch to a note...")
        self.search_input.setStyleSheet("QLineEdit { padding: 7px 11px; }")
        self.search_input.textChanged.connect(self.perform_search)
        self.search_input.installEventFilter(self)

        self.search_tag_filter = QComboBox()
        self.search_tag_filter.setObjectName("searchTagFilter")
        self.search_tag_filter.setToolTip("Filter search results by tag")
        self.search_tag_filter.setMinimumContentsLength(8)
        self.search_tag_filter.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.search_tag_filter.addItem("All tags", "")
        self.search_tag_filter.currentIndexChanged.connect(self.perform_search)

        self.search_path_filter = QComboBox()
        self.search_path_filter.setObjectName("searchPathFilter")
        self.search_path_filter.setToolTip("Filter search results by folder")
        self.search_path_filter.setMinimumContentsLength(8)
        self.search_path_filter.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.search_path_filter.addItem("All paths", "")
        self.search_path_filter.currentIndexChanged.connect(self.perform_search)

        self.search_results = QListWidget(self)
        self.search_results.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.search_results.setStyleSheet(
            """
            QListWidget {
                background: #262626;
                color: #d6d3d1;
                border: 1px solid #6555a3;
                border-radius: 6px;
                padding: 4px;
            }
            QListWidget::item {
                border-radius: 4px;
                padding: 6px 8px;
            }
            QListWidget::item:hover {
                background: #343039;
            }
            QListWidget::item:selected {
                background: #3d3552;
                color: #e9d5ff;
            }
            """
        )
        self.search_results.itemClicked.connect(self._on_search_result_clicked)
        self.search_results.itemActivated.connect(self._on_search_result_clicked)
        self.search_results.installEventFilter(self)
        self.search_results.setVisible(False)
        self.search_results.setMaximumHeight(180)
        self.search_results.setAlternatingRowColors(False)

        self.suggested_titles: list[str] = []

        search_layout.addWidget(self.search_input)
        filter_layout = QHBoxLayout()
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(6)
        filter_layout.addWidget(self.search_tag_filter, 1)
        filter_layout.addWidget(self.search_path_filter, 1)
        search_layout.addLayout(filter_layout)
        top_bar_layout.addWidget(self.search_panel, 1)

        self.settings_button = QPushButton()
        self.settings_button.setIcon(_sidebar_action_icon("settings"))
        self.settings_button.setIconSize(QSize(20, 20))
        self.settings_button.setAccessibleName("Settings")
        self.settings_button.setToolTip("Settings")
        self.settings_button.setFixedSize(32, 32)
        self.settings_button.setEnabled(False)
        self.settings_button.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid transparent; border-radius: 5px; padding: 0; }"
            "QPushButton:hover { background: #343039; border-color: #454047; }"
        )
        top_bar_layout.addWidget(self.settings_button)

        root_layout.addWidget(self.top_bar)

        self.main_content = QSplitter(Qt.Horizontal)
        self.main_content.setChildrenCollapsible(True)
        self.main_content.setHandleWidth(6)
        self.main_content.setStyleSheet(
            """
            QSplitter::handle {
                background: #dfe3e8;
            }
            """
        )

        self.nav_panel = QWidget()
        self.nav_panel.setObjectName("navPanel")
        self.nav_panel.setMinimumWidth(0)
        self.nav_panel.setStyleSheet(
            """
            QWidget#navPanel {
                background: #242424;
                border-right: 1px solid #3b383d;
            }
            QPushButton {
                background: #2b2b2b;
                border: 1px solid #454047;
                border-radius: 6px;
                min-height: 30px;
            }
            """
        )
        nav_layout = QVBoxLayout(self.nav_panel)
        nav_layout.setContentsMargins(10, 10, 10, 10)
        nav_layout.setSpacing(8)

        self.new_note_button = QPushButton("New note")
        self.new_note_button.clicked.connect(self.new_note)
        self.new_note_button.setFixedHeight(32)

        self.new_folder_button = QPushButton("New folder")
        self.new_folder_button.clicked.connect(self.new_folder)
        self.new_folder_button.setFixedHeight(32)

        self.save_note_button = QPushButton("Save")
        self.save_note_button.clicked.connect(self.save_current_note)
        self.save_note_button.setFixedHeight(32)
        self.daily_note_button = QPushButton("Daily note")
        self.daily_note_button.clicked.connect(lambda: self.create_daily_note())
        self.daily_note_button.setFixedHeight(32)

        self.insert_template_button = QPushButton("Insert template")
        self.insert_template_button.clicked.connect(lambda: self._choose_template())
        self.insert_template_button.setFixedHeight(32)

        sidebar_actions = (
            (self.select_vault_button, "vault", "Open vault"),
            (self.new_note_button, "note", "New note"),
            (self.new_folder_button, "folder", "New folder"),
            (self.save_note_button, "save", "Save note"),
            (self.daily_note_button, "calendar", "Create daily note"),
            (self.insert_template_button, "template", "Insert template"),
        )
        for button, icon_kind, label in sidebar_actions:
            button.setText("")
            button.setIcon(_sidebar_action_icon(icon_kind))
            button.setIconSize(QSize(20, 20))
            button.setFixedSize(34, 32)
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.setStyleSheet(
                "QPushButton { background: transparent; border: 1px solid transparent; "
                "border-radius: 5px; padding: 0; }"
                "QPushButton:hover { background: #343039; border-color: #454047; }"
                "QPushButton:pressed { background: #40394a; }"
            )

        action_row = QHBoxLayout()
        action_row.setSpacing(4)
        action_row.addWidget(self.select_vault_button)
        action_row.addWidget(self.new_note_button)
        action_row.addWidget(self.new_folder_button)
        action_row.addWidget(self.save_note_button)
        nav_layout.addLayout(action_row)

        self.note_tree_container = QWidget()
        self.note_tree_container.setObjectName("drawer")
        self.note_tree_container.setStyleSheet(
            """
            QWidget#drawer {
                background: transparent;
                border: 0;
            }
            """
        )
        note_tree_layout = QVBoxLayout(self.note_tree_container)
        note_tree_layout.setContentsMargins(0, 0, 0, 0)
        note_tree_layout.setSpacing(8)

        self.note_tree = VaultTreeWidget(self._move_tree_item)
        self.note_tree.setHeaderHidden(True)
        self.note_tree.setIndentation(14)
        self.note_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.note_tree.customContextMenuRequested.connect(self._show_tree_context_menu)
        self.note_tree.itemClicked.connect(self._on_tree_item_clicked)
        note_tree_layout.addWidget(self.note_tree)
        nav_layout.addWidget(self.note_tree_container, 1)

        self.main_content.addWidget(self.nav_panel)

        self.editor_panel = QWidget()
        self.editor_panel.setObjectName("editorPanel")
        self.editor_panel.setStyleSheet("QWidget#editorPanel { background: #202020; }")
        right_layout = QVBoxLayout(self.editor_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Markdown title is derived from # heading")
        self.title_input.setVisible(False)
        self.title_input.setStyleSheet("QLineEdit { padding: 8px 10px; background: #202020; color: #e7e5e4; border: 0; border-bottom: 1px solid #3b383d; border-radius: 0; }")

        self.editor = self._create_note_editor()

        right_layout.addWidget(self.title_input)
        self.note_tabs = QTabWidget()
        self.note_tabs.setDocumentMode(True)
        self.note_tabs.setTabsClosable(True)
        self.note_tabs.setMovable(True)
        self.note_tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.note_tabs.currentChanged.connect(self._on_note_tab_changed)
        self.note_tabs.tabCloseRequested.connect(self._close_note_tab)
        right_layout.addWidget(self.note_tabs, 1)
        self.main_content.addWidget(self.editor_panel)

        self.right_panel = QWidget()
        self.right_panel.setObjectName("rightPanel")
        self.right_panel.setMinimumWidth(0)
        self.right_panel.setStyleSheet(
            """
            QWidget#rightPanel {
                background: #242424;
                border-left: 1px solid #3b383d;
            }
            """
        )
        right_panel_layout = QVBoxLayout(self.right_panel)
        right_panel_layout.setContentsMargins(12, 10, 12, 10)
        right_panel_layout.setSpacing(10)

        self.right_tabs = QTabWidget()
        self.right_tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.right_tabs.setDocumentMode(True)
        self.right_tabs.tabBar().setUsesScrollButtons(False)
        self.right_tabs.setStyleSheet(
            """
            QTabWidget::pane {
                background: transparent;
                border: 1px solid #454047;
                border-radius: 6px;
            }
            QTabBar::tab {
                background: #2b292c;
                color: #a8a29e;
                border: 1px solid #454047;
                border-bottom: 0;
                padding: 7px 12px;
                margin-right: 3px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background: #262626;
                color: #e9d5ff;
                border-color: #6555a3;
            }
            """
        )

        self.backlinks_panel = QWidget()
        self.backlinks_panel.setObjectName("drawer")
        self.backlinks_layout = QVBoxLayout(self.backlinks_panel)
        self.backlinks_layout.setContentsMargins(8, 8, 8, 8)
        self.backlinks_layout.setSpacing(8)
        self.backlinks_list = QListWidget()
        self.backlinks_list.setMinimumHeight(100)
        self.backlinks_list.itemDoubleClicked.connect(self._on_list_item_open)
        self.backlinks_label = QLabel("Backlinks")
        self.backlinks_label.setStyleSheet("QLabel { color: #8f8991; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }")
        self.backlinks_layout.addWidget(self.backlinks_label)
        self.backlinks_layout.addWidget(self.backlinks_list)
        self.unresolved_label = QLabel("Unresolved")
        self.unresolved_label.setStyleSheet("QLabel { color: #d7a84b; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }")
        self.unresolved_list = QListWidget()
        self.unresolved_list.setMinimumHeight(80)
        self.unresolved_list.itemDoubleClicked.connect(self._on_unresolved_link_open)
        self.backlinks_layout.addWidget(self.unresolved_label)
        self.backlinks_layout.addWidget(self.unresolved_list)

        self.connected_panel = QWidget()
        self.connected_panel.setObjectName("drawer")
        self.connected_layout = QVBoxLayout(self.connected_panel)
        self.connected_layout.setContentsMargins(8, 8, 8, 8)
        self.connected_layout.setSpacing(8)
        self.outgoing_list = QListWidget()
        self.outgoing_list.setMinimumHeight(100)
        self.outgoing_list.itemDoubleClicked.connect(self._on_list_item_open)
        self.graph_view = VaultGraphView()
        self.graph_scene = QGraphicsScene(self)
        self.graph_view.setScene(self.graph_scene)
        self.graph_view.setMinimumHeight(210)
        self.graph_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.graph_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.graph_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.graph_view.setStyleSheet(
            "QGraphicsView { background: #1f1f1f; border: 1px solid #454047; border-radius: 6px; }"
        )
        self._graph_simulation = GraphForceSimulation(self.graph_view)
        self._graph_surface = GraphSurface(self.graph_scene, self.graph_view, self._graph_simulation)
        self.graph_list = QListWidget()
        self.graph_list.setVisible(False)
        self.graph_list.itemDoubleClicked.connect(self._on_list_item_open)
        self.outgoing_label = QLabel("Outgoing")
        self.outgoing_label.setStyleSheet("QLabel { color: #8f8991; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }")
        self.graph_label = QLabel("Connected Notes")
        self.graph_label.setStyleSheet("QLabel { color: #8f8991; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }")
        self.graph_scope_button = QPushButton("Full vault graph")
        self.graph_scope_button.setFixedHeight(26)
        self.graph_scope_button.setToolTip("Open the full vault graph in a new tab")
        self.graph_scope_button.clicked.connect(self._open_full_graph_tab)
        self.graph_controls_layout = QHBoxLayout()
        self.graph_controls_layout.setContentsMargins(0, 0, 0, 0)
        self.graph_controls_layout.setSpacing(6)
        self.graph_controls_layout.addWidget(self.graph_label)
        self.graph_controls_layout.addStretch()
        self.graph_controls_layout.addWidget(self.graph_scope_button)
        self.connected_layout.addWidget(self.outgoing_label)
        self.connected_layout.addWidget(self.outgoing_list)
        self.connected_layout.addLayout(self.graph_controls_layout)
        self.connected_layout.addWidget(self.graph_view)
        self.connected_layout.addWidget(self.graph_list)

        self.tag_panel = QWidget()
        self.tag_panel.setObjectName("drawer")
        self.tag_layout = QVBoxLayout(self.tag_panel)
        self.tag_layout.setContentsMargins(8, 8, 8, 8)
        self.tag_layout.setSpacing(8)
        self.tag_list = QListWidget()
        self.tag_list.setMinimumHeight(80)
        self.tag_list.itemDoubleClicked.connect(self._on_tag_clicked)
        self.tags_label = QLabel("Tags")
        self.tags_label.setStyleSheet("QLabel { color: #8f8991; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }")
        self.tag_matches_label = QLabel("")
        self.tag_matches_label.setStyleSheet("QLabel { color: #8f8991; font-size: 12px; letter-spacing: 0.04em; text-transform: uppercase; }")
        self.tag_matches_label.setVisible(False)
        self.tag_matches_list = QListWidget()
        self.tag_matches_list.setMinimumHeight(120)
        self.tag_matches_list.itemDoubleClicked.connect(self._on_tag_match_open)
        self.tag_matches_list.setVisible(False)
        self.tag_layout.addWidget(self.tags_label)
        self.tag_layout.addWidget(self.tag_list)
        self.tag_layout.addWidget(self.tag_matches_label)
        self.tag_layout.addWidget(self.tag_matches_list)

        self.properties_panel = QWidget()
        self.properties_panel.setObjectName("drawer")
        self.properties_layout = QVBoxLayout(self.properties_panel)
        self.properties_layout.setContentsMargins(8, 8, 8, 8)
        self.properties_layout.setSpacing(8)
        self.properties_table = QTableWidget(0, 2)
        self.properties_table.setHorizontalHeaderLabels(["Property", "Value"])
        self.properties_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.properties_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.properties_table.verticalHeader().setVisible(False)
        self.properties_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        property_actions = QHBoxLayout()
        self.add_property_button = QPushButton("Add")
        self.add_property_button.clicked.connect(self._add_property_row)
        self.remove_property_button = QPushButton("Remove")
        self.remove_property_button.clicked.connect(self._remove_property_row)
        self.apply_properties_button = QPushButton("Apply")
        self.apply_properties_button.clicked.connect(self._apply_properties_to_note)
        property_actions.addWidget(self.add_property_button)
        property_actions.addWidget(self.remove_property_button)
        property_actions.addStretch()
        property_actions.addWidget(self.apply_properties_button)
        self.properties_layout.addLayout(property_actions)
        self.properties_layout.addWidget(self.properties_table, 1)

        self.right_tabs.addTab(self.backlinks_panel, "Backlinks")
        self.right_tabs.addTab(self.connected_panel, "Graph")
        self.right_tabs.addTab(self.tag_panel, "Tags")
        self.right_tabs.addTab(self.properties_panel, "Properties")
        right_panel_layout.addWidget(self.right_tabs)
        self.main_content.addWidget(self.right_panel)

        self.main_content.setCollapsible(0, True)
        self.main_content.setCollapsible(1, False)
        self.main_content.setCollapsible(2, True)
        self.main_content.setSizes([260, 900, 300])
        root_layout.addWidget(self.main_content, 1)

        self.status_bar = QWidget()
        self.status_bar.setObjectName("statusBar")
        self.status_bar.setStyleSheet(
            """
            QWidget#statusBar {
                background: #242424;
                border-top: 1px solid #3b383d;
            }
            QLabel {
                color: #8f8991;
                font-size: 11px;
            }
            """
        )
        status_layout = QHBoxLayout(self.status_bar)
        status_layout.setContentsMargins(12, 6, 12, 6)
        status_layout.setSpacing(8)
        self.status_label = QLabel("Phase 4: local search and fuzzy lookup ready")
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.vault_label)
        status_layout.addWidget(self.breadcrumb_label)
        root_layout.addWidget(self.status_bar)

        self._setup_shortcuts()
        self._sync_toggle_state()

    def _toggle_note_tree(self) -> None:
        if hasattr(self, "note_tree_container"):
            self.note_tree_container.setHidden(not self.note_tree_container.isHidden())
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

    def _populate_filter_combo(
        self, combo: QComboBox, all_label: str, options: list[str], prefix: str = ""
    ) -> None:
        selected = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(all_label, "")
        for option in options:
            combo.addItem(f"{prefix}{option}", option)
        combo.setCurrentIndex(max(0, combo.findData(selected)))
        combo.blockSignals(False)

    def _refresh_search_index(self) -> None:
        if self.vault is None:
            return
        refresh_search_index(self.vault.path, self.vault)

        tags = sorted({tag for note in self.vault.notes.values() for tag in note.tags}, key=str.lower)
        paths = sorted(
            {
                parent.as_posix()
                for relative_path in self.vault.notes
                if (parent := Path(relative_path).parent).as_posix() != "."
            },
            key=str.lower,
        )
        self._populate_filter_combo(self.search_tag_filter, "All tags", tags, prefix="#")
        self._populate_filter_combo(self.search_path_filter, "All paths", paths)

    def _add_search_result(self, result: dict[str, str], suggested: bool = False) -> None:
        title = result.get("title", "Untitled")
        path = result.get("path", "")
        snippet = result.get("snippet", "").replace("\n", " ").strip()
        label = f"Suggested: {title}" if suggested else title
        item = QListWidgetItem(f"{label}\n{path}\n{snippet}")
        item.setData(Qt.ItemDataRole.UserRole, path)
        if suggested:
            item.setToolTip("Fuzzy title suggestion")
        self.search_results.addItem(item)

    def perform_search(self, *_args) -> None:
        query = self.search_input.text().strip()
        self.search_results.clear()
        if self.vault is None:
            self.search_results.setVisible(False)
            return

        tag = self.search_tag_filter.currentData() or ""
        path = self.search_path_filter.currentData() or ""
        matches = search_notes(self.vault.path, query, tag=tag, path=path)
        suggestions = fuzzy_note_results(
            self.vault.path, query, tag=tag, path=path
        )
        self.suggested_titles = [result["title"] for result in suggestions]
        shown_paths: set[str] = set()
        for result in matches:
            self._add_search_result(result)
            shown_paths.add(result.get("path", ""))
        for result in suggestions:
            if result.get("path") not in shown_paths:
                self._add_search_result(result, suggested=True)
                shown_paths.add(result.get("path", ""))

        if self.search_results.count() == 0:
            empty_text = f"No results for: {query}" if query else "No notes in this vault"
            self.search_results.addItem(empty_text)
        self._position_search_results()
        self.search_results.setVisible(True)
        self.search_results.raise_()

    def _on_search_result_clicked(self, item: QListWidgetItem) -> None:
        text = item.text()
        if not text or text.startswith("No results") or text == "No notes in this vault":
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            lines = text.splitlines()
            if len(lines) < 2:
                return
            path = lines[1].strip()
        if self.vault is not None:
            self._open_note_file(self.vault.path / path)
            self.search_results.setVisible(False)

    def _open_search(self) -> None:
        self.search_panel.setVisible(True)
        self.search_input.selectAll()
        self.perform_search()
        self.search_input.setFocus()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if watched is self.search_input:
                if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                    if self.search_results.count():
                        current_row = self.search_results.currentRow()
                        if current_row < 0:
                            current_row = -1 if key == Qt.Key.Key_Down else 0
                        next_row = current_row + (1 if key == Qt.Key.Key_Down else -1)
                        self.search_results.setCurrentRow(
                            next_row % self.search_results.count()
                        )
                    return True
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    item = self.search_results.currentItem() or self.search_results.item(0)
                    if item is not None:
                        self._on_search_result_clicked(item)
                    return True
                if key == Qt.Key.Key_Escape:
                    self.search_results.setVisible(False)
                    return True
            elif watched is self.search_results:
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    item = self.search_results.currentItem()
                    if item is not None:
                        self._on_search_result_clicked(item)
                    return True
                if key == Qt.Key.Key_Escape:
                    self.search_results.setVisible(False)
                    self.search_input.setFocus()
                    return True
                if key == Qt.Key.Key_Up and self.search_results.currentRow() <= 0:
                    self.search_input.setFocus()
                    return True
        return super().eventFilter(watched, event)

    def _available_templates(self) -> list[Path]:
        if self.vault is None:
            return []
        templates_dir = self.vault.path / TEMPLATES_FOLDER
        if not templates_dir.is_dir():
            return []
        return sorted(templates_dir.rglob("*.md"), key=lambda path: path.as_posix().lower())

    def _render_template_content(
        self,
        content: str,
        note_day: date | None = None,
        title: str | None = None,
        time_value: str | None = None,
    ) -> str:
        current_time = datetime.now()
        date_value = (note_day or current_time.date()).isoformat()
        title_value = title or (
            self.current_note_path.stem if self.current_note_path else date_value
        )
        replacements = {
            "{{date}}": date_value,
            "{{time}}": time_value or current_time.strftime("%H:%M"),
            "{{title}}": title_value,
        }
        for placeholder, value in replacements.items():
            content = content.replace(placeholder, value)
        return content

    def _insert_template_content(
        self,
        content: str,
        note_day: date | None = None,
        title: str | None = None,
        time_value: str | None = None,
    ) -> str:
        rendered = self._render_template_content(
            content, note_day=note_day, title=title, time_value=time_value
        )
        cursor = self.editor.textCursor()
        cursor.insertText(rendered)
        self.editor.setTextCursor(cursor)
        return rendered

    def _insert_template_file(self, template_path: Path) -> bool:
        if self.vault is None:
            return False
        templates_root = (self.vault.path / TEMPLATES_FOLDER).resolve()
        try:
            resolved_path = template_path.resolve()
            resolved_path.relative_to(templates_root)
        except (OSError, ValueError):
            QMessageBox.warning(self, "Invalid template", "Templates must be inside the Templates folder.")
            return False
        if not resolved_path.is_file() or resolved_path.suffix.lower() != ".md":
            return False
        self._insert_template_content(
            resolved_path.read_text(encoding="utf-8", errors="replace")
        )
        self.status_label.setText(f"Inserted template: {resolved_path.stem}")
        return True

    def _choose_template(self) -> None:
        templates = self._available_templates()
        if not templates:
            QMessageBox.information(
                self,
                "No templates",
                f"Add Markdown templates under the vault's {TEMPLATES_FOLDER} folder.",
            )
            return
        if self.vault is None:
            return
        labels = [path.relative_to(self.vault.path).as_posix() for path in templates]
        selected, accepted = QInputDialog.getItem(
            self, "Insert template", "Template:", labels, 0, False
        )
        if accepted:
            self._insert_template_file(self.vault.path / selected)

    def create_daily_note(self, note_day: date | None = None) -> Path | None:
        if self.vault is None:
            QMessageBox.warning(self, "No vault", "Select a vault before creating a daily note.")
            return None
        day = note_day or date.today()
        daily_dir = self.vault.path / DAILY_NOTES_FOLDER
        daily_dir.mkdir(parents=True, exist_ok=True)
        note_path = daily_dir / f"{day.isoformat()}.md"
        if not note_path.exists():
            template = next(
                (
                    path
                    for path in self._available_templates()
                    if path.stem.lower() in {"daily note", "daily"}
                ),
                None,
            )
            if template is not None:
                initial_content = self._render_template_content(
                    template.read_text(encoding="utf-8", errors="replace"),
                    note_day=day,
                    title=day.isoformat(),
                )
            else:
                initial_content = f"# {day.isoformat()}\n\n"
            note_path.write_text(initial_content, encoding="utf-8")
        self.vault.refresh()
        self.populate_note_tree()
        self._selected_folder_path = daily_dir
        self._open_note_file(note_path)
        self.status_label.setText(f"Daily note: {day.isoformat()}")
        return note_path

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

        daily_note_action = QAction("Create Daily Note", self)
        daily_note_action.setShortcut(QKeySequence("Ctrl+Shift+D"))
        daily_note_action.triggered.connect(lambda: self.create_daily_note())
        self.addAction(daily_note_action)

        insert_template_action = QAction("Insert Template", self)
        insert_template_action.setShortcut(QKeySequence("Ctrl+Shift+I"))
        insert_template_action.triggered.connect(lambda: self._choose_template())
        self.addAction(insert_template_action)

        quick_switcher_action = QAction("Quick Switcher", self)
        quick_switcher_action.setShortcut(QKeySequence("Ctrl+P"))
        quick_switcher_action.triggered.connect(self._open_search)
        self.addAction(quick_switcher_action)

        self.back_action = QAction("Previous Note", self)
        self.back_action.setShortcut(QKeySequence("Alt+Left"))
        self.back_action.triggered.connect(self._go_back_history)
        self.addAction(self.back_action)

        self.forward_action = QAction("Next Note", self)
        self.forward_action.setShortcut(QKeySequence("Alt+Right"))
        self.forward_action.triggered.connect(self._go_forward_history)
        self.addAction(self.forward_action)
        self._update_history_buttons()

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        relative_path = item.data(0, Qt.UserRole)
        if self.vault is None:
            return
        if item.data(0, VaultTreeWidget.IS_DIRECTORY_ROLE):
            self._selected_folder_path = self.vault.path / relative_path if relative_path else self.vault.path
            self.status_label.setText(f"Folder selected: {relative_path or self.vault.path.name}")
            return
        if not relative_path:
            return
        self._selected_folder_path = (self.vault.path / relative_path).parent
        self._open_note_file(self.vault.path / relative_path)

    def _build_tree_context_menu(self, item: QTreeWidgetItem) -> QMenu | None:
        relative_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not relative_path:
            return None

        is_directory = bool(item.data(0, VaultTreeWidget.IS_DIRECTORY_ROLE))
        menu = QMenu(self)
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        rename_action.triggered.connect(
            lambda _checked=False, path=relative_path: self._prompt_rename_vault_item(path)
        )
        delete_action.triggered.connect(
            lambda _checked=False, path=relative_path: self._confirm_delete_vault_item(path)
        )
        if not is_directory:
            duplicate_action = menu.addAction("Duplicate")
            duplicate_action.triggered.connect(
                lambda _checked=False, path=relative_path: self._duplicate_vault_note(path)
            )
        return menu

    def _show_tree_context_menu(self, position: QPoint) -> None:
        item = self.note_tree.itemAt(position)
        if item is None:
            return
        self.note_tree.setCurrentItem(item)
        menu = self._build_tree_context_menu(item)
        if menu is not None:
            menu.exec(self.note_tree.viewport().mapToGlobal(position))

    def _vault_item_path(self, relative_path: str) -> Path | None:
        if self.vault is None or not relative_path:
            return None
        item_path = self.vault.path / relative_path
        try:
            item_path.resolve().relative_to(self.vault.path.resolve())
        except (OSError, ValueError):
            return None
        return item_path if item_path.exists() else None

    def _prompt_rename_vault_item(self, relative_path: str) -> None:
        item_path = self._vault_item_path(relative_path)
        if item_path is None:
            return
        is_note = item_path.is_file()
        current_name = item_path.stem if is_note else item_path.name
        new_name, accepted = QInputDialog.getText(
            self, "Rename", "New name:", text=current_name
        )
        if accepted:
            self._rename_vault_item(relative_path, new_name)

    def _rename_vault_item(self, relative_path: str, new_name: str) -> bool:
        if self.vault is None:
            return False
        source = self._vault_item_path(relative_path)
        new_name = new_name.strip()
        if source is None:
            return False
        if (
            not new_name
            or new_name in {".", ".."}
            or any(character in new_name for character in '<>:"/\\|?*')
            or new_name.endswith((".", " "))
        ):
            QMessageBox.warning(self, "Invalid name", "Enter a valid file or folder name.")
            return False

        is_note = source.is_file()
        if is_note:
            if new_name.lower().endswith(".md"):
                new_name = new_name[:-3]
            if not new_name:
                QMessageBox.warning(self, "Invalid name", "A note name cannot be empty.")
                return False
            destination = source.with_name(f"{new_name}.md")
        else:
            destination = source.with_name(new_name)
        if destination == source:
            return True
        if destination.exists():
            QMessageBox.warning(self, "Name conflict", f"'{destination.name}' already exists.")
            return False

        old_relative = source.relative_to(self.vault.path).as_posix()
        new_relative = destination.relative_to(self.vault.path).as_posix()
        if is_note:
            renamed_notes = {old_relative: new_relative} if old_relative in self.vault.notes else {}
        else:
            prefix = f"{old_relative}/"
            renamed_notes = {
                note_path: f"{new_relative}/{note_path[len(prefix):]}"
                for note_path in self.vault.notes
                if note_path.startswith(prefix)
            }

        pending_contents: dict[str, str] = {}
        active_relative = None
        if self.current_note_path is not None:
            try:
                active_relative = self.current_note_path.relative_to(self.vault.path).as_posix()
            except ValueError:
                active_relative = None

        try:
            for note_path in self.vault.notes:
                path = self.vault.path / note_path
                open_editor = self._editor_for_relative_path(note_path)
                content = (
                    open_editor.toPlainText()
                    if open_editor is not None
                    else path.read_text(encoding="utf-8", errors="replace")
                )
                updated = content
                if is_note and note_path == old_relative:
                    lines = updated.splitlines(keepends=True)
                    for index, line in enumerate(lines):
                        heading = re.match(r"^(#\s+)(.*?)(\r?\n)?$", line)
                        if heading:
                            lines[index] = f"# {new_name}{heading.group(3) or ''}"
                            updated = "".join(lines)
                            break
                for old_path, new_path in renamed_notes.items():
                    updated = self._rewrite_wikilink_references(old_path, new_path, updated)
                if updated != content or note_path in renamed_notes:
                    pending_contents[note_path] = updated
                    if open_editor is not None:
                        open_editor.setPlainText(updated)

            source.rename(destination)
            for old_path, content in pending_contents.items():
                target_path = self.vault.path / renamed_notes.get(old_path, old_path)
                target_path.write_text(content, encoding="utf-8")
        except OSError as error:
            QMessageBox.warning(self, "Rename failed", str(error))
            self.vault.refresh()
            self.populate_note_tree()
            return False

        self._update_open_tab_paths(renamed_notes)
        if active_relative is not None:
            active_relative = renamed_notes.get(active_relative, active_relative)
            self.current_note_path = self.vault.path / active_relative
        if self._selected_folder_path is not None:
            try:
                selected_relative = self._selected_folder_path.relative_to(self.vault.path).as_posix()
                if selected_relative == old_relative or selected_relative.startswith(f"{old_relative}/"):
                    suffix = selected_relative[len(old_relative):].lstrip("/")
                    self._selected_folder_path = destination / suffix if suffix else destination
            except ValueError:
                pass

        self.vault.refresh()
        self.populate_note_tree()
        if self.current_note_path is not None and self.current_note_path.exists():
            self._open_note_file(self.current_note_path)
        self.status_label.setText(f"Renamed: {source.name} to {destination.name}")
        return True

    def _confirm_delete_vault_item(self, relative_path: str) -> bool:
        item_path = self._vault_item_path(relative_path)
        if item_path is None:
            return False
        answer = QMessageBox.question(
            self,
            "Delete",
            f"Delete '{item_path.name}'? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        return self._delete_vault_item(relative_path)

    def _delete_vault_item(self, relative_path: str) -> bool:
        if self.vault is None:
            return False
        item_path = self._vault_item_path(relative_path)
        if item_path is None:
            return False
        try:
            resolved = item_path.resolve()
            vault_root = self.vault.path.resolve()
            resolved.relative_to(vault_root)
            if item_path.is_symlink() or not item_path.is_dir():
                item_path.unlink()
            else:
                shutil.rmtree(item_path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Delete failed", str(error))
            return False

        removed_history_positions: list[int] = []
        for history_index, history_path in enumerate(self._note_history):
            try:
                Path(history_path).resolve().relative_to(resolved)
                removed_history_positions.append(history_index)
            except ValueError:
                continue
        old_history_index = self._note_history_index
        self._note_history = [
            history_path
            for history_path in self._note_history
            if not Path(history_path).resolve().is_relative_to(resolved)
        ]
        self._note_history_index = max(
            -1,
            old_history_index - sum(position <= old_history_index for position in removed_history_positions),
        )
        for tab_index in reversed(range(self.note_tabs.count())):
            page = self.note_tabs.widget(tab_index)
            try:
                Path(page.property("notePath")).resolve().relative_to(resolved)
            except (OSError, ValueError):
                continue
            self.note_tabs.removeTab(tab_index)
            page.deleteLater()

        if self.current_note_path is not None:
            try:
                self.current_note_path.resolve().relative_to(resolved)
                self.current_note_path = None
                self.editor.clear()
                self.backlinks_list.clear()
                self.unresolved_list.clear()
                self.outgoing_list.clear()
                self.graph_list.clear()
                self.tag_list.clear()
                self.tag_matches_list.clear()
                self.tag_matches_label.setVisible(False)
                self.tag_matches_list.setVisible(False)
                self._refresh_graph_panel()
            except ValueError:
                pass
        if self._selected_folder_path is not None:
            try:
                self._selected_folder_path.resolve().relative_to(resolved)
                self._selected_folder_path = self.vault.path
            except ValueError:
                pass

        self.vault.refresh()
        self.populate_note_tree()
        self.status_label.setText(f"Deleted: {item_path.name}")
        return True

    def _duplicate_vault_note(self, relative_path: str) -> Path | None:
        if self.vault is None:
            return None
        source = self._vault_item_path(relative_path)
        if source is None or not source.is_file() or source.suffix.lower() != ".md":
            return None

        copy_name = f"{source.stem} copy"
        destination = source.with_name(f"{copy_name}.md")
        index = 2
        while destination.exists():
            destination = source.with_name(f"{copy_name} {index}.md")
            index += 1
        try:
            shutil.copy2(source, destination)
        except OSError as error:
            QMessageBox.warning(self, "Duplicate failed", str(error))
            return None

        self.vault.refresh()
        self.populate_note_tree()
        self.status_label.setText(f"Duplicated: {source.name}")
        return destination

    def _move_failed(self, message: str) -> bool:
        QMessageBox.warning(self, "Move failed", message)
        if self.vault is not None:
            self.vault.refresh()
            self.populate_note_tree()
        return False

    def _move_tree_item(self, source_relative: str, target_relative: str) -> bool:
        if self.vault is None:
            return False

        source = self.vault.path / source_relative
        destination_parent = self.vault.path / target_relative if target_relative else self.vault.path
        destination = destination_parent / source.name

        try:
            source_resolved = source.resolve()
            destination_parent_resolved = destination_parent.resolve()
            vault_root = self.vault.path.resolve()
        except OSError:
            return self._move_failed("The selected path could not be resolved.")

        if not source.exists() or not destination_parent.is_dir():
            return self._move_failed("The selected file or destination folder is missing.")
        if source_resolved == destination_parent_resolved:
            return False
        if source.is_dir() and destination_parent_resolved.is_relative_to(source_resolved):
            return self._move_failed("A folder cannot be moved inside itself.")
        if not destination_parent_resolved.is_relative_to(vault_root):
            return self._move_failed("Items can only be moved inside the selected vault.")
        if destination.exists():
            return self._move_failed(f"An item named '{source.name}' already exists there.")

        source_was_directory = source.is_dir()
        source_relative = source.relative_to(self.vault.path).as_posix()
        destination_relative = destination.relative_to(self.vault.path).as_posix()
        if source_was_directory:
            prefix = f"{source_relative}/"
            moved_notes = {
                note_path: f"{destination_relative}/{note_path[len(prefix):]}"
                for note_path in self.vault.notes
                if note_path.startswith(prefix)
            }
        else:
            moved_notes = (
                {source_relative: destination_relative}
                if source_relative in self.vault.notes
                else {}
            )
        current_note = self.current_note_path
        try:
            source.rename(destination)
        except OSError as error:
            return self._move_failed(str(error))

        self._update_open_tab_paths(moved_notes)

        if current_note is not None:
            try:
                current_resolved = current_note.resolve()
                if current_resolved == source_resolved or (
                    source_was_directory and current_resolved.is_relative_to(source_resolved)
                ):
                    self.current_note_path = destination / current_resolved.relative_to(source_resolved)
            except OSError:
                self.current_note_path = None

        self.vault.refresh()
        self.populate_note_tree()
        if self.current_note_path is not None and self.current_note_path.exists():
            self._open_note_file(self.current_note_path)
        self.status_label.setText(f"Moved: {source.name}")
        return True

    def populate_note_tree(self) -> None:
        self.note_tree.clear()
        if self.vault is None:
            return

        root_item = QTreeWidgetItem([self.vault.path.name])
        root_item.setData(0, Qt.UserRole, "")
        root_item.setData(0, VaultTreeWidget.IS_DIRECTORY_ROLE, True)
        root_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
        root_item.setFlags(root_item.flags() | Qt.ItemFlag.ItemIsDropEnabled)
        self.note_tree.addTopLevelItem(root_item)

        paths: set[str] = set(self.vault.notes.keys())
        for directory in self.vault.path.rglob("*"):
            if directory.is_dir():
                paths.add(directory.relative_to(self.vault.path).as_posix())

        for raw_path in sorted(paths, key=lambda path: (path.count("/"), path)):
            parts = raw_path.split("/")
            current_item = root_item
            for part_index, part in enumerate(parts):
                child_match = None
                for child_index in range(current_item.childCount()):
                    candidate = current_item.child(child_index)
                    if candidate.text(0) == part:
                        child_match = candidate
                        break
                if child_match is None:
                    child_match = QTreeWidgetItem([part])
                    current_item.addChild(child_match)
                current_item = child_match
                if part_index == len(parts) - 1:
                    current_item.setData(0, Qt.UserRole, raw_path)
                    current_item.setData(0, VaultTreeWidget.IS_DIRECTORY_ROLE, raw_path not in self.vault.notes)
                else:
                    current_item.setData(0, Qt.UserRole, "/".join(parts[: part_index + 1]))
                    current_item.setData(0, VaultTreeWidget.IS_DIRECTORY_ROLE, True)

                flags = current_item.flags() | Qt.ItemFlag.ItemIsDragEnabled
                if current_item.data(0, VaultTreeWidget.IS_DIRECTORY_ROLE):
                    flags |= Qt.ItemFlag.ItemIsDropEnabled
                    current_item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                current_item.setFlags(flags)

        self._add_empty_folder_indicators(root_item)
        self.note_tree.expandAll()
        self._refresh_search_index()
        self._refresh_graph_panel()
        if self._graph_tab_page is not None:
            self._graph_tab_page.refresh()

    def _add_empty_folder_indicators(self, item: QTreeWidgetItem) -> None:
        is_directory = bool(item.data(0, VaultTreeWidget.IS_DIRECTORY_ROLE))
        if is_directory and item.childCount() == 0:
            hidden_child = QTreeWidgetItem([""])
            hidden_child.setFlags(Qt.ItemFlag.NoItemFlags)
            item.addChild(hidden_child)
            hidden_child.setSizeHint(0, QSize(0, 0))
            return

        for child_index in range(item.childCount()):
            self._add_empty_folder_indicators(item.child(child_index))

    def _create_note_editor(self) -> MarkdownEditor:
        editor = MarkdownEditor()
        editor_palette = editor.palette()
        editor_palette.setColor(QPalette.ColorRole.Base, QColor("#202020"))
        editor_palette.setColor(QPalette.ColorRole.Text, QColor("#d6d3d1"))
        editor_palette.setColor(QPalette.ColorRole.Mid, QColor("#8f8991"))
        editor_palette.setColor(QPalette.ColorRole.Link, QColor("#9b8afa"))
        editor.setPalette(editor_palette)
        editor.setPlaceholderText("Write a note in Markdown...")
        editor.setMinimumHeight(340)
        editor.setStyleSheet(
            """
            QTextEdit {
                font-family: Consolas;
                font-size: 13px;
                line-height: 1.6;
                padding: 14px 16px;
                background: #202020;
                color: #d6d3d1;
                selection-background-color: #5a4b80;
            }
            """
        )
        editor.linkActivated.connect(self._open_note_from_reference)
        editor.linkHovered.connect(self._show_editor_link_tooltip)
        editor.document().modificationChanged.connect(
            lambda modified, current_editor=editor: self._update_note_tab_modified(
                current_editor, modified
            )
        )
        return editor

    @staticmethod
    def _tab_editor(page: QWidget) -> MarkdownEditor:
        layout = page.layout()
        editor = layout.itemAt(0).widget() if layout is not None else None
        if not isinstance(editor, MarkdownEditor):
            raise RuntimeError("Note tab is missing its Markdown editor")
        return editor

    def _find_note_tab(self, file_path: Path) -> int:
        expected_path = str(file_path.resolve())
        for index in range(self.note_tabs.count()):
            page = self.note_tabs.widget(index)
            if page.property("notePath") == expected_path:
                return index
        return -1

    def _editor_for_relative_path(self, relative_path: str) -> MarkdownEditor | None:
        if self.vault is None:
            return None
        index = self._find_note_tab(self.vault.path / relative_path)
        if index < 0:
            return None
        return self._tab_editor(self.note_tabs.widget(index))

    def _record_note_history(self, file_path: Path) -> None:
        if self._history_navigation:
            return
        path_value = str(file_path.resolve())
        if self._note_history_index >= 0 and self._note_history[self._note_history_index] == path_value:
            return
        self._note_history = self._note_history[: self._note_history_index + 1]
        self._note_history.append(path_value)
        self._note_history_index = len(self._note_history) - 1
        self._update_history_buttons()

    def _update_history_buttons(self) -> None:
        if not hasattr(self, "back_action"):
            return
        self.back_action.setEnabled(self._note_history_index > 0)
        self.forward_action.setEnabled(
            self._note_history_index >= 0
            and self._note_history_index < len(self._note_history) - 1
        )

    def _set_note_tab_title(self, index: int, title: str) -> None:
        page = self.note_tabs.widget(index)
        page.setProperty("tabTitle", title)
        self.note_tabs.setTabText(
            index, f"{title}*" if page.property("modified") else title
        )

    def _update_note_tab_modified(self, editor: MarkdownEditor, modified: bool) -> None:
        for index in range(self.note_tabs.count()):
            page = self.note_tabs.widget(index)
            if self._tab_editor(page) is editor:
                page.setProperty("modified", modified)
                title = page.property("tabTitle") or Path(page.property("notePath")).stem
                self.note_tabs.setTabText(index, f"{title}*" if modified else title)
                return

    def _navigate_history(self, offset: int) -> None:
        target_index = self._note_history_index + offset
        if target_index < 0 or target_index >= len(self._note_history):
            return
        target_path = Path(self._note_history[target_index])
        if not target_path.exists():
            self._note_history.pop(target_index)
            self._note_history_index = min(self._note_history_index, len(self._note_history) - 1)
            self._update_history_buttons()
            return
        self._history_navigation = True
        try:
            self._open_note_file(target_path)
            self._note_history_index = target_index
        finally:
            self._history_navigation = False
        self._update_history_buttons()

    def _go_back_history(self) -> None:
        self._navigate_history(-1)

    def _go_forward_history(self) -> None:
        self._navigate_history(1)

    def _on_note_tab_changed(self, index: int) -> None:
        if index < 0:
            self.current_note_path = None
            self.title_input.clear()
            self.breadcrumb_label.clear()
            self.backlinks_list.clear()
            self.unresolved_list.clear()
            self.outgoing_list.clear()
            self.graph_list.clear()
            self.tag_list.clear()
            self.tag_matches_list.clear()
            self.tag_matches_label.setVisible(False)
            self.tag_matches_list.setVisible(False)
            self.editor = self._create_note_editor()
            self._update_history_buttons()
            self._refresh_graph_panel()
            return

        page = self.note_tabs.widget(index)
        if isinstance(page, GraphTabWidget):
            page.refresh()
            return
        path_value = page.property("notePath")
        if not path_value:
            return
        self.editor = self._tab_editor(page)
        self.current_note_path = Path(path_value)
        relative_path = self.current_note_path.relative_to(self.vault.path).as_posix() if self.vault else self.current_note_path.name
        note = self.vault.notes.get(relative_path) if self.vault else None
        self.title_input.setText(note.title if note else self.current_note_path.stem)
        self._selected_folder_path = self.current_note_path.parent
        self.breadcrumb_label.setText(str(self.current_note_path))
        self.status_label.setText(f"Open note: {relative_path}")
        self._refresh_related_lists()
        self._record_note_history(self.current_note_path)

    def _update_open_tab_paths(self, path_changes: dict[str, str]) -> None:
        if self.vault is None or not path_changes:
            return
        for index in range(self.note_tabs.count()):
            page = self.note_tabs.widget(index)
            if not page.property("notePath"):
                continue
            old_path = Path(page.property("notePath"))
            try:
                old_relative = old_path.relative_to(self.vault.path).as_posix()
            except ValueError:
                continue
            new_relative = path_changes.get(old_relative)
            if new_relative is None:
                continue
            new_path = self.vault.path / new_relative
            page.setProperty("notePath", str(new_path.resolve()))
            self._set_note_tab_title(index, new_path.stem)
            self.note_tabs.setTabToolTip(index, new_relative)
        updated_history: list[str] = []
        for history_path in self._note_history:
            path = Path(history_path)
            try:
                relative_path = path.relative_to(self.vault.path).as_posix()
            except ValueError:
                updated_history.append(history_path)
                continue
            new_relative = path_changes.get(relative_path)
            updated_history.append(
                str((self.vault.path / new_relative).resolve())
                if new_relative is not None
                else history_path
            )
        self._note_history = updated_history
        current_page = self.note_tabs.currentWidget()
        if current_page is not None:
            current_path = current_page.property("notePath")
            self.current_note_path = Path(current_path) if current_path else None
        self._update_history_buttons()

    def _reset_open_notes(self) -> None:
        while self.note_tabs.count():
            page = self.note_tabs.widget(0)
            self.note_tabs.removeTab(0)
            page.deleteLater()
        self._graph_tab_page = None
        self.current_note_path = None
        self._note_history.clear()
        self._note_history_index = -1
        self.editor = self._create_note_editor()
        self._update_history_buttons()

    def _close_note_tab(self, index: int) -> None:
        page = self.note_tabs.widget(index)
        if isinstance(page, GraphTabWidget):
            self._close_graph_tab()
            return
        editor = self._tab_editor(page)
        if editor.document().isModified():
            answer = QMessageBox.question(
                self,
                "Unsaved note",
                f"Save changes to '{self.note_tabs.tabText(index)}' before closing?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if answer == QMessageBox.StandardButton.Cancel:
                return
            if answer == QMessageBox.StandardButton.Save:
                self.note_tabs.setCurrentIndex(index)
                self.save_current_note()
                if editor.document().isModified():
                    return
        self.note_tabs.removeTab(index)
        page.deleteLater()

    def _close_note_page(self, page: QWidget) -> None:
        index = self.note_tabs.indexOf(page)
        if index >= 0:
            self._close_note_tab(index)

    def _add_tab_close_button(self, index: int, page: QWidget, tooltip: str, on_close) -> None:
        close_button = QToolButton(self.note_tabs.tabBar())
        close_button.setIcon(_sidebar_action_icon("close"))
        close_button.setIconSize(QSize(12, 12))
        close_button.setFixedSize(20, 20)
        close_button.setAutoRaise(True)
        close_button.setToolTip(tooltip)
        close_button.setStyleSheet(
            "QToolButton { background: transparent; border: 0; padding: 2px; }"
            "QToolButton:hover { background: #3b383d; border-radius: 4px; }"
        )
        close_button.clicked.connect(lambda _checked=False: on_close(page))
        self.note_tabs.tabBar().setTabButton(
            index, QTabBar.ButtonPosition.RightSide, close_button
        )

    def _open_full_graph_tab(self) -> None:
        if self.vault is None:
            QMessageBox.warning(self, "No vault", "Select a vault before opening the graph.")
            return
        if self._graph_tab_page is not None:
            index = self.note_tabs.indexOf(self._graph_tab_page)
            if index >= 0:
                self.note_tabs.setCurrentIndex(index)
                self._graph_tab_page.refresh()
                return
            self._graph_tab_page = None

        page = GraphTabWidget(self)
        index = self.note_tabs.addTab(page, "Graph")
        self.note_tabs.setTabToolTip(index, "Full vault graph")
        self._add_tab_close_button(
            index, page, "Close graph", lambda _page: self._close_graph_tab()
        )
        self._graph_tab_page = page
        self.note_tabs.setCurrentIndex(index)
        page.refresh()

    def _close_graph_tab(self) -> None:
        if self._graph_tab_page is None:
            return
        page = self._graph_tab_page
        self._graph_tab_page = None
        index = self.note_tabs.indexOf(page)
        if index >= 0:
            self.note_tabs.removeTab(index)
        page.stop()
        page.deleteLater()

    def _open_note_file(self, file_path: Path) -> None:
        if not file_path.exists():
            QMessageBox.warning(self, "Missing note", f"The note was not found: {file_path}")
            return

        file_path = file_path.resolve()
        existing_index = self._find_note_tab(file_path)
        if existing_index >= 0:
            self.note_tabs.setCurrentIndex(existing_index)
            return

        page = QWidget()
        page.setProperty("notePath", str(file_path))
        page.setProperty("tabTitle", file_path.stem)
        page.setProperty("modified", False)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        if self.note_tabs.count() == 0 and self.editor.parentWidget() is None:
            editor = self.editor
        else:
            editor = self._create_note_editor()
        editor.setPlainText(file_path.read_text(encoding="utf-8", errors="replace"))
        editor.document().setModified(False)
        page_layout.addWidget(editor)
        relative_path = (
            file_path.relative_to(self.vault.path).as_posix()
            if self.vault is not None
            else file_path.name
        )
        index = self.note_tabs.addTab(page, file_path.stem)
        self.note_tabs.setTabToolTip(index, relative_path)
        self._add_tab_close_button(index, page, "Close note", self._close_note_page)
        self.note_tabs.setCurrentIndex(index)

    def _refresh_related_lists(self) -> None:
        if self.vault is None or self.current_note_path is None:
            if hasattr(self, "properties_table"):
                self.properties_table.setRowCount(0)
            return

        rel_path = self.current_note_path.relative_to(self.vault.path).as_posix()
        note = self.vault.notes.get(rel_path)
        if note is None:
            return

        self._refresh_properties_table()

        self.backlinks_list.clear()
        self.unresolved_list.clear()
        self.outgoing_list.clear()
        self.graph_list.clear()
        self.tag_list.clear()
        self.tag_matches_list.clear()
        self.tag_matches_label.setVisible(False)
        self.tag_matches_list.setVisible(False)
        self._refresh_graph_panel()

        for backlink in note.backlinks:
            self.backlinks_list.addItem(backlink)
        for unresolved in note.unresolved_links:
            self.unresolved_list.addItem(unresolved)
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
        if self.unresolved_list.count() == 0:
            self.unresolved_list.addItem("No unresolved links")
        if self.outgoing_list.count() == 0:
            self.outgoing_list.addItem("No outgoing links")
        if self.graph_list.count() == 0:
            self.graph_list.addItem("No connected notes")

    def _refresh_properties_table(self) -> None:
        if self.current_note_path is None:
            self.properties_table.setRowCount(0)
            return
        metadata, _body = extract_frontmatter(self.editor.toPlainText())
        self.properties_table.setRowCount(0)
        for key, value in metadata.items():
            row = self.properties_table.rowCount()
            self.properties_table.insertRow(row)
            self.properties_table.setItem(row, 0, QTableWidgetItem(key))
            self.properties_table.setItem(row, 1, QTableWidgetItem(value))

    def _add_property_row(self) -> None:
        row = self.properties_table.rowCount()
        self.properties_table.insertRow(row)
        self.properties_table.setItem(row, 0, QTableWidgetItem(""))
        self.properties_table.setItem(row, 1, QTableWidgetItem(""))
        self.properties_table.setCurrentCell(row, 0)
        self.properties_table.editItem(self.properties_table.item(row, 0))

    def _remove_property_row(self) -> None:
        selected_rows = sorted(
            {index.row() for index in self.properties_table.selectionModel().selectedRows()},
            reverse=True,
        )
        if not selected_rows and self.properties_table.currentRow() >= 0:
            selected_rows = [self.properties_table.currentRow()]
        for row in selected_rows:
            self.properties_table.removeRow(row)

    def _apply_properties_to_note(self) -> bool:
        if self.current_note_path is None:
            return False
        properties: dict[str, str] = {}
        for row in range(self.properties_table.rowCount()):
            key_item = self.properties_table.item(row, 0)
            value_item = self.properties_table.item(row, 1)
            key = key_item.text().strip() if key_item else ""
            value = value_item.text() if value_item else ""
            if not key and not value:
                continue
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key):
                QMessageBox.warning(
                    self,
                    "Invalid property",
                    "Property names must start with a letter or underscore and contain only letters, numbers, underscores, or hyphens.",
                )
                return False
            if key in properties:
                QMessageBox.warning(
                    self, "Duplicate property", f"'{key}' appears more than once."
                )
                return False
            properties[key] = value

        try:
            updated = set_frontmatter(self.editor.toPlainText(), properties)
        except ValueError as error:
            QMessageBox.warning(self, "Invalid properties", str(error))
            return False
        self.editor.setPlainText(updated)
        self.editor.document().setModified(True)
        self._update_note_tab_modified(self.editor, True)
        self.status_label.setText("Properties applied. Save to write changes.")
        return True

    def _refresh_graph_panel(self) -> None:
        if not hasattr(self, "graph_scene"):
            return
        if self.vault is None:
            self.graph_scene.clear()
            self._graph_simulation.stop()
            return
        if self.current_note_path is None:
            self.graph_scene.clear()
            self._graph_simulation.stop()
            return
        rel_path = self.current_note_path.relative_to(self.vault.path).as_posix()
        note = self.vault.notes.get(rel_path)
        if note is None:
            return

        node_entries = [(rel_path, note.title)]
        edge_pairs: list[tuple[str, str]] = []
        seen = {rel_path}
        for reference in note.backlinks + note.outgoing_links:
            if reference in seen:
                continue
            seen.add(reference)
            related_note = self.vault.notes.get(reference)
            node_entries.append((reference, related_note.title if related_note else Path(reference).stem))
            edge_pairs.append((rel_path, reference))
        self._render_graph(self._graph_surface, node_entries, edge_pairs, rel_path)

    def _render_full_vault_graph_into(self, page: "GraphTabWidget") -> None:
        if self.vault is None:
            self._render_graph(page.surface, [], [], None, empty_message="No vault selected")
            return

        tags = sorted({tag for note in self.vault.notes.values() for tag in note.tags}, key=str.lower)
        paths = sorted(
            {
                parent.as_posix()
                for relative_path in self.vault.notes
                if (parent := Path(relative_path).parent).as_posix() != "."
            },
            key=str.lower,
        )
        self._populate_filter_combo(page.tag_filter, "All tags", tags, prefix="#")
        self._populate_filter_combo(page.path_filter, "All paths", paths)

        if not self.vault.notes:
            self._render_graph(page.surface, [], [], None, empty_message="No notes in this vault")
            return

        tag_filter = page.tag_filter.currentData() or ""
        path_filter = (page.path_filter.currentData() or "").strip("/")

        def included(relative_path: str, note) -> bool:
            if tag_filter and tag_filter not in note.tags:
                return False
            if path_filter and not (
                relative_path == path_filter or relative_path.startswith(f"{path_filter}/")
            ):
                return False
            return True

        filtered = {
            relative_path: note
            for relative_path, note in self.vault.notes.items()
            if included(relative_path, note)
        }
        if not filtered:
            self._render_graph(page.surface, [], [], None, empty_message="No notes match the current filters")
            return

        node_entries = [(relative_path, note.title) for relative_path, note in filtered.items()]
        edge_pairs = [
            (relative_path, target)
            for relative_path, note in filtered.items()
            for target in note.outgoing_links
            if target in filtered
        ]

        current_relative = None
        if self.current_note_path is not None:
            try:
                current_relative = self.current_note_path.relative_to(self.vault.path).as_posix()
            except ValueError:
                current_relative = None

        self._render_graph(page.surface, node_entries, edge_pairs, current_relative)

    def _render_graph(
        self,
        surface: GraphSurface,
        node_entries: list[tuple[str, str]],
        edge_pairs: list[tuple[str, str]],
        current_reference: str | None,
        empty_message: str = "No connected notes",
    ) -> None:
        surface.scene.clear()
        surface.simulation.stop()
        surface.nodes = {}
        surface.edges = []
        if not node_entries:
            self._show_empty_graph_message(surface, empty_message)
            return

        degree: dict[str, int] = {reference: 0 for reference, _label in node_entries}
        for source, target in edge_pairs:
            if source in degree:
                degree[source] += 1
            if target in degree:
                degree[target] += 1

        graph = nx.Graph()
        graph.add_nodes_from(degree)
        graph.add_edges_from(pair for pair in edge_pairs if pair[0] in degree and pair[1] in degree)

        if len(degree) == 1:
            positions = {next(iter(degree)): (0.0, 0.0)}
        else:
            positions = nx.spring_layout(graph, seed=7, k=1.4 / (len(degree) ** 0.5))

        scale = 200.0
        nodes: dict[str, GraphNodeItem] = {}
        for reference, label in node_entries:
            is_current = reference == current_reference
            node = GraphNodeItem(
                label,
                reference,
                self._open_note_from_reference,
                on_hover=lambda node, entering, surface=surface: self._on_graph_node_hover(surface, node, entering),
                on_drag_end=surface.simulation.wake,
                radius=14 + min(16, degree.get(reference, 0) * 3),
                base_color=QColor("#4b3920") if is_current else QColor("#25233b"),
                hover_color=QColor("#5c4626") if is_current else QColor("#3b3560"),
                border_color=QColor("#d7a84b") if is_current else QColor("#8176e8"),
                text_color=QColor("#fff4d1") if is_current else QColor("#d7d4dc"),
            )
            x, y = positions.get(reference, (0.0, 0.0))
            node.setPos(x * scale, y * scale)
            nodes[reference] = node
            surface.scene.addItem(node)

        edges: list[GraphEdgeItem] = []
        edge_pen = QPen(QColor("#4b4658"), 1.4)
        for source, target in graph.edges():
            edge = GraphEdgeItem(nodes[source], nodes[target], edge_pen)
            nodes[source].edges.append(edge)
            nodes[target].edges.append(edge)
            surface.scene.addItem(edge)
            edges.append(edge)
        for node in nodes.values():
            node.setZValue(2)

        surface.nodes = nodes
        surface.edges = edges
        surface.simulation.set_graph(list(nodes.values()), edges)

        positions_px = [(node.x(), node.y()) for node in nodes.values()]
        margin = 90
        min_x = min(x for x, _ in positions_px) - margin
        max_x = max(x for x, _ in positions_px) + margin
        min_y = min(y for _, y in positions_px) - margin
        max_y = max(y for _, y in positions_px) + margin
        surface.scene.setSceneRect(min_x, min_y, max_x - min_x, max_y - min_y)
        surface.view.fitInView(surface.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _on_graph_node_hover(self, surface: GraphSurface, node: GraphNodeItem, entering: bool) -> None:
        if entering:
            connected = {node}
            for edge in surface.edges:
                if edge.source is node:
                    connected.add(edge.target)
                elif edge.target is node:
                    connected.add(edge.source)
            for other in surface.nodes.values():
                other.setOpacity(1.0 if other in connected else 0.25)
            for edge in surface.edges:
                edge.setOpacity(1.0 if edge.source in connected and edge.target in connected else 0.12)
        else:
            for other in surface.nodes.values():
                other.setOpacity(1.0)
            for edge in surface.edges:
                edge.setOpacity(1.0)

    def _show_empty_graph_message(self, surface: GraphSurface, message: str) -> None:
        empty_label = surface.scene.addText(message, QFont("Segoe UI", 9))
        empty_label.setDefaultTextColor(QColor("#89899a"))
        empty_label.setPos(-len(message) * 3, -8)
        surface.scene.setSceneRect(-150, -90, 300, 180)
        surface.view.fitInView(surface.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def _on_list_item_open(self, item) -> None:
        text = item.text()
        if not text or text.startswith("No "):
            return
        self._open_note_from_reference(text)

    def _on_unresolved_link_open(self, item) -> None:
        target = item.text()
        if not target or target == "No unresolved links":
            return
        self._open_note_from_reference(target)

    def _on_tag_clicked(self, item) -> None:
        text = item.text()
        if not text or text == "No tags":
            return
        self._show_tag_matches(text.lstrip("#"))

    def _show_tag_matches(self, tag: str) -> None:
        self.tag_matches_list.clear()
        if self.vault is None:
            return
        matches = sorted(
            (
                (note.title, relative_path)
                for relative_path, note in self.vault.notes.items()
                if tag in note.tags
            ),
            key=lambda entry: entry[0].lower(),
        )
        for title, relative_path in matches:
            list_item = QListWidgetItem(f"{title}\n{relative_path}")
            list_item.setData(Qt.ItemDataRole.UserRole, relative_path)
            self.tag_matches_list.addItem(list_item)
        self.tag_matches_label.setText(f"Notes tagged #{tag} ({len(matches)})")
        self.tag_matches_label.setVisible(True)
        self.tag_matches_list.setVisible(True)

    def _on_tag_match_open(self, item: QListWidgetItem) -> None:
        relative_path = item.data(Qt.ItemDataRole.UserRole)
        if relative_path and self.vault is not None:
            self._open_note_file(self.vault.path / relative_path)

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
            resolved = self.vault.create_note_for_reference(target)
            if resolved is None:
                QMessageBox.warning(self, "Invalid note link", f"Cannot create a note for: {target}")
                return
            self.vault.refresh()
            self.populate_note_tree()
        self._open_note_file(self.vault.path / resolved)

    def _show_editor_link_tooltip(self, reference: str) -> None:
        if not reference or self.vault is None:
            QToolTip.hideText()
            return
        target = reference.split("#", 1)[0]
        resolved = self.vault.resolve_reference(target)
        message = f"{target} ({resolved})" if resolved else f"Unresolved note: {target}"
        QToolTip.showText(QCursor.pos(), message, self.editor)

    def _rewrite_wikilink_references(self, old_path: str, new_path: str, content: str) -> str:
        pattern = re.compile(r"\[\[([^\]|#]+?)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]")

        def replace(match: re.Match[str]) -> str:
            target = match.group(1).strip()
            heading = match.group(2)
            alias = match.group(3)
            if self.vault is None or self.vault.resolve_reference(target) != old_path:
                return match.group(0)

            target = new_path if target.lower().endswith(".md") else Path(new_path).with_suffix("").as_posix()
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
        safe_name = f"{desired_title}.md"
        if safe_name == current_name:
            return

        destination = self.current_note_path.with_name(safe_name)
        if destination.exists() and destination != self.current_note_path:
            QMessageBox.warning(self, "Name conflict", f"A note named '{safe_name}' already exists in this folder.")
            return

        old_relative_path = self.current_note_path.relative_to(self.vault.path).as_posix()
        new_relative_path = destination.relative_to(self.vault.path).as_posix()
        for relative_path in list(self.vault.notes):
            path = self.vault.path / relative_path
            source_content = (
                self.editor.toPlainText()
                if relative_path == old_relative_path
                else path.read_text(encoding="utf-8", errors="replace")
            )
            updated_content = self._rewrite_wikilink_references(
                old_relative_path, new_relative_path, source_content
            )
            if updated_content != source_content:
                if relative_path == old_relative_path:
                    self.editor.setPlainText(updated_content)
                else:
                    path.write_text(updated_content, encoding="utf-8")

        self.current_note_path.rename(destination)
        self.current_note_path = destination
        self._update_open_tab_paths({old_relative_path: new_relative_path})

    def save_current_note(self) -> None:
        if self.current_note_path is None:
            QMessageBox.information(self, "No note selected", "Select or create a note before saving.")
            return

        self._rename_note_file_if_needed()
        self.current_note_path.write_text(self.editor.toPlainText(), encoding="utf-8")
        self.editor.document().setModified(False)
        if self.note_tabs.currentIndex() >= 0:
            self._set_note_tab_title(
                self.note_tabs.currentIndex(), self.current_note_path.stem
            )
        self.status_label.setText(f"Saved: {self.current_note_path.name}")
        if self.vault is not None:
            self.vault.refresh()
            self.populate_note_tree()
            self._refresh_related_lists()

    def new_note(self) -> None:
        if self.vault is None:
            QMessageBox.warning(self, "No vault", "Select a vault before creating a note.")
            return

        target_folder = self._selected_folder_path or self.vault.path
        if not target_folder.exists() or not target_folder.is_dir():
            target_folder = self.vault.path

        base_name = "Untitled.md"
        candidate = target_folder / base_name
        index = 1
        while candidate.exists():
            candidate = target_folder / f"Untitled_{index}.md"
            index += 1

        candidate.write_text("# Untitled\n\n", encoding="utf-8")
        self.vault.refresh()
        self.populate_note_tree()
        self._open_note_file(candidate)

    def new_folder(self) -> None:
        if self.vault is None:
            QMessageBox.warning(self, "No vault", "Select a vault before creating a folder.")
            return

        folder_name, accepted = QInputDialog.getText(
            self,
            "New folder",
            "Folder name:",
            text="New folder",
        )
        if not accepted:
            return

        folder_name = folder_name.strip()
        if not folder_name or folder_name in {".", ".."} or "/" in folder_name or "\\" in folder_name:
            QMessageBox.warning(self, "Invalid folder name", "Use a folder name without path separators.")
            return

        target_folder = self._selected_folder_path or self.vault.path
        if not target_folder.exists() or not target_folder.is_dir():
            target_folder = self.vault.path
        folder_path = target_folder / folder_name
        if folder_path.exists():
            QMessageBox.warning(self, "Folder exists", f"A folder named '{folder_name}' already exists.")
            return

        folder_path.mkdir()
        self.populate_note_tree()
        self.status_label.setText(f"Created folder: {folder_name}")

    def select_vault(self) -> None:
        vault_dir = QFileDialog.getExistingDirectory(
            self,
            "Select vault folder",
            str(Path.home()),
        )
        if not vault_dir:
            return

        self._reset_open_notes()
        self._vault_path = Path(vault_dir)
        self.vault = Vault(self._vault_path)
        self._selected_folder_path = self._vault_path
        self.vault.refresh()
        self.vault_label.setText("")
        self.breadcrumb_label.setText(str(self._vault_path))
        self.populate_note_tree()
        self._start_vault_watcher()
        self.status_label.setText(f"Vault selected: {self._vault_path.name}")

        if self.vault.notes:
            first_note = sorted(self.vault.notes)[0]
            self._open_note_file(self._vault_path / first_note)
        else:
            self.editor.clear()


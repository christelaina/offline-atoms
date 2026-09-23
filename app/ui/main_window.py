from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Local Knowledge Vault")
        self.resize(1400, 900)

        self._vault_path: Path | None = None
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

        header.addWidget(self.vault_label)
        header.addWidget(self.select_vault_button)
        root_layout.addLayout(header)

        editor = QTextEdit()
        editor.setPlaceholderText("Editor placeholder. A note editor will be implemented in later phases.")
        editor.setMinimumHeight(300)
        root_layout.addWidget(editor)

        self.status_label = QLabel("Phase 1: application shell ready")
        root_layout.addWidget(self.status_label)

    def select_vault(self) -> None:
        vault_dir = QFileDialog.getExistingDirectory(
            self,
            "Select vault folder",
            str(Path.home()),
        )
        if not vault_dir:
            return

        self._vault_path = Path(vault_dir)
        self.vault_label.setText(f"Vault: {self._vault_path}")
        self.status_label.setText(f"Vault selected: {self._vault_path.name}")

        QMessageBox.information(
            self,
            "Vault selected",
            f"Selected vault: {self._vault_path}\n\nThe next phases will add indexing, notes, links, and graph support.",
        )

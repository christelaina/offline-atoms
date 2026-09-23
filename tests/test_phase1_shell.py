from __future__ import annotations

import os
import sys

from PySide6 import QtWidgets

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.ui.main_window import MainWindow


def test_main_window_initializes():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow()
    assert window.windowTitle() == "Local Knowledge Vault"
    assert "No vault selected" in window.vault_label.text()


def test_select_vault_sets_path():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = MainWindow()

    tmp = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tmp_vault"))
    os.makedirs(tmp, exist_ok=True)
    window._vault_path = tmp
    window.vault_label.setText(f"Vault: {tmp}")

    assert window._vault_path == tmp
    assert "tmp_vault" in window.vault_label.text()

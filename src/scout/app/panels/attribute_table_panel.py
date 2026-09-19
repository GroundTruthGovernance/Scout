"""The Attribute Table dock — a spreadsheet-style view over Samples (and,
as they're wired up, Probes/Responses/Pins) with multi-select delete/
archive. This is the concrete fix for "no remove/archive pin control yet"
in the GEE prototype's bug list, and the basis for ad-hoc multi-select
comparison (barcode/heatstrip, pairwise cosine-similarity matrix).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

COLUMNS = ["sample_id", "sample_name", "field_code", "sample_role", "sample_type",
           "record_status", "created_utc"]


class AttributeTablePanel(QWidget):
    archive_requested = Signal(list)     # list of sample_id
    delete_requested = Signal(list)
    compare_selected_requested = Signal(list)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.table = QTableWidget(0, len(COLUMNS), self)
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)

    def load_samples(self, rows) -> None:
        self.table.setRowCount(0)
        for row in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, col in enumerate(COLUMNS):
                self.table.setItem(r, c, QTableWidgetItem(str(row[col] if row[col] is not None else "")))

    def selected_sample_ids(self) -> list[str]:
        ids = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 0)
            if item is not None:
                ids.append(item.text())
        return ids

    def _show_context_menu(self, pos) -> None:
        ids = self.selected_sample_ids()
        if not ids:
            return
        menu = QMenu(self)
        archive_action = menu.addAction(f"Archive {len(ids)} selected")
        delete_action = menu.addAction(f"Delete {len(ids)} selected")
        menu.addSeparator()
        compare_action = menu.addAction(f"Compare {len(ids)} selected…")
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is archive_action:
            self.archive_requested.emit(ids)
        elif chosen is delete_action:
            self.delete_requested.emit(ids)
        elif chosen is compare_action:
            self.compare_selected_requested.emit(ids)

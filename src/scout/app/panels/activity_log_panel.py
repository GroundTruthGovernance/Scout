"""The Activity Log dock — the automated logger for vital info, and the
browsing surface for run comparison history (selecting entries here feeds
the Run Compare / Tiled Product View tools). See docs/ARCHITECTURE.md.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

LEVEL_COLORS = {
    "info": QColor("#166534"),
    "working": QColor("#b45309"),
    "error": QColor("#b91c1c"),
}


class ActivityLogPanel(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.list_widget = QListWidget(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.list_widget)

    def append(self, timestamp_utc: str, level: str, message: str) -> None:
        item = QListWidgetItem(f"{timestamp_utc}  [{level.upper()}]  {message}")
        item.setForeground(LEVEL_COLORS.get(level, QColor("#000000")))
        self.list_widget.addItem(item)
        self.list_widget.scrollToBottom()

    def clear(self) -> None:
        self.list_widget.clear()

    def load_rows(self, rows) -> None:
        """rows: iterable of sqlite3.Row from repository.list_activity(),
        newest-first — displayed oldest-first so it reads like a log."""
        self.clear()
        for row in reversed(list(rows)):
            self.append(row["timestamp_utc"], row["level"], row["message"])

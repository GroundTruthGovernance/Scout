"""The Batch Queue dock. Draw a polygon -> "Run now" or "Add to queue" from
the same action (see docs/ARCHITECTURE.md — this panel *is* what the GEE
prototype's roadmap called "Scout Batch Runner", not a separate tool).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

COLUMNS = ["job_id", "job_kind", "status", "queue_order"]

POST_QUEUE_ACTIONS = ["None", "Sleep", "Shutdown"]


class BatchQueuePanel(QWidget):
    run_queue_requested = Signal(str)   # post_queue_action
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.table = QTableWidget(0, len(COLUMNS), self)
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.post_action_combo = QComboBox(self)
        self.post_action_combo.addItems(POST_QUEUE_ACTIONS)

        self.run_button = QPushButton("Run queue", self)
        self.cancel_button = QPushButton("Cancel", self)
        self.run_button.clicked.connect(
            lambda: self.run_queue_requested.emit(self.post_action_combo.currentText())
        )
        self.cancel_button.clicked.connect(self.cancel_requested.emit)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("When queue finishes:"))
        controls.addWidget(self.post_action_combo)
        controls.addWidget(self.run_button)
        controls.addWidget(self.cancel_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls)
        layout.addWidget(self.table)

    def load_jobs(self, rows) -> None:
        self.table.setRowCount(0)
        for row in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, col in enumerate(COLUMNS):
                self.table.setItem(r, c, QTableWidgetItem(str(row[col])))

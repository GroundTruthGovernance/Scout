"""A floating probe inspector — Summary / AE 64-D / Spectral / DW / Raw
tabs, matching the GEE prototype's inspector. The Raw tab is wrapped in a
QScrollArea specifically because "Probe Raw pane overflows inspector" was
an open bug in that prototype (fixed-height Code Editor widgets cannot
scroll); a real dock widget has no such limit, but the scroll area also
protects against a probe with unusually many raw fields.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class ProbeInspectorPanel(QWidget):
    def __init__(self, probe_id: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.probe_id = probe_id
        self.tabs = QTabWidget(self)

        self.summary_label = QLabel("Loading…", self)
        self.summary_label.setWordWrap(True)
        self.tabs.addTab(self._scrollable(self.summary_label), "Summary")

        self.ae_placeholder = QLabel("AE 64-D chart renders here.", self)
        self.tabs.addTab(self._scrollable(self.ae_placeholder), "AE 64-D")

        self.spectral_placeholder = QLabel("Spectral charts render here.", self)
        self.tabs.addTab(self._scrollable(self.spectral_placeholder), "Spectral")

        self.dw_placeholder = QLabel("Dynamic World chart renders here.", self)
        self.tabs.addTab(self._scrollable(self.dw_placeholder), "DW")

        self.raw_text = QPlainTextEdit(self)
        self.raw_text.setReadOnly(True)
        raw_scroll = QScrollArea(self)
        raw_scroll.setWidgetResizable(True)
        raw_scroll.setWidget(self.raw_text)
        self.tabs.addTab(raw_scroll, "Raw")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(QLabel(f"{probe_id} — Probe inspector", self))
        layout.addWidget(self.tabs)

    @staticmethod
    def _scrollable(widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        return scroll

    def set_summary(self, text: str) -> None:
        self.summary_label.setText(text)

    def set_raw_text(self, text: str) -> None:
        self.raw_text.setPlainText(text)

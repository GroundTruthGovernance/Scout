"""The Figure Capture dialog — title (required, becomes the report
heading) + caption (optional, becomes the paragraph under the image in
the composed report). Deliberately just two fields; the figure's recipe
context (sample/response, extent, mask settings) is captured separately
from whatever the currently-open response actually is, not typed by hand.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QWidget


class FigureCaptureDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Capture Figure")

        self.title_edit = QLineEdit(self)
        self.caption_edit = QLineEdit(self)

        form = QFormLayout()
        form.addRow("Title *", self.title_edit)
        form.addRow("Caption", self.caption_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.setLayout(form)

        self._values: dict | None = None

    def _on_accept(self) -> None:
        title = self.title_edit.text().strip()
        if not title:
            return  # required field missing — dialog stays open
        self._values = {"title": title, "caption": self.caption_edit.text().strip()}
        self.accept()

    def values(self) -> dict | None:
        return self._values

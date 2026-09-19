"""The New Project dialog — project/location/sub-location codes are the
three required fields the whole project_key derivation depends on
(see core.models.project_key). Project name is optional, matching the
GEE prototype's "required for formal saves, not exploration" pattern
carried over from the original UI.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QWidget

from scout.core.util import safe_code


class NewProjectDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("New Project")

        self.project_code_edit = QLineEdit(self)
        self.location_code_edit = QLineEdit(self)
        self.sublocation_code_edit = QLineEdit(self)
        self.project_name_edit = QLineEdit(self)

        form = QFormLayout()
        form.addRow("Project code *", self.project_code_edit)
        form.addRow("Location code *", self.location_code_edit)
        form.addRow("Sub-location code *", self.sublocation_code_edit)
        form.addRow("Project name", self.project_name_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = form
        self.setLayout(layout)
        layout.addRow(buttons)

        self._values: dict | None = None

    def _on_accept(self) -> None:
        project_code = safe_code(self.project_code_edit.text())
        location_code = safe_code(self.location_code_edit.text())
        sublocation_code = safe_code(self.sublocation_code_edit.text())
        if not (project_code and location_code and sublocation_code):
            return  # required fields missing — dialog stays open, no silent partial accept
        self._values = {
            "project_code": project_code,
            "location_code": location_code,
            "sublocation_code": sublocation_code,
            "project_name": self.project_name_edit.text().strip(),
        }
        self.accept()

    def values(self) -> dict | None:
        """None if the dialog was cancelled or closed without valid required fields."""
        return self._values

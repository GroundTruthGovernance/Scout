"""Runs the blocking, browser-opening Earth Engine sign-in flow off the Qt
UI thread. `ee.Authenticate()` blocks waiting on a local HTTP callback
from the browser; running it on the UI thread would freeze the whole
application until the user finishes (or abandons) the consent screen.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from scout.core.ee_auth import EarthEngineAuth


class EarthEngineSignInWorker(QThread):
    succeeded = Signal()
    failed = Signal(str)

    def __init__(self, auth: EarthEngineAuth, project: str | None = None, parent=None):
        super().__init__(parent)
        self.auth = auth
        self.project = project

    def run(self) -> None:
        try:
            self.auth.authenticate_interactive()
            self.auth.initialize(project=self.project)
        except Exception as exc:  # noqa: BLE001 — reported to the UI, not swallowed
            self.failed.emit(str(exc))
            return
        self.succeeded.emit()

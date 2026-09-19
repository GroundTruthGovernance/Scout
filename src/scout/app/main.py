"""Scout desktop application entry point (`scout` console script)."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from scout.app.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Scout")
    app.setOrganizationName("GroundTruthGovernance")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

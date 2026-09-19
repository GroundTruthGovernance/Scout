"""Shared pytest fixtures for the Qt-dependent test suite.

Requires QT_QPA_PLATFORM=offscreen (set here, before Qt is imported by any
test module) since this and CI environments have no real display.
QTWEBENGINE_DISABLE_SANDBOX is required because QtWebEngine's Chromium
sandbox refuses to run as root/without a display otherwise — both are
sandbox/CI realities, not something a normal user install needs.

QTWEBENGINE_CHROMIUM_FLAGS disables GPU compositing: without it, this
sandbox (and apparently windows-latest GitHub runners too — see
docs/DEVLOG.md, the first CI run) hits a WebGL-blocklisted code path
during QtWebEngine's shutdown that appears to cause python.exe to exit
non-zero on Windows even though pytest itself reports every test passing.
Sidestepping the GPU/WebGL path entirely avoids that code path rather than
trying to out-race it during teardown.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS",
    "--disable-gpu --disable-software-rasterizer --disable-gpu-compositing",
)

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    # Web engine pages/profiles scheduled via deleteLater() only actually
    # get destroyed once the event loop runs again. Pump it a few times
    # before the interpreter starts tearing down C++ objects out from
    # under still-pending Qt cleanup — this is the one Windows CI hit that
    # this sandbox's Linux run did not (see docs/DEVLOG.md).
    for _ in range(10):
        QCoreApplication.processEvents()


@pytest.fixture
def qt_cleanup(qapp):
    """Explicit per-test cleanup point for anything that creates a
    QWebEngineView (MapPanel, MainWindow). Call `qt_cleanup.flush()` after
    closing/deleting such widgets instead of leaving it to session end."""

    class _Flusher:
        @staticmethod
        def flush(rounds: int = 5) -> None:
            for _ in range(rounds):
                QCoreApplication.processEvents()

    return _Flusher()

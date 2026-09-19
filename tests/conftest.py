"""Shared pytest fixtures for the Qt-dependent test suite.

Requires QT_QPA_PLATFORM=offscreen (set here, before Qt is imported by any
test module) since this and CI environments have no real display.
QTWEBENGINE_DISABLE_SANDBOX is required because QtWebEngine's Chromium
sandbox refuses to run as root/without a display otherwise — both are
sandbox/CI realities, not something a normal user install needs.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app

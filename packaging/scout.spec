# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Scout Windows executable.
Build from the repo root with: pyinstaller packaging/scout.spec

This spec has been written for, but not yet built/run on, a Windows
machine — this development sandbox is Linux and cannot produce a Windows
binary. It is exercised for real by .github/workflows/build-windows.yml
on a windows-latest runner; treat the first few CI runs as the actual
verification of this file; PySide6 + QtWebEngine packaging is a known
fiddly combination (bundling the QtWebEngineProcess executable and its
locale/resource files correctly), so expect to iterate here based on
what CI actually reports rather than assuming this is correct on paper.
"""

import os

from PyInstaller.utils.hooks import collect_data_files

SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
SRC_DIR = os.path.join(SPEC_DIR, "..", "src")

# PyInstaller ships its own hook-PySide6.QtWebEngineWidgets.py /
# hook-PySide6.QtWebEngineCore.py (confirmed present in
# pyinstaller-hooks-contrib 2026.7) which already bundles
# QtWebEngineProcess and its locale/resource files once QWebEngineView is
# detected as imported — collect_all("PySide6") was tried here first and
# pulled in ~880MB of unrelated Qt modules (Multimedia, Quick3D, Wayland
# compositor, every SQL driver, TextToSpeech) that Scout never imports.
# Rely on the targeted hooks instead; only add what they don't cover.
datas = collect_data_files("scout.core", includes=["*.sql"])
datas += collect_data_files("scout.webmap", includes=["*.html", "*.js", "*.css", "vendor/*"])
binaries = []
hiddenimports = ["ee"]

a = Analysis(
    [os.path.join(SRC_DIR, "scout", "app", "main.py")],
    pathex=[SRC_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Scout",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Scout",
)

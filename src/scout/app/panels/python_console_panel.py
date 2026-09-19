"""A real (not stubbed) Python scripting console dock — `Tools > Python
Console`. Runs in the same process as the app, with `project_context`
pre-bound in its namespace, for one-off queries and scripting that don't
warrant a dedicated UI control.
"""

from __future__ import annotations

import code
import io
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

PROMPT_PRIMARY = ">>> "
PROMPT_CONTINUATION = "... "


class PythonConsolePanel(QWidget):
    def __init__(self, namespace: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.interpreter = code.InteractiveInterpreter(namespace or {})
        self._buffer_lines: list[str] = []

        self.output = QPlainTextEdit(self)
        self.output.setReadOnly(False)
        self.output.setUndoRedoEnabled(False)
        font = self.output.font()
        font.setFamily("Monospace")
        self.output.setFont(font)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.output)

        self._write_banner()
        self._write_prompt()
        self.output.installEventFilter(self)

    def _write_banner(self) -> None:
        self.output.appendPlainText(
            f"Scout Python console — Python {sys.version.split()[0]}\n"
            "`project_context` is bound to the currently open project."
        )

    def _write_prompt(self) -> None:
        prompt = PROMPT_CONTINUATION if self._buffer_lines else PROMPT_PRIMARY
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.output.setTextCursor(cursor)
        self.output.insertPlainText(prompt)
        self._prompt_position = self.output.textCursor().position()

    def _current_input_line(self) -> str:
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.setPosition(self._prompt_position, QTextCursor.KeepAnchor)
        return cursor.selectedText()

    def eventFilter(self, obj, event):
        if obj is self.output and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._submit_current_line()
                return True
            cursor = self.output.textCursor()
            if cursor.position() < self._prompt_position and event.key() not in (
                Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down,
            ):
                return True  # protect the transcript above the active prompt
        return super().eventFilter(obj, event)

    def _submit_current_line(self) -> None:
        line = self._current_input_line()
        self.output.appendPlainText("")
        self._buffer_lines.append(line)
        source = "\n".join(self._buffer_lines)

        stdout, stderr = io.StringIO(), io.StringIO()
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = stdout, stderr
        try:
            needs_more = self.interpreter.runsource(source, "<scout-console>")
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr

        output_text = stdout.getvalue() + stderr.getvalue()
        if output_text:
            self.output.appendPlainText(output_text.rstrip("\n"))

        if not needs_more:
            self._buffer_lines = []
        self._write_prompt()

    def run_silently(self, source: str) -> None:
        """Execute code without going through the interactive echo — used
        by tests and by other panels wiring quick actions into the
        console's namespace."""
        self.interpreter.runsource(source, "<scout-console>")

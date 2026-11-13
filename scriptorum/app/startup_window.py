"""The start-up window with checks (design document F9, decided 11 November
2026, built in M5).

A small window in the app's palette comes first. It shows the name and
version, a progress bar, and one line per check, each ticked as it passes.
When every check passes it closes by itself and the main window opens. When
a check fails it stays open, the failed line gives the reason in plain
words, and Continue anyway opens the app without that part; Copy details
copies the results as text. Every line comes from the interface language
module (F15). The checks themselves are in scriptorum/core/startup.py.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from scriptorum import paths
from scriptorum.core.startup import CHECKS, CheckResult, Startup, line_text, report_text, text_of

TICK, CROSS, WAITING = "✓", "✕", "·"

# Claret & Ink (F16), used when the chosen palette cannot be read yet.
FALLBACK = {
    "light": {"window": "#DED5C7", "editor": "#F3EEE6", "text": "#1B2F33", "muted": "#4E5859", "claret": "#69353F",
              "on-claret": "#F3EEE6", "claret-text": "#69353F", "green": "#4D9078", "error": "#8A2E22", "line-strong": "#AE9F89"},
    "dark": {"window": "#1B2F33", "editor": "#243B40", "text": "#DED5C7", "muted": "#A9B3AE", "claret": "#69353F",
             "on-claret": "#DED5C7", "claret-text": "#CC9A8E", "green": "#74B89E", "error": "#E0A99F", "line-strong": "#56686B"},
}


def startup_colours(system_dark: bool = False) -> Dict[str, str]:
    """The colours of the palette the author chose (F16), read straight from
    the app's folder, since the module library has not been checked yet.
    Anything unreadable falls back to Claret & Ink."""
    mode = "dark" if system_dark else "light"
    colours = dict(FALLBACK[mode])
    try:
        home = paths.app_home()
        values = {}
        settings = home / "app-settings.json"
        if settings.is_file():
            values = json.loads(settings.read_text("utf-8"))
        if values.get("mode") in ("light", "dark"):
            mode = values["mode"]
            colours = dict(FALLBACK[mode])
        palette_id = values.get("palette") or "scriptorum.claret-and-ink"
        candidates = sorted((home / "modules" / palette_id).glob("*/palette.json"))
        wanted = values.get("palette_version")
        chosen = next((c for c in candidates if c.parent.name == wanted), candidates[-1] if candidates else None)
        if chosen is None:
            chosen = paths.BUNDLED_MODULES_DIR / "scriptorum.claret-and-ink" / "palette.json"
        stored = json.loads(chosen.read_text("utf-8")).get(mode) or {}
        for key in colours:
            value = stored.get(key)
            if isinstance(value, str) and len(value) == 7 and value.startswith("#"):
                colours[key] = value
    except (OSError, ValueError, AttributeError):
        pass
    return colours


class CheckWorker(QThread):
    """Runs the checks off the window's thread, so the window keeps drawing."""

    result = Signal(object)

    def __init__(self, startup: Startup, parent=None):
        super().__init__(parent)
        self.startup = startup

    def run(self) -> None:  # noqa: D401 - Qt's name
        self.startup.run(self.result.emit)


class StartupWindow(QWidget):
    done = Signal(bool)  # True: open the main window; False: quit

    def __init__(self, startup: Startup, strings: Dict[str, str], version: str, colours: Optional[Dict[str, str]] = None):
        super().__init__()
        self.startup = startup
        self.strings = strings
        self.version = version
        self.results: List[CheckResult] = []
        self.finished_checks = False
        self.answered = False
        self.worker: Optional[CheckWorker] = None
        c = colours or startup_colours()
        self.colours = c
        t = lambda key, **details: text_of(strings, key, **details)  # noqa: E731

        self.setWindowTitle(t("app.name"))
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setObjectName("startup")
        self.setStyleSheet(
            f"#startup {{ background: {c['window']}; }}"
            f"QLabel {{ color: {c['text']}; font-size: 13px; }}"
            f"QLabel#name {{ color: {c['claret-text']}; font-size: 24px; font-weight: 600; }}"
            f"QLabel#version, QLabel#status {{ color: {c['muted']}; font-size: 12px; }}"
            f"QLabel[state=\"ok\"] {{ color: {c['green']}; font-weight: 700; }}"
            f"QLabel[state=\"failed\"] {{ color: {c['error']}; font-weight: 700; }}"
            f"QLabel[state=\"waiting\"] {{ color: {c['muted']}; }}"
            f"QLabel[failed=\"true\"] {{ color: {c['error']}; }}"
            f"QProgressBar {{ border: 1px solid {c['line-strong']}; border-radius: 4px; background: {c['editor']}; height: 8px; }}"
            f"QProgressBar::chunk {{ background: {c['claret']}; border-radius: 3px; }}"
            f"QPushButton {{ border: 1px solid {c['line-strong']}; border-radius: 6px; padding: 6px 14px; background: {c['editor']}; color: {c['text']}; }}"
            f"QPushButton#continue {{ background: {c['claret']}; color: {c['on-claret']}; border-color: {c['claret']}; }}"
            f"QPushButton:disabled {{ color: {c['muted']}; background: {c['window']}; border-color: {c['line-strong']}; }}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 22, 26, 20)
        outer.setSpacing(8)
        name = QLabel(t("app.name"))
        name.setObjectName("name")
        version_label = QLabel(t("startup.version", version=version))
        version_label.setObjectName("version")
        outer.addWidget(name)
        outer.addWidget(version_label)

        self.bar = QProgressBar()
        self.bar.setRange(0, len(CHECKS))
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        outer.addSpacing(6)
        outer.addWidget(self.bar)
        outer.addSpacing(6)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)
        self.marks: Dict[str, QLabel] = {}
        self.lines: Dict[str, QLabel] = {}
        for row, check_id in enumerate(CHECKS):
            mark = QLabel(WAITING)
            mark.setProperty("state", "waiting")
            mark.setFixedWidth(16)
            mark.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            line = QLabel(t(f"startup.check.{check_id}"))
            line.setWordWrap(True)
            line.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(mark, row, 0)
            grid.addWidget(line, row, 1)
            self.marks[check_id] = mark
            self.lines[check_id] = line
        outer.addLayout(grid)

        self.status = QLabel(t("startup.checking"))
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        outer.addSpacing(4)
        outer.addWidget(self.status)

        buttons = QHBoxLayout()
        self.copy_button = QPushButton(t("startup.copyDetails"))
        self.quit_button = QPushButton(t("startup.quit"))
        self.continue_button = QPushButton(t("startup.continueAnyway"))
        self.continue_button.setObjectName("continue")
        self.copy_button.clicked.connect(self.copy_details)
        self.quit_button.clicked.connect(lambda: self._answer(False))
        self.continue_button.clicked.connect(lambda: self._answer(True))
        buttons.addWidget(self.copy_button)
        buttons.addStretch(1)
        buttons.addWidget(self.quit_button)
        buttons.addWidget(self.continue_button)
        for button in (self.copy_button, self.quit_button, self.continue_button):
            button.setVisible(False)
        outer.addLayout(buttons)
        self.setMinimumWidth(470)
        self.adjustSize()

    # --- running the checks --------------------------------------------------------
    def start(self) -> None:
        """Run the checks in the background; the window keeps drawing."""
        self.worker = CheckWorker(self.startup, self)
        self.worker.result.connect(self.show_result)
        self.worker.finished.connect(self.checks_finished)
        self.worker.start()

    def run_now(self) -> None:
        """Run the checks in this thread (used by the tests)."""
        self.startup.run(self.show_result)
        self.checks_finished()

    def show_result(self, result: CheckResult) -> None:
        self.results.append(result)
        mark, line = self.marks[result.id], self.lines[result.id]
        mark.setText(TICK if result.ok else CROSS)
        mark.setProperty("state", "ok" if result.ok else "failed")
        line.setText(line_text(self.strings, result))
        line.setProperty("failed", "false" if result.ok else "true")
        for widget in (mark, line):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.bar.setValue(len(self.results))

    def checks_finished(self) -> None:
        self.finished_checks = True
        if self.startup.ok:
            # Every check passed: the window closes by itself.
            self._answer(True)
            return
        can = self.startup.can_continue
        self.status.setText(text_of(self.strings, "startup.failed" if can else "startup.cannotStart"))
        for button in (self.copy_button, self.quit_button, self.continue_button):
            button.setVisible(True)
        self.continue_button.setEnabled(can)
        self.adjustSize()

    # --- the buttons ---------------------------------------------------------------
    def details_text(self) -> str:
        return report_text(self.strings, self.results, self.version)

    def copy_details(self) -> None:
        QGuiApplication.clipboard().setText(self.details_text())
        self.status.setText(text_of(self.strings, "startup.copied"))

    def _answer(self, open_app: bool) -> None:
        if self.answered:
            return
        self.answered = True
        self.done.emit(open_app)
        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt's name
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(15000)
        if not self.answered:
            # Closed with its own close button: the same as Quit.
            self.answered = True
            self.done.emit(False)
        event.accept()

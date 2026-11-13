"""The Scriptorum window: PySide6 with the interface in Qt WebEngine (D4)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEvent, QUrl, Qt
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestInfo,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow

from scriptorum import paths
from scriptorum.app.bridge import Bridge
from scriptorum.core import crashlog
from scriptorum.core.session import Session

ALLOWED_SCHEMES = {"file", "qrc", "data", "blob"}


class OfflineInterceptor(QWebEngineUrlRequestInterceptor):
    """D9: the interface may load only local files. Every network request is blocked."""

    def __init__(self):
        super().__init__()
        self.blocked = []

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:
        url = info.requestUrl()
        if url.scheme() not in ALLOWED_SCHEMES:
            self.blocked.append(url.toString())
            info.block(True)


class MainWindow(QMainWindow):
    def __init__(self, session: Session, headless_test: bool = False, spelling=None,
                 startup_results: Optional[list] = None, skip_css: Optional[bool] = None,
                 test_eval: Optional[bool] = None):
        super().__init__()
        self.headless_test = headless_test
        # F9 (M6): the pages' script policy forbids eval. The automated tests
        # drive the window with eval, so only a test window loads the same page
        # with eval allowed; T-UI-30 checks the real page with test_eval=False.
        self.test_eval = headless_test if test_eval is None else test_eval
        # F9 (M5): the start-up window hands over the dictionaries it loaded,
        # and what it found missing, which a quiet bar in the window names.
        self.bridge = Bridge(session, self, spelling=spelling)
        self.bridge.startup_results = list(startup_results or [])
        # F16: holding Shift while the app starts skips a palette's own
        # stylesheet, so a broken one can always be undone. The start-up
        # window comes first, so Shift is read when the app starts (F9).
        if skip_css is None:
            skip_css = bool(QGuiApplication.queryKeyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)
        self.bridge.skip_css = skip_css
        # F16, F18: "Follow the computer" follows its light or dark mode.
        hints = QGuiApplication.styleHints()
        self.bridge.system_dark = hints.colorScheme() == Qt.ColorScheme.Dark
        hints.colorSchemeChanged.connect(lambda scheme: self.bridge.set_system_dark(scheme == Qt.ColorScheme.Dark))

        self.profile = QWebEngineProfile(self)  # off the record: nothing stored
        self.interceptor = OfflineInterceptor()
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.page = QWebEnginePage(self.profile, self)
        settings = self.page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)

        self.channel = QWebChannel(self)
        self.channel.registerObject("core", self.bridge)
        self.page.setWebChannel(self.channel)

        self.view = QWebEngineView(self)
        self.view.setPage(self.page)
        self.setCentralWidget(self.view)
        self.resize(1440, 900)
        self.update_title()
        self.load_page(self.view, "index.html")

    @property
    def session(self) -> Session:
        return self.bridge.session

    @session.setter
    def session(self, value: Session) -> None:
        self._first_session = value

    def update_title(self) -> None:
        t = self.session.t
        adventure = self.session.adventure
        if adventure is None:
            self.setWindowTitle(t("app.name"))
            return
        if self.session.read_only:
            key = "app.windowTitleReadOnly"
        else:
            key = "app.windowTitleDirty" if self.session.dirty else "app.windowTitle"
        self.setWindowTitle(t(key, title=adventure.title or t("app.untitled")))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.bridge.confirm_close_all():
            event.accept()
            self._release_web()
        else:
            event.ignore()

    def load_page(self, view, name: str) -> None:
        """Load one of the app's pages, under its script policy (F9)."""
        file = paths.UI_DIR / name
        if not self.test_eval:
            view.load(QUrl.fromLocalFile(str(file)))
            return
        html = file.read_text("utf-8").replace("script-src 'self' qrc:;", "script-src 'self' qrc: 'unsafe-eval';", 1)
        view.setHtml(html, QUrl.fromLocalFile(str(file)))

    # --- full screen (F9, M6 part B) -------------------------------------------------
    def set_full_screen(self, on: bool) -> None:
        """Fill the screen, or go back. On the Mac this is the normal macOS
        full screen in its own Space. The choice is remembered (F18)."""
        if on and not self.isFullScreen():
            self.showFullScreen()
        elif not on and self.isFullScreen():
            self.showNormal()
        self._remember_full_screen(on)

    def _remember_full_screen(self, on: bool) -> None:
        settings = self.session.app_settings
        if bool(settings.get("full_screen")) != bool(on):
            settings.update({"full_screen": bool(on)})

    def changeEvent(self, event) -> None:
        # The green window button on the Mac, or the window manager, changed it.
        if event.type() == QEvent.Type.WindowStateChange:
            on = self.isFullScreen()
            self._remember_full_screen(on)
            self.bridge.full_screen_changed(on)
        super().changeEvent(event)

    def open_preview_window(self) -> None:
        """F7.2 (M5): the preview in a separate window. It shares this window's
        offline profile (D9) and talks to the same bridge."""
        existing = getattr(self, "preview_window", None)
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return
        window = QMainWindow(self)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        window.channel = QWebChannel(window)
        window.channel.registerObject("core", self.bridge)
        window.page = QWebEnginePage(self.profile, window)
        window.page.setWebChannel(window.channel)
        window.view = QWebEngineView(window)
        window.view.setPage(window.page)
        window.setCentralWidget(window.view)
        window.resize(820, 1000)
        self.load_page(window.view, "preview.html")
        self.preview_window = window
        window.show()

    def _release_web(self) -> None:
        """Qt WebEngine needs the view and page gone before their profile."""
        import shiboken6

        preview = getattr(self, "preview_window", None)
        if preview is not None:
            preview.channel.deregisterObject(self.bridge)
            for name in ("view", "page"):
                obj = getattr(preview, name, None)
                if obj is not None and shiboken6.isValid(obj):
                    shiboken6.delete(obj)
            preview.close()
            self.preview_window = None
        self.bridge.shutdown()
        if getattr(self, "channel", None) is not None:
            self.channel.deregisterObject(self.bridge)

        for name in ("view", "page", "profile"):
            obj = getattr(self, name, None)
            if obj is not None and shiboken6.isValid(obj):
                shiboken6.delete(obj)
            setattr(self, name, None)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="scriptorum")
    parser.add_argument("adventure", nargs="?", help="a .scav file to open")
    args, qt_args = parser.parse_known_args(argv if argv is not None else sys.argv[1:])

    app = QApplication([sys.argv[0], *qt_args])
    crashlog.install()  # F2.11: crash logs stay on this computer
    # F16: Shift held while the app starts skips a palette's stylesheet.
    skip_css = bool(QGuiApplication.queryKeyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)

    # F9 (decided 11 Nov 2026, M5): the start-up window with checks comes first.
    from scriptorum import __version__
    from scriptorum.app.startup_window import StartupWindow, startup_colours
    from scriptorum.core.startup import Startup, bundled_strings

    startup = Startup()
    strings = bundled_strings()
    app.setApplicationName(strings.get("app.name", "Scriptorum"))
    dark = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    splash = StartupWindow(startup, strings, __version__, startup_colours(dark))
    windows = []

    def open_app(go_on: bool) -> None:
        if not go_on or startup.session is None:
            app.quit()
            return
        session = startup.session
        app.setApplicationName(session.t("app.name"))
        problem = None
        if args.adventure:
            # The adventure that was double-clicked, if any.
            try:
                session.open(Path(args.adventure))
            except Exception as exc:  # noqa: BLE001 - shown in the window, never a silent exit
                problem = exc
        window = MainWindow(session, spelling=startup.spelling, startup_results=startup.failed(), skip_css=skip_css)
        if problem is not None:
            window.bridge.open_problem = problem
        windows.append(window)
        # F9 (M6): Scriptorum opens in full screen if it was left that way.
        if session.app_settings.get("full_screen"):
            window.showFullScreen()
        else:
            window.show()

    splash.done.connect(open_app)
    splash.show()
    splash.start()
    return app.exec()

"""The bridge between the interface (TypeScript) and the core (3.1).

Every slot returns JSON text. The interface never touches files: dialogs,
saving, building and exporting all happen here, in the core.

Several adventures can be open at the same time, each in its own tab (F2.2);
every slot works on the active tab.
"""

from __future__ import annotations

import base64
import json
import shutil
import threading
import time
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QMessageBox

from scriptorum.core.build import BuildResult, Problem
from scriptorum.core.fonts import FontRefused
from scriptorum.core import modmanager
from scriptorum.core.modules import ModuleError
from scriptorum.core.scav import ScavError
from scriptorum.core.session import Session
from scriptorum.core.world import WorldError
from scriptorum.core.spelling import SpellChecker

BUILD_DELAY_MS = 300  # F7.1.1: about 0.3 seconds after typing stops
SNAPSHOT_TICK_MS = 30_000  # F2.6: how often to ask whether a snapshot is due


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False)


class Bridge(QObject):
    buildStarted = Signal()
    buildFinished = Signal(str)
    documentChanged = Signal()
    spellReady = Signal()
    suggestions = Signal(str)
    appearanceChanged = Signal(str)  # F16: the computer switched light/dark
    fullScreenChanged = Signal(bool)  # F9 (M6): the window entered or left full screen
    selfTestFinished = Signal(str)   # F9: the theme self-test of Help ▸ Check installation
    updateChecked = Signal(str)      # F21 (M6 part C): the result of an update check
    updateInstalled = Signal(str)    # F22 (M6 part C5): the result of Download and install
    _buildDone = Signal(object, object, int)
    _suggestDone = Signal(str)
    _selfTestDone = Signal(str)
    _updateDone = Signal(str)
    _installDone = Signal(str)

    def __init__(self, session: Session, window=None, spelling=None):
        super().__init__()
        self.sessions: List[Session] = [session]
        self.active = 0
        self.window = window
        self.ui_ready = False
        self.on_ui_ready = None
        self.confirm_discard = self._ask_discard  # tests replace this
        self.pick_portrait = None  # tests may stand in for the portrait's file dialog
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(BUILD_DELAY_MS)
        self._timer.timeout.connect(self._start_build)
        self._build_seq = 0
        self.player_preview = False  # F6.4: the "Handouts only" toggle
        self.show_breaks = False     # F7.2 (M5): View ▸ Show breaks
        self._building = False
        self._rebuild = False
        self.last_request_time = 0.0  # when typing last paused (T-BUILD-06)
        self.last_build_start = 0.0
        self.element_map: list = []
        self._buildDone.connect(self._finish_build)
        self._suggestDone.connect(self.suggestions.emit)
        self._updateDone.connect(self.updateChecked.emit)
        self._installDone.connect(self.updateInstalled.emit)
        # F21: the update address and the reader of the update file; the
        # tests replace them, so no test ever reaches the internet.
        from scriptorum.core import updates
        self.update_url = updates.UPDATE_URL
        self.update_opener = None
        self.update_requests: List[str] = []   # every address asked, for the tests
        self.update_download: Optional[str] = None
        self.opened_downloads: List[str] = []
        # F22: the pack named in the last signed update file, what downloads
        # it (the tests replace it), and the versions kept in the author's
        # folder. ``update_key`` and ``update_runtime`` stand in for the
        # built-in key and this computer's libraries in the tests.
        self.update_pack: Optional[dict] = None
        self.update_version: Optional[str] = None
        self.update_downloader = None
        self.update_key: Optional[str] = None
        self.update_runtime: Optional[dict] = None
        self.update_moved: Optional[str] = None
        from scriptorum import paths as _p
        from scriptorum.core.packs import Versions
        self.versions = Versions(_p.app_home())
        self.start_notice = None
        # F21.4: the question at first start; test windows skip it unless a
        # test asks for it, so the other window tests are not interrupted.
        self.ask_updates_at_start = not getattr(window, "headless_test", False)
        self._snapshots = QTimer(self)
        self._snapshots.setInterval(SNAPSHOT_TICK_MS)
        self._snapshots.timeout.connect(self.snapshot_tick)
        self._snapshots.start()
        # F9 (M5): the start-up window loads the dictionaries, so they are
        # ready at once in the editor; without it they load in the background.
        self.spelling = spelling or SpellChecker()
        self.startup_results: list = []   # checks that failed at start-up
        self.open_problem = None           # why the double-clicked adventure did not open
        self._selfTestDone.connect(self.selfTestFinished.emit)
        from scriptorum import paths as _paths
        from scriptorum.core.viewstate import ViewState
        self.view_state = ViewState(_paths.app_home() / "view-state.json")  # F7.2: zoom per adventure
        self._spell_watch = QTimer(self)
        self._spell_watch.setInterval(250)
        self._spell_watch.timeout.connect(self._check_spell_ready)
        self.spelling.start()
        self._spell_watch.start()
        self.closed = False
        self.skip_css = False  # F16: Shift held at start skips a palette's stylesheet
        self.system_dark = False  # F16: whether the computer is in dark mode

    def shutdown(self) -> None:
        """The window is closing: stop every timer and ignore results that
        arrive later from background work, so nothing reaches a page that
        Qt has already deleted."""
        self.closed = True
        for timer in (self._timer, self._snapshots, self._spell_watch):
            timer.stop()

    # --- the active tab ---------------------------------------------------------
    @property
    def session(self) -> Session:
        return self.sessions[self.active]

    def _new_tab(self) -> Session:
        base = self.sessions[0].work_dir
        tab = self.session.sibling(base.parent / f"{base.name}-tab{len(self.sessions) + int(time.time() * 1000) % 100000}")
        self.sessions.append(tab)
        self.active = len(self.sessions) - 1
        return tab

    def _tab_for_new_document(self) -> Session:
        """An empty tab is reused; otherwise a new tab opens (F2.2)."""
        if self.session.adventure is None:
            return self.session
        return self._new_tab()

    # --- helpers --------------------------------------------------------------
    def _error(self, exc: Exception) -> str:
        if isinstance(exc, WorldError) and exc.key == "error.codex.inUse":
            # F3.8: the refusal lists the places that use the entry.
            text = self.session.t(exc.key, places=self._places(exc.details.get("places", [])))
        elif isinstance(exc, (ScavError, ModuleError, FontRefused, WorldError)):
            text = self.session.t(exc.key, **exc.details)
        else:
            text = str(exc)
        return _json({"ok": False, "error": text})

    def _places(self, places: list) -> str:
        t = self.session.t
        parts = []
        for p in places:
            if p["where"] == "text":
                parts.append(t("codex.usedInScene", scene=p["scene"], line=p["line"]) if p.get("scene")
                             else t("codex.usedAtLine", line=p["line"]))
            elif p["where"] == "entry":
                parts.append(t("codex.usedInEntry", title=p["title"]))
            else:
                parts.append(t("codex.usedInMap", title=p["title"]))
        return "; ".join(parts)

    def _title_changed(self) -> None:
        if self.window is not None:
            self.window.update_title()

    def _ask_discard(self) -> bool:
        """Unsaved changes before closing: Save, Don't save or Cancel."""
        if self.session.adventure is None or not self.session.dirty:
            return True
        t = self.session.t
        box = QMessageBox(self.window)
        box.setWindowTitle(t("dialog.unsavedTitle"))
        box.setText(t("dialog.unsavedText", title=self.session.adventure.title))
        save = box.addButton(t("dialog.save"), QMessageBox.AcceptRole)
        discard = box.addButton(t("dialog.discard"), QMessageBox.DestructiveRole)
        box.addButton(t("dialog.cancel"), QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save:
            return json.loads(self.save())["ok"]
        return clicked is discard

    def confirm_close_all(self) -> bool:
        """Before quitting: every tab with unsaved changes asks in turn."""
        for index in range(len(self.sessions)):
            self.active = index
            if self.sessions[index].dirty and not self.confirm_discard():
                return False
        for tab in self.sessions:
            tab.close()
        return True

    # --- start-up ---------------------------------------------------------------
    @Slot(result=str)
    def strings(self) -> str:
        return _json(self.session.strings.table)

    @Slot(result=str)
    def uiReady(self) -> str:
        self.ui_ready = True
        # F22.5: this version opened its window, so it has started; anything
        # the start-up step has to say is shown once.
        from scriptorum import __version__
        try:
            self.versions.started(__version__)
            if self.start_notice is None:
                self.start_notice = self.versions.take_notice()
        except OSError:
            pass
        if self.on_ui_ready:
            self.on_ui_ready()
        return _json({"ok": True})

    @Slot(result=str)
    def info(self) -> str:
        return _json(self.session.info())

    @Slot(result=str)
    def editorInfo(self) -> str:
        return _json(self.session.editor_info())

    @Slot(result=str)
    def gameSystems(self) -> str:
        return _json(self.session.game_systems())

    # --- app settings (F18) and palettes (F16), M4 ---------------------------------------
    def _app_info(self) -> dict:
        from scriptorum import paths
        from scriptorum.core import appsettings

        library = self.session.library
        settings = self.session.app_settings
        chosen = appsettings.chosen_palette(library, settings)
        return {
            "values": dict(settings.values),
            "systemDark": self.system_dark,
            "skipCss": self.skip_css,
            "palette": appsettings.palette_info(chosen, self.skip_css) if chosen else None,
            "palettes": [appsettings.palette_info(m, True) for m in appsettings.palettes(library)],
            "tokens": list(appsettings.TOKENS),
            "languages": [{"id": m.id, "name": m.name} for m in library.of_kind("interface-language")],
            # F14, F18 (M6): the module manager's list, disabled modules included.
            "modules": modmanager.module_list(library, self.session.recent._read(), settings),
            "crashLogs": str(paths.logs_dir()),
        }

    @Slot(result=str)
    def appSettings(self) -> str:
        return _json(self._app_info())

    @Slot(str, result=str)
    def setAppSettings(self, data: str) -> str:
        """F18: every change takes effect at once, without a restart."""
        changes = json.loads(data)
        if "palette" in changes:
            changes.setdefault("palette_version", None)
        self.session.app_settings.update(changes)
        for tab in self.sessions:
            tab.apply_app_settings()
        return _json(self._app_info())

    @Slot(str, result=str)
    def savePalette(self, data: str) -> str:
        """F16 New palette from this one: saved as a palette module and chosen."""
        from scriptorum.core import appsettings
        from scriptorum.core.palettes import low_contrast

        request = json.loads(data)
        try:
            module = appsettings.save_palette(self.session.library, request.get("name", ""),
                                              request.get("light", {}), request.get("dark", {}))
        except Exception as exc:  # noqa: BLE001 - shown to the author in plain words
            return self._error(exc)
        self.session.app_settings.update({"palette": module.id, "palette_version": module.version})
        info = self._app_info()
        info["ok"] = True
        info["saved"] = {"id": module.id, "version": module.version, "name": module.name}
        info["warnings"] = low_contrast(request.get("light", {})) + low_contrast(request.get("dark", {}))
        return _json(info)

    @Slot(result=str)
    def resetPalette(self) -> str:
        """F16: Reset to Claret & Ink is always offered."""
        from scriptorum.core import appsettings

        self.session.app_settings.update({"palette": appsettings.DEFAULT_PALETTE, "palette_version": None})
        return _json(self._app_info())

    # --- Help ▸ About Scriptorum (F9, M6 part B) ------------------------------------
    @Slot(result=str)
    def aboutInfo(self) -> str:
        from scriptorum.core import about

        return _json(about.info(self.session.library))

    @Slot(str, result=str)
    def aboutText(self, ref: str) -> str:
        from scriptorum.core import about

        text = about.text(ref, self.session.library)
        return _json({"ok": text is not None, "text": text or ""})

    @Slot(result=str)
    def openIdeaSite(self) -> str:
        """lyzio.net opens in the computer's own web browser; Scriptorum
        itself makes no network request (D9). Only this one address."""
        from PySide6.QtGui import QDesktopServices
        from scriptorum.core.about import IDEA_SITE

        self.opened_sites = getattr(self, "opened_sites", []) + [IDEA_SITE]
        if not getattr(self.window, "headless_test", False):
            QDesktopServices.openUrl(QUrl(IDEA_SITE))
        return _json({"ok": True})

    # --- the update check (F21, M6 part C) and installing updates (F22, C5) ----------
    def update_address(self) -> str:
        """F22: the Update address the author entered, or the built-in one."""
        from scriptorum.core import updates
        return updates.address_in_use(self.session.app_settings.get("update_address"), self.update_url)

    def _run_update_check(self, auto: bool) -> None:
        """Ask for the update file in the background, so the window stays
        usable; the result arrives through ``updateChecked``."""
        from scriptorum import __version__
        from scriptorum.core import updates

        url = self.update_address()
        settings = self.session.app_settings

        def opener(address: str) -> bytes:
            self.update_requests.append(address)
            return (self.update_opener or updates.fetch)(address)

        def work():
            result = updates.check(__version__, url, opener, key=self.update_key, have=self.update_runtime)
            if result["state"] not in (updates.NO_ADDRESS, updates.NOT_HTTPS):
                settings.update({"update_last_check": int(time.time())})
            self.update_download = result.get("download")
            self.update_pack = result.pop("pack", None)
            self.update_version = result.get("version") if self.update_pack else None
            self.update_moved = result.get("moved")
            result["installable"] = self.update_pack is not None
            result["auto"] = auto
            result["current"] = __version__
            result["address"] = url if updates.address_set(url) else ""
            result["entered"] = bool((settings.get("update_address") or "").strip())
            if not self.closed:
                self._updateDone.emit(_json(result))
        threading.Thread(target=work, daemon=True).start()

    @Slot(result=str)
    def checkForUpdates(self) -> str:
        """Help ▸ Check for updates…: with Download and install, the only
        network requests the app makes (D9)."""
        self._run_update_check(auto=False)
        return _json({"ok": True})

    @Slot(result=str)
    def installUpdate(self) -> str:
        """F22: Download and install, only when the author clicks it. The pack
        is checked and unpacked into the author's own folder in the
        background; open adventures are never interrupted. The result
        arrives through ``updateInstalled``."""
        from scriptorum import __version__
        from scriptorum.core import updates

        pack, version = self.update_pack, self.update_version
        if not pack:
            return _json({"ok": False})

        def download(address: str) -> bytes:
            self.update_requests.append(address)
            return (self.update_downloader or updates.fetch_pack)(address)

        def work():
            try:
                installed = updates.install(pack, self.versions, download, key=self.update_key,
                                            have=self.update_runtime, running=self._running_kept(__version__),
                                            expected=version)
                result = {"ok": True, "version": installed}
            except updates.InstallError as exc:
                result = {"ok": False, "reason": exc.reason}
            except Exception as exc:  # noqa: BLE001 - said plainly, details in the crash log
                from scriptorum.core import crashlog
                crashlog.write_crash_log(type(exc), exc, exc.__traceback__)
                result = {"ok": False, "reason": "damaged"}
            if not self.closed:
                self._installDone.emit(_json(result))
        threading.Thread(target=work, daemon=True).start()
        return _json({"ok": True})

    def _running_kept(self, running: str) -> Optional[str]:
        """The version running now, when it runs from the author's folder."""
        import os
        from scriptorum.boot import ENV_FOLDER
        folder = os.environ.get(ENV_FOLDER)
        if folder and Path(folder).name == running and Path(folder).parent == self.versions.root:
            return running
        return None

    @Slot(result=str)
    def useMovedAddress(self) -> str:
        """F22: the signed update file said the address has moved, and the
        author answered Yes: the new address goes into the Update address field."""
        from scriptorum.core import updates
        moved = self.update_moved
        if not updates.address_ok(moved or ""):
            return _json({"ok": False})
        self.session.app_settings.update({"update_address": moved})
        self.update_moved = None
        return _json({"ok": True, "app": self._app_info()})

    @Slot(str, result=str)
    def setUpdateAddress(self, address: str) -> str:
        """F22: Settings ▸ Application ▸ Updates ▸ Update address. Only https
        is accepted; an empty field (Use built-in address) means UPDATE_URL."""
        from scriptorum.core import updates
        address = (address or "").strip()
        if address and not updates.address_ok(address):
            return _json({"ok": False, "error": self.session.t("update.addressRefused")})
        self.session.app_settings.update({"update_address": address})
        return _json({"ok": True, "app": self._app_info()})

    @Slot(result=str)
    def versionInfo(self) -> str:
        """F22: the version running, the installed app's own, the one Help ▸
        Go back to version would run, and what the start-up step has to say."""
        from scriptorum import __version__
        from scriptorum.boot import builtin_version
        builtin = builtin_version()
        try:
            back = self.versions.back_target(__version__, builtin)
        except OSError:
            back = None
        notice, self.start_notice = self.start_notice, None
        return _json({"running": __version__, "builtin": builtin, "back": back, "notice": notice})

    @Slot(result=str)
    def goBack(self) -> str:
        """F22.5: Help ▸ Go back to version X. The next start runs X."""
        from scriptorum import __version__
        from scriptorum.boot import builtin_version
        target = self.versions.go_back(__version__, builtin_version())
        return _json({"ok": target is not None, "version": target})

    @Slot(result=str)
    def weeklyUpdateCheck(self) -> str:
        """F21.4: at start, only when the author turned on Check once a week
        and a week has passed since the last check."""
        from scriptorum.core import updates

        due = updates.weekly_due(self.session.app_settings) and updates.address_set(self.update_address())
        if due:
            self._run_update_check(auto=True)
        return _json({"ok": True, "started": due})

    @Slot(result=str)
    def updatePrompt(self) -> str:
        """F21.4: at first start Scriptorum asks once whether to check weekly."""
        asked = bool(self.session.app_settings.get("update_asked"))
        return _json({"ask": self.ask_updates_at_start and not asked})

    @Slot(bool, result=str)
    def answerUpdatePrompt(self, weekly: bool) -> str:
        self.session.app_settings.update({"update_asked": True, "update_weekly": bool(weekly)})
        return _json(self._app_info())

    @Slot(result=str)
    def openDownloadPage(self) -> str:
        """The button opens the download page from the last update file in the
        computer's own web browser; Scriptorum downloads nothing (F21.3)."""
        from PySide6.QtGui import QDesktopServices

        page = self.update_download
        if not page:
            return _json({"ok": False})
        self.opened_downloads.append(page)
        if not getattr(self.window, "headless_test", False):
            QDesktopServices.openUrl(QUrl(page))
        return _json({"ok": True})

    # --- full screen (F9, M6 part B) ---------------------------------------------
    @Slot(bool, result=str)
    def setFullScreen(self, on: bool) -> str:
        if self.window is not None and hasattr(self.window, "set_full_screen"):
            self.window.set_full_screen(bool(on))
        return _json({"ok": True, "fullScreen": self.is_full_screen()})

    @Slot(result=bool)
    def isFullScreen(self) -> bool:
        return self.is_full_screen()

    def is_full_screen(self) -> bool:
        return bool(self.window is not None and self.window.isFullScreen())

    def full_screen_changed(self, on: bool) -> None:
        if not self.closed:
            self.fullScreenChanged.emit(bool(on))

    @Slot(result=str)
    def openCrashLogFolder(self) -> str:
        """F18: the button that opens the crash-log folder (on this computer)."""
        from PySide6.QtGui import QDesktopServices
        from scriptorum import paths

        if not getattr(self.window, "headless_test", False):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.logs_dir())))
        return _json({"ok": True, "path": str(paths.logs_dir())})

    def set_system_dark(self, dark: bool) -> None:
        self.system_dark = bool(dark)
        if not self.closed:
            self.appearanceChanged.emit(_json({"systemDark": self.system_dark}))

    @Slot(result=str)
    def openExample(self) -> str:
        """F20: open the example adventure as a copy in the user's documents."""
        tab = self._tab_for_new_document()
        try:
            path = tab.open_example()
        except Exception as exc:  # noqa: BLE001
            return self._error(exc)
        tab.recent.add(path)
        self._changed()
        return _json({"ok": True, "path": str(path)})

    @Slot(str, result=str)
    def setTheme(self, theme_id: str) -> str:
        """F8: the theme is chosen on the adventure settings page; the preview
        re-renders at once."""
        try:
            info = self.session.set_theme(theme_id)
        except ValueError as exc:
            return self._error(exc)
        self._changed()
        return _json(info)

    # --- module manager (F14; M6 part A) -----------------------------------------
    def _modules_changed(self, extra: Optional[dict] = None) -> str:
        """After a module is installed, enabled, disabled or removed: every
        open adventure checks its modules again, and the lists are sent back."""
        changed = False
        for tab in self.sessions:
            changed = tab.refresh_modules() or changed
        if changed:
            self._changed()
            self._title_changed()
        info = self._app_info()
        info["ok"] = True
        info.update(extra or {})
        return _json(info)

    @Slot(result=str)
    def installModuleDialog(self) -> str:
        """Settings ▸ Modules ▸ Install module…: choose a .scmod file."""
        t = self.session.t
        path, _ = QFileDialog.getOpenFileName(self.window, t("dialog.installModuleTitle"), "", t("dialog.scmodFilter"))
        if not path:
            return _json({"ok": False, "cancelled": True})
        return self.installModulePath(path)

    @Slot(str, result=str)
    def installModulePath(self, path: str) -> str:
        """Install a module from a .scmod file with every check of 9.7."""
        try:
            result = modmanager.install(self.session.library, Path(path), self.session.localize)
        except Exception as exc:  # noqa: BLE001 - refused, with the reason in plain words
            return self._error(exc)
        module = result["module"]
        return self._modules_changed({"status": result["status"],
                                      "module": {"id": module.id, "version": module.version, "name": module.name}})

    @Slot(str, str, bool, result=str)
    def setModuleDisabled(self, module_id: str, version: str, disabled: bool) -> str:
        try:
            modmanager.set_disabled(self.session.library, module_id, version, disabled, self.session.app_settings)
        except Exception as exc:  # noqa: BLE001
            return self._error(exc)
        return self._modules_changed()

    @Slot(str, str, result=str)
    def removeModule(self, module_id: str, version: str) -> str:
        try:
            modmanager.remove(self.session.library, module_id, version, self.session.app_settings)
        except Exception as exc:  # noqa: BLE001
            return self._error(exc)
        return self._modules_changed()

    @Slot(str, str, result=str)
    def saveModuleDialog(self, module_id: str, version: str) -> str:
        """Save as .scmod file…: one file to send along with an adventure."""
        t = self.session.t
        module = self.session.library.get(module_id, version, include_disabled=True)
        suggested = modmanager.default_file_name(module) if module else "module.scmod"
        path, _ = QFileDialog.getSaveFileName(self.window, t("dialog.saveModuleTitle"), suggested, t("dialog.scmodFilter"))
        if not path:
            return _json({"ok": False, "cancelled": True})
        return self.saveModuleTo(module_id, version, path)

    @Slot(str, str, str, result=str)
    def saveModuleTo(self, module_id: str, version: str, path: str) -> str:
        try:
            written = modmanager.save_as_scmod(self.session.library, module_id, version, Path(path))
        except Exception as exc:  # noqa: BLE001
            return self._error(exc)
        return _json({"ok": True, "path": str(written)})

    # --- module versions (F14.3; M6 part A) ---------------------------------------
    @Slot(str, str, result=str)
    def previewVersion(self, which: str, version: str) -> str:
        """Try another installed version in the preview; nothing changes yet."""
        try:
            info = self.session.preview_version(which, version)
        except Exception as exc:  # noqa: BLE001
            return self._error(exc)
        self._changed()
        return _json(info)

    @Slot(result=str)
    def applyVersion(self) -> str:
        info = self.session.apply_version_preview()
        self._changed()
        self._title_changed()
        return _json(info)

    @Slot(result=str)
    def cancelVersion(self) -> str:
        info = self.session.cancel_version_preview()
        self._changed()
        return _json(info)

    # --- tabs (F2.2) -------------------------------------------------------------
    @Slot(result=str)
    def tabs(self) -> str:
        return _json([
            {
                "id": s.id,
                "title": s.adventure.title if s.adventure else None,
                "dirty": s.dirty,
                "readOnly": s.read_only,
                "active": i == self.active,
            }
            for i, s in enumerate(self.sessions)
        ])

    @Slot(str, result=str)
    def switchTab(self, tab_id: str) -> str:
        for index, tab in enumerate(self.sessions):
            if tab.id == tab_id:
                self.active = index
                self._title_changed()
                self.requestBuild()
                return _json({"ok": True})
        return _json({"ok": False})

    @Slot(str, result=str)
    def closeTab(self, tab_id: str) -> str:
        previous = self.active
        if json.loads(self.switchTab(tab_id)).get("ok") is not True:
            return _json({"ok": False})
        if not self.confirm_discard():
            self.active = previous
            return _json({"ok": False, "cancelled": True})
        tab = self.session
        closing = self.active
        tab.close()
        if len(self.sessions) == 1:
            self.sessions[0] = tab.sibling(tab.work_dir)
            self.active = 0
        else:
            self.sessions.pop(closing)
            if previous > closing:
                previous -= 1
            elif previous == closing:
                previous = max(0, closing - 1)
            self.active = min(previous, len(self.sessions) - 1)
        self._title_changed()
        return _json({"ok": True})

    # --- files --------------------------------------------------------------------
    @Slot(str, result=str)
    def newAdventure(self, request: str) -> str:
        data = json.loads(request)
        reuse = self.session.adventure is None
        tab = self._tab_for_new_document()
        try:
            tab.new(
                data["title"], data["gameSystem"]["id"], data["gameSystem"]["version"],
                data["theme"]["id"], data["theme"]["version"],
            )
        except (ScavError, ModuleError) as exc:
            if not reuse:
                self.sessions.pop(self.active)
                self.active = len(self.sessions) - 1
            return self._error(exc)
        self._title_changed()
        return _json({"ok": True})

    @Slot(result=str)
    def openDialog(self) -> str:
        t = self.session.t
        path, _ = QFileDialog.getOpenFileName(self.window, t("dialog.openTitle"), "", t("dialog.scavFilter"))
        if not path:
            return _json({"ok": False, "cancelled": True})
        return self.openPath(path)

    @Slot(result=str)
    def openFolderDialog(self) -> str:
        """F2.4: open an unpacked adventure folder."""
        path = QFileDialog.getExistingDirectory(self.window, self.session.t("dialog.openFolderTitle"))
        if not path:
            return _json({"ok": False, "cancelled": True})
        return self.openPath(path)

    @Slot(str, result=str)
    def openPath(self, path: str) -> str:
        wanted = Path(path).resolve()
        for index, tab in enumerate(self.sessions):
            if tab.adventure is not None and tab.adventure.path is not None and Path(tab.adventure.path).resolve() == wanted:
                self.active = index  # already open in this window: show its tab
                self._title_changed()
                return _json({"ok": True, "switched": True})
        reuse = self.session.adventure is None
        tab = self._tab_for_new_document()
        try:
            tab.open(Path(path))
        except (ScavError, ModuleError) as exc:
            if not reuse:
                self.sessions.pop(self.active)
                self.active = len(self.sessions) - 1
            reply = self._error(exc)
            self._show_error(json.loads(reply)["error"])
            return reply
        self._title_changed()
        return _json({"ok": True, "readOnly": tab.read_only})

    @Slot(result=str)
    def save(self) -> str:
        if self.session.adventure is None:
            return _json({"ok": False})
        if self.session.adventure.path is None or self.session.read_only:
            return self.saveAs()
        return self.saveTo(str(self.session.adventure.path))

    @Slot(result=str)
    def saveAs(self) -> str:
        t = self.session.t
        suggestion = (self.session.adventure.title or t("app.untitled")) + ".scav"
        path, _ = QFileDialog.getSaveFileName(self.window, t("dialog.saveTitle"), suggestion, t("dialog.scavFilter"))
        if not path:
            return _json({"ok": False, "cancelled": True})
        return self.saveTo(path)

    @Slot(result=str)
    def saveAsFolderDialog(self) -> str:
        """F2.4: save as an unpacked folder, for authors who use Git."""
        path = QFileDialog.getExistingDirectory(self.window, self.session.t("dialog.saveFolderTitle"))
        if not path:
            return _json({"ok": False, "cancelled": True})
        return self.saveToFolder(path)

    @Slot(str, result=str)
    def saveTo(self, path: str) -> str:
        return self._save(path, None)

    @Slot(str, result=str)
    def saveToFolder(self, path: str) -> str:
        return self._save(path, True)

    def _save(self, path: str, as_folder: Optional[bool]) -> str:
        try:
            target = self.session.save(Path(path), as_folder=as_folder)
        except (ScavError, OSError) as exc:
            detail = self.session.t(exc.key, **exc.details) if isinstance(exc, ScavError) else str(exc)
            message = self.session.t("error.save.failed", message=detail)
            self._show_error(message)
            return _json({"ok": False, "error": message})
        self._title_changed()
        return _json({"ok": True, "path": str(target)})

    # --- work protection (F2.5–F2.8) ------------------------------------------------
    @Slot(result=str)
    def recoveries(self) -> str:
        return _json(self.session.recovery.orphans())

    @Slot(str, result=str)
    def restoreRecovery(self, session_id: str) -> str:
        meta = next((m for m in self.session.recovery.orphans() if m["session"] == session_id), None)
        if meta is None:
            return _json({"ok": False})
        tab = self._tab_for_new_document()
        tab.restore_recovery(meta)
        self._title_changed()
        return _json({"ok": True})

    @Slot(str, result=str)
    def discardRecovery(self, session_id: str) -> str:
        self.session.recovery.remove(session_id)
        return _json({"ok": True})

    def snapshot_tick(self) -> None:
        if self.closed:
            return
        for tab in self.sessions:
            tab.maybe_snapshot()

    @Slot(result=str)
    def snapshots(self) -> str:
        return _json(self.session.snapshot_list())

    @Slot(str, result=str)
    def revertTo(self, snapshot_id: str) -> str:
        try:
            self.session.revert(snapshot_id)
        except OSError as exc:
            return _json({"ok": False, "error": str(exc)})
        self._title_changed()
        self.requestBuild()
        return _json({"ok": True})

    # --- chapters ---------------------------------------------------------------------
    @Slot(int, result=str)
    def chapter(self, index: int) -> str:
        return _json(self.session.chapter(index))

    @Slot(int, str, result=str)
    def setChapterText(self, index: int, text: str) -> str:
        reply = self.session.set_chapter_text(index, text)
        self._title_changed()
        self.requestBuild()
        return _json(reply)

    @Slot(int, str, result=str)
    def setChapterDoc(self, index: int, doc: str) -> str:
        reply = self.session.set_chapter_doc(index, json.loads(doc))
        self._title_changed()
        self.requestBuild()
        return _json(reply)

    @Slot(str, result=str)
    def blockSource(self, block: str) -> str:
        """F4.1 Hybrid mode: the source of one block, as Source mode shows it."""
        from scriptorum.core import source

        return _json({"text": source.block_text(json.loads(block), self.session.kinds())})

    # --- settings page (F7.3, F7.9) -------------------------------------------------------
    @Slot(result=str)
    def settings(self) -> str:
        return _json(self.session.settings_info())

    @Slot(str, result=str)
    def setSettings(self, data: str) -> str:
        reply = self.session.set_settings(json.loads(data))
        self._title_changed()
        self.requestBuild()
        return _json(reply)

    # --- find and replace (F4.7) -------------------------------------------------------
    @Slot(str, result=str)
    def find(self, request: str) -> str:
        data = json.loads(request)
        return _json(self.session.find(data.get("query", ""), bool(data.get("matchCase"))))

    @Slot(str, result=str)
    def replaceAll(self, request: str) -> str:
        data = json.loads(request)
        count = self.session.replace_all(data.get("query", ""), data.get("replacement", ""), bool(data.get("matchCase")))
        if count:
            self._title_changed()
            self.requestBuild()
        return _json({"ok": True, "count": count})

    # --- images and fonts (F4.6, F11) -----------------------------------------------------
    @Slot(str, str, result=str)
    def addImageData(self, name: str, data: str) -> str:
        """An image dropped into the editor, as base64 from the interface."""
        try:
            path = self.session.add_image(name, base64.b64decode(data.split(",", 1)[-1]))
        except (ScavError, ValueError) as exc:
            return self._error(exc)
        self._title_changed()
        return _json({"ok": True, "path": path})

    @Slot(result=str)
    def addImageDialog(self) -> str:
        t = self.session.t
        path, _ = QFileDialog.getOpenFileName(self.window, t("dialog.imageTitle"), "", t("dialog.imageFilter"))
        if not path:
            return _json({"ok": False, "cancelled": True})
        try:
            stored = self.session.add_image(Path(path).name, Path(path).read_bytes())
        except (ScavError, OSError) as exc:
            return self._error(exc)
        self._title_changed()
        return _json({"ok": True, "path": stored})

    @Slot(result=str)
    def addPortraitDialog(self) -> str:
        """11.4 (M6 part C): choose a person's portrait, JPEG or PNG only."""
        t = self.session.t
        if self.pick_portrait is not None:  # the scenario tests stand in for the file dialog
            path = self.pick_portrait()
        else:
            path, _ = QFileDialog.getOpenFileName(self.window, t("dialog.portraitTitle"), "", t("dialog.portraitFilter"))
        if not path:
            return _json({"ok": False, "cancelled": True})
        return self.addPortraitPath(path)

    @Slot(str, result=str)
    def addPortraitPath(self, path: str) -> str:
        try:
            stored = self.session.add_portrait(Path(path).name, Path(path).read_bytes())
        except (ScavError, OSError) as exc:
            return self._error(exc)
        self._title_changed()
        return _json({"ok": True, "path": stored})

    @Slot(result=str)
    def addFontDialog(self) -> str:
        t = self.session.t
        path, _ = QFileDialog.getOpenFileName(self.window, t("dialog.fontTitle"), "", t("dialog.fontFilter"))
        if not path:
            return _json({"ok": False, "cancelled": True})
        return self.addFontPath(path)

    @Slot(str, result=str)
    def addFontPath(self, path: str) -> str:
        try:
            result = self.session.add_font(Path(path))
        except FontRefused as exc:
            return self._error(exc)
        self._title_changed()
        return _json({"ok": True, **result})

    @Slot(result=str)
    def fonts(self) -> str:
        return _json(self.session.font_list())

    @Slot(str, result=str)
    def imageUrl(self, path: str) -> str:
        """A local URL for showing an adventure image in the editor."""
        data = self.session.adventure.files.get(path.lstrip("/")) if self.session.adventure else None
        if data is None:
            return _json({"ok": False})
        folder = self.session.work_dir / "editor-images"
        folder.mkdir(parents=True, exist_ok=True)
        file = folder / Path(path).name
        if not file.is_file() or file.read_bytes() != data:
            file.write_bytes(data)
        return _json({"ok": True, "url": QUrl.fromLocalFile(str(file)).toString()})

    # --- spell check (F4.8) ---------------------------------------------------------------
    def _check_spell_ready(self) -> None:
        if self.closed:
            return
        if self.spelling.ready:
            self._spell_watch.stop()
            self.spellReady.emit()

    @Slot(str, result=str)
    def spell(self, words: str) -> str:
        # F9: a part that failed never waits silently; spell check says it
        # is unavailable instead of waiting for dictionaries that never load.
        if self.spelling.ready and self.spelling.unavailable:
            return _json({"ready": True, "wrong": [], "unavailable": self.session.t("spell.unavailable")})
        # F17.2 (M5): the adventure's document language chooses the dictionaries.
        lang = (self.session.adventure.settings.get("language") if self.session.adventure else None) or ""
        languages = {"sv": ("sv",), "en": ("en", "en-gb")}.get(lang)
        return _json({"ready": self.spelling.ready, "wrong": self.spelling.misspelled(json.loads(words), languages)})

    # --- the start-up checks in the main window (F9, M5) -----------------------------------
    def _check_lines(self, results) -> list:
        from scriptorum.core.startup import line_text

        table = self.session.strings.table
        return [{**r.to_json(), "text": line_text(table, r)} for r in results]

    @Slot(result=str)
    def startupReport(self) -> str:
        """What the start-up window found missing: the quiet bar names it."""
        problem = self.open_problem
        self.open_problem = None
        return _json({
            "problems": self._check_lines(self.startup_results),
            "openError": json.loads(self._error(problem))["error"] if problem is not None else "",
        })

    @Slot(result=str)
    def checkInstallation(self) -> str:
        """Help ▸ Check installation: the same list as the start-up window, on demand."""
        from scriptorum import __version__
        from scriptorum.core.startup import Startup, report_text

        startup = Startup()
        results = startup.run()
        self.startup_results = startup.failed()
        if startup.spelling is not None and not startup.spelling.unavailable and self.spelling.unavailable:
            self.spelling = startup.spelling  # the missing part was put back
        return _json({
            "ok": startup.ok,
            "results": self._check_lines(results),
            "report": report_text(self.session.strings.table, results, __version__),
            "version": __version__,
        })

    @Slot(result=str)
    def themeSelfTest(self) -> str:
        """Help ▸ Check installation: the slower theme self-test (9.7.5). The
        result arrives later through the ``selfTestFinished`` signal."""
        session = self.session

        def work():
            from scriptorum.core.startup import theme_self_test

            try:
                reply = _json({"ok": True, "lines": theme_self_test(session)})
            except Exception as exc:  # noqa: BLE001
                reply = _json({"ok": False, "error": str(exc), "lines": []})
            if not self.closed:
                self._selfTestDone.emit(reply)
        threading.Thread(target=work, daemon=True).start()
        return _json({"ok": True})

    @Slot(str, result=str)
    def copyText(self, text: str) -> str:
        """Copy details: the results as text on the clipboard."""
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.clipboard().setText(text)
        return _json({"ok": True})

    # --- preview zoom, remembered for each adventure outside its file (F7.2, M5) -----------
    @Slot(result=str)
    def previewZoom(self) -> str:
        return _json({"zoom": self.view_state.get_zoom(self.session.snapshot_key())})

    @Slot(str, result=str)
    def setPreviewZoom(self, value: str) -> str:
        try:
            wanted = json.loads(value)
        except json.JSONDecodeError:
            wanted = value
        return _json({"zoom": self.view_state.set_zoom(self.session.snapshot_key(), wanted)})

    @Slot(str, result=str)
    def suggest(self, word: str) -> str:
        """Suggestions arrive later through the ``suggestions`` signal."""
        def work():
            reply = _json({"word": word, "suggestions": self.spelling.suggest(word)})
            if not self.closed:
                self._suggestDone.emit(reply)
        threading.Thread(target=work, daemon=True).start()
        return _json({"ok": True})

    # --- building and export ---------------------------------------------------------
    @Slot(result=str)
    def requestBuild(self) -> str:
        """Restart the 0.3 s timer; the build runs when typing pauses."""
        if self.session.adventure is not None:
            self.last_request_time = time.monotonic()
            self._timer.start()
        return _json({"ok": True})

    def _start_build(self) -> None:
        if self.closed:
            return
        if self._building:
            self._rebuild = True
            return
        self._building = True
        self.last_build_start = time.monotonic()
        self._build_seq += 1
        seq = self._build_seq
        self.buildStarted.emit()
        session = self.session

        def work():
            element_map = []
            try:
                # SVG: vector pages, four times faster than PNG on long adventures.
                player = self.player_preview
                result = session.build("svg", player=player, show_breaks=self.show_breaks and not player)
                if result.ok and not player:
                    element_map = session.element_map()
            except Exception as exc:  # never leave the interface waiting
                result = BuildResult(False, errors=[Problem("error.build.typst", message=str(exc))])
            self._buildDone.emit(result, (session, element_map), seq)

        threading.Thread(target=work, daemon=True).start()

    def _finish_build(self, result: BuildResult, extra, seq: int) -> None:
        self._building = False
        if self.closed:
            return
        built_for, element_map = extra
        if self._rebuild or built_for is not self.session:
            self._rebuild = False
            self._start_build()
            return
        session = self.session
        if result.ok:
            self.element_map = element_map
            folder = session.work_dir / "preview"
            shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir(parents=True, exist_ok=True)
            urls = []
            for number, page in enumerate(result.output, start=1):
                file = folder / f"page-{seq}-{number}.svg"
                file.write_bytes(page if isinstance(page, bytes) else page.encode("utf-8"))
                urls.append(QUrl.fromLocalFile(str(file)).toString())
            payload = {
                "ok": True, "pages": urls,
                "warnings": [session.problem_json(w) for w in result.warnings],
                "seconds": result.seconds,
                "elements": element_map,
            }
        else:
            payload = {"ok": False, "errors": [session.problem_json(e) for e in result.errors]}
        self.last_build_payload = payload  # F7.2 (M5): for the separate preview window
        self.buildFinished.emit(_json(payload))

    @Slot(result=str)
    def exportDialog(self) -> str:
        if self.session.adventure is None:
            return _json({"ok": False})
        t = self.session.t
        base = self.session.adventure.path
        suggestion = str(base.with_suffix(".pdf")) if base else (self.session.adventure.title or "adventure") + ".pdf"
        path, _ = QFileDialog.getSaveFileName(self.window, t("dialog.exportTitle"), suggestion, t("dialog.pdfFilter"))
        if not path:
            return _json({"ok": False, "cancelled": True})
        return self.exportTo(path)

    @Slot(str, result=str)
    def exportTo(self, path: str) -> str:
        try:
            reply = self.session.export_pdf(Path(path))
        except OSError as exc:
            message = self.session.t("error.export.failed", message=str(exc))
            self._show_error(message)
            return _json({"ok": False, "error": message})
        return _json(reply)

    @Slot(result=str)
    def exportHandoutsDialog(self) -> str:
        """F7.6.2: the player PDF, with only the handouts (F6.2)."""
        if self.session.adventure is None:
            return _json({"ok": False})
        t = self.session.t
        base = self.session.adventure.path
        name = (base.stem if base else (self.session.adventure.title or "adventure")) + " - " + t("export.handoutsSuffix") + ".pdf"
        suggestion = str(base.with_name(name)) if base else name
        path, _ = QFileDialog.getSaveFileName(self.window, t("dialog.exportHandoutsTitle"), suggestion, t("dialog.pdfFilter"))
        if not path:
            return _json({"ok": False, "cancelled": True})
        return self.exportHandoutsTo(path)

    @Slot(str, result=str)
    def exportHandoutsTo(self, path: str) -> str:
        try:
            reply = self.session.export_pdf(Path(path), variant="handouts")
        except OSError as exc:
            message = self.session.t("error.export.failed", message=str(exc))
            self._show_error(message)
            return _json({"ok": False, "error": message})
        return _json(reply)

    @Slot(str, result=str)
    def exportVariantDialog(self, variant: str) -> str:
        """F7.6 (M5): File ▸ Export ▸ Booklet PDF… and Print-shop PDF…"""
        if self.session.adventure is None:
            return _json({"ok": False})
        t = self.session.t
        base = self.session.adventure.path
        name = (base.stem if base else (self.session.adventure.title or "adventure")) + " - " + t(f"export.suffix.{variant}") + ".pdf"
        suggestion = str(base.with_name(name)) if base else name
        path, _ = QFileDialog.getSaveFileName(self.window, t(f"export.title.{variant}"), suggestion, t("dialog.pdfFilter"))
        if not path:
            return _json({"ok": False, "cancelled": True})
        return self.exportVariantTo(path, variant)

    @Slot(str, str, result=str)
    def exportVariantTo(self, path: str, variant: str) -> str:
        try:
            reply = self.session.export_pdf(Path(path), variant=variant)
        except OSError as exc:
            message = self.session.t("error.export.failed", message=str(exc))
            self._show_error(message)
            return _json({"ok": False, "error": message})
        return _json(reply)

    # --- world-building (F3, F5, F6) ----------------------------------------------------
    def _changed(self) -> None:
        self._title_changed()
        self.requestBuild()

    def _world_call(self, work, changes: bool = True):
        """Every codex, map and chart action. F3 (M6 part C4): codex actions
        never fail silently. A refusal says why in plain words; an
        unexpected error says so too, and its details go to the crash log in
        the app's own folder (F2.11). Nothing is ever sent anywhere."""
        if self.session.adventure is None:
            return _json({"ok": False, "error": self.session.t("error.codex.noAdventure")})
        try:
            result = work()
        except (WorldError, ScavError, ModuleError) as exc:
            return self._error(exc)
        except Exception as exc:  # noqa: BLE001
            return self._unexpected(exc)
        if changes:
            self._changed()
        return _json({"ok": True, **(result if isinstance(result, dict) else {"result": result})})

    def _unexpected(self, exc: Exception) -> str:
        from scriptorum.core.crashlog import write_crash_log
        try:
            log = write_crash_log(type(exc), exc, exc.__traceback__, getattr(self, "crash_folder", None))
            self.last_crash_log = str(log)
        except OSError:
            self.last_crash_log = None
        return _json({"ok": False, "error": self.session.t("error.codex.failed"), "logged": self.last_crash_log is not None})

    @Slot(result=str)
    def codex(self) -> str:
        if self.session.adventure is None:
            return _json({"types": [], "entries": [], "maps": [], "handouts": []})
        return _json(self.session.codex())

    @Slot(str, result=str)
    def entry(self, entry_id: str) -> str:
        return self._world_call(lambda: self.session.entry_info(entry_id), changes=False)

    @Slot(str, result=str)
    def convertInfo(self, request: str) -> str:
        """F3 (M6 part C4): what Convert to codex entry offers for a block."""
        data = json.loads(request)
        return self._world_call(lambda: self.session.convert_info(int(data.get("chapter", 0)), data.get("path", [])),
                                changes=False)

    @Slot(str, result=str)
    def convertToEntry(self, request: str) -> str:
        data = json.loads(request)
        return self._world_call(lambda: self.session.convert_to_entry(
            int(data.get("chapter", 0)), data.get("path", []), data.get("type", ""), data.get("link") or None))

    @Slot(str, result=str)
    def createEntry(self, request: str) -> str:
        data = json.loads(request)
        return self._world_call(lambda: self.session.create_entry(
            data.get("type", ""), data.get("title", ""), data.get("fields"), data.get("folder", "")))

    @Slot(str, result=str)
    def updateEntry(self, request: str) -> str:
        data = json.loads(request)
        return self._world_call(lambda: self.session.update_entry(data["id"], data.get("data", {})))

    @Slot(str, result=str)
    def deleteEntry(self, entry_id: str) -> str:
        return self._world_call(lambda: self.session.delete_entry(entry_id))

    @Slot(str, result=str)
    def saveCodexType(self, request: str) -> str:
        return self._world_call(lambda: self.session.save_codex_type(json.loads(request)))

    @Slot(int, int, result=str)
    def sceneEntries(self, chapter: int, line: int) -> str:
        if self.session.adventure is None:
            return _json({"scene": None, "entries": []})
        return _json(self.session.scene_entries(chapter, line if line > 0 else None))

    @Slot(result=str)
    def worldUndo(self) -> str:
        done = self.session.world_undo()
        if done:
            self._changed()
        return _json({"ok": done})

    @Slot(str, result=str)
    def mapInfo(self, map_id: str) -> str:
        try:
            m = self.session.map_info(map_id)
        except WorldError as exc:
            return self._error(exc)
        data = self.session.adventure.files.get(m["image"])
        url = None
        if data is not None:
            folder = self.session.work_dir / "editor-maps"
            folder.mkdir(parents=True, exist_ok=True)
            file = folder / (m["id"] + Path(m["image"]).suffix)
            if not file.is_file() or file.read_bytes() != data:
                file.write_bytes(data)
            url = QUrl.fromLocalFile(str(file)).toString()
        return _json({"ok": True, "map": m, "url": url})

    @Slot(str, result=str)
    def createMapDialog(self, title: str) -> str:
        """F5.7: a map's base image is a JPEG or PNG file."""
        t = self.session.t
        path, _ = QFileDialog.getOpenFileName(self.window, t("dialog.mapImageTitle"), "", t("dialog.mapImageFilter"))
        if not path:
            return _json({"ok": False, "cancelled": True})
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            return _json({"ok": False, "error": str(exc)})
        return self._world_call(lambda: self.session.create_map(title or Path(path).stem, Path(path).name, data))

    @Slot(str, str, str, result=str)
    def createMapData(self, title: str, name: str, data: str) -> str:
        raw = base64.b64decode(data.split(",", 1)[-1])
        return self._world_call(lambda: self.session.create_map(title, name, raw))

    @Slot(str, result=str)
    def updateMap(self, request: str) -> str:
        return self._world_call(lambda: self.session.update_map(json.loads(request)))

    @Slot(str, result=str)
    def deleteMap(self, map_id: str) -> str:
        return self._world_call(lambda: self.session.delete_map(map_id))

    @Slot(result=str)
    def chart(self) -> str:
        return _json(self.session.chart() if self.session.adventure else {"nodes": [], "edges": []})

    @Slot(str, result=str)
    def setChartPositions(self, request: str) -> str:
        return self._world_call(lambda: self.session.set_chart_positions(json.loads(request)))

    @Slot(result=str)
    def upgradeOffer(self) -> str:
        """F3.12: offered once when an adventure saved before M3 opens."""
        if self.session.adventure is None:
            return _json({"offer": False, "candidates": []})
        return _json({"offer": self.session.offers_upgrade(), "candidates": self.session.upgrade_candidates()})

    @Slot(str, result=str)
    def applyUpgrade(self, request: str) -> str:
        return self._world_call(lambda: self.session.apply_upgrade(json.loads(request)))

    @Slot(result=str)
    def lastBuild(self) -> str:
        """F7.2 (M5): the last build's pages, for a newly opened preview window."""
        return _json(getattr(self, "last_build_payload", None))

    @Slot(result=str)
    def previewWindowTitle(self) -> str:
        adventure = self.session.adventure
        title = adventure.title if adventure else ""
        return _json({"title": self.session.t("app.previewWindowTitle", title=title or self.session.t("app.untitled"))})

    @Slot(result=str)
    def openPreviewWindow(self) -> str:
        """F7.2 (M5): the preview in a window of its own, with the same zoom bar."""
        if self.window is None or not hasattr(self.window, "open_preview_window"):
            return _json({"ok": False})
        self.window.open_preview_window()
        return _json({"ok": True})

    @Slot(bool, result=str)
    def setShowBreaks(self, on: bool) -> str:
        """F7.2 (M5): View ▸ Show breaks marks page and column breaks in the
        preview. Exported PDFs never show them."""
        self.show_breaks = bool(on)
        self.requestBuild()
        return _json({"ok": True, "on": self.show_breaks})

    @Slot(bool, result=str)
    def setHandoutsOnly(self, on: bool) -> str:
        """F6.4: the preview shows exactly what the players will receive."""
        self.player_preview = bool(on)
        self.requestBuild()
        return _json({"ok": True, "on": self.player_preview})

    @Slot(result=str)
    def quit(self) -> str:
        if self.window is not None:
            self.window.close()
        return _json({"ok": True})

    # --- messages --------------------------------------------------------------------
    def _show_error(self, text: str) -> None:
        if self.window is None or getattr(self.window, "headless_test", False):
            return
        QMessageBox.warning(self.window, self.session.t("dialog.errorTitle"), text)

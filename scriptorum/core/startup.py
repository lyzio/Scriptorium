"""The start-up checks (design document F9, decided 11 November 2026, M5).

When Scriptorum starts, a small window shows one line per check, each ticked
as it passes: modules found, fonts present, spelling dictionaries loaded,
Typst can build a one-line page, and the app's folders can be written to.
Only quick checks run here, about two seconds in all; the dictionaries and
Typst are then ready at once in the editor.

A check that fails gives its reason in plain words. "Continue anyway" opens
the app without that part, unless the app cannot run at all without it (no
modules, so no interface text). Help ▸ Check installation shows the same
list on demand and can also run the slower theme self-test (9.7.5).

This file has no window in it: the window is scriptorum/app/startup_window.py.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from scriptorum import paths

# The lines of the start-up window, in the order they are shown.
CHECKS = ("modules", "fonts", "dictionaries", "typst", "folders")
FONT_SUFFIXES = (".ttf", ".otf", ".woff2")


@dataclass
class CheckResult:
    id: str
    ok: bool
    reason: str = ""                       # a string key in startup.json
    details: Dict[str, object] = field(default_factory=dict)
    fatal: bool = False                    # the app cannot open without this part

    def to_json(self) -> dict:
        return {"id": self.id, "ok": self.ok, "reason": self.reason, "details": self.details, "fatal": self.fatal}


def bundled_strings() -> Dict[str, str]:
    """The interface text of the bundled interface-language module (F15),
    read straight from the app's own folder: the start-up window needs its
    words before the module library has been checked."""
    table: Dict[str, str] = {}
    folder = paths.BUNDLED_MODULES_DIR / "scriptorum.en" / "strings"
    for file in sorted(folder.glob("*.json")):
        try:
            for key, value in json.loads(file.read_text("utf-8")).items():
                table[f"{file.stem}.{key}"] = value
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
    return table


def text_of(strings: Dict[str, str], key: str, **details) -> str:
    text = strings.get(key, key)
    for name, value in details.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def line_text(strings: Dict[str, str], result: CheckResult) -> str:
    """One line as the window shows it: the check's name, and for a failed
    one the reason, such as "Spelling dictionaries: the spylls library is
    not installed"."""
    name = text_of(strings, f"startup.check.{result.id}")
    if result.ok:
        return name
    return text_of(strings, "startup.failedLine", check=name, reason=text_of(strings, result.reason, **result.details))


def report_text(strings: Dict[str, str], results: List[CheckResult], version: str) -> str:
    """Copy details: the results as plain text."""
    lines = [text_of(strings, "startup.reportTitle", version=version)]
    for result in results:
        mark = text_of(strings, "startup.reportOk" if result.ok else "startup.reportFailed")
        lines.append(f"{mark}  {line_text(strings, result)}")
    return "\n".join(lines) + "\n"


class Startup:
    """Runs the checks and keeps what they made ready: the session (module
    library and interface text) and the loaded spell checker."""

    def __init__(self):
        self.session = None
        self.spelling = None
        self.results: List[CheckResult] = []

    # --- the checks, one per line -------------------------------------------------
    def check_modules(self) -> CheckResult:
        """Modules found: the core element kit, game systems and themes."""
        from scriptorum.core.session import Session

        try:
            self.session = Session.start()
        except Exception as exc:  # noqa: BLE001 - the reason is shown in plain words
            return CheckResult("modules", False, "startup.reason.modulesFailed", {"message": _plain(exc)}, fatal=True)
        library = self.session.library
        if not any(m.id == "scriptorum.core" for m in library.of_kind("element-kit")):
            return CheckResult("modules", False, "startup.reason.noCoreKit", fatal=True)
        if not library.of_kind("game-system"):
            return CheckResult("modules", False, "startup.reason.noGameSystem")
        if not library.of_kind("theme"):
            return CheckResult("modules", False, "startup.reason.noTheme")
        return CheckResult("modules", True)

    def check_fonts(self) -> CheckResult:
        """Fonts present: every theme has its fonts, and the core element
        kit has the handwriting hands (F8), each a readable file."""
        if self.session is None:
            return CheckResult("fonts", False, "startup.reason.noModules")
        library = self.session.library
        for module in [*library.of_kind("theme"), *library.of_kind("element-kit")]:
            fonts = [f for f in sorted((module.path / "fonts").glob("*")) if f.suffix.lower() in FONT_SUFFIXES]
            if module.kind == "theme" and not fonts:
                return CheckResult("fonts", False, "startup.reason.noFonts", {"module": module.name})
            for font in fonts:
                try:
                    if font.stat().st_size < 1000:
                        raise OSError
                    with font.open("rb") as handle:
                        handle.read(4)
                except OSError:
                    return CheckResult("fonts", False, "startup.reason.fontUnreadable", {"file": font.name, "module": module.name})
        return CheckResult("fonts", True)

    def check_dictionaries(self) -> CheckResult:
        """Spelling dictionaries loaded: they are then ready at once in the editor."""
        from scriptorum.core.spelling import SpellChecker

        self.spelling = SpellChecker()
        self.spelling.load_now()
        if self.spelling.unavailable == "library":
            return CheckResult("dictionaries", False, "startup.reason.noSpylls")
        if self.spelling.unavailable:
            return CheckResult("dictionaries", False, "startup.reason.noDictionaries")
        missing = self.spelling.missing_languages()
        if missing:
            return CheckResult("dictionaries", False, "startup.reason.dictionaryMissing", {"languages": ", ".join(missing)})
        return CheckResult("dictionaries", True)

    def check_typst(self) -> CheckResult:
        """Typst can build a one-line page."""
        try:
            import typst
        except ImportError:
            return CheckResult("typst", False, "startup.reason.noTypst")
        try:
            with tempfile.TemporaryDirectory(prefix="scriptorum-check-") as folder:
                source = Path(folder) / "line.typ"
                source.write_text("One line.\n", "utf-8")
                empty = Path(folder) / "none"
                empty.mkdir()
                compiler = typst.Compiler(input=str(source), root=folder, ignore_system_fonts=True,
                                          package_path=str(empty), package_cache_path=str(empty))
                data = compiler.compile(format="pdf", timestamp=0)
            if not bytes(data).startswith(b"%PDF"):
                raise ValueError("no PDF")
        except Exception as exc:  # noqa: BLE001
            return CheckResult("typst", False, "startup.reason.typstFailed", {"message": _plain(exc)})
        return CheckResult("typst", True)

    def check_folders(self) -> CheckResult:
        """The app's folders can be written to."""
        try:
            folders = [paths.app_home(), paths.module_library_dir(), paths.build_root(), paths.logs_dir()]
        except OSError as exc:
            return CheckResult("folders", False, "startup.reason.folderFailed", {"folder": "", "message": _plain(exc)}, fatal=True)
        for folder in folders:
            try:
                with tempfile.NamedTemporaryFile(dir=folder, prefix=".write-check-"):
                    pass
            except OSError as exc:
                return CheckResult("folders", False, "startup.reason.folderFailed", {"folder": str(folder), "message": _plain(exc)}, fatal=True)
        return CheckResult("folders", True)

    # --- running them ----------------------------------------------------------------
    def run(self, on_result: Optional[Callable[[CheckResult], None]] = None) -> List[CheckResult]:
        self.results = []
        for check_id in CHECKS:
            try:
                result = getattr(self, f"check_{check_id}")()
            except Exception as exc:  # noqa: BLE001 - a check never stops the others
                result = CheckResult(check_id, False, "startup.reason.unexpected", {"message": _plain(exc)})
            self.results.append(result)
            if on_result is not None:
                on_result(result)
        return self.results

    @property
    def ok(self) -> bool:
        return bool(self.results) and all(r.ok for r in self.results)

    @property
    def can_continue(self) -> bool:
        """Continue anyway opens the app without the part that failed; it
        cannot when there is no session (no modules, no interface text)."""
        return self.session is not None and not any(r.fatal and not r.ok for r in self.results)

    def failed(self) -> List[CheckResult]:
        return [r for r in self.results if not r.ok]


def _plain(exc: Exception) -> str:
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return text[:200]


def theme_self_test(session, work_dir: Optional[Path] = None) -> List[dict]:
    """Help ▸ Check installation: the slower theme self-test (9.7.5), not
    run at start-up. One line per theme and the game system it is offered
    for, with the problems found."""
    from scriptorum.core.build import TEST_ADVENTURE, Builder
    from scriptorum.core.modules import theme_offered_for
    from scriptorum.core.scav import ModuleRef, new_adventure

    library = session.library
    kits = [ModuleRef(m.id, m.version) for m in library.of_kind("element-kit")]
    lines = []
    with tempfile.TemporaryDirectory(prefix="scriptorum-selftest-") as folder:
        root = Path(work_dir or folder)
        for theme in library.of_kind("theme"):
            for gs in library.of_kind("game-system"):
                if not theme_offered_for(library, theme, gs):
                    continue
                adventure = new_adventure("Test", ModuleRef(gs.id, gs.version), ModuleRef(theme.id, theme.version), kits, TEST_ADVENTURE)
                result = Builder(library, root / f"selftest-{theme.id}-{gs.id}").build(adventure, "pdf")
                lines.append({
                    "theme": theme.name, "gameSystem": gs.name, "ok": result.ok,
                    "problems": [session.localize(p) for p in result.errors],
                })
    return lines

"""The build assembler (design document 3.3 and 9.6).

For every build it prepares a private build folder:

    m/<module-id>/        copies of the adventure's pinned content modules
    text/<chapter>.typ    each chapter, with one import line put in front
    assets/               the adventure's own images and fonts (F4.6, F11)
    page.json             the page setup: the theme's, overridden by the
                          adventure settings page (F7.3)
    world.json            M3: codex entries and types, maps, the relationship
                          chart, and whether this is the adventure PDF or the
                          player PDF (F3, F5, F6)
    maps/                 the adventure's map images (F5)
    prelude.typ           connects the element functions of the core element
                          kit (and the game system) to the theme's renderers,
                          passes the game system's data, loads printed words
    main.typ              the entry file: page setup, title page (F7.9),
                          act-heading rule (F7.4), the chapters in order and
                          the end-of-book material (F3.10). For the player
                          PDF (F6.2) it holds only the handouts, in order.

Typst compiles main.typ with that folder as its root, so it can read nothing
else (T-BUILD-08). The author's own files are never touched (T-BUILD-07).
Errors are mapped back to the author's own line (T-BUILD-04).
"""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

try:
    import typst
except ImportError:  # F9: the start-up window names it; the app still opens
    typst = None


class _NoTypst(Exception):
    """Stands in for typst.TypstError when the Typst library is missing."""


TypstError = typst.TypstError if typst is not None else _NoTypst
# F7.1 (M6 part B): every compile runs in the build helper, which sends Typst
# errors back as HelperTypstError and raises BuildStopped when it is stopped.
from scriptorum.core.helper import BuildStopped, HelperTypstError, helper  # noqa: E402

TYPST_ERRORS = (TypstError, HelperTypstError)


def stopped_problem(stopped: "BuildStopped") -> "Problem":
    """F7.1: the build was stopped after the time limit, or the helper ended."""
    from scriptorum.core import helper as helper_module
    if stopped.reason == "time":
        return Problem("error.build.timeLimit", {"seconds": int(helper_module.TIME_LIMIT)})
    return Problem("error.build.crashed", {})

from scriptorum import __version__
from scriptorum.core.modules import Library, Module, package_import
from scriptorum.core.scav import Adventure, ModuleRef
from scriptorum.core.source import complete_bare_calls, fit_to_game_system, quote_string, retag_outside_headings

PRELUDE_LINES = 1  # lines put in front of every chapter in the build folder
PACKAGE_IMPORT = re.compile(r'"@[a-z0-9-]+/')
LOCATION = re.compile(r"┌─ (\S+?):(\d+):(\d+)")
SCRIPTORUM_PANIC = re.compile(r"SCRIPTORUM:([a-z]+):([a-z0-9-]+):([a-z0-9-]+)")
FIXED_TIMESTAMP = 0  # F7.8: no clock in the output
# Theme renderers the core element kit uses that are not element kinds of
# their own: the codex card for any codex type (F3.4) and the end-of-book
# material (F3.10).
EXTRA_RENDERERS = ("codex-card", "end-clues", "end-index")


@dataclass
class Problem:
    key: str
    details: Dict[str, object] = field(default_factory=dict)
    chapter: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    message: str = ""

    def to_json(self) -> dict:
        return {
            "key": self.key,
            "details": self.details,
            "chapter": self.chapter,
            "line": self.line,
            "column": self.column,
            "message": self.message,
        }


@dataclass
class BuildResult:
    ok: bool
    output: List[bytes] = field(default_factory=list)
    errors: List[Problem] = field(default_factory=list)
    warnings: List[Problem] = field(default_factory=list)
    seconds: float = 0.0


class BuildFailed(Exception):
    def __init__(self, problem: Problem):
        super().__init__(problem.key)
        self.problem = problem


class Builder:
    def __init__(self, library: Library, work_dir: Path):
        self.library = library
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._compiled = False  # a build has run here, so its folder can be queried

    # --- modules -----------------------------------------------------------
    def resolve(self, ref: ModuleRef) -> Module:
        module = self.library.get(ref.id, ref.version)
        if module is None:
            raise BuildFailed(Problem("error.build.missingModule", {"id": ref.id, "version": ref.version}))
        return module

    def content_modules(self, adventure: Adventure) -> Dict[str, Module]:
        return {ref.id: self.resolve(ref) for ref in adventure.modules}

    def element_kinds(self, adventure: Adventure, modules: Optional[Dict[str, Module]] = None) -> Dict[str, dict]:
        """The element kinds this adventure can use (9.3, amended 5 Nov 2026).

        The core element kit holds every kind; the game system turns on the
        ones it needs in its elements.json (layout markers are always on) and
        may add kinds of its own. A stat block field is filled in from the
        game system's stat-blocks/<element>.json (11.5)."""
        modules = modules if modules is not None else self.content_modules(adventure)
        game = modules.get(adventure.game_system.id)
        turned_on = game.turned_on() if game is not None else None
        stat_blocks = game.stat_blocks() if game is not None else {}
        kinds: Dict[str, dict] = {}
        for module in modules.values():
            if module.kind != "element-kit":
                continue
            for kind_id, definition in module.element_kinds().items():
                if turned_on is None or kind_id in turned_on or definition.get("always_on"):
                    kinds[kind_id] = {**definition, "module": module.id}
        if game is not None:
            for kind_id, definition in game.element_kinds().items():
                kinds[kind_id] = {**definition, "module": game.id}
        return {k: expand_stat_block(d, stat_blocks) for k, d in kinds.items()}

    # --- preparing the build folder -----------------------------------------
    def _copy_modules(self, modules: Dict[str, Module]) -> None:
        mroot = self.work_dir / "m"
        mroot.mkdir(exist_ok=True)
        for module in modules.values():
            # 9.7 (decided 12 Nov 2026): a module that imports a package by
            # name is refused before compiling, on every build, so one copied
            # or edited in the library by hand is caught too (D9).
            found = package_import(module.path)
            if found:
                raise BuildFailed(Problem("error.build.modulePackage", {"module": module.name, **found}))
            target = mroot / module.id
            stamp = target / ".scriptorum-version"
            if target.exists() and stamp.exists() and stamp.read_text() == module.version:
                continue
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(module.path, target)
            stamp.write_text(module.version)
        for stale in mroot.iterdir():
            if stale.name not in modules:
                shutil.rmtree(stale, ignore_errors=True)

    def prepare(self, adventure: Adventure, world: Optional[dict] = None,
                player: Optional[List[str]] = None, language: Optional[str] = None,
                page_extra: str = "") -> List[Problem]:
        """Write the build folder. ``world`` is the data for world.json;
        ``player`` the handouts' source text for the player PDF (F6.2);
        ``language`` the adventure's document language (9.6.6)."""
        modules = self.content_modules(adventure)
        game_system = modules[adventure.game_system.id]
        theme = modules[adventure.theme.id]
        kits = [m for m in modules.values() if m.kind == "element-kit"]
        self._copy_modules(modules)
        kinds = self.element_kinds(adventure, modules)
        warnings: List[Problem] = []

        th = theme.id
        lines = [
            f"// Generated by Scriptorum {__version__} for every build. Never edit by hand.",
            f'#import "/m/{th}/templates/_page.typ": setup as _scriptorum-setup',
            f'#import "/m/{th}/templates/_generic.typ": render as _scriptorum-generic',
        ]
        label_files = [f"/m/{m.id}/labels/en.json" for m in [*kits, game_system, theme] if (m.path / "labels" / "en.json").is_file()]
        # 9.6.6: an adventure-language module the adventure pins for its
        # document language replaces the built-in English words.
        if language and language != "en":
            for module in modules.values():
                if module.kind == "adventure-language" and module.manifest.get("language") == language:
                    for m in [*kits, game_system, theme]:
                        if (module.path / "labels" / f"{m.id}.json").is_file():
                            label_files.append(f"/m/{module.id}/labels/{m.id}.json")
                    warnings.extend(missing_translations(module, [*kits, game_system, theme]))
        lines.append("#let _scriptorum-labels = " + " + ".join(f'json("{p}")' for p in label_files))
        lines.append('#let _scriptorum-page = json("/page.json")')
        lines.append('#let _scriptorum-world = json("/world.json")')
        # The game system's data for the core element kit (11.5, 11.7).
        game_parts = []
        blocks = [f'{quote_string(name)}: json("/m/{game_system.id}/stat-blocks/{name}.json")' for name in game_system.stat_blocks()]
        game_parts.append("stat-blocks: (" + (", ".join(blocks) + ("," if len(blocks) == 1 else "") if blocks else ":") + ")")
        if (game_system.path / "notation.json").is_file():
            game_parts.append(f'notation: json("/m/{game_system.id}/notation.json")')
        lines.append("#let _scriptorum-game = (" + ", ".join(game_parts) + ")")
        if theme.has_template("title-page"):
            lines.append(f'#import "/m/{th}/templates/title-page.typ": render as _scriptorum-title-page')
        else:
            lines.append("#let _scriptorum-title-page(f, labels) = align(center + horizon, text(size: 24pt, f.title))")

        makers = []
        exported: List[str] = []
        for index, module in enumerate([*kits, game_system]):
            renderers = []
            for kind_id, definition in kinds.items():
                if definition.get("module") != module.id:
                    continue
                exported.append(kind_id)
                # Layout markers have no renderer, and neither do codex cards
                # and references: they print through other renderers (F3.4).
                if definition.get("category") == "layout" or definition.get("renderer") is False:
                    continue
                if theme.has_template(kind_id):
                    alias = f"_scriptorum-r-{kind_id}"
                    lines.append(f'#import "/m/{th}/templates/{kind_id}.typ": render as {alias}')
                    renderers.append(f"{kind_id}: {alias}")
                else:
                    renderers.append(f"{kind_id}: _scriptorum-generic.with(kind: {quote_string(kind_id)})")
                    warnings.append(Problem("warning.build.genericFrame", {"element": kind_id, "theme": theme.name}))
            if not (module.path / "typst" / "elements.typ").is_file():
                continue
            extra = ""
            if module.kind == "element-kit":
                for name in EXTRA_RENDERERS:
                    if theme.has_template(name):
                        alias = f"_scriptorum-r-{name}"
                        lines.append(f'#import "/m/{th}/templates/{name}.typ": render as {alias}')
                        renderers.append(f"{name}: {alias}")
                    else:
                        renderers.append(f"{name}: _scriptorum-generic.with(kind: {quote_string(name)})")
                # M3: the core element kit also gets the codex, maps and mode.
                extra = ", world: _scriptorum-world"
            maker = f"_scriptorum-make-{index}"
            lines.append(f'#import "/m/{module.id}/typst/elements.typ": make as {maker}')
            table = "(" + ", ".join(renderers) + (",)" if len(renderers) == 1 else ")") if renderers else "(:)"
            makers.append(f"{maker}({table}, _scriptorum-labels, game: _scriptorum-game{extra})")
        lines.append("#let _scriptorum-el = " + (" + ".join(makers) if makers else "(:)"))
        for kind_id in exported:
            lines.append(f'#let {kind_id} = _scriptorum-el.at("{kind_id}")')
        (self.work_dir / "prelude.typ").write_text("\n".join(lines) + "\n", "utf-8")

        # F7.3: the theme's page setup, overridden by the adventure settings.
        page = effective_page(theme.page_setup(), adventure.settings)
        # F17.2 (M5): the document language is used for the PDF (and its tags).
        page["values"]["lang"] = language or "en"
        (self.work_dir / "page.json").write_text(json.dumps(page["values"], indent=2), "utf-8")
        world = world or {"mode": "gm"}
        (self.work_dir / "world.json").write_text(json.dumps(world, ensure_ascii=False, indent=1), "utf-8")

        text_dir = self.work_dir / "text"
        shutil.rmtree(text_dir, ignore_errors=True)
        text_dir.mkdir()
        chapters = {c: adventure.chapter_text(c) for c in adventure.chapters}
        if player is not None:
            # F6.2: the player PDF holds only the handouts, each on a page of
            # its own, in adventure order.
            chapters = {"text/player.typ": "\n\n#pagebreak(weak: true)\n\n".join(player) + "\n"}
        for chapter, content in chapters.items():
            match = PACKAGE_IMPORT.search(content)
            if match:
                line = content.count("\n", 0, match.start()) + 1
                raise BuildFailed(Problem("error.build.packagesNotAllowed", {}, chapter, line))
            # F4, F7.4 (M6 part C): older text with a bare #column-break
            # and the like prints correctly; the author's file is unchanged.
            # F14 (M6-0.6.9): text written for another game system prints;
            # what does not fit is left out of this copy only.
            content = fit_to_game_system(content, kinds, game_system.notation())[0]
            content = complete_bare_calls(content, kinds)
            content = retag_outside_headings(content, kinds)
            target = self.work_dir / chapter
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('#import "/prelude.typ": *\n' + content, "utf-8")

        # F4.6, F11: the adventure's own images and fonts.
        assets = self.work_dir / "assets"
        shutil.rmtree(assets, ignore_errors=True)
        shutil.rmtree(self.work_dir / "maps", ignore_errors=True)
        for name, data in adventure.files.items():
            if (name.startswith("assets/") or name.startswith("maps/")) and safe_member(name):
                target = self.work_dir / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)

        title = title_page_fields(adventure)
        main = [
            '#import "/prelude.typ": *',
            f"#set document(title: {quote_string(adventure.title)}, date: none)",
            "#show: _scriptorum-setup.with(_scriptorum-page, _scriptorum-labels)",
        ]
        if page_extra:
            # F7.6.5 (M5): the print-shop version's bleed, slug and crop marks.
            main.append(page_extra)
        if player is not None:
            # One full-width column and no page numbers: each page is a
            # handout to give to the players (F6.2).
            main.append("#set page(columns: 1, numbering: none, footer: none, header: none)")
            main += [f'#include "/{c}"' for c in chapters]
            (self.work_dir / "main.typ").write_text("\n".join(main) + "\n", "utf-8")
            return warnings
        main += [
            # F7.4: an act heading starts a page and its first scene shares it.
            # Act headings straight after each other share one page with the
            # first scene after them (decided 6 Nov 2026, M4); a page-break
            # marker before an act heading still starts a new page.
            # F17 (M5): the title on the title page is a heading, but no act heading.
            '#show heading.where(level: 1): it => if it.has("label") and it.label == <scriptorum-title-heading> { it } else { context { if not state("scriptorum-act-open", false).get() { pagebreak(weak: true) } }; state("scriptorum-act-open", false).update(true); it }',
            "#let _scriptorum-title = (" + ", ".join(f"{k}: {quote_string(v)}" for k, v in title.items()) + ")",
            # F7.9: the title page; the chapter text starts on the next page.
            "#page(columns: 1, numbering: none, header: none, footer: none, _scriptorum-title-page(_scriptorum-title, _scriptorum-labels))",
        ]
        main += [f'#include "/{chapter}"' for chapter in adventure.chapters]
        # F3.10: end-of-book material, each switched on in the settings.
        end = world.get("end", {})
        if end.get("clue_overview") and "_end-clues" in self._kit_exports(kits):
            main.append('#(_scriptorum-el.at("_end-clues"))()')
        if end.get("index") and "_end-index" in self._kit_exports(kits):
            main.append('#(_scriptorum-el.at("_end-index"))()')
        (self.work_dir / "main.typ").write_text("\n".join(main) + "\n", "utf-8")
        return warnings

    @staticmethod
    def _kit_exports(kits) -> set:
        names = set()
        for kit in kits:
            file = kit.path / "typst" / "elements.typ"
            if file.is_file():
                names.update(re.findall(r"^\s*(_end-[a-z]+):", file.read_text("utf-8"), re.M))
        return names

    # --- compiling --------------------------------------------------------------
    def _spec(self) -> dict:
        """What the helper needs to compile this build folder (F7.1)."""
        candidates = [*sorted((self.work_dir / "m").glob("*/fonts")), self.work_dir / "assets" / "fonts"]
        font_dirs = [str(p) for p in candidates if p.is_dir() and any(p.iterdir())]
        nopkg = self.work_dir / ".no-packages"
        nopkg.mkdir(exist_ok=True)
        return {
            "input": str(self.work_dir / "main.typ"),
            "root": str(self.work_dir),
            "font_paths": font_dirs,
            # A changed font set needs a new compiler in the helper.
            "fonts_key": tuple(sorted(f.name for d in font_dirs for f in Path(d).iterdir())),
            "no_packages": str(nopkg),  # F7.8: no packages and no system fonts
        }

    def _query(self, selector: str, **kwargs):
        """One query on the last build, in the helper; None when it fails."""
        if not (self.work_dir / "main.typ").is_file():
            return None
        try:
            return helper().call({"op": "query", "spec": self._spec(), "selector": selector, "kwargs": kwargs})
        except (BuildStopped, *TYPST_ERRORS):
            return None

    def build(self, adventure: Adventure, fmt: str = "pdf", ppi: Optional[float] = None,
              world: Optional[dict] = None, player: Optional[List[str]] = None,
              language: Optional[str] = None, page_extra: str = "",
              standards: Optional[List[str]] = None) -> BuildResult:
        started = time.monotonic()
        if typst is None:
            # F9: a part that is missing never waits silently.
            return BuildResult(False, errors=[Problem("error.build.noTypst")])
        with self._lock:
            try:
                warnings = self.prepare(adventure, world, player, language, page_extra)
                self.content_modules(adventure)
                kwargs = {"format": fmt}
                if fmt == "png":
                    kwargs["ppi"] = ppi or 110
                if fmt == "pdf":
                    kwargs["timestamp"] = FIXED_TIMESTAMP
                    if standards:
                        # F7.6.5, F17 (M5): PDF/A-2b for the print shop; PDF/UA-1.
                        kwargs["pdf_standards"] = list(standards)
                # F7.1 (M6): compiled in the build helper, within the time limit.
                reply = helper().call({"op": "compile", "spec": self._spec(), "kwargs": kwargs})
                data, typst_warnings = reply["data"], reply["warnings"]
                self._compiled = True
            except BuildFailed as failed:
                return BuildResult(False, errors=[failed.problem], seconds=time.monotonic() - started)
            except BuildStopped as stopped:
                return BuildResult(False, errors=[stopped_problem(stopped)], seconds=time.monotonic() - started)
            except TYPST_ERRORS as exc:
                return BuildResult(False, errors=[self.map_error(exc)], seconds=time.monotonic() - started)
        output = data if isinstance(data, list) else [data]
        for w in typst_warnings:
            warnings.append(Problem("warning.build.typst", {}, message=str(w)))
        return BuildResult(True, output=output, warnings=warnings, seconds=time.monotonic() - started)

    def positions(self) -> List[dict]:
        """F12 stage 1: the kind and page position of every element in the
        last build, in document order."""
        with self._lock:
            if not self._compiled:
                return []
            data = self._query("<scriptorum-el>", field="value")
            if data is None:
                return []
        items = json.loads(data) if isinstance(data, (str, bytes)) else data
        result = []
        for item in items or []:
            pos = item.get("pos", {})
            result.append({
                "kind": item.get("k"),
                "page": int(pos.get("page", 1)),
                "x": float(str(pos.get("x", "0pt")).rstrip("pt") or 0),
                "y": float(str(pos.get("y", "0pt")).rstrip("pt") or 0),
            })
        return result

    def references(self) -> List[dict]:
        """F3.6: the page every codex reference of the last build printed on."""
        with self._lock:
            data = self._query("<scriptorum-ref>")
            if data is None:
                return []
        items = json.loads(data) if isinstance(data, (str, bytes)) else data
        result = []
        for item in items or []:
            value = item.get("value", {}) or {}
            result.append({"id": value.get("id"), "how": value.get("how"), "page": value.get("page")})
        return result

    def sheets(self) -> Dict[int, int]:
        """F6.5: how many sheets each handout needs in the player PDF, as the
        theme reported it in the last adventure-PDF build."""
        with self._lock:
            data = self._query("<scriptorum-sheets>", field="value")
            if data is None:
                return {}
        items = json.loads(data) if isinstance(data, (str, bytes)) else data
        return {int(i["number"]): int(i["sheets"]) for i in items or [] if isinstance(i, dict) and "number" in i}

    def _relative_to_build(self, shown: str) -> Optional[str]:
        """Typst shows file paths relative to the current folder, absolute, or
        relative to the root. Return the path inside the build folder."""
        candidates = [Path(shown)]
        if not candidates[0].is_absolute():
            candidates = [Path.cwd() / shown, self.work_dir / shown.lstrip("/")]
        root = self.work_dir.resolve()
        for candidate in candidates:
            try:
                return candidate.resolve().relative_to(root).as_posix()
            except (ValueError, OSError):
                continue
        return None

    def map_error(self, exc: Exception) -> Problem:
        """Map a Typst error to the author's own chapter and line (3.4)."""
        message = getattr(exc, "message", str(exc))
        text = "\n".join([getattr(exc, "diagnostic", "") or "", *(getattr(exc, "trace", []) or [])])
        chapter = line = column = None
        for path, ln, col in LOCATION.findall(text):
            relative = self._relative_to_build(path)
            if relative and relative.startswith("text/"):
                chapter, line, column = relative, max(1, int(ln) - PRELUDE_LINES), int(col)
                break
        panic = SCRIPTORUM_PANIC.search(message) or SCRIPTORUM_PANIC.search(text)
        if panic:
            kind, element, fld = panic.groups()
            key = {
                "required": "error.build.requiredField",
                "variant": "error.build.unknownVariant",
                "range": "error.build.outOfRange",
                "field": "error.build.unknownField",
                "dice": "error.build.badDice",
            }.get(kind, "error.build.element")
            return Problem(key, {"element": element, "field": fld}, chapter, line, column, message)
        return Problem("error.build.typst", {}, chapter, line, column, message)


TITLE_FIELDS = ("header", "subtitle", "author", "description", "extra")

PAGE_DEFAULTS = {
    # App defaults (F7.3.2), used only when neither the adventure nor the
    # theme sets a value.
    "paper": "a4",
    "orientation": "portrait",
    "columns": 1,
    "column_gap_mm": 7,
    "margin_mm": {"top": 20, "bottom": 20, "x": 20},
    "font": "Libertinus Serif",
    "font_size_pt": 10.5,
    "page_numbers": True,
    "header": "",                     # F7.3 (M5): a line at the top of each page
    "footer": "",                     # F7.3 (M5): a line at the foot of each page
}

# F7.3: the values the settings page can change (M2: paper, orientation and
# columns; M5: margins, header, footer and page numbers).
PAGE_SETTINGS = ("paper", "orientation", "columns", "margin_mm", "header", "footer", "page_numbers")
PAPERS = ("a4", "a5", "us-letter")
ORIENTATIONS = ("portrait", "landscape")
# Paper sizes in millimetres (width, height), portrait. A3 and Tabloid are the
# sheets a booklet is printed on (F7.6).
PAPER_MM = {"a5": (148.0, 210.0), "a4": (210.0, 297.0), "a3": (297.0, 420.0),
            "us-letter": (215.9, 279.4), "us-tabloid": (279.4, 431.8)}
SHEET_UP = {"a5": "a4", "a4": "a3", "us-letter": "us-tabloid"}
MIN_COLUMN_MM = 45.0  # F7.3: a column narrower than this reads badly


def paper_size(paper: str, orientation: str = "portrait") -> tuple:
    w, h = PAPER_MM.get(paper, PAPER_MM["a4"])
    return (h, w) if orientation == "landscape" else (w, h)


def classical_margins(paper: str, orientation: str = "portrait") -> dict:
    """F7.3 (decided 11 Nov 2026: Scriptorum's own calculation, since the
    tschich package could not be judged without network access): margins in
    the classical proportions inside : top : outside : bottom = 2 : 3 : 4 : 6,
    scaled so the inside margin is a twelfth of the page width."""
    w, _h = paper_size(paper, orientation)
    unit = w / 12 / 2
    return {"top": round(unit * 3, 1), "bottom": round(unit * 6, 1),
            "inside": round(unit * 2, 1), "outside": round(unit * 4, 1)}


def column_width(page: dict) -> float:
    """The width of one column in millimetres."""
    w, _h = paper_size(page.get("paper", "a4"), page.get("orientation", "portrait"))
    m = page.get("margin_mm", {})
    sides = (m.get("inside", 0) + m.get("outside", 0)) if "inside" in m else 2 * m.get("x", 20)
    columns = max(1, int(page.get("columns", 1)))
    return (w - sides - (columns - 1) * page.get("column_gap_mm", 7)) / columns


def clean_margins(value) -> Optional[dict]:
    """A margin setting: top and bottom, and either x or inside and outside,
    each 5 to 60 mm. Anything else is ignored."""
    if not isinstance(value, dict):
        return None
    keys = ("top", "bottom", "inside", "outside") if "inside" in value else ("top", "bottom", "x")
    out = {}
    for key in keys:
        try:
            number = float(value[key])
        except (KeyError, TypeError, ValueError):
            return None
        out[key] = max(5.0, min(60.0, round(number, 1)))
    return out


def title_page_fields(adventure: Adventure) -> Dict[str, str]:
    """F7.9: the title page fields from the adventure settings."""
    stored = adventure.settings.get("title_page", {}) or {}
    fields = {"title": adventure.title}
    for key in TITLE_FIELDS:
        value = stored.get(key)
        fields[key] = value if isinstance(value, str) else ""
    return fields


def effective_page(theme_page: dict, settings: dict) -> dict:
    """F7.3.2: every page value with where it comes from: the adventure
    settings, the theme or the app default."""
    stored = (settings or {}).get("page", {}) or {}
    values, origins = {}, {}
    for key, default in PAGE_DEFAULTS.items():
        if key in stored and key in PAGE_SETTINGS:
            values[key], origins[key] = stored[key], "adventure"
        elif key in theme_page:
            values[key], origins[key] = theme_page[key], "theme"
        else:
            values[key], origins[key] = default, "app"
    for key, value in theme_page.items():
        values.setdefault(key, value)
    return {"values": values, "origins": origins}


def expand_stat_block(definition: dict, stat_blocks: Dict[str, dict]) -> dict:
    """11.5: a "stats" field becomes one number field per stat the game
    system lists; sections the game system does not use are left out."""
    fields = definition.get("fields", [])
    if not any(f.get("kind") == "stats" for f in fields):
        return definition
    block = stat_blocks.get(definition["id"], {"stats": [], "sections": []})
    used = set(block.get("sections", []))
    expanded = []
    for f in fields:
        if f.get("kind") == "stats":
            for stat in block.get("stats", []):
                expanded.append({
                    "name": stat["id"], "kind": "number", "required": False,
                    "min": stat.get("min"), "max": stat.get("max"),
                    "label": stat.get("label", stat["id"]), "group": "stats",
                })
            if block.get("free_stats"):
                # F8 Plain game system: no fixed stats; free name-and-value
                # lines, one per line, such as "Strength 3".
                expanded.append({
                    "name": "stat-lines", "kind": "text", "required": False, "multiline": True,
                    "label": "field.creature.stat-lines",
                })
        elif f.get("section") and f["name"] not in used:
            continue
        else:
            expanded.append(f)
    return {**definition, "fields": expanded}


def missing_translations(language_module: Module, translated: List[Module]) -> List[Problem]:
    """9.3: a printed word the adventure language lacks is printed in English,
    and preflight warns (T-MOD-07)."""
    problems = []
    for module in translated:
        english = module.labels("en")
        file = language_module.path / "labels" / f"{module.id}.json"
        words = json.loads(file.read_text("utf-8")) if file.is_file() else {}
        missing = sorted(k for k in english if k.startswith("print.") and k not in words)
        if missing and file.is_file():
            problems.append(Problem("warning.build.missingTranslation",
                                    {"language": language_module.name, "module": module.name, "count": len(missing),
                                     "words": ", ".join(missing[:5])}))
    return problems


def safe_member(name: str) -> bool:
    """F2.10: a file name inside an adventure may not reach outside it."""
    parts = name.replace("\\", "/").split("/")
    return not name.startswith("/") and ".." not in parts and ":" not in parts[0]


TEST_ADVENTURE = """= Test adventure

#scene(title: "Test scene", location: "A place", present: "Someone")[
Plain text with *bold* and _italic_ text: å ä ö.

#read-aloud[A text to read aloud.]

#information(variant: "hint")[A hint.]

#person(name: "Test person", mood: "Calm", description: [A short description.], linked-to: "A place")[
#information(variant: "secret")[Something only they know.]
]

#creature(name: "Test creature", type: "Vaesen", description: [A test creature.])

#countdown(title: "Test night")[
#countdown-step(when: "Midnight")[Something happens.]
]

#dice(dice: "D6")[Roll a die.]

#check(roll: "Observation", difficulty: "hard")[Something is found.]

#handout(title: "A letter")[Dear reader.]
]
"""


def test_adventure_for(kinds, notation: Optional[dict] = None) -> str:
    """9.7.5: the built-in test adventure with only the elements that are
    turned on, so a game system that turns on a few is tested with those,
    and its dice written in the game system's own notation."""
    allowed = set(kinds)
    dice = (notation or {}).get("dice") or []
    text = TEST_ADVENTURE
    if dice and "d6" not in [d.lower() for d in dice]:
        text = text.replace('#dice(dice: "D6")', f'#dice(dice: {quote_string(dice[0])})')
    calls = re.compile(r"#([a-z][a-z0-9-]*)\(|#([a-z][a-z0-9-]*)\[")
    head, _, body = text.partition("\n\n")
    scene_open, _, rest = body.partition("\n")
    inner = rest.rsplit("\n]", 1)[0]
    kept = [part for part in inner.split("\n\n")
            if all((m.group(1) or m.group(2)) in allowed for m in calls.finditer(part))]
    if "scene" not in allowed:
        return head + "\n\n" + "\n\n".join(kept) + "\n"
    return head + "\n\n" + scene_open + "\n" + "\n\n".join(kept) + "\n]\n"


def self_test(library: Library, work_dir: Path) -> List[Problem]:
    """9.7.5: every installed theme, with the game system it requires, must
    compile against the built-in test adventure."""
    from scriptorum.core.modules import theme_offered_for
    from scriptorum.core.scav import new_adventure

    problems: List[Problem] = []
    kits = [ModuleRef(m.id, m.version) for m in library.of_kind("element-kit")]
    for theme in library.of_kind("theme"):
        # A general theme (F8) is tested with every game system it is offered for.
        if True:
            for gs in library.of_kind("game-system"):
                if not theme_offered_for(library, theme, gs):
                    continue
                adventure = new_adventure(
                    "Test", ModuleRef(gs.id, gs.version), ModuleRef(theme.id, theme.version), kits, TEST_ADVENTURE
                )
                result = Builder(library, Path(work_dir) / f"selftest-{theme.id}-{gs.id}").build(adventure, "pdf")
                problems.extend(result.errors)
    return problems

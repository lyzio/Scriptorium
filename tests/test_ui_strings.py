"""Test Plan T-UI-02 (no interface text in code) and the interface's escaping
rules matching the core's (T-SRC-04, interface side)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

from scriptorum import paths
from scriptorum.core import source
from scriptorum.core.i18n import Strings

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
UI_SRC = ROOT / "ui-src"


class _TextFinder(HTMLParser):
    def __init__(self):
        super().__init__()
        self.texts = []
        self.keys = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "svg"):
            self._skip += 1
        for name, value in attrs:
            if name.startswith("data-i18n"):
                self.keys.append(value)
            if name in ("title", "alt", "placeholder", "aria-label"):
                self.texts.append(f"{name}={value}")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "svg"):
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.texts.append(data.strip())


def _strings(library):
    return Strings.from_library(library).table


def test_T_UI_02_no_text_in_html(library):
    """T-UI-02: the page holds no visible text of its own; every key exists."""
    finder = _TextFinder()
    finder.feed((paths.UI_DIR / "index.html").read_text("utf-8"))
    assert finder.texts == []
    table = _strings(library)
    missing = [k for k in finder.keys if k not in table]
    assert missing == []


def test_T_UI_02_every_key_used_in_code_exists(library):
    """T-UI-02: every t("…") key in the interface and the core exists in scriptorum.en."""
    table = _strings(library)
    used = set()
    for file in UI_SRC.glob("*.ts"):
        used |= set(re.findall(r"""\bt\(\s*["']([\w.]+)["']""", file.read_text("utf-8")))
    for file in (ROOT / "scriptorum").rglob("*.py"):
        text = file.read_text("utf-8")
        used |= set(re.findall(r"""\bt\(\s*["']([\w.]+)["']""", text))
        used |= set(re.findall(r"""["']((?:error|warning)\.[a-z]+\.[A-Za-z]+)["']""", text))
    missing = sorted(k for k in used if k not in table)
    assert missing == []


def test_T_UI_02_no_literal_words_in_ts():
    """T-UI-02: no English words are assigned as visible text in the TypeScript."""
    pattern = re.compile(r"""(textContent|title|placeholder|innerText)\s*=\s*["'][A-Za-z]{3,}""")
    offenders = []
    for file in UI_SRC.glob("*.ts"):
        for number, line in enumerate(file.read_text("utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{file.name}:{number}: {line.strip()}")
    assert offenders == []


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_T_SRC_04_interface_escaping_matches_core():
    """The interface escapes typed text exactly as the core does."""
    bundle = ROOT / "tests" / "js" / "inline.cjs"
    cases = [
        "Price: 5 $ or 10 % off, mail@example.com",
        "Use *stars* and _underscores_ and #hashes",
        "Brackets [like this] and <label> and `code`",
        "- not a list", "= not a heading", "1. not a numbered list", "+ plus",
        "a // not a comment, a/b and C:\\path", "Swedish: Åsa, Märta, Örjan ~ tilde",
    ]
    script = (
        f"const m = require({json.dumps(str(bundle))});"
        f"const cases = {json.dumps(cases)};"
        "console.log(JSON.stringify(cases.map(c => [m.escapeInline(c), m.inlineToPlain(m.escapeInline(c))])));"
    )
    out = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    for case, (escaped, plain) in zip(cases, out):
        assert escaped == source.escape_inline(case)
        assert plain == source.inline_to_plain(source.escape_inline(case))

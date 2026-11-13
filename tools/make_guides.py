"""Write the author guides (F19) into the interface-language module.

The English guides are written as Markdown in tools/guides/. The same files
are kept in the project as documents. This tool turns each one into
strings/<area>.json of scriptorum.en, keyed by identifier like every other
interface text (9.3, F15), so a translator translates them like the rest of
the interface:

    title        the guide's title ("# ")
    intro        the text before the first section
    sNN.title    each section's heading ("## ")
    sNN.body     each section's text

A body keeps a small, plain markup that the Help viewer draws: paragraphs
separated by a blank line, "- " list items, `code`, **bold**, and code
blocks between ``` lines. A code block's first line may name a file
("```file: module.json"), which the viewer shows above the block.

    python tools/make_guides.py          write the JSON files
    python tools/make_guides.py --check  fail if they are out of date
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "tools" / "guides"
STRINGS = ROOT / "scriptorum" / "bundled" / "scriptorum.en" / "strings"

# Source file -> interface-text area (strings/<area>.json).
GUIDES = {
    "how-to-write-a-theme.md": "guide-theme",
    "how-to-write-a-game-system.md": "guide-game-system",
}


def convert(markdown: str) -> dict:
    """One guide's Markdown as keyed interface texts."""
    title = ""
    intro: list = []
    sections: list = []
    fenced = False
    for line in markdown.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        if not fenced and line.startswith("## "):
            sections.append((line[3:].strip(), []))
            continue
        (sections[-1][1] if sections else intro).append(line)
    if fenced:
        raise ValueError("a code block is not closed")
    out = {"title": title, "intro": "\n".join(intro).strip()}
    for number, (heading, body) in enumerate(sections, start=1):
        out[f"s{number:02d}.title"] = heading
        out[f"s{number:02d}.body"] = "\n".join(body).strip()
    return out


def generated() -> dict:
    return {area: convert((SOURCES / name).read_text("utf-8")) for name, area in GUIDES.items()}


def main(argv: list) -> int:
    stale = []
    for area, texts in generated().items():
        target = STRINGS / f"{area}.json"
        text = json.dumps(texts, ensure_ascii=False, indent=2) + "\n"
        if "--check" in argv:
            if not target.is_file() or target.read_text("utf-8") != text:
                stale.append(target.name)
        else:
            target.write_text(text, "utf-8")
    if stale:
        print("Out of date, run tools/make_guides.py: " + ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

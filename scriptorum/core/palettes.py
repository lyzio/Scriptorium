"""App palettes (design document F16) and their contrast check (T-UI-20).

A palette is an app module (kind "palette", 9.3) with palette.json: colour
tokens for light mode, dark mode or both. A palette changes only the app
window, never the printed PDF. Every text colour must read at a contrast of
at least 4.5 on the backgrounds it is used on; a palette made with the colour
pickers that falls below gets a quiet warning but may still be saved (F16).

Optionally palette.css carries window styles for palettes made outside the
app. Anything in it that would fetch from the internet is refused at install
(F16, T-REL-02, T-UI-22).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# The tokens a palette sets, in the order the colour pickers show them.
TOKENS = (
    "window", "bar", "sidebar", "editor", "input", "line", "line-strong",
    "text", "text-2", "muted", "faint",
    "claret", "on-claret", "claret-text", "claret-tint",
    "teal", "teal-text", "green", "frame", "ochre",
    "secret", "public", "hint", "error", "preview",
)

# CSS variable for each token (scriptorum/ui/styles.css uses these).
CSS_VARS = {
    "window": "--bg", "bar": "--bar", "sidebar": "--panel", "editor": "--paper", "input": "--input",
    "line": "--line", "line-strong": "--line-strong", "text": "--ink", "text-2": "--ink-2",
    "muted": "--quiet", "faint": "--faint", "claret": "--accent", "on-claret": "--on-accent",
    "claret-text": "--accent-ink", "claret-tint": "--accent-tint", "teal": "--focus",
    "teal-text": "--focus-text", "green": "--ok", "frame": "--frame", "ochre": "--ochre",
    "secret": "--secret", "public": "--public", "hint": "--hint", "error": "--error",
    "preview": "--preview-bg",
}

# Text colours and the backgrounds they are used on (T-UI-20). Greens and
# teal are shapes and highlights, not text (F16).
TEXT_PAIRS: Tuple[Tuple[str, str], ...] = (
    ("text", "window"), ("text", "bar"), ("text", "sidebar"), ("text", "editor"), ("text", "input"), ("text", "claret-tint"),
    ("text-2", "window"), ("text-2", "sidebar"), ("text-2", "editor"),
    ("muted", "window"), ("muted", "bar"), ("muted", "sidebar"), ("muted", "editor"),
    ("claret-text", "window"), ("claret-text", "sidebar"), ("claret-text", "editor"), ("claret-text", "claret-tint"),
    ("on-claret", "claret"), ("teal-text", "editor"), ("teal-text", "sidebar"),
    ("secret", "editor"), ("public", "editor"), ("hint", "editor"), ("error", "editor"), ("ochre", "editor"),
)

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
REMOTE = re.compile(r"""(?:url\(\s*['"]?\s*|@import\s+['"]?|src\s*:\s*['"]?)((?:https?:)?//[^'")\s;]+)|((?:https?|ftp|wss?):\/\/[^'")\s;]+)""", re.I)


def luminance(colour: str) -> float:
    r, g, b = (int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5))

    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio of two #RRGGBB colours."""
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def low_contrast(colours: Dict[str, str], minimum: float = 4.5) -> List[dict]:
    """Every text colour below the minimum contrast on one of its backgrounds."""
    found = []
    for fg, bg in TEXT_PAIRS:
        a, b = colours.get(fg), colours.get(bg)
        if a and b and HEX.match(a) and HEX.match(b):
            ratio = contrast(a, b)
            if ratio < minimum:
                found.append({"text": fg, "background": bg, "ratio": round(ratio, 2)})
    return found


def remote_address(css: str) -> Optional[str]:
    """The first address in a palette stylesheet that would reach the
    internet, such as a remote font or picture (F16, T-REL-02)."""
    for m in REMOTE.finditer(css):
        return m.group(1) or m.group(2)
    return None


def css_variables(colours: Dict[str, str]) -> Dict[str, str]:
    return {CSS_VARS[k]: v for k, v in colours.items() if k in CSS_VARS and HEX.match(str(v))}

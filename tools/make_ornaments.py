"""Draw the themes' own ornaments as SVG (F8, decided 6 November 2026).

The drawings are generated, not traced from anyone's artwork: spirals,
scrolls, a pen nib, an hourglass, cups, beans, leaves, a sigil and diamonds,
each a few vector paths. Run once; the SVG files are stored in each theme's
ornaments/ folder. Usage: python tools/make_ornaments.py
"""

from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "scriptorum" / "bundled"


def spiral(cx, cy, turns, r0, r1, start, n=90, sign=1):
    pts = []
    for i in range(n + 1):
        t = i / n
        a = start + sign * t * turns * 2 * math.pi
        r = r0 + (r1 - r0) * t
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def path(pts):
    return "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts)


def svg(w, h, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f"{body}</svg>\n")


def write(theme, name, text):
    folder = ROOT / theme / "ornaments"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, "utf-8")


def curl(colour):
    # A spiral that ends tangent to a rule leaving to the right (the corner of
    # the open curl frame). The rule starts at (40, 20).
    pts = spiral(20, 20, 1.6, 1.2, 9.5, math.pi, sign=1)
    pts.append((26, 10.6))
    pts.append((40, 10.6))
    return svg(40, 40, f'<path d="{path(pts)}" fill="none" stroke="{colour}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>')


def scroll(colour):
    left = spiral(14, 12, 1.25, 0.8, 6.5, 0, sign=-1)
    right = [(100 - x, y) for x, y in spiral(14, 12, 1.25, 0.8, 6.5, 0, sign=-1)]
    wave = [(14 + 72 * t / 40, 12 + 4.5 * math.sin(t / 40 * 2 * math.pi) * (1 - abs(t - 20) / 26)) for t in range(41)]
    leaf = "M50,4 C53,8 53,16 50,20 C47,16 47,8 50,4 Z"
    body = (f'<path d="{path(left)}" fill="none" stroke="{colour}" stroke-width="1.8" stroke-linecap="round"/>'
            f'<path d="{path(right)}" fill="none" stroke="{colour}" stroke-width="1.8" stroke-linecap="round"/>'
            f'<path d="{path(wave)}" fill="none" stroke="{colour}" stroke-width="1.5" stroke-linecap="round"/>'
            f'<path d="{leaf}" fill="{colour}"/>'
            f'<circle cx="38" cy="12" r="1.6" fill="{colour}"/><circle cx="62" cy="12" r="1.6" fill="{colour}"/>')
    return svg(100, 24, body)


def nib(colour):
    body = (f'<path d="M5,1 L9,5 L6,13 L5,14 L4,13 L1,5 Z" fill="{colour}"/>'
            f'<path d="M5,6 L5,13" stroke="#FFFFFF" stroke-width="0.7"/>'
            f'<circle cx="5" cy="6" r="1.1" fill="#FFFFFF"/>')
    return svg(10, 15, body)


def hourglass(frame, sand):
    body = (f'<path d="M3,2 H21 M3,30 H21" stroke="{frame}" stroke-width="2" stroke-linecap="round"/>'
            f'<path d="M6,3 C6,11 11,13 11,16 C11,19 6,21 6,29 M18,3 C18,11 13,13 13,16 C13,19 18,21 18,29" '
            f'fill="none" stroke="{frame}" stroke-width="1.3"/>'
            f'<path d="M8.2,8 C9,11.5 11.3,13.3 12,14.4 C12.7,13.3 15,11.5 15.8,8 Z" fill="{sand}"/>'
            f'<path d="M12,16 L12,22" stroke="{sand}" stroke-width="0.8"/>'
            f'<path d="M7.4,28 C8.5,24 10.5,22.6 12,22.4 C13.5,22.6 15.5,24 16.6,28 Z" fill="{sand}"/>')
    return svg(24, 32, body)


def cup(colour):
    steam = "".join(
        f'<path d="M{x},11 C{x - 2},8 {x + 2},6 {x},3" fill="none" stroke="{colour}" stroke-width="1" stroke-linecap="round"/>'
        for x in (9, 13, 17))
    body = (steam + f'<path d="M4,13 H22 C22,20 19,24 13,24 C7,24 4,20 4,13 Z" fill="none" stroke="{colour}" stroke-width="1.5"/>'
            f'<path d="M22,15 C27,15 27,21 21,21" fill="none" stroke="{colour}" stroke-width="1.4"/>'
            f'<path d="M2,26 H24" stroke="{colour}" stroke-width="1.4" stroke-linecap="round"/>')
    return svg(28, 28, body)


def bean(colour):
    body = (f'<ellipse cx="6" cy="6" rx="4.2" ry="5.4" transform="rotate(25 6 6)" fill="{colour}"/>'
            f'<path d="M4.2,1.8 C7.2,4 4.8,8 7.8,10.2" fill="none" stroke="#FFFFFF" stroke-width="0.9"/>')
    return svg(12, 12, body)


def leaf(colour):
    body = (f'<path d="M2,26 C8,20 14,16 24,4" fill="none" stroke="{colour}" stroke-width="1.3" stroke-linecap="round"/>'
            + "".join(f'<path d="M{x},{y} C{x - 6},{y - 2} {x - 7},{y - 7} {x - 2},{y - 9} C{x},{y - 5} {x + 1},{y - 2} {x},{y} Z" fill="{colour}"/>'
                      for x, y in ((10, 20), (16, 13), (22, 7)))
            + "".join(f'<path d="M{x},{y} C{x + 2},{y + 5} {x + 7},{y + 6} {x + 9},{y + 2} C{x + 5},{y} {x + 2},{y - 1} {x},{y} Z" fill="{colour}"/>'
                      for x, y in ((8, 21), (14, 14))))
    return svg(28, 28, body)


def sigil(colour, accent):
    pts = []
    for i in range(7):
        a = -math.pi / 2 + i * 2 * math.pi * 3 / 7
        pts.append((20 + 15 * math.cos(a), 20 + 15 * math.sin(a)))
    star = path(pts) + " Z"
    body = (f'<circle cx="20" cy="20" r="18" fill="none" stroke="{colour}" stroke-width="1.2"/>'
            f'<circle cx="20" cy="20" r="15.5" fill="none" stroke="{colour}" stroke-width="0.6"/>'
            f'<path d="{star}" fill="none" stroke="{colour}" stroke-width="0.9" stroke-linejoin="round"/>'
            f'<circle cx="20" cy="20" r="3" fill="{accent}"/>')
    return svg(40, 40, body)


def diamond(colour):
    return svg(10, 10, f'<path d="M5,0.5 L9.5,5 L5,9.5 L0.5,5 Z" fill="{colour}"/>')


def bracket(colour):
    return svg(16, 16, f'<path d="M1,15 V1 H15" fill="none" stroke="{colour}" stroke-width="1.6" stroke-linecap="square"/>'
                       f'<path d="M4,15 V4 H15" fill="none" stroke="{colour}" stroke-width="0.6"/>')


def main():
    # Vaesen: frame brown, a deep wine red for the scroll and the sand.
    brown, wine = "#4A2F24", "#7B1F2A"
    write("scriptorum.vaesen", "curl.svg", curl(brown))
    write("scriptorum.vaesen", "scroll.svg", scroll(wine))
    write("scriptorum.vaesen", "nib.svg", nib(brown))
    write("scriptorum.vaesen", "hourglass.svg", hourglass(brown, wine))
    # Legends and Lattes: coffee brown and sage green.
    coffee, sage = "#5A3A24", "#6E8B5E"
    write("scriptorum.legends-and-lattes", "cup.svg", cup(coffee))
    write("scriptorum.legends-and-lattes", "bean.svg", bean(coffee))
    write("scriptorum.legends-and-lattes", "leaf.svg", leaf(sage))
    write("scriptorum.legends-and-lattes", "hourglass.svg", hourglass(coffee, coffee))
    # Call of Cthulhu: ink black and sepia with a sickly green accent.
    ink, green = "#1E1B18", "#5E7A2E"
    write("scriptorum.call-of-cthulhu", "sigil.svg", sigil(ink, green))
    write("scriptorum.call-of-cthulhu", "diamond.svg", diamond(green))
    write("scriptorum.call-of-cthulhu", "bracket.svg", bracket(ink))
    write("scriptorum.call-of-cthulhu", "hourglass.svg", hourglass(ink, green))


if __name__ == "__main__":
    main()

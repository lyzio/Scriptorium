"""Make the app and file-type icons from the SVG drafts (design document F10, D16).

The drafts in icons/source/ are copied from the UX canvas (Logo mock A and
File icons). Each icon has its own drawing per size, because details drop
away as an icon shrinks, so every size is drawn from the nearest drawing at
or above it, never scaled down from the largest.

Writes into icons/:
  scriptorum.png, scav.png, scmod.png      256 px, for Linux and the docs
  png/<name>-<size>.png                    every size, for the AppImage
  <name>.ico                               Windows (16, 24, 32, 48, 64, 128, 256)
  <name>.icns                              macOS (16 to 1024, with @2x)

Run it again when the final logo is chosen (D16): replace the SVG drafts and
run  python common/make_icons.py --font <path to a Cormorant Garamond Bold
font>. The finished icons are kept in the kit, so a normal build does not run
this. It needs only PySide6 (already in the build environment).
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QFontDatabase, QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

KIT = Path(__file__).resolve().parents[1]
SOURCE = KIT / "icons" / "source"
OUT = KIT / "icons"

# The drawings that exist for each icon, by the size they were drawn for.
DRAWINGS = {
    "scriptorum": [16, 32, 128],
    "scav": [16, 32, 48, 128, 256],
    "scmod": [16, 32, 48, 128, 256],
}
SVG_NAME = {"scriptorum": "app"}

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
# ICNS entry types: (type code, pixel size).
ICNS_TYPES = [
    (b"icp4", 16), (b"ic11", 32),     # 16 and 16@2x
    (b"icp5", 32), (b"ic12", 64),     # 32 and 32@2x
    (b"ic07", 128), (b"ic13", 256),   # 128 and 128@2x
    (b"ic08", 256), (b"ic14", 512),   # 256 and 256@2x
    (b"ic09", 512), (b"ic10", 1024),  # 512 and 512@2x
]
LINUX_SIZES = [16, 24, 32, 48, 64, 128, 256, 512]


def drawing_for(name: str, size: int) -> Path:
    """The drawing made for the nearest size at or above this one (or the largest)."""
    drawn = DRAWINGS[name]
    pick = next((d for d in drawn if d >= size), drawn[-1])
    return SOURCE / f"{SVG_NAME.get(name, name)}-{pick}.svg"


def render(name: str, size: int) -> QImage:
    renderer = QSvgRenderer(str(drawing_for(name, size)))
    if not renderer.isValid():
        raise SystemExit(f"Cannot read {drawing_for(name, size)}")
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def write_ico(path: Path, images: dict) -> None:
    """A Windows icon holding one PNG per size (supported since Windows Vista)."""
    sizes = sorted(images)
    head = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries, blobs = b"", b""
    for size in sizes:
        blob = images[size]
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
        blobs += blob
    path.write_bytes(head + entries + blobs)


def write_icns(path: Path, images: dict) -> None:
    """A macOS icon: the 'icns' header, then one PNG entry per type."""
    body = b""
    for code, size in ICNS_TYPES:
        blob = images[size]
        body += code + struct.pack(">I", len(blob) + 8) + blob
    path.write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--font", action="append", default=[],
                        help="a font file for the band text (Cormorant Garamond Bold); may be given more than once")
    args = parser.parse_args()

    app = QGuiApplication(sys.argv[:1])  # noqa: F841 - Qt needs it for fonts
    for font in args.font:
        if QFontDatabase.addApplicationFont(font) < 0:
            print(f"Could not load the font {font}", file=sys.stderr)
            return 1
    if not args.font:
        print("No --font given: the SCAV / SCMOD band text uses the nearest serif font on this computer.")

    (OUT / "png").mkdir(parents=True, exist_ok=True)
    for name in DRAWINGS:
        cache: dict = {}

        def png(size: int) -> bytes:
            if size not in cache:
                cache[size] = png_bytes(render(name, size))
            return cache[size]

        for size in LINUX_SIZES:
            (OUT / "png" / f"{name}-{size}.png").write_bytes(png(size))
        (OUT / f"{name}.png").write_bytes(png(256))
        write_ico(OUT / f"{name}.ico", {s: png(s) for s in ICO_SIZES})
        write_icns(OUT / f"{name}.icns", {s: png(s) for _, s in ICNS_TYPES})
        print(f"{name}: png, ico, icns written")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Copy a Typst package into a Scriptorum module folder (design doc D15).

Typst packages import each other as "@preview/<name>:<version>" and their
own files as "/src/...", both of which only work from the package cache.
Scriptorum never fetches packages (D9), so each package is copied into the
module, pinned, with its licence file, and those imports are rewritten as
relative paths. Nothing else in the package is changed.

usage: vendor_typst.py <package-folder> <target-folder> [name=relative/entry.typ ...]
"""
import os
import re
import shutil
import sys
from pathlib import Path

src, target = Path(sys.argv[1]), Path(sys.argv[2])
deps = dict(a.split("=", 1) for a in sys.argv[3:])  # "@preview/cetz:0.3.4" = path relative to target's parent
shutil.rmtree(target, ignore_errors=True)
(target).mkdir(parents=True)
for name in ("LICENSE", "typst.toml"):
    if (src / name).is_file():
        shutil.copy(src / name, target / (name if name == "LICENSE" else "typst.toml.txt"))
files = sorted((src / "src").rglob("*.typ")) if (src / "src").is_dir() else sorted(src.glob("*.typ"))
for file in files:
    rel = file.relative_to(src)
    out = target / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    text = file.read_text("utf-8")

    def fix(m):
        quote_path = m.group(2)
        if quote_path.startswith("@preview/"):
            dest = target.parent / deps[quote_path]
        elif quote_path.startswith("/"):
            dest = target / quote_path.lstrip("/")
        else:
            return m.group(0)
        new = m.group(1) + '"' + os.path.relpath(dest, out.parent).replace(os.sep, "/") + '"'
        if quote_path.startswith("@preview/") and not re.match(r"\s*(:|as\b)", m.group(3)):
            # A bare package import binds the package name; keep that name.
            new += " as " + quote_path[len("@preview/"):].split(":")[0]
        return new + m.group(3)

    text = re.sub(r'(#?(?:import|include)\s+)"([^"]+)"([^\n]*)', fix, text)
    out.write_text(text, "utf-8")
print("vendored", target, sum(1 for _ in target.rglob("*.typ")), "files")

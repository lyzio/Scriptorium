"""Build the Linux kit: Scriptorum-<version>-linux.tar.gz.

Run from the project folder:  python tools/make_linux_kit.py [output-folder]

The kit holds the Scriptorum wheel, the scripts in linux-kit/ (setup.sh,
uninstall.sh, the menu entry, file type and icon), README-LINUX.txt and the
sample adventures as .scav files. setup.sh installs it into a private
virtual environment in the user's home folder.
"""

import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ["m3-handouts", "m3-world", "m2-full", "m1-basic"]


def version() -> str:
    for line in (ROOT / "pyproject.toml").read_text().splitlines():
        if line.startswith("version"):
            return line.split('"')[1]
    raise SystemExit("no version in pyproject.toml")


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "dist").resolve()
    out.mkdir(parents=True, exist_ok=True)
    v = version()
    name = f"Scriptorum-{v}-linux"
    with tempfile.TemporaryDirectory() as tmp:
        kit = Path(tmp) / name
        shutil.copytree(ROOT / "linux-kit", kit)
        subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--quiet",
                        "--wheel-dir", str(kit), str(ROOT)], check=True)
        (kit / "samples").mkdir()
        for sample in SAMPLES:
            folder = ROOT / "tests" / "samples" / sample
            with zipfile.ZipFile(kit / "samples" / f"{sample}.scav", "w", zipfile.ZIP_DEFLATED) as zf:
                for f in sorted(folder.rglob("*")):
                    if f.is_file():
                        zf.write(f, f.relative_to(folder).as_posix())
        shutil.copy(ROOT / "COPYING", kit / "COPYING")
        target = out / f"{name}.tar.gz"

        def mode(info: tarfile.TarInfo) -> tarfile.TarInfo:
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            if info.name.endswith(".sh") or info.isdir():
                info.mode = 0o755
            else:
                info.mode = 0o644
            return info

        with tarfile.open(target, "w:gz") as tar:
            tar.add(kit, arcname=name, filter=mode)
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env bash
# Scriptorum for Linux: installs the app for the current user only.
#
# What it does:
#   1. finds Python 3.11, 3.12 or 3.13
#   2. makes a private virtual environment in ~/.local/share/scriptorum-app/venv
#   3. installs Scriptorum and its pinned packages there (needs the internet once)
#   4. adds the command ~/.local/bin/scriptorum, a menu entry and the .scav file type
#
# Nothing is installed system-wide and no root password is needed.
# Run it again to update; run uninstall.sh to remove it.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/scriptorum-app"
VENV="$APP_DIR/venv"
BIN_DIR="$HOME/.local/bin"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"

say() { printf '\n== %s\n' "$*"; }

# 1. Python
PY=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 13) else 1)'; then
      PY="$(command -v "$candidate")"; break
    fi
  fi
done
if [ -z "$PY" ]; then
  echo "Scriptorum needs Python 3.11, 3.12 or 3.13, and none was found."
  echo "  Ubuntu/Debian: sudo apt install python3 python3-venv"
  echo "  Fedora:        sudo dnf install python3.13"
  echo "  Arch:          install python313 from the AUR, or use pyenv"
  exit 1
fi
say "Using $("$PY" --version) at $PY"

if ! "$PY" -c 'import venv, ensurepip' >/dev/null 2>&1; then
  echo "Python's venv module is missing."
  echo "  Ubuntu/Debian: sudo apt install python3-venv   (or python3.12-venv, matching your version)"
  exit 1
fi

# 2. Virtual environment
say "Making the virtual environment in $VENV"
mkdir -p "$APP_DIR"
if [ -x "$VENV/bin/python" ] && ! "$VENV/bin/python" -c 'import sys' >/dev/null 2>&1; then
  rm -rf "$VENV"   # a broken old one, for example after a Python upgrade
fi
[ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip

# 3. Scriptorum and its packages (PySide6 6.8.3, typst 0.15.0, spylls 0.1.7)
say "Installing Scriptorum (the first time downloads about 250 MB)"
WHEEL="$(ls "$HERE"/scriptorum-*.whl | sort -V | tail -n 1)"
"$VENV/bin/python" -m pip install --upgrade --force-reinstall --no-deps "$WHEEL"
"$VENV/bin/python" -m pip install "$WHEEL"

# 4. Command, icon, menu entry and file type
say "Adding the command, menu entry and .scav file type"
mkdir -p "$BIN_DIR" "$DATA_DIR/applications" "$DATA_DIR/icons/hicolor/scalable/apps" "$DATA_DIR/mime/packages"
# The launcher: the app's window is a built-in web view (Qt WebEngine). Its
# Chromium sandbox cannot start as root, nor where AppArmor blocks
# unprivileged user namespaces (Ubuntu 23.10 and later); only then is it
# switched off. The view shows only Scriptorum's own local pages.
cat > "$APP_DIR/scriptorum" <<LAUNCHER
#!/bin/sh
if [ "\$(id -u)" = 0 ] || [ "\$(cat /proc/sys/kernel/apparmor_restrict_unprivileged_userns 2>/dev/null)" = 1 ]; then
  export QTWEBENGINE_DISABLE_SANDBOX=1
fi
exec "$VENV/bin/scriptorum" "\$@"
LAUNCHER
chmod +x "$APP_DIR/scriptorum"
ln -sf "$APP_DIR/scriptorum" "$BIN_DIR/scriptorum"
cp "$HERE/scriptorum.svg" "$DATA_DIR/icons/hicolor/scalable/apps/scriptorum.svg"
cp "$HERE/scriptorum-scav.xml" "$DATA_DIR/mime/packages/scriptorum-scav.xml"
sed "s|@EXEC@|$APP_DIR/scriptorum|" "$HERE/scriptorum.desktop.in" > "$DATA_DIR/applications/scriptorum.desktop"
command -v update-mime-database >/dev/null 2>&1 && update-mime-database "$DATA_DIR/mime" >/dev/null 2>&1 || true
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA_DIR/applications" >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$DATA_DIR/icons/hicolor" >/dev/null 2>&1 || true

# Sample adventures
mkdir -p "$APP_DIR/samples"
cp "$HERE"/samples/*.scav "$APP_DIR/samples/" 2>/dev/null || true

# Qt needs a few system libraries that are not always installed.
if command -v ldconfig >/dev/null 2>&1 && ! ldconfig -p 2>/dev/null | grep -q 'libxcb-cursor.so.0'; then
  echo
  echo "Note: libxcb-cursor is not installed; Qt needs it to open windows under X11/XWayland."
  echo "  Ubuntu/Debian: sudo apt install libxcb-cursor0"
  echo "  Fedora:        sudo dnf install xcb-util-cursor"
  echo "  Arch:          sudo pacman -S xcb-util-cursor"
fi

say "Done"
echo "Start Scriptorum from the applications menu, or type:  scriptorum"
echo "Sample adventures are in $APP_DIR/samples"
case ":$PATH:" in *":$BIN_DIR:"*) ;; *) echo "($BIN_DIR is not on your PATH; log out and in again, or run $APP_DIR/scriptorum)";; esac

#!/usr/bin/env bash
# Removes Scriptorum for the current user. Your adventures (.scav files) are
# left alone, and so is Scriptorum's own data folder ~/.local/share/scriptorum
# (installed modules, settings and build cache); delete that by hand if you
# want everything gone.
set -euo pipefail
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -rf "$DATA_DIR/scriptorum-app"
rm -f "$HOME/.local/bin/scriptorum" \
      "$DATA_DIR/applications/scriptorum.desktop" \
      "$DATA_DIR/icons/hicolor/scalable/apps/scriptorum.svg" \
      "$DATA_DIR/mime/packages/scriptorum-scav.xml"
command -v update-mime-database >/dev/null 2>&1 && update-mime-database "$DATA_DIR/mime" >/dev/null 2>&1 || true
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA_DIR/applications" >/dev/null 2>&1 || true
echo "Scriptorum is removed. Its data folder ${DATA_DIR}/scriptorum is kept."

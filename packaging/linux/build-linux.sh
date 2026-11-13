#!/bin/sh
# Build the Scriptorum AppImage. Usage: ./linux/build-linux.sh <unpacked build folder>
# Everything else is in build.py; see docs/BUILD-LINUX.md.
KIT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$(command -v python3.13)"
if [ -z "$PY" ]; then
    echo "Python 3.13 was not found (python3.13). See docs/BUILD-LINUX.md, section 1." >&2
    exit 1
fi
exec "$PY" "$KIT/build.py" "$@"

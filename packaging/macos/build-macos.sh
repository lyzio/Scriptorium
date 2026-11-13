#!/bin/sh
# Build the Scriptorum .dmg. Usage: ./macos/build-macos.sh <unpacked build folder>
# Everything else is in build.py; see docs/BUILD-MACOS.md.
KIT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$(command -v python3.13)"
if [ -z "$PY" ]; then
    echo "Python 3.13 was not found (python3.13). See docs/BUILD-MACOS.md, section 1." >&2
    exit 1
fi
exec "$PY" "$KIT/build.py" "$@"

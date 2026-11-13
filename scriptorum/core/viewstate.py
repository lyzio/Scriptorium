"""How each adventure was last looked at (design document F7.2, M5).

The preview's zoom is remembered for each adventure, outside the .scav file,
so the adventure opens at the same size next time and the author's file
never changes because of it. It is kept in the app's own folder
(view-state.json), keyed by where the adventure is saved; an adventure that
has not been saved yet is remembered only while the app runs.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Union

Zoom = Union[str, int]

ZOOM_MIN, ZOOM_MAX = 50, 400         # F7.2: text stays sharp from 50 % to 400 %
ZOOM_MODES = ("fit-width", "whole-page")
ZOOM_DEFAULT: Zoom = "fit-width"
KEPT = 300                            # adventures remembered


def clean_zoom(value) -> Zoom:
    """A zoom is "fit-width", "whole-page" or a whole percentage, 50 to 400."""
    if value in ZOOM_MODES:
        return value
    try:
        percent = int(round(float(value)))
    except (TypeError, ValueError):
        return ZOOM_DEFAULT
    return max(ZOOM_MIN, min(ZOOM_MAX, percent))


class ViewState:
    def __init__(self, file: Path):
        self.file = Path(file)
        self.zoom: Dict[str, Zoom] = {}
        self._unsaved: Dict[str, Zoom] = {}
        if self.file.is_file():
            try:
                stored = json.loads(self.file.read_text("utf-8")).get("zoom", {})
                self.zoom = {str(k): clean_zoom(v) for k, v in stored.items()}
            except (json.JSONDecodeError, UnicodeDecodeError, OSError, AttributeError):
                self.zoom = {}  # an unreadable file falls back to the default

    def get_zoom(self, key: str) -> Zoom:
        return self._unsaved.get(key, self.zoom.get(key, ZOOM_DEFAULT))

    def set_zoom(self, key: str, value) -> Zoom:
        zoom = clean_zoom(value)
        if key.startswith("unsaved-"):
            self._unsaved[key] = zoom
            return zoom
        self.zoom.pop(key, None)
        self.zoom[key] = zoom  # the newest last
        while len(self.zoom) > KEPT:
            self.zoom.pop(next(iter(self.zoom)))
        self._save()
        return zoom

    def _save(self) -> None:
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".view-state-", dir=self.file.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"zoom": self.zoom}, handle, ensure_ascii=False, indent=1)
            os.replace(tmp, self.file)
        except OSError:
            pass  # remembering the zoom is a convenience, never an error

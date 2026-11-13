"""Recent files (F2.1): most recent first, no duplicates, at most ten."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

MAX_RECENT = 10


class RecentFiles:
    def __init__(self, store: Path):
        self.store = Path(store)

    def _read(self) -> List[str]:
        try:
            data = json.loads(self.store.read_text("utf-8"))
            return [p for p in data if isinstance(p, str)]
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def add(self, path: Path) -> None:
        entry = str(Path(path).resolve())
        items = [p for p in self._read() if p != entry]
        items.insert(0, entry)
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text(json.dumps(items[:MAX_RECENT], indent=2), "utf-8")

    def list(self) -> List[str]:
        """Only files that still exist."""
        return [p for p in self._read() if Path(p).is_file()]

"""Interface text (F15). Every visible text comes from an interface-language
module; nothing is written into the code."""

from __future__ import annotations

from typing import Dict

from scriptorum.core.modules import Library


class Strings:
    def __init__(self, table: Dict[str, str], locale: str = "en"):
        self.table = table
        self.locale = locale

    @classmethod
    def from_library(cls, library: Library, locale: str = "en") -> "Strings":
        candidates = [
            m for m in library.of_kind("interface-language")
            if m.manifest.get("locale", "en") == locale
        ]
        if not candidates:
            candidates = library.of_kind("interface-language")
        if not candidates:
            raise RuntimeError("No interface-language module is installed.")
        module = max(candidates, key=lambda m: tuple(int(p) for p in m.version.split(".")))
        return cls(module.strings(), module.manifest.get("locale", locale))

    def t(self, key: str, **details) -> str:
        text = self.table.get(key, key)
        for name, value in details.items():
            text = text.replace("{" + name + "}", str(value))
        return text

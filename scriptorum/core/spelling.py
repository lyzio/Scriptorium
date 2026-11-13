"""Spell check in Swedish and English (design document F4.8, D10).

The Hunspell dictionaries in ``scriptorum/dictionaries`` are read with
spylls, a pure-Python Hunspell (MIT), so nothing needs a network connection
or a compiled library. Dictionaries load in the background the first time
they are needed; a word is correct when either language knows it.
"""

from __future__ import annotations

import re
import threading
from typing import Dict, Iterable, List

from scriptorum import paths

LANGUAGES = ("sv", "en", "en-gb")
WORD = re.compile(r"[^\W\d_](?:[^\W\d_]|['’-](?=[^\W\d_]))*")


class SpellChecker:
    def __init__(self, languages=LANGUAGES):
        self.languages = languages
        self._dicts: Dict[str, object] = {}
        self._cache: Dict[str, bool] = {}
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._thread = None
        # F9 (M5): why spell check cannot work ("library" or "dictionaries"),
        # so it says so instead of waiting for dictionaries that never load.
        self.unavailable: str = ""

    def start(self) -> None:
        """Load the dictionaries in the background."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._load, daemon=True)
            self._thread.start()

    def _load(self) -> None:
        try:
            from spylls.hunspell import Dictionary
        except ImportError:
            self.unavailable = "library"
            self._ready.set()
            return
        for lang in self.languages:
            base = dictionary_dir() / lang / lang
            if base.with_suffix(".dic").is_file() and base.with_suffix(".aff").is_file():
                try:
                    self._dicts[lang] = Dictionary.from_files(str(base))
                except Exception:  # noqa: BLE001 - a damaged dictionary is a missing one
                    pass
        if not self._dicts:
            self.unavailable = "dictionaries"
        self._ready.set()

    def load_now(self) -> None:
        """Load the dictionaries in this thread (the start-up window, F9)."""
        if not self.ready:
            self._thread = threading.current_thread()
            self._load()

    def missing_languages(self) -> List[str]:
        return [lang for lang in self.languages if lang not in self._dicts]

    @property
    def ready(self) -> bool:
        return self._ready.is_set()

    def wait(self, timeout: float = 30) -> bool:
        self.start()
        return self._ready.wait(timeout)

    def correct(self, word: str, languages=None) -> bool:
        """A word is correct when a dictionary of the given languages knows
        it; with no languages given, any dictionary (F4.8)."""
        key = (word, tuple(languages) if languages else None)
        if key in self._cache:
            return self._cache[key]
        if len(word) < 2:
            return True
        dicts = [d for lang, d in self._dicts.items() if not languages or lang in languages] or list(self._dicts.values())
        with self._lock:
            ok = any(d.lookup(word) for d in dicts)
        self._cache[key] = ok
        return ok

    def misspelled(self, words: Iterable[str], languages=None) -> List[str]:
        """The words the dictionaries do not know. Empty until loaded. F17.2
        (M5): an adventure's document language chooses the dictionaries."""
        if not self.ready:
            self.start()
            return []
        if self.unavailable:
            return []  # F9: no dictionaries, so nothing is marked wrong
        return sorted({w for w in words if not self.correct(w, languages)})

    def suggest(self, word: str, limit: int = 6) -> List[str]:
        if not self.wait():
            return []
        result: List[str] = []
        with self._lock:
            for d in self._dicts.values():
                for s in d.suggest(word):
                    if s not in result:
                        result.append(s)
                    if len(result) >= limit:
                        return result
        return result


def dictionary_dir():
    """Where the Hunspell dictionaries are. SCRIPTORUM_DICTIONARIES overrides
    it (used by the tests to show a missing dictionary)."""
    import os
    from pathlib import Path

    override = os.environ.get("SCRIPTORUM_DICTIONARIES")
    return Path(override) if override else paths.PACKAGE_DIR / "dictionaries"


def words_in(text: str) -> List[str]:
    return WORD.findall(text)

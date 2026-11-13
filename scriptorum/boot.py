"""The start-up step of the installed app (design document F22.4 and F22.5,
decided 13 November 2026, built in M6 part C5).

At every start the installed app looks in the author's own Scriptorum folder
for a newer verified version made for its own Python, Qt and Typst, and runs
it; when there is none, or it is missing or damaged, it runs its own built-in
version as before. A version that fails to start is set aside: Scriptorum
goes back to the previous one at once (when it fails with an error) or at the
next start (when it never reported that it started), and says so.

The installed app is never changed: a newer version runs from its folder in
``<app home>/app-versions`` by putting that folder first on Python's path.
This module is the first thing ``python -m scriptorum`` runs, and it loads
nothing but the standard library and the signature check before deciding.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path
from typing import Optional

# Set while a newer version runs, so the build helper and the app know which
# folder and which installed version they belong to.
ENV_FOLDER = "SCRIPTORUM_VERSION_DIR"
ENV_BUILTIN = "SCRIPTORUM_BUILTIN_VERSION"
ENV_OFF = "SCRIPTORUM_NO_UPDATES"   # for the tests and for anyone who wants it


def builtin_version() -> str:
    """The version of the installed app itself."""
    value = os.environ.get(ENV_BUILTIN)
    if value:
        return value
    from scriptorum import __version__
    return __version__


def _forget_scriptorum() -> None:
    for name in list(sys.modules):
        if name == "scriptorum" or name.startswith("scriptorum."):
            del sys.modules[name]


_LOGS: Optional[Path] = None   # the crash log folder, found before any version is loaded


def _log(text: str) -> None:
    """A version that failed to start leaves its details in the crash log
    folder (F2.11); nothing is sent anywhere."""
    try:
        import time
        stamp = time.strftime("%Y%m%d-%H%M%S")
        if _LOGS is not None:
            _LOGS.mkdir(parents=True, exist_ok=True)
            (_LOGS / f"update-start-{stamp}-{os.getpid()}.log").write_text(text, "utf-8")
    except Exception:  # noqa: BLE001 - logging must never stop the start
        pass


def _main_of(folder: Optional[Path], argv: list):
    """Load ``scriptorum.app.main`` from a kept version's folder (or, with no
    folder, from the installed app) and return its ``main``."""
    _forget_scriptorum()
    if folder is not None:
        sys.path.insert(0, str(folder))
        os.environ[ENV_FOLDER] = str(folder)
    else:
        os.environ.pop(ENV_FOLDER, None)
    from scriptorum.app.main import main
    return main


def _builtin_main(argv: list) -> int:
    """The installed app's own version (the tests stand in for it)."""
    main = _main_of(None, argv)
    return main(argv)


def run(argv: Optional[list] = None, home: Optional[Path] = None) -> int:
    """Choose the version to run and run it. Returns the app's exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    builtin = builtin_version()
    os.environ[ENV_BUILTIN] = builtin
    installed_path = list(sys.path)
    chosen = None
    versions = None
    global _LOGS
    if not os.environ.get(ENV_OFF):
        try:
            from scriptorum import paths
            from scriptorum.core.packs import Versions
            _LOGS = (Path(home) / "logs") if home else paths.logs_dir()
            versions = Versions(home or paths.app_home())
            chosen = versions.select(builtin)
        except Exception:  # noqa: BLE001 - a broken store never stops the app
            _log(traceback.format_exc())
            chosen = None
    while chosen and versions is not None:
        folder = versions.folder(chosen)
        try:
            main = _main_of(folder, argv)
            from scriptorum import __version__ as loaded
            if loaded != chosen:
                raise RuntimeError(f"the folder of {chosen} holds version {loaded}")
            code = main(argv)
            versions.started(chosen)   # it ran and closed normally
            return code
        except SystemExit:
            raise
        except BaseException:  # noqa: BLE001 - KeyboardInterrupt included: go back
            if versions.state().get("trying") != chosen:
                raise              # it had started: an ordinary error, not a failed start
            _log(f"Scriptorum {chosen} failed to start:\n" + traceback.format_exc())
            chosen = versions.failed_now(chosen, builtin)
            sys.path[:] = installed_path
    sys.path[:] = installed_path
    return _builtin_main(argv)


def helper_path() -> None:
    """The installed app's build helper (``--scriptorum-build-helper``) runs
    from the same folder as the app that started it."""
    folder = os.environ.get(ENV_FOLDER)
    if folder and Path(folder).is_dir():
        _forget_scriptorum()
        sys.path.insert(0, folder)

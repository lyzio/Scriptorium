"""The update check (design document F21, decided 12 November 2026, built in
M6 part C) and installing updates (F22, decided 13 November 2026, built in M6
part C5).

Help ▸ Check for updates… reads one small file at a fixed web address over
https (UPDATE_URL, or the Update address the author entered in the app
settings). From F22 the file is signed with the project's key, and the app
checks that signature before it uses anything in it::

    {
      "update": {
        "version": "1.0.1",
        "note": "Fixes the booklet order.",
        "download": {"linux": "https://…", "macos": "https://…", "windows": "https://…"},
        "runtime": {"python": "3.13", "pyside6": "6.8.3", "typst": "0.15.0", …},
        "pack": {"url": "https://…/scriptorum-1.0.1-update.zip", "sha256": "…",
                 "size": 26214400, "signature": "…"},
        "moved_to": "https://…"            (optional: the address has moved)
      },
      "signature": "<Ed25519 signature of the canonical JSON of 'update'>"
    }

Scriptorum never downloads or installs anything by itself: the pack is
downloaded only when the author clicks Download and install, and installed
into the author's own folder for the next start (``packs``). It never checks
by itself unless the author turns on the weekly check (F18); at first start
it asks once, with the answer off by default. The update file and the pack
are the only network requests the app makes (D9), and each sends nothing but
the request for the file: no version, no identifier, no cookies. The
window's web view, Typst builds, modules and palettes stay without network
access.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path
import urllib.error
import urllib.request
from typing import Callable, Optional

from scriptorum.core import signing
from scriptorum.core.modules import parse_version

# F21.1: the fixed address of the update file. While a copy of the app holds
# the placeholder, Check for updates… says that no update address is set yet
# (and makes no request), unless the author entered an address (F22).
PLACEHOLDER = "Paste update url here"
# From M6-0.6.7 (decided 13 November 2026): every released version is a
# GitHub release of lyzio/Scriptorum; GitHub points "latest" at the newest.
UPDATE_URL = "https://github.com/lyzio/Scriptorum/releases/latest/download/scriptorium-update.json"

WEEK_SECONDS = 7 * 24 * 60 * 60
TIMEOUT_SECONDS = 10
MAX_BYTES = 64 * 1024  # a small file; anything larger is not an update file

# The outcomes, each with its own interface text (strings/update.json).
NO_ADDRESS = "no-address"   # the placeholder is still in place
NOT_HTTPS = "not-https"     # an address that is not https is never asked
NEWER = "newer"             # a newer version exists
CURRENT = "current"         # this is the newest version
UNREACHABLE = "unreachable" # the address could not be reached
INVALID = "invalid"         # the file is not an update file
UNSIGNED = "unsigned"       # F22: not signed with the project's key; ignored
NO_KEY = "no-key"           # F22: this copy holds no project key yet

MAX_PACK_BYTES = 300 * 1024 * 1024


def platform_key(platform: Optional[str] = None) -> str:
    """The key of this computer's download page in the update file."""
    p = platform or sys.platform
    if p.startswith("win"):
        return "windows"
    if p == "darwin":
        return "macos"
    return "linux"


def address_set(url: str) -> bool:
    return bool(url) and url.strip() != PLACEHOLDER


def _https(url: str) -> bool:
    return isinstance(url, str) and url.lower().startswith("https://") and len(url) > len("https://")


def fetch(url: str, timeout: float = TIMEOUT_SECONDS) -> bytes:
    """Read the update file: one GET over https with nothing but the request
    itself. Proxies set on the computer are used as for any program."""
    request = urllib.request.Request(url, headers={"User-Agent": "Scriptorum", "Accept": "application/json"})
    # urllib keeps no cookies. A redirect that ends anywhere but on https is
    # treated as unreachable.
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (https checked by the caller)
        if not _https(response.geturl()):
            raise urllib.error.URLError("redirected away from https")
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("update file too large")
    return data


def address_ok(url) -> bool:
    """F22: only an https address may be used."""
    return isinstance(url, str) and _https(url.strip()) and not any(c.isspace() for c in url.strip())


def address_in_use(entered: Optional[str], builtin: Optional[str] = None) -> str:
    """F22: the Update address the author entered, or the built-in one."""
    builtin = UPDATE_URL if builtin is None else builtin
    entered = (entered or "").strip()
    return entered if entered else builtin


def read_file(data: bytes, current: str, platform: Optional[str] = None, key: Optional[str] = None,
              have: Optional[dict] = None, url: Optional[str] = None) -> dict:
    """Check the update file's signature, then compare it with this version
    (F21.2, F21.3, F22). Nothing in a file that is not signed with the
    project's key is used."""
    try:
        wrapper = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"state": INVALID}
    if not isinstance(wrapper, dict):
        return {"state": INVALID}
    info = wrapper.get("update")
    if not isinstance(info, dict) or not isinstance(wrapper.get("signature"), str):
        return {"state": UNSIGNED}
    if not signing.key_set(key if key is not None else signing.public_key()):
        return {"state": NO_KEY}
    try:
        signing.verify(signing.canonical(info), wrapper["signature"], key)
    except signing.SignatureError:
        return {"state": UNSIGNED}
    try:
        newest = str(info["version"]).strip()
        is_newer = parse_version(newest) > parse_version(current)
    except (ValueError, KeyError, TypeError, AttributeError):
        return {"state": INVALID}
    result: dict = {}
    moved = info.get("moved_to")
    if address_ok(moved) and (url is None or moved.strip() != url.strip()):
        result["moved"] = moved.strip()   # F22: offered to the author, never used by itself
    if not is_newer:
        result.update({"state": CURRENT, "version": newest})
        return result
    note = info.get("note") if isinstance(info.get("note"), str) else ""
    downloads = info.get("download") if isinstance(info.get("download"), dict) else {}
    page = downloads.get(platform_key(platform))
    # The download page opens in the computer's browser: only an https address.
    page = page if _https(page) else None
    result.update({"state": NEWER, "version": newest, "note": note.strip(), "download": page})
    # F22.2: Download and install only for a pack made for this Python, Qt and
    # Typst; otherwise the version needs a new installer.
    from scriptorum.core.packs import runtime_matches
    pack = info.get("pack")
    if isinstance(pack, dict) and address_ok(pack.get("url")) and isinstance(pack.get("sha256"), str) \
            and isinstance(pack.get("signature"), str) and isinstance(pack.get("size"), int):
        if runtime_matches(info.get("runtime"), have):
            result["pack"] = {k: pack[k] for k in ("url", "sha256", "size", "signature")}
        else:
            result["needsInstaller"] = True
    elif info.get("runtime") is not None and not runtime_matches(info.get("runtime"), have):
        result["needsInstaller"] = True
    return result


def check(current: str, url: str = None, opener: Optional[Callable[[str], bytes]] = None,
          platform: Optional[str] = None, key: Optional[str] = None, have: Optional[dict] = None) -> dict:
    """Help ▸ Check for updates… (F21, F22). ``opener`` stands in for
    ``fetch`` in the tests. Returns a dict with ``state`` and, for a newer
    version, its ``version``, ``note``, ``download`` page and, when it can
    be installed from inside the app, its ``pack``."""
    url = UPDATE_URL if url is None else url
    if not address_set(url):
        return {"state": NO_ADDRESS}
    if not _https(url.strip()):
        return {"state": NOT_HTTPS}
    try:
        data = (opener or fetch)(url.strip())
    except (OSError, ValueError, urllib.error.URLError):
        # F21.3: said plainly, and nothing else is affected.
        return {"state": UNREACHABLE}
    return read_file(data, current, platform, key, have, url.strip())


# --- installing an update (F22) ---------------------------------------------------------

class InstallError(Exception):
    """Why an update could not be installed: ``reason`` is unreachable,
    damaged, signature or one of the pack checks (packs.PackError)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def fetch_pack(url: str, timeout: float = 60) -> bytes:
    """Download an update pack: one GET over https with nothing but the
    request itself, only when the author clicked Download and install."""
    request = urllib.request.Request(url, headers={"User-Agent": "Scriptorum", "Accept": "application/zip"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (https checked by the caller)
        if not _https(response.geturl()):
            raise urllib.error.URLError("redirected away from https")
        data = response.read(MAX_PACK_BYTES + 1)
    if len(data) > MAX_PACK_BYTES:
        raise ValueError("update pack too large")
    return data


def install(pack: dict, versions, download: Optional[Callable[[str], bytes]] = None,
            key: Optional[str] = None, have: Optional[dict] = None, running: Optional[str] = None,
            expected: Optional[str] = None) -> str:
    """F22.3, F22.4: download the pack named in a signed update file, check
    its size, checksum and signature, and unpack it into the author's own
    folder for the next start. Nothing changes unless every check passes.
    Returns the version installed."""
    from scriptorum.core.packs import PackError

    url = pack.get("url") if isinstance(pack, dict) else None
    if not address_ok(url):
        raise InstallError("damaged")
    try:
        data = (download or fetch_pack)(url.strip())
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise InstallError("unreachable") from exc
    if len(data) != pack.get("size") or hashlib.sha256(data).hexdigest() != pack.get("sha256"):
        raise InstallError("damaged")
    try:
        signing.verify(data, pack.get("signature", ""), key)
    except signing.SignatureError as exc:
        raise InstallError("signature") from exc
    versions.root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=versions.root, prefix=".download-") as temp:
        file = Path(temp) / "pack.zip"
        file.write_bytes(data)
        try:
            manifest = versions.install(file, key, have, running, expected)
        except PackError as exc:
            raise InstallError(exc.reason) from exc
    return manifest["version"]


def weekly_due(settings, now: Optional[float] = None) -> bool:
    """F21.4: the weekly check runs only when the author turned it on, and at
    most once a week."""
    if not settings.get("update_weekly"):
        return False
    try:
        last = float(settings.get("update_last_check") or 0)
    except (TypeError, ValueError):
        last = 0.0
    return (now if now is not None else time.time()) - last >= WEEK_SECONDS

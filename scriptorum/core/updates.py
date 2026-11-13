"""The update check (design document F21, decided 12 November 2026, built in
M6 part C).

Help ▸ Check for updates… reads one small file at a fixed web address over
https, chosen by the project and written into the app. The file gives the
newest version, a short note on what is new, and the download page for each
platform::

    {
      "version": "1.0.1",
      "note": "Fixes the booklet order.",
      "download": {
        "linux": "https://example.org/scriptorum/linux",
        "macos": "https://example.org/scriptorum/macos",
        "windows": "https://example.org/scriptorum/windows"
      }
    }

Scriptorum never downloads or installs anything (installing updates is the
later item L8). It never checks by itself unless the author turns on the
weekly check (F18); at first start it asks once, with the answer off by
default. This is the only network request the app makes (D9), and it sends
nothing but the request for the file: no version, no identifier, no cookies.
The window's web view, Typst builds, modules and palettes stay without
network access.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Callable, Optional

from scriptorum.core.modules import parse_version

# F21.1: the fixed address of the update file. Until the project chooses one,
# the app holds this placeholder, and Check for updates… says that no update
# address is set yet (and makes no request).
PLACEHOLDER = "Paste update url here"
UPDATE_URL = PLACEHOLDER

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


def read_file(data: bytes, current: str, platform: Optional[str] = None) -> dict:
    """Compare the update file with this version (F21.2, F21.3)."""
    try:
        info = json.loads(data.decode("utf-8"))
        newest = str(info["version"]).strip()
        newer = parse_version(newest) > parse_version(current)
    except (ValueError, KeyError, TypeError, UnicodeDecodeError, AttributeError):
        return {"state": INVALID}
    note = info.get("note") if isinstance(info.get("note"), str) else ""
    downloads = info.get("download") if isinstance(info.get("download"), dict) else {}
    page = downloads.get(platform_key(platform))
    # The download page opens in the computer's browser: only an https address.
    page = page if _https(page) else None
    if not newer:
        return {"state": CURRENT, "version": newest}
    return {"state": NEWER, "version": newest, "note": note.strip(), "download": page}


def check(current: str, url: str = None, opener: Optional[Callable[[str], bytes]] = None,
          platform: Optional[str] = None) -> dict:
    """Help ▸ Check for updates… (F21). ``opener`` stands in for ``fetch`` in
    the tests. Returns a dict with ``state`` and, for a newer version, its
    ``version``, ``note`` and ``download`` page."""
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
    return read_file(data, current, platform)


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

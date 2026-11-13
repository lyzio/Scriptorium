"""A signing key for the tests of F21 and F22 (M6-0.6.7).

The tests never use the project's own key: they make a key pair of their own
and put its public key into the app while they run (conftest.py), so the
app's signature checks are exercised exactly as in use. ``OTHER`` is a
second key, standing in for anyone who is not the project.
"""

from __future__ import annotations

import json

from scriptorum.core import signing

PRIVATE, PUBLIC = signing.new_key_pair()
OTHER_PRIVATE, OTHER_PUBLIC = signing.new_key_pair()


def signed(info: dict, private: bytes = PRIVATE) -> bytes:
    """An update file: the information and its signature (F22)."""
    return json.dumps({"update": info, "signature": signing.sign(signing.canonical(info), private)}).encode()

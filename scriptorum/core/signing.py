"""Signatures on update files and update packs (design document F22, decided
13 November 2026, built in M6 part C5).

Every update pack and every update file is signed with the project's private
Ed25519 key, which is kept outside the app and the repository (the release
script, ``tools/release.py``, makes and uses it). The app holds only the
matching public key, in ``scriptorum/core/update_key.py``, and checks every
signature against it before it uses anything in an update file or a pack.
This is not the operating systems' code signing (D6): it costs nothing and
needs no certificate.

The library is ``cryptography`` (Apache-2.0 OR BSD-3-Clause, pinned in
TechStack and section 7 of the design document).
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Optional

from scriptorum.core import update_key


class SignatureError(Exception):
    """A signature that is missing, malformed or does not match."""


def public_key() -> str:
    """The project's public key built into this copy of the app, as base64,
    or an empty string while no key has been made yet."""
    key = getattr(update_key, "PUBLIC_KEY", "") or ""
    return key.strip()


def key_set(key: Optional[str] = None) -> bool:
    key = public_key() if key is None else key
    try:
        return len(base64.b64decode(key, validate=True)) == 32
    except (binascii.Error, ValueError, TypeError):
        return False


def canonical(data) -> bytes:
    """The exact bytes that are signed for a JSON object: keys sorted, no
    spaces, UTF-8. The signer and the app produce the same bytes."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def verify(data: bytes, signature: str, key: Optional[str] = None) -> None:
    """Raise ``SignatureError`` unless ``signature`` (base64) is the project's
    Ed25519 signature of ``data``."""
    key = public_key() if key is None else key
    if not key_set(key):
        raise SignatureError("no key")
    try:
        raw_signature = base64.b64decode(signature or "", validate=True)
    except (binascii.Error, ValueError, TypeError) as exc:
        raise SignatureError("malformed") from exc
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:  # pragma: no cover - the library ships with the app
        raise SignatureError("no library") from exc
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(key)).verify(raw_signature, data)
    except (InvalidSignature, ValueError) as exc:
        raise SignatureError("mismatch") from exc


def sign(data: bytes, private_pem: bytes) -> str:
    """Sign ``data`` with a private key in PEM form (used only by the release
    script and the tests). Returns the signature as base64."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = serialization.load_pem_private_key(private_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SignatureError("not an Ed25519 key")
    return base64.b64encode(key.sign(data)).decode("ascii")


def new_key_pair() -> tuple:
    """A new key pair: (private key as PEM bytes, public key as base64)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return pem, base64.b64encode(raw).decode("ascii")


def public_of(private_pem: bytes) -> str:
    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_private_key(private_pem, password=None)
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")

"""Check a downloaded file: its SHA-256 and, in signed-update mode, an Ed25519 signature."""

import base64
import binascii
import hashlib
import hmac
from pathlib import Path

from cornea.core.update.release import UpdateError

KEY_BYTES = 32


def file_digest(path: Path) -> bytes:
    """The SHA-256 digest of a file, as 32 bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.digest()


def check_hash(actual_hex: str, expected_hex: str) -> None:
    """Raise :class:`UpdateError` unless the two hashes are the same."""
    if not hmac.compare_digest(actual_hex.lower(), expected_hex.lower()):
        raise UpdateError("the download does not match its checksum", "verify")


def decode_public_key(text: str) -> bytes:
    """The 32 raw bytes of a base64 Ed25519 public key.

    Raises:
        ValueError: If the text is not a base64 key of the right size.

    Example:
        >>> len(decode_public_key(base64.b64encode(bytes(32)).decode()))
        32
    """
    try:
        raw = base64.b64decode(text.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("public_key must be a base64 text") from exc
    if len(raw) != KEY_BYTES:
        raise ValueError(f"public_key must be {KEY_BYTES} bytes (a raw Ed25519 key)")
    return raw


def check_signature(digest: bytes, signature_b64: str, public_key: bytes) -> None:
    """Raise :class:`UpdateError` unless ``signature_b64`` signs ``digest`` with ``public_key``.

    The publisher signs the file's raw SHA-256 digest, so a large file never has to be loaded
    to be signed or checked. Needs the ``signed-updates`` extra (``cryptography``).
    """
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise UpdateError(
            "signed updates need the 'signed-updates' extra "
            "(pip install cornea-shell[signed-updates])",
            "verify",
        ) from exc
    try:
        signature = base64.b64decode(signature_b64, validate=True)
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, digest)
    except (binascii.Error, ValueError, InvalidSignature) as exc:
        raise UpdateError("the update's signature is not valid", "verify") from exc

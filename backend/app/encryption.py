"""FoldAgent Encryption at Rest — Infrastructure Stubs

Configuration scaffold for encryption. Not for production use without
a proper key management solution.
"""

from __future__ import annotations

import hashlib
import os
import warnings
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Crypto library probe
# ---------------------------------------------------------------------------

try:
    from cryptography.hazmat.primitives import hashes, padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False


@dataclass
class EncryptionConfig:
    """Encryption configuration parameters."""

    enabled: bool
    algorithm: str  # e.g. AES-256-CBC
    key_derivation: str  # e.g. PBKDF2-SHA256


# ---------------------------------------------------------------------------
# Encrypt / decrypt
# ---------------------------------------------------------------------------

_XOR_WARNING = (
    "cryptography library not available — using XOR placeholder. "
    "This is NOT secure. Install 'cryptography' for real encryption."
)


def _xor_bytes(data: bytes, key: bytes) -> bytes:
    """Insecure XOR-based placeholder (only used as fallback)."""
    if not key:
        return data
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def encrypt_data(data: bytes, key: bytes) -> bytes:
    """Encrypt *data* with *key*.

    Uses AES-256-CBC via the ``cryptography`` library when available;
    falls back to an XOR placeholder with a warning otherwise.
    """
    if _CRYPTO_AVAILABLE:
        iv = os.urandom(16)
        padder = padding.PKCS7(128).padder()
        padded = padder.update(data) + padder.finalize()
        cipher = Cipher(algorithms.AES(key[:32].ljust(32, b"\x00")), modes.CBC(iv))
        encryptor = cipher.encryptor()
        ct = encryptor.update(padded) + encryptor.finalize()
        return iv + ct
    warnings.warn(_XOR_WARNING, stacklevel=2)
    return _xor_bytes(data, key)


def decrypt_data(data: bytes, key: bytes) -> bytes:
    """Decrypt *data* with *key*.

    Reverses ``encrypt_data``.
    """
    if _CRYPTO_AVAILABLE:
        iv, ct = data[:16], data[16:]
        cipher = Cipher(algorithms.AES(key[:32].ljust(32, b"\x00")), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded = decryptor.update(ct) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        return unpadder.update(padded) + unpadder.finalize()
    warnings.warn(_XOR_WARNING, stacklevel=2)
    return _xor_bytes(data, key)


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


def derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 32-byte key from *password* and *salt* using PBKDF2-SHA256.

    Falls back to a plain hashlib PBKDF2 when ``cryptography`` is absent.
    """
    if _CRYPTO_AVAILABLE:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480_000,
        )
        return kdf.derive(password.encode())
    # stdlib fallback
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 480_000, dklen=32)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def check_encryption_status() -> dict:
    """Return current encryption configuration status."""
    from backend.app.config import settings

    return {
        "configured": settings.encryption_at_rest_enabled,
        "algorithm": "AES-256-CBC" if _CRYPTO_AVAILABLE else "XOR-placeholder",
        "key_derivation": "PBKDF2-SHA256",
        "crypto_library_available": _CRYPTO_AVAILABLE,
        "key_set": settings.encryption_key is not None,
        "note": ("Production scaffold only — integrate with a proper KMS before enabling."),
    }

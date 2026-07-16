"""Polyfill hashlib.scrypt on macOS/LibreSSL Python builds that lack it."""
from __future__ import annotations

import hashlib


def ensure_scrypt() -> None:
    if hasattr(hashlib, "scrypt"):
        return
    try:
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
        from cryptography.hazmat.backends import default_backend
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "hashlib.scrypt is unavailable and the cryptography package is not installed. "
            "Install cryptography or use a Python build with OpenSSL scrypt support."
        ) from exc

    def _scrypt(password, *, salt, n, r, p, maxmem=0, dklen=64):  # noqa: ARG001
        kdf = Scrypt(
            salt=salt,
            length=dklen,
            n=n,
            r=r,
            p=p,
            backend=default_backend(),
        )
        return kdf.derive(password)

    hashlib.scrypt = _scrypt  # type: ignore[attr-defined]

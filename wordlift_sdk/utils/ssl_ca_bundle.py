from __future__ import annotations

import os
import ssl
from pathlib import Path
from typing import Optional

try:
    import certifi
except Exception:  # pragma: no cover - optional dependency
    certifi = None


def _is_readable_file(path: str | None) -> bool:
    if not path:
        return False
    return Path(path).is_file()


def _system_ca_path() -> Optional[str]:
    paths = ssl.get_default_verify_paths()
    if _is_readable_file(paths.cafile):
        return paths.cafile
    if _is_readable_file(paths.openssl_cafile):
        return paths.openssl_cafile
    return None


def _certifi_path() -> Optional[str]:
    if certifi is None:
        return None
    try:
        path = certifi.where()
    except Exception:
        return None
    return path if _is_readable_file(path) else None


def resolve_ssl_ca_cert(override: str | None = None) -> Optional[str]:
    if _is_readable_file(override):
        return override

    if os.name == "posix" and os.uname().sysname == "Darwin":
        system_ca = _system_ca_path()
        if system_ca:
            return system_ca
        return _certifi_path()

    return _system_ca_path()

from __future__ import annotations

import hashlib
from pathlib import Path


def normalize_python_source_bytes(source: bytes) -> bytes:
    """Return strict UTF-8 source with every newline represented as LF."""
    text = source.decode("utf-8")
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def canonical_source_checksum(source: bytes) -> str:
    """Hash Python source independently of checkout newline conventions."""
    return hashlib.sha256(normalize_python_source_bytes(source)).hexdigest()


def canonical_source_file_checksum(path: str | Path) -> str:
    return canonical_source_checksum(Path(path).read_bytes())

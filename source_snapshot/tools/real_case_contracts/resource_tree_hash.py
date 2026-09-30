from __future__ import annotations

import hashlib
import os
import struct
from pathlib import Path
from typing import Iterable, Literal


_TEXT_SUFFIXES = frozenset({".json", ".csv", ".fasta", ".md"})
_TEXT_FILENAMES = frozenset({".gitattributes"})
_BINARY_SUFFIXES = frozenset({".gb"})
_EntryKind = Literal["directory", "file", "symlink", "other"]
_MAX_U64 = (1 << 64) - 1


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _classify_entry(path: Path) -> _EntryKind:
    if path.is_symlink():
        return "symlink"
    if path.is_dir():
        return "directory"
    if path.is_file():
        return "file"
    return "other"


def _relative_posix(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _collect_files(*, repo_root: Path, resource_root: Path) -> list[tuple[bytes, Path]]:
    files: list[tuple[bytes, Path]] = []
    pending = [resource_root]

    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                relative_path = _relative_posix(path, repo_root)
                kind = _classify_entry(path)
                if kind == "symlink":
                    raise ValueError(f"Symlink is not supported: {relative_path}")
                if kind == "directory":
                    pending.append(path)
                    continue
                if kind != "file":
                    raise ValueError(f"Unsupported filesystem entry: {relative_path}")
                files.append((relative_path.encode("utf-8"), path))

    files.sort(key=lambda item: item[0])
    return files


def _logical_content(*, path: Path, relative_path: str) -> bytes:
    suffix = path.suffix
    if path.name in _TEXT_FILENAMES or suffix in _TEXT_SUFFIXES:
        raw_bytes = path.read_bytes()
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"Invalid UTF-8 text file: {relative_path}") from error
        return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    if suffix in _BINARY_SUFFIXES:
        return path.read_bytes()
    unsupported_type = suffix or "<no extension>"
    raise ValueError(f"Unsupported file type {unsupported_type}: {relative_path}")


def _unsigned_64(value: int) -> bytes:
    if not 0 <= value <= _MAX_U64:
        raise ValueError("Canonical resource tree field exceeds unsigned 64-bit range")
    return struct.pack(">Q", value)


def _validated_files(*, repo_root: Path, resource_root: Path) -> list[tuple[bytes, Path]]:
    absolute_repo_root = _absolute_lexical(repo_root)
    absolute_resource_root = _absolute_lexical(resource_root)

    try:
        absolute_resource_root.relative_to(absolute_repo_root)
    except ValueError as error:
        raise ValueError("resource_root must be located within repo_root") from error

    resource_relative = _relative_posix(absolute_resource_root, absolute_repo_root)
    root_kind = _classify_entry(absolute_resource_root)
    if root_kind == "symlink":
        raise ValueError(f"Symlink is not supported: {resource_relative}")
    if root_kind != "directory":
        raise ValueError(f"resource_root must be a directory: {resource_relative}")

    return _collect_files(
        repo_root=absolute_repo_root,
        resource_root=absolute_resource_root,
    )


def _framed_tree_chunks(files: list[tuple[bytes, Path]]) -> Iterable[bytes]:
    """Yield u64 entry count, then u64-length-prefixed path/content pairs."""
    yield _unsigned_64(len(files))
    for encoded_path, path in files:
        relative_path = encoded_path.decode("utf-8")
        content = _logical_content(path=path, relative_path=relative_path)
        yield _unsigned_64(len(encoded_path))
        yield encoded_path
        yield _unsigned_64(len(content))
        yield content


def _serialize_logical_resource_tree(*, repo_root: Path, resource_root: Path) -> bytes:
    """Return the exact deterministic byte framing used by the public hash API."""
    files = _validated_files(repo_root=repo_root, resource_root=resource_root)
    return b"".join(_framed_tree_chunks(files))


def hash_logical_resource_tree(*, repo_root: Path, resource_root: Path) -> str:
    """Hash length-framed POSIX paths and canonical logical file content."""
    files = _validated_files(repo_root=repo_root, resource_root=resource_root)
    digest = hashlib.sha256()
    for chunk in _framed_tree_chunks(files):
        digest.update(chunk)
    return digest.hexdigest()

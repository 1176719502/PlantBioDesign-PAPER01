from __future__ import annotations

import hashlib
import os
import re
import struct
from pathlib import Path

import pytest

from tools.real_case_contracts import resource_tree_hash
from tools.real_case_contracts.resource_tree_hash import hash_logical_resource_tree


def _make_tree(tmp_path: Path, content: bytes, *, name: str = "record.json") -> tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    resource_root = repo_root / "data" / "resources"
    resource_root.mkdir(parents=True)
    (resource_root / name).write_bytes(content)
    return repo_root, resource_root


def _hash(repo_root: Path, resource_root: Path) -> str:
    return hash_logical_resource_tree(repo_root=repo_root, resource_root=resource_root)


def _u64(value: int) -> bytes:
    return struct.pack(">Q", value)


@pytest.mark.parametrize("variant", [b"alpha\r\nbeta\r\n", b"alpha\r\nbeta\rgamma\n"])
def test_text_eol_variants_match_lf(tmp_path: Path, variant: bytes) -> None:
    expected_lines = b"alpha\nbeta\n" if b"gamma" not in variant else b"alpha\nbeta\ngamma\n"
    repo_root, resource_root = _make_tree(tmp_path, expected_lines)
    expected = _hash(repo_root, resource_root)
    (resource_root / "record.json").write_bytes(variant)
    assert _hash(repo_root, resource_root) == expected


def test_text_content_change_changes_hash(tmp_path: Path) -> None:
    repo_root, resource_root = _make_tree(tmp_path, b'{"value": 1}\n')
    before = _hash(repo_root, resource_root)
    (resource_root / "record.json").write_bytes(b'{"value": 2}\n')
    assert _hash(repo_root, resource_root) != before


def test_adding_and_deleting_file_changes_hash(tmp_path: Path) -> None:
    repo_root, resource_root = _make_tree(tmp_path, b"{}\n")
    original = _hash(repo_root, resource_root)
    added = resource_root / "extra.md"
    added.write_bytes(b"extra\n")
    assert _hash(repo_root, resource_root) != original
    added.unlink()
    assert _hash(repo_root, resource_root) == original


def test_empty_file_is_distinct_from_missing_file(tmp_path: Path) -> None:
    repo_root, resource_root = _make_tree(tmp_path, b"", name="empty.gb")
    with_empty_file = _hash(repo_root, resource_root)
    (resource_root / "empty.gb").unlink()
    assert _hash(repo_root, resource_root) != with_empty_file


def test_paths_are_sorted_by_posix_utf8_bytes(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    resource_root = repo_root / "data" / "resources"
    resource_root.mkdir(parents=True)
    names = ["\u4e2d.json", "z.json", "\u00e9.json", "A.json"]
    for name in reversed(names):
        (resource_root / name).write_bytes(name.encode("utf-8"))

    records = []
    for name in sorted(names, key=lambda item: item.encode("utf-8")):
        relative = f"data/resources/{name}".encode("utf-8")
        content = name.encode("utf-8")
        records.append(_u64(len(relative)) + relative + _u64(len(content)) + content)
    framed = _u64(len(names)) + b"".join(records)
    assert _hash(repo_root, resource_root) == hashlib.sha256(framed).hexdigest()


def test_directory_enumeration_order_does_not_change_framing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root, resource_root = _make_tree(tmp_path, b"{}\n")
    (resource_root / "a.md").write_bytes(b"a\n")
    (resource_root / "z.md").write_bytes(b"z\n")
    expected = resource_tree_hash._serialize_logical_resource_tree(
        repo_root=repo_root, resource_root=resource_root
    )
    original_scandir = resource_tree_hash.os.scandir

    class ReversedEntries:
        def __init__(self, directory: Path) -> None:
            with original_scandir(directory) as entries:
                self.entries = list(entries)[::-1]

        def __enter__(self) -> list[os.DirEntry[str]]:
            return self.entries

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(resource_tree_hash.os, "scandir", ReversedEntries)
    actual = resource_tree_hash._serialize_logical_resource_tree(
        repo_root=repo_root, resource_root=resource_root
    )
    assert actual == expected


@pytest.mark.skipif(os.name != "nt", reason="Windows mixed-separator input contract")
def test_mixed_separator_input_paths_do_not_change_hash(tmp_path: Path) -> None:
    repo_root, resource_root = _make_tree(tmp_path, b"alpha\nbeta\n")
    mixed_repo_root = Path(str(repo_root).replace("\\", "/"))
    mixed_resource_root = Path(str(resource_root).replace("\\", "/"))
    assert _hash(mixed_repo_root, mixed_resource_root) == _hash(repo_root, resource_root)


def test_genbank_allows_nul_and_uses_raw_bytes(tmp_path: Path) -> None:
    repo_root, resource_root = _make_tree(tmp_path, b"LOCUS\x00raw\n", name="record.gb")
    original = _hash(repo_root, resource_root)
    (resource_root / "record.gb").write_bytes(b"LOCUS\x00raw\r\n")
    assert _hash(repo_root, resource_root) != original


def test_review_framing_collision_has_distinct_bytes_and_hashes(tmp_path: Path) -> None:
    repo_a, root_a = _make_tree(
        tmp_path / "tree_a",
        b"X\x00data/resources/b.gb\x00Y",
        name="a.gb",
    )
    repo_b, root_b = _make_tree(tmp_path / "tree_b", b"X", name="a.gb")
    (root_b / "b.gb").write_bytes(b"Y")

    framed_a = resource_tree_hash._serialize_logical_resource_tree(
        repo_root=repo_a, resource_root=root_a
    )
    framed_b = resource_tree_hash._serialize_logical_resource_tree(
        repo_root=repo_b, resource_root=root_b
    )
    legacy_a = b"data/resources/a.gb\x00X\x00data/resources/b.gb\x00Y\x00"
    legacy_b = (
        b"data/resources/a.gb\x00X\x00"
        b"data/resources/b.gb\x00Y\x00"
    )

    assert legacy_a == legacy_b
    assert framed_a != framed_b
    assert framed_a.startswith(_u64(1))
    assert framed_b.startswith(_u64(2))
    assert _hash(repo_a, root_a) != _hash(repo_b, root_b)


def test_unknown_file_type_and_invalid_text_are_rejected(tmp_path: Path) -> None:
    repo_root, resource_root = _make_tree(tmp_path, b"unknown", name="payload.txt")
    with pytest.raises(ValueError, match=r"Unsupported file type \.txt: data/resources/payload\.txt"):
        _hash(repo_root, resource_root)
    (resource_root / "payload.txt").rename(resource_root / "record.json")
    (resource_root / "record.json").write_bytes(b"\xff")
    with pytest.raises(ValueError, match=r"Invalid UTF-8 text file: data/resources/record\.json"):
        _hash(repo_root, resource_root)


def test_resource_root_outside_repo_root_is_rejected(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    resource_root = tmp_path / "outside"
    resource_root.mkdir()
    with pytest.raises(ValueError, match="resource_root must be located within repo_root"):
        _hash(repo_root, resource_root)


def test_hash_is_lowercase_sha256(tmp_path: Path) -> None:
    repo_root, resource_root = _make_tree(tmp_path, b"attribute=value\n", name=".gitattributes")
    assert re.fullmatch(r"[0-9a-f]{64}", _hash(repo_root, resource_root))


def test_symlink_entries_are_rejected_without_platform_symlink_support(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root, resource_root = _make_tree(tmp_path, b"{}\n")
    entry = resource_root / "record.json"
    original_classifier = resource_tree_hash._classify_entry

    def classify_as_symlink(path: Path) -> resource_tree_hash._EntryKind:
        if path == entry:
            return "symlink"
        return original_classifier(path)

    monkeypatch.setattr(resource_tree_hash, "_classify_entry", classify_as_symlink)
    with pytest.raises(ValueError, match=r"Symlink is not supported: data/resources/record\.json"):
        _hash(repo_root, resource_root)

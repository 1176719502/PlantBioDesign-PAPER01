"""Build one independent knowledge release in offline staging."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.knowledge_base.builder import build_knowledge_release_from_file
from services.knowledge_base.errors import KnowledgeBuildError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a deterministic KB-00 SQLite release from a reviewed local JSON bundle."
    )
    parser.add_argument("bundle", type=Path, help="Reviewed local KB-00 import bundle.")
    parser.add_argument("output_directory", type=Path, help="Build staging directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = build_knowledge_release_from_file(args.bundle, args.output_directory)
    except KnowledgeBuildError as exc:
        print(f"KB00_BUILD_FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        "KB00_BUILD_PASS: "
        f"database={result.database_path} "
        f"sha256={result.database_sha256} "
        f"logical_sha256={result.logical_dump_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

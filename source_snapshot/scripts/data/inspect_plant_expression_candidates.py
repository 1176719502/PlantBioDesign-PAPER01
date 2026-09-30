from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.plant_expression_candidate_ingestion.config import default_data_root
from services.plant_expression_candidate_ingestion.inspection import inspect_candidate_knowledge_base


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect the local plant expression candidate knowledge base.")
    parser.add_argument("--data-root", default=str(default_data_root()), help="Local knowledge-base root.")
    parser.add_argument("--search", default="", help="Optional read-only search term.")
    parser.add_argument("--limit", type=int, default=10, help="Search result limit.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = inspect_candidate_knowledge_base(data_root=Path(args.data_root), search=args.search, limit=args.limit)
    except Exception as exc:
        print(json.dumps({"ok": False, "fatal_error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "summary": result}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

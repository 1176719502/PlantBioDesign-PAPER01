from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.plant_expression_candidate_ingestion.config import (
    DEFAULT_QUERY_PLAN_PATH,
    DEFAULT_SOURCE_REGISTRY_PATH,
    default_data_root,
)
from services.plant_expression_candidate_ingestion.pipeline import IngestionOptions, run_ingestion


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest plant expression candidate metadata.")
    parser.add_argument("--source", required=True, help="Source ID such as europe_pmc, uniprot, or all.")
    parser.add_argument("--query-plan", default=str(DEFAULT_QUERY_PLAN_PATH), help="Query-plan JSON path.")
    parser.add_argument("--source-registry", default=str(DEFAULT_SOURCE_REGISTRY_PATH), help="Source registry JSON path.")
    parser.add_argument("--query-id", action="append", default=[], help="Specific query ID; may be repeated.")
    parser.add_argument("--data-root", default=str(default_data_root()), help="Local knowledge-base root.")
    parser.add_argument("--max-records", type=int, default=0, help="Overall maximum records for the selected source.")
    parser.add_argument("--page-size", type=int, default=100, help="Maximum records per API page.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Request timeout in seconds.")
    parser.add_argument("--retries", type=int, default=2, help="Retries per page.")
    parser.add_argument("--retry-delay", type=float, default=1.0, help="Delay between retries in seconds.")
    parser.add_argument("--pace-seconds", type=float, default=0.2, help="Delay between successful pages.")
    parser.add_argument("--resume", action="store_true", help="Reserved for run checkpoint continuation.")
    parser.add_argument("--run-id", default="", help="Explicit ingestion run ID.")
    parser.add_argument("--dry-run", action="store_true", help="Preview selected sources and queries without writing.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_ingestion(
            IngestionOptions(
                data_root=Path(args.data_root),
                source_id=args.source,
                query_plan_path=Path(args.query_plan),
                source_registry_path=Path(args.source_registry),
                query_ids=tuple(args.query_id),
                max_records=args.max_records,
                page_size=args.page_size,
                timeout=args.timeout,
                retries=args.retries,
                retry_delay=args.retry_delay,
                pace_seconds=args.pace_seconds,
                dry_run=args.dry_run,
                resume=args.resume,
                explicit_run_id=args.run_id,
            )
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "fatal_error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "summary": result}, ensure_ascii=False, indent=2, sort_keys=True))
    if not args.dry_run and result.get("error_count", 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

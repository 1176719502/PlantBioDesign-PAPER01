"""Compatibility entry point for the current generic Gate 3 Pathway runner."""
from __future__ import annotations

try:
    from scripts.acceptance.run_formal_pathway_blank_acceptance import main
except ModuleNotFoundError:  # direct ``python scripts/acceptance/...`` execution
    from run_formal_pathway_blank_acceptance import main


if __name__ == "__main__":
    raise SystemExit(main())

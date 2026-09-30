from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from services.knowledge_base.builder import BuildResult, build_knowledge_release


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_BUNDLE = ROOT / "tests" / "fixtures" / "kb00" / "synthetic_release_v0.json"


def load_synthetic_bundle() -> dict[str, Any]:
    return json.loads(SYNTHETIC_BUNDLE.read_text(encoding="utf-8"))


def cloned_synthetic_bundle() -> dict[str, Any]:
    return copy.deepcopy(load_synthetic_bundle())


def build_synthetic_release(output_directory: Path) -> BuildResult:
    return build_knowledge_release(load_synthetic_bundle(), output_directory)

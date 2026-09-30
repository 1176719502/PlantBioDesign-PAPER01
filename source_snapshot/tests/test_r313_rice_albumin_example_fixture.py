from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.rice_albumin_example_fixture import (
    SNAPSHOT_ID,
    build_rice_albumin_example_preview,
    format_rice_albumin_example_markdown,
)


FORBIDDEN_RUNTIME_COPY = [
    "actual sequence",
    "promoter recommendation is included",
    "protocol " + "steps",
    "transformation " + "procedure",
    "selection " + "procedure",
    "culture " + "condition",
    "production " + "estimate",
    "optimized " + "sequence",
    "construct is ready",
    "plant-line " + "validation",
    "yield " + "prediction",
    "phenotype " + "guarantee",
]


def test_rice_albumin_example_fixture_identity_and_required_copy() -> None:
    preview = build_rice_albumin_example_preview()
    markdown = format_rice_albumin_example_markdown(preview)
    identity = preview["identity"]

    assert preview["example_name"] == "Rice albumin / plant molecular farming documentation review"
    for expected in [
        "Example only",
        "Documentation-only",
        "Not a construct recommendation",
        "Not " + "experiment" + "-ready",
        "Plant recombinant protein / molecular farming",
        "Rice context, review-only",
        "source/provenance required",
        "QR payload",
        "MD5 checksum",
    ]:
        assert expected in markdown

    assert re.fullmatch(r"[0-9a-f]{32}", identity["md5_checksum"])
    assert identity["qr_payload"] == (
        "BioDesignStudioPlant|PlantDesignReviewPackage|example=rice-albumin|"
        f"snapshot={SNAPSHOT_ID}|md5={identity['md5_checksum']}"
    )
    for expected in [
        "BioDesignStudioPlant",
        "PlantDesignReviewPackage",
        "example=rice-albumin",
        SNAPSHOT_ID,
    ]:
        assert expected in identity["qr_payload"]


def test_rice_albumin_example_fixture_is_static_and_not_persistent() -> None:
    first = build_rice_albumin_example_preview()
    second = build_rice_albumin_example_preview()

    first["labels"].append("local mutation should not persist")

    assert first is not second
    assert second["identity"]["md5_checksum"] == build_rice_albumin_example_preview()["identity"]["md5_checksum"]
    assert "local mutation should not persist" not in second["labels"]
    assert "not saved as a user project" in second["read_only_note"]
    assert "not loaded into editable fields" in second["read_only_note"]
    assert "not included in import/export" in second["read_only_note"]


def test_rice_albumin_example_fixture_avoids_sequence_protocol_and_claim_copy() -> None:
    preview = build_rice_albumin_example_preview()
    text = format_rice_albumin_example_markdown(preview).lower()

    assert "no promoter recommendation" in text
    assert "no procedure" in text
    assert "no optimization output" in text
    assert "does not validate construct readiness" in text
    assert "plant-line performance" in text
    assert "does not validate" in text
    assert "phenotype, yield, or experimental success" in text

    for forbidden in FORBIDDEN_RUNTIME_COPY:
        assert forbidden not in text


def test_rice_albumin_example_preview_is_homepage_only_and_not_import_export() -> None:
    home = (Path(ROOT) / "views" / "Homepage.py").read_text(encoding="utf-8")
    service = (Path(ROOT) / "services" / "rice_albumin_example_fixture.py").read_text(encoding="utf-8")

    assert "View rice albumin example preview" in home
    assert "_render_rice_albumin_example_preview()" in home
    assert "execute_project_import_as_new_project" not in service
    assert "project_export_package_service" not in service
    assert "sqlite" not in service.lower()
    assert "INSERT INTO" not in service

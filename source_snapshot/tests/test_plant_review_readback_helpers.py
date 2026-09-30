from __future__ import annotations

from services.plant_review_readback_helpers import (
    coerce_list,
    coerce_mapping_list,
    coerce_mapping,
    coerce_text,
    first_text,
    readback_list,
    readback_summary,
    status_label,
)


def test_readback_helpers_normalize_text_mapping_and_list_inputs() -> None:
    assert coerce_text("  manual_review_required  ") == "manual_review_required"
    assert coerce_text(None) == ""
    assert coerce_mapping({"status": "manual_review_required"}) == {"status": "manual_review_required"}
    assert coerce_mapping("not a mapping") == {}
    assert coerce_list(("a", "b")) == ["a", "b"]
    assert coerce_list("abc") == []
    assert coerce_mapping_list([{"status": "manual_review_required"}, "skip"]) == [
        {"status": "manual_review_required"}
    ]


def test_first_text_and_status_label_keep_existing_plant_review_fallbacks() -> None:
    assert first_text("", None, "  Source note  ") == "Source note"
    assert first_text("", None) == ""
    assert status_label("manual_review_required") == "manual review required"
    assert status_label("") == "not recorded"


def test_readback_summary_prefers_named_keys_and_skips_nested_values() -> None:
    value = {
        "status": "manual_review_required",
        "source_type": "manual note",
        "nested": {"ignored": True},
        "row": ["ignored"],
        "extra": "shown only without preferred keys",
    }

    assert readback_summary(value, ("status", "source_type")) == (
        "status: manual_review_required; source_type: manual note"
    )
    assert readback_summary(value) == "extra: shown only without preferred keys; source_type: manual note; status: manual_review_required"
    assert readback_summary({}) == "not recorded"
    assert readback_summary("not a mapping") == "not recorded"


def test_readback_list_keeps_plain_visible_values_only() -> None:
    assert readback_list([" slot A ", "", None, "slot B"]) == "slot A; slot B"
    assert readback_list("slot A") == "none visible"
    assert readback_list([]) == "none visible"

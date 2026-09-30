from __future__ import annotations

from services.formal_t_dna_review import (
    TDnaReviewError,
    build_t_dna_confirmation,
    confirmation_is_current,
    imported_feature_confirmation,
    imported_feature_rows,
    manual_border_confirmation,
    validate_t_dna_operation,
)


def _backbone(*, topology: str = "circular") -> dict:
    return {
        "normalized_sequence": "A" * 1000,
        "topology": topology,
        "imported_feature_records": [
            {"feature_id": "feature-lb", "name": "chosen left annotation", "type": "misc_feature", "start": 100, "end": 110, "strand": 1, "qualifiers": {"label": ["user-selected"]}},
            {"feature_id": "feature-rb", "name": "chosen right annotation", "type": "misc_feature", "start": 800, "end": 810, "strand": -1, "qualifiers": {"note": ["source"]}},
        ],
    }


def test_imported_features_remain_unclassified_until_explicitly_selected() -> None:
    rows = imported_feature_rows(_backbone())

    assert [row["name"] for row in rows] == ["chosen left annotation", "chosen right annotation"]
    assert all("lb" not in row and "rb" not in row for row in rows)


def test_imported_feature_confirmation_preserves_original_metadata() -> None:
    feature = _backbone()["imported_feature_records"][0]
    confirmation = imported_feature_confirmation(feature, role="lb")

    assert confirmation["confirmation_method"] == "imported_annotation"
    assert confirmation["original_name"] == "chosen left annotation"
    assert confirmation["feature_type"] == "misc_feature"
    assert confirmation["start"] == 101
    assert confirmation["end"] == 110
    assert confirmation["qualifiers"] == {"label": ["user-selected"]}


def test_manual_coordinate_confirmation_requires_direction_note() -> None:
    try:
        manual_border_confirmation(role="lb", start=101, end=110, direction_note="", backbone_length=1000)
    except TDnaReviewError as exc:
        assert "direction note" in str(exc)
    else:
        raise AssertionError("manual LB confirmation must require a direction note")


def test_non_wrapping_t_dna_confirmation_cannot_replace_an_operation_contract() -> None:
    backbone = _backbone()
    lb, rb = backbone["imported_feature_records"]
    confirmation = build_t_dna_confirmation(
        backbone,
        lb=imported_feature_confirmation(lb, role="lb"),
        rb=imported_feature_confirmation(rb, role="rb"),
        direction="lb_to_rb",
    )

    assert confirmation["region"] == {"start": 111, "end": 800, "crosses_origin": False, "coordinate_convention": "1-based-inclusive"}
    for start, end in ((500, 501), (90, 91), (105, 106)):
        operation = validate_t_dna_operation(
            backbone,
            confirmation=confirmation,
            insertion_settings={"mode": "insertion", "start_coordinate": start, "end_coordinate": end},
        )
        assert operation["status"] == "vector_asset_contract_blocked"
        assert operation["allowed"] is False


def test_circular_cross_origin_review_does_not_unlock_unverified_vector() -> None:
    backbone = _backbone()
    lb, rb = backbone["imported_feature_records"]
    confirmation = build_t_dna_confirmation(
        backbone,
        lb=imported_feature_confirmation(lb, role="lb"),
        rb=imported_feature_confirmation(rb, role="rb"),
        direction="rb_to_lb",
    )

    assert confirmation["region"]["crosses_origin"] is True
    for start, end in ((900, 901), (500, 501)):
        operation = validate_t_dna_operation(
            backbone,
            confirmation=confirmation,
            insertion_settings={"mode": "insertion", "start_coordinate": start, "end_coordinate": end},
        )
        assert operation["allowed"] is False
        assert operation["status"] == "vector_asset_contract_blocked"


def test_manual_4200_bp_backbone_remains_blocked_without_reviewed_contract() -> None:
    backbone = {
        "normalized_sequence": "A" * 4200,
        "topology": "circular",
        "imported_feature_records": [],
        "length": 4200,
    }
    confirmation = build_t_dna_confirmation(
        backbone,
        lb=manual_border_confirmation(role="lb", start=1, end=10, direction_note="LB → RB manual review", backbone_length=4200),
        rb=manual_border_confirmation(role="rb", start=4191, end=4200, direction_note="LB → RB manual review", backbone_length=4200),
        direction="lb_to_rb",
    )

    assert confirmation["region"] == {
        "start": 11,
        "end": 4190,
        "crosses_origin": False,
        "coordinate_convention": "1-based-inclusive",
    }
    operation = validate_t_dna_operation(
        backbone,
        confirmation=confirmation,
        insertion_settings={"mode": "insertion", "start_coordinate": 2000, "end_coordinate": 2001},
    )
    assert operation["status"] == "vector_asset_contract_blocked"
    assert operation["allowed"] is False


def test_manual_confirmation_blocks_out_of_range_coordinates_and_overlapping_borders() -> None:
    backbone = {
        "normalized_sequence": "A" * 4200,
        "topology": "circular",
        "imported_feature_records": [],
        "length": 4200,
    }
    try:
        manual_border_confirmation(
            role="rb",
            start=4191,
            end=4201,
            direction_note="LB → RB manual review",
            backbone_length=4200,
        )
    except TDnaReviewError as exc:
        assert "outside the imported backbone" in str(exc)
    else:
        raise AssertionError("RB end beyond the backbone length must remain blocked")

    try:
        build_t_dna_confirmation(
            backbone,
            lb=manual_border_confirmation(role="lb", start=1, end=20, direction_note="LB → RB manual review", backbone_length=4200),
            rb=manual_border_confirmation(role="rb", start=15, end=30, direction_note="LB → RB manual review", backbone_length=4200),
            direction="lb_to_rb",
        )
    except TDnaReviewError as exc:
        assert "cannot overlap" in str(exc)
    else:
        raise AssertionError("Overlapping LB/RB coordinates must remain blocked")


def test_changed_backbone_invalidates_confirmation() -> None:
    backbone = _backbone()
    lb, rb = backbone["imported_feature_records"]
    confirmation = build_t_dna_confirmation(backbone, lb=imported_feature_confirmation(lb, role="lb"), rb=imported_feature_confirmation(rb, role="rb"), direction="lb_to_rb")
    backbone["normalized_sequence"] = "C" * 1000

    assert confirmation_is_current(backbone, confirmation) is False
    assert validate_t_dna_operation(backbone, confirmation=confirmation, insertion_settings={"mode": "insertion", "start_coordinate": 500, "end_coordinate": 501})["status"] == "vector_asset_contract_blocked"


def test_confirmation_roundtrips_in_existing_single_gene_snapshot(tmp_path) -> None:
    import mvp_app
    from services.mvp_single_gene_persistence import open_mvp_single_gene_design, save_mvp_single_gene_design
    from services.plant_project_draft_repository import PlantProjectDraftRepository

    base = mvp_app.generate_complete_vector(mvp_app.load_real_case(), project_name="T-DNA review record")
    backbone = base["input_records"]["backbone"]
    length = int(backbone["length"])
    confirmation = build_t_dna_confirmation(
        backbone,
        lb=manual_border_confirmation(role="lb", start=1, end=10, direction_note="manual LB boundary", backbone_length=length),
        rb=manual_border_confirmation(role="rb", start=length - 9, end=length, direction_note="manual RB boundary", backbone_length=length),
        direction="lb_to_rb",
    )
    settings = dict(base["insertion_settings"])
    settings["t_dna_confirmation"] = confirmation
    settings["t_dna_operation_validation"] = validate_t_dna_operation(backbone, confirmation=confirmation, insertion_settings=settings)
    result = mvp_app.generate_complete_vector(
        mvp_app.load_real_case(),
        input_records=base["input_records"],
        cds_input=base["cds_input"],
        insertion_settings=settings,
        project_id=base["project_id"],
        project_name=base["project_name"],
    )
    result["formal_project_context"] = {"host_key": "Rice (O. sativa)", "current_step": 6}
    repo = PlantProjectDraftRepository(tmp_path / "projects")

    saved = save_mvp_single_gene_design(result, repository=repo)
    reopened = open_mvp_single_gene_design(saved.project_id, repository=repo)

    assert reopened["insertion_settings"]["t_dna_confirmation"] == confirmation
    assert reopened["insertion_settings"]["t_dna_operation_validation"]["status"] == "vector_asset_contract_blocked"
    assert reopened["vector_asset_admission"]["legacy_project_read_only"] is True
    assert reopened["vector_asset_admission"]["completed_design_allowed"] is False

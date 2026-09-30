# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as streamlit_module

from services import expression_construct_repository as repo
from services import project_catalog_asset_link_repository as project_catalog_link_repo
from tests.helpers.fake_streamlit import FakeStreamlit
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path
import views.pathway_workspace_sections.export_package_section as export_package_section
import views.pathway_workspace_sections.import_preview_section as import_preview_section
import views.pathway_workspace_sections.project_documentation_package_section as package_section


class _UploadedText:
    def __init__(self, text: str):
        self._text = text

    def getvalue(self) -> bytes:
        return self._text.encode("utf-8")


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(export_package_section, "st", fake_st)
    monkeypatch.setattr(import_preview_section, "st", fake_st)
    monkeypatch.setattr(package_section, "st", fake_st)
    monkeypatch.setattr(streamlit_module, "session_state", fake_st.session_state, raising=False)
    return fake_st


def _rendered_text(fake_st: FakeStreamlit) -> str:
    return "\n".join(
        fake_st.subheaders
        + fake_st.caption_messages
        + fake_st.info_messages
        + fake_st.warning_messages
        + fake_st.error_messages
        + fake_st.success_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [call["label"] for call in fake_st.download_button_calls]
        + [call["label"] for call in fake_st.file_uploader_calls]
        + [call["label"] for call in fake_st.text_area_calls]
        + [call["label"] for call in fake_st.metric_calls]
    )


def _use_temp_db(monkeypatch, name: str = "project_documentation_package_ui.db") -> None:
    db_path = repo_local_sqlite_db_path(".pytest_tmp_r82_project_documentation_package_dbs", name)
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(db_path))


def _seed_construct_records() -> None:
    profile = repo.create_construct_profile(
        construct_id="construct-ui",
        construct_label="UI construct",
        construct_type="documentation-only construct draft",
        source_reference="UI notebook",
        provenance_note="UI provenance note.",
        review_status="documentation review pending",
    )
    cassette = repo.create_construct_cassette(
        profile["construct_id"],
        cassette_id="cassette-ui",
        cassette_label="UI cassette",
        cassette_order=1,
        promoter_label="UI promoter",
        gene_label="crtI",
        terminator_label="UI terminator",
        source_reference="UI cassette notebook",
        provenance_note="UI cassette provenance note.",
    )
    repo.add_construct_cassette_part(
        cassette["cassette_id"],
        part_order=1,
        part_role="promoter",
        part_label="UI promoter row",
        source_reference="UI promoter notebook",
        source_catalog="Plant Promoter Catalog",
        source_record_id="plant-promoter-ui",
        source_record_label="UI promoter source record",
        evidence_context_note="UI promoter evidence context",
        provenance_note="UI promoter provenance note.",
    )
    repo.add_construct_gene_link(
        profile["construct_id"],
        gene_label="crtI",
        gene_reference="crtI-ui-ref",
        source_reference="UI gene notebook",
        provenance_note="UI gene provenance note.",
    )
    repo.add_construct_pathway_step_link(
        profile["construct_id"],
        pathway_step_id="step-ui",
        pathway_step_label="UI pathway step",
        source_reference="UI pathway note",
        provenance_note="UI pathway provenance note.",
    )
    repo.create_construct_project_link(
        project_id="project-ui",
        construct_id=profile["construct_id"],
        link_label="UI project link",
        link_note="UI project construct note.",
        source_context="UI pathway workspace context",
        curation_status="documentation review pending",
        review_note="UI review note.",
    )


def _seed_catalog_reference() -> None:
    project_catalog_link_repo.add_project_catalog_asset_link(
        {
            "project_id": "project-ui",
            "asset_id": "plant-promoter-ui",
            "asset_display_name": "UI persisted promoter profile",
            "asset_type": "plant_promoter_profile",
            "linkage_role": "source_review_context",
            "documentation_note": "Documentation-only Plant Promoter Catalog reference for project traceability.",
            "source_context_snapshot": {
                "catalog": "Plant Promoter Catalog",
                "profile_id": "plant-promoter-ui",
                "plant_clade": "monocot",
                "species": "Zea mays (maize)",
                "source_labels": "Fixture source: UI",
            },
            "review_status_snapshot": {
                "curation_statuses": "source review needed",
                "missing_metadata_count": 2,
            },
            "human_review_required": True,
        }
    )


def _seed_host_context_reference(
    *,
    project_id: str = "project-ui",
    asset_id: str = "host-context-ui",
    label: str = "UI host context note",
    host_context: str = "Nicotiana benthamiana documentation context",
) -> None:
    project_catalog_link_repo.add_project_catalog_asset_link(
        {
            "project_id": project_id,
            "asset_id": asset_id,
            "asset_display_name": label,
            "asset_type": "host_chassis_context_note",
            "linkage_role": "report_context",
            "documentation_note": "Documentation-only host / chassis context reference for project traceability.",
            "source_context_snapshot": {
                "host_context": host_context,
                "project_documentation_context": "Pathway Workspace linked catalog assets",
            },
            "review_status_snapshot": {
                "review_status": "human review needed",
            },
            "human_review_required": True,
        }
    )


def test_export_panel_renders_preview_labels_counts_and_download(monkeypatch) -> None:
    _use_temp_db(monkeypatch)
    _seed_construct_records()
    fake_st = _install_fake_streamlit(monkeypatch)

    export_package_section.render_export_package_section(
        {"id": "project-ui", "name": "UI Project", "target_product": "UI target"},
        [],
        [],
        [],
        {},
        [],
    )

    rendered = _rendered_text(fake_st)
    assert "Project Documentation Package" in rendered
    assert "Documentation-only JSON package preview for local review, traceability, manifest metadata review, and project record handoff." in rendered
    assert "Documentation package preview summary" in rendered
    assert "Documentation package JSON preview" in rendered
    assert "Package schema" in rendered
    assert "Project metadata fields" in rendered
    assert "Promoter source-link rows" in rendered
    assert "Manifest summary" in rendered
    assert "Package schema version: 2.6-r39" in rendered
    assert "Export scope: project_scoped" in rendered
    assert "Integrity summary" in rendered
    assert "Package ID:" in rendered
    assert "Project-level construct links: 1" in rendered
    assert "Construct profiles: 1" in rendered
    assert "Expression cassettes: 1" in rendered
    assert "Cassette parts: 1" in rendered
    assert "Linked genes: 1" in rendered
    assert "Linked pathway steps: 1" in rendered
    assert "Review gaps: 0" in rendered
    assert "Export Documentation Package (.json)" in [call["label"] for call in fake_st.download_button_calls]
    json_call = next(call for call in fake_st.download_button_calls if call["label"] == "Export Documentation Package (.json)")
    payload = json.loads(json_call["data"])
    assert payload["package_metadata"]["package_version"] == "2.6-r39"
    assert payload["manifest"]["package_schema_version"] == "2.6-r39"
    assert json_call["file_name"].endswith(".json")


def test_export_panel_renders_host_chassis_context_readback(monkeypatch) -> None:
    _use_temp_db(monkeypatch)
    fake_st = _install_fake_streamlit(monkeypatch)
    _seed_host_context_reference(host_context="E. coli documentation context")

    package_section.render_project_documentation_package_export_panel(
        {"id": "project-ui", "name": "UI Project", "host": "CHO cell line"}
    )

    rendered = _rendered_text(fake_st)
    assert "Host / chassis documentation context" in rendered
    assert "Read-only host / chassis context readback for documentation package review." in rendered
    assert "Schema boundary: this preview/readback is review context only." in rendered
    assert "It does not add a host / chassis summary field to the exported JSON package schema" in rendered
    assert "downstream package or import consumers should not assume such a field is present." in rendered
    assert "Active project context: Mammalian" in rendered
    assert "Supported chassis-neutral contexts: bacterial, yeast, mammalian, plant, generic / unspecified" in rendered
    assert "Contexts present in readback: Bacterial, Mammalian" in rendered
    assert "Plant and Nicotiana examples may appear as examples, not as default or preferred contexts." in rendered
    json_call = next(call for call in fake_st.download_button_calls if call["label"] == "Export Documentation Package (.json)")
    payload = json.loads(json_call["data"])
    assert "host_chassis_context_summary" not in payload
    assert set(payload.keys()) == {
        "manifest",
        "package_metadata",
        "project_metadata",
        "project_construct_links",
        "project_catalog_asset_links",
        "construct_profiles",
        "expression_cassettes",
        "cassette_parts",
        "linked_genes",
        "linked_pathway_steps",
        "review_gaps",
        "report_references",
        "documentation_only_boundary",
        "known_limitations",
        "integrity_summary",
    }
    assert "host_chassis" not in payload
    assert "host_chassis_context" not in payload


def test_import_panel_does_not_claim_host_chassis_context_exists_when_package_lacks_it(monkeypatch) -> None:
    _use_temp_db(monkeypatch)
    _seed_construct_records()
    fake_st = _install_fake_streamlit(monkeypatch)
    package = package_section.build_project_documentation_export_package(
        project={"id": "project-ui", "name": "UI Project", "host": "Nicotiana benthamiana"},
        project_id="project-ui",
        report_reference={"source_area": "test"},
    )
    fake_st.file_uploader_value = _UploadedText(json.dumps(package, ensure_ascii=False))

    package_section.render_project_documentation_package_import_panel()

    rendered = _rendered_text(fake_st)
    assert "Accepted package for documentation-only review." in rendered
    assert "host / chassis" not in rendered.lower()
    assert "package_schema_version: 2.6-r39" in rendered


def test_import_panel_can_review_existing_host_chassis_fields_when_present_in_package_content(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    package = {
        "manifest": {
            "package_format": "biodesign-studio-project-documentation-package",
            "package_schema_version": "2.6-r39",
            "exported_by_app": "BioDesign Studio",
            "documentation_boundary": "documentation-only local package review context",
            "record_counts": {},
        },
        "package_metadata": {
            "package_kind": "BioDesign Studio project documentation package",
            "package_version": "2.6-r39",
            "package_schema_version": "2.6-r39",
            "documentation_only_boundary": "documentation-only local package review context",
            "counts": {},
        },
        "project_metadata": {
            "project_id": "p-host",
            "project_name": "Host Context Package",
            "host": "Example host field retained in existing package content",
        },
        "project_construct_links": [],
        "project_catalog_asset_links": [],
        "construct_profiles": [],
        "expression_cassettes": [],
        "cassette_parts": [],
        "linked_genes": [],
        "linked_pathway_steps": [],
        "review_gaps": [],
        "report_references": {},
        "documentation_only_boundary": "documentation-only local package review context",
        "known_limitations": [],
        "integrity_summary": {},
    }
    fake_st.file_uploader_value = _UploadedText(json.dumps(package, ensure_ascii=False))

    package_section.render_project_documentation_package_import_panel()

    rendered = _rendered_text(fake_st)
    assert "Accepted package for documentation-only review." in rendered
    assert "project_name: Host Context Package" in rendered
    assert "host / chassis" not in rendered.lower()


def test_export_panel_host_context_unknown_host_falls_back_to_generic_unspecified(monkeypatch) -> None:
    _use_temp_db(monkeypatch)
    fake_st = _install_fake_streamlit(monkeypatch)
    _seed_host_context_reference(host_context="custom unknown token")

    package_section.render_project_documentation_package_export_panel(
        {"id": "project-ui", "name": "UI Project", "host": "amazing custom context token"}
    )

    rendered = _rendered_text(fake_st)
    assert "Active project context: Generic / unspecified" in rendered
    assert "Contexts present in readback: Generic / unspecified" in rendered


def test_export_panel_treats_plant_as_supported_context_not_default(monkeypatch) -> None:
    _use_temp_db(monkeypatch)
    fake_st = _install_fake_streamlit(monkeypatch)
    _seed_host_context_reference(host_context="Nicotiana benthamiana documentation context")

    package_section.render_project_documentation_package_export_panel(
        {"id": "project-ui", "name": "UI Project"}
    )

    rendered = _rendered_text(fake_st)
    assert "Active project context: Generic / unspecified" in rendered
    assert "Contexts present in readback: Plant, Generic / unspecified" in rendered
    assert "Plant and Nicotiana examples may appear as examples, not as default or preferred contexts." in rendered


def test_export_panel_summarizes_persisted_catalog_references(monkeypatch) -> None:
    _use_temp_db(monkeypatch)
    fake_st = _install_fake_streamlit(monkeypatch)
    _seed_catalog_reference()

    package_section.render_project_documentation_package_export_panel(
        {"id": "project-ui", "name": "UI Project"}
    )

    rendered = _rendered_text(fake_st)
    assert "Linked catalog references" in rendered
    assert "Linked Component Library promoter asset references" in rendered
    assert "1 catalog references; 1 Component Library promoter asset references; 2 missing source/review metadata fields." in rendered
    assert "Linked catalog reference metadata review gaps remain visible in this package summary." in rendered
    assert "Review linked catalog references and record missing source or review metadata when needed." in rendered
    assert "Project documentation contexts:" in rendered
    assert "Expression Wizard catalog traceability: 0 documentation-level reference(s); 0 Component Library promoter asset reference(s); 0 missing metadata field(s)." in rendered
    json_call = next(call for call in fake_st.download_button_calls if call["label"] == "Export Documentation Package (.json)")
    payload = json.loads(json_call["data"])
    assert payload["report_references"]["linked_catalog_asset_count"] == 1
    assert payload["report_references"]["linked_plant_promoter_count"] == 1
    assert payload["package_metadata"]["counts"]["project_catalog_asset_link_count"] == 1
    assert payload["package_metadata"]["counts"]["expression_wizard_catalog_reference_count"] == 0
    assert payload["project_catalog_asset_links"][0]["asset_id"] == "plant-promoter-ui"


def test_export_panel_handles_empty_states(monkeypatch) -> None:
    _use_temp_db(monkeypatch)
    fake_st = _install_fake_streamlit(monkeypatch)

    package_section.render_project_documentation_package_export_panel({"id": "empty-project", "name": "Empty"})

    rendered = _rendered_text(fake_st)
    assert "No construct profiles are included yet" in rendered
    assert "No project-level construct links are recorded in this package preview." in rendered
    assert "No expression cassettes are included in this package preview." in rendered
    assert "No cassette parts are included in this package preview." in rendered
    assert "No promoter source-link rows are included in this package preview." in rendered
    assert "No project catalog reference links are included in this package preview yet." in rendered
    assert "No linked genes are included in this package preview." in rendered
    assert "No linked pathway steps are included in this package preview." in rendered


def test_import_panel_renders_empty_state_when_no_input_is_provided(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)

    package_section.render_project_documentation_package_import_panel()

    rendered = _rendered_text(fake_st)
    assert "Documentation Package Check" in rendered
    assert "Upload Documentation Package (.json)" in rendered
    assert "Or paste Documentation Package JSON" in rendered
    assert "Upload a documentation package JSON file or paste package JSON text to review structure." in rendered


def test_import_panel_reports_invalid_json(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    fake_st.text_area_values["project_documentation_package_paste_json"] = "{bad json"

    package_section.render_project_documentation_package_import_panel()

    rendered = _rendered_text(fake_st)
    assert "Documentation package JSON could not be parsed." in rendered
    assert "JSON parser detail:" in rendered


def test_import_panel_reports_valid_package_summary(monkeypatch) -> None:
    _use_temp_db(monkeypatch)
    _seed_construct_records()
    _seed_catalog_reference()
    fake_st = _install_fake_streamlit(monkeypatch)
    valid_package = package_section.build_project_documentation_export_package(
        project={"id": "project-ui", "name": "UI Project"},
        project_id="project-ui",
        report_reference={"source_area": "test"},
    )
    fake_st.file_uploader_value = _UploadedText(json.dumps(valid_package, ensure_ascii=False))

    package_section.render_project_documentation_package_import_panel()

    rendered = _rendered_text(fake_st)
    assert "Accepted package for documentation-only review." in rendered
    assert "package_version: 2.6-r39" in rendered
    assert "package_schema_version: 2.6-r39" in rendered
    assert "project_name: UI Project" in rendered
    assert "Promoter source-link rows: 1" in rendered
    assert "Project catalog reference links: 1" in rendered
    assert "Linked Component Library promoter asset references: 1" in rendered
    assert "Catalog references missing source/review metadata: 2" in rendered
    assert "Import Manifest Review" in rendered
    assert "Package format: biodesign-studio-project-documentation-package" in rendered
    assert "Package schema version: 2.6-r39" in rendered
    assert "Exported by app: BioDesign Studio" in rendered
    assert "Included sections: project_metadata" in rendered
    assert "Manifest record counts" in rendered
    assert "construct_profile_count: 1" in rendered
    assert "Compatibility notes" in rendered
    assert "Documentation boundary" in rendered
    assert "Limitations" in rendered
    assert "Manifest review notes: none reported." in rendered
    assert "Dry-run import summary" in rendered
    assert "No structural errors were reported by the package checker." in rendered
    assert "Package shape review" in rendered
    assert "Conflict preview" in rendered
    assert "Constructs that would be created: 1" in rendered
    assert "Project catalog reference links that would be created: 1" in rendered
    assert "Linked catalog reference import review" in rendered
    assert "Total linked catalog reference rows in package: 1" in rendered
    assert "Rows with complete documentation context: 1" in rendered
    assert "Rows using safe fallback labels: 0" in rendered
    assert "Rows with live metadata fallback / missing snapshot state: 1" in rendered
    assert "Rows with missing record identifier or source/status: 0" in rendered
    assert "Create-as-new import stays unavailable until this confirmation is explicit." in rendered


def test_import_panel_reports_structural_errors_and_unknown_fields(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    package = {
        "package_metadata": {
            "package_kind": "BioDesign Studio project documentation package",
            "package_version": "2.6-r28",
            "documentation_only_boundary": "documentation-only",
            "unexpected_package_field": "future",
        },
        "manifest": {
            "package_schema_version": "2.6-r28",
            "package_format": "biodesign-studio-project-documentation-package",
            "documentation_boundary": "documentation-only",
            "unexpected_manifest_field": "future",
        },
        "project_metadata": {"project_id": "p-1", "extra_project_field": "future"},
        "construct_profiles": [{"construct_label": "Only label", "unexpected_row_field": "future"}],
        "expression_cassettes": [],
        "cassette_parts": [],
        "linked_genes": [],
        "linked_pathway_steps": [],
        "project_construct_links": [],
        "review_gaps": [],
        "documentation_only_boundary": "documentation-only local package",
    }
    fake_st.text_area_values["project_documentation_package_paste_json"] = json.dumps(package, ensure_ascii=False)

    package_section.render_project_documentation_package_import_panel()

    rendered = _rendered_text(fake_st)
    assert "Accepted package for documentation-only review." in rendered
    assert "Unknown extra fields" in rendered
    assert "manifest.unexpected_manifest_field" in rendered
    assert "package_metadata.unexpected_package_field" in rendered
    assert "project_metadata.extra_project_field" in rendered
    assert "construct_profiles[0].unexpected_row_field" in rendered


def test_import_panel_reports_older_package_manifest_empty_state(monkeypatch) -> None:
    _use_temp_db(monkeypatch)
    _seed_construct_records()
    fake_st = _install_fake_streamlit(monkeypatch)
    legacy_package = package_section.build_project_documentation_export_package(
        project={"id": "project-ui", "name": "UI Project"},
        project_id="project-ui",
        report_reference={"source_area": "test"},
    )
    legacy_package.pop("manifest", None)
    legacy_package["package_metadata"]["package_version"] = "2.6-r24"
    legacy_package["package_metadata"].pop("package_schema_version", None)
    fake_st.file_uploader_value = _UploadedText(json.dumps(legacy_package, ensure_ascii=False))

    package_section.render_project_documentation_package_import_panel()

    rendered = _rendered_text(fake_st)
    assert "Accepted package for documentation-only review." in rendered
    assert "Import Manifest Review" in rendered
    assert "Older package format: package manifest metadata was not provided." in rendered
    assert "Package format: Not available" in rendered
    assert "Exported by app: Not available" in rendered
    assert "Compatibility notes: Not available" in rendered
    assert "Manifest review notes: needs review" in rendered


def test_import_panel_reports_linked_catalog_reference_fallback_states(monkeypatch) -> None:
    _use_temp_db(monkeypatch)
    _seed_construct_records()
    _seed_catalog_reference()
    fake_st = _install_fake_streamlit(monkeypatch)
    package = package_section.build_project_documentation_export_package(
        project={"id": "project-ui", "name": "UI Project"},
        project_id="project-ui",
        report_reference={"source_area": "test"},
    )
    row = package["project_catalog_asset_links"][0]
    row.pop("compact_metadata", None)
    row["asset_snapshot"] = {}
    row["source_label"] = "Source status not recorded"
    row["documentation_status"] = "Not recorded"
    row["project_documentation_context"] = "Documentation context not provided"
    fake_st.file_uploader_value = _UploadedText(json.dumps(package, ensure_ascii=False))

    package_section.render_project_documentation_package_import_panel()

    rendered = _rendered_text(fake_st)
    assert "Linked catalog reference import review" in rendered
    assert "Total linked catalog reference rows in package: 1" in rendered
    assert "Rows with complete documentation context: 0" in rendered
    assert "Rows using safe fallback labels: 1" in rendered
    assert "Rows with live metadata fallback / missing snapshot state: 1" in rendered
    assert "Rows with missing record identifier or source/status: 1" in rendered
    assert "legacy package fallback" in rendered.lower()
    assert "source status not recorded" in rendered.lower()
    assert "documentation context not provided" in rendered.lower()


def test_import_panel_reports_partial_manifest_review_notes(monkeypatch) -> None:
    _use_temp_db(monkeypatch)
    _seed_construct_records()
    fake_st = _install_fake_streamlit(monkeypatch)
    package = package_section.build_project_documentation_export_package(
        project={"id": "project-ui", "name": "UI Project"},
        project_id="project-ui",
        report_reference={"source_area": "test"},
    )
    package["manifest"] = {
        "package_schema_version": "2.6-r28",
        "documentation_boundary": package["documentation_only_boundary"],
        "record_counts": "needs review",
    }
    fake_st.file_uploader_value = _UploadedText(json.dumps(package, ensure_ascii=False))

    package_section.render_project_documentation_package_import_panel()

    rendered = _rendered_text(fake_st)
    assert "Accepted package for documentation-only review." in rendered
    assert "Package format not provided in manifest metadata." in rendered
    assert "Exported by app not provided in manifest metadata." in rendered
    assert "Export scope not provided in manifest metadata." in rendered
    assert "Manifest record counts need review because record_counts is not an object." in rendered


def test_package_section_copy_mentions_review_chain_and_trail(monkeypatch) -> None:
    _use_temp_db(monkeypatch)
    _seed_construct_records()
    fake_st = _install_fake_streamlit(monkeypatch)

    package_section.render_project_documentation_package_export_panel(
        {"id": "project-ui", "name": "UI Project", "target_product": "UI target"}
    )

    source = open(package_section.__file__, encoding="utf-8").read()
    rendered = _rendered_text(fake_st) + "\n" + source
    assert "Exchange trail: exported packages include manifest metadata" in rendered
    assert "Package workflow: create or review project documentation" in rendered
    assert "export a documentation package with manifest metadata" in rendered
    assert "review it in Import Manifest Review" in rendered
    assert "create a new project copy only after explicit confirmation" in rendered
    assert "Package Exchange Review Trail in the Project Review Report and Project Quality Dashboard" in rendered
    assert "Manifest review fields support package exchange review trail context in reports and quality review." in rendered
    assert "Review chain: exported packages include a manifest; imported packages show Import Manifest Review" in rendered
    assert "keep the package in read-only documentation context" in rendered
    assert "manifest metadata review" in rendered
    assert "create a new project copy only through explicit confirmation" in rendered
    assert "older or partial packages may show limited metadata and review notes" in rendered.lower()


def test_import_panel_shows_conflict_preview_and_confirmation_language(monkeypatch) -> None:
    _use_temp_db(monkeypatch)
    _seed_construct_records()
    fake_st = _install_fake_streamlit(monkeypatch)
    valid_package = package_section.build_project_documentation_export_package(
        project={"id": "project-ui", "name": "UI Project"},
        project_id="project-ui",
        report_reference={"source_area": "test"},
    )
    fake_st.file_uploader_value = _UploadedText(json.dumps(valid_package, ensure_ascii=False))

    package_section.render_project_documentation_package_import_panel()

    rendered = _rendered_text(fake_st)
    assert "Possible conflicts were detected. Review them before any create-as-new action." in rendered
    assert "construct_label_exists" in rendered
    assert "project_construct_link_exists" in rendered
    assert any(call["label"] == "I confirm that create-as-new should add new local documentation rows only and must not overwrite or merge existing rows." for call in fake_st.checkbox_calls)
    assert "Create-as-new import is unavailable until the explicit confirmation control is checked." in rendered


def test_import_panel_can_create_as_new_after_confirmation(monkeypatch) -> None:
    _use_temp_db(monkeypatch)
    fake_st = _install_fake_streamlit(monkeypatch)
    seed_db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r82_project_documentation_package_dbs",
        "project_documentation_package_seed.db",
    )
    monkeypatch.setattr(repo, "DB_PATH", str(seed_db_path))
    _seed_construct_records()
    valid_package = package_section.build_project_documentation_export_package(
        project={"id": "project-ui", "name": "UI Project"},
        project_id="project-ui",
        report_reference={"source_area": "test"},
    )
    target_db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_r82_project_documentation_package_dbs",
        "project_documentation_package_import_target.db",
    )
    monkeypatch.setattr(repo, "DB_PATH", str(target_db_path))
    fake_st.file_uploader_value = _UploadedText(json.dumps(valid_package, ensure_ascii=False))
    fake_st.checkbox_values["project_documentation_package_confirm_create_as_new"] = True
    fake_st.button_values["project_documentation_package_create_as_new"] = True

    package_section.render_project_documentation_package_import_panel()

    rendered = _rendered_text(fake_st)
    assert any(call["label"] == "Create As New Documentation Records" for call in fake_st.button_calls)
    assert "Documentation project records were created as new local rows." in rendered
    assert "construct_profiles: 1" in rendered
    assert "project_construct_links: 1" in rendered
    assert "project_catalog_asset_links: 0" in rendered


def test_import_preview_section_includes_documentation_package_check(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)

    import_preview_section.render_import_preview_section()

    rendered = _rendered_text(fake_st)
    assert "Documentation Package Check" in rendered
    assert "Review a JSON documentation package before any create-as-new workflow." in rendered
    assert "Overwrite, merge, delete, restore, CSV or Excel import, external source imports, and complex sequence parsing remain deferred." in rendered


def test_ui_copy_avoids_destructive_or_unsafe_claims(monkeypatch) -> None:
    _use_temp_db(monkeypatch)
    _seed_construct_records()
    _seed_host_context_reference()
    fake_st = _install_fake_streamlit(monkeypatch)
    export_package_section.render_export_package_section(
        {"id": "project-ui", "name": "UI Project", "target_product": "UI target"},
        [],
        [],
        [],
        {},
        [],
    )
    package_section.render_project_documentation_package_import_panel()

    combined = _rendered_text(fake_st).lower()
    forbidden = [
        "successful import",
        "project imported",
        "ready for execution",
        "experiment-ready",
        "production-ready",
        "validated construct",
        "optimized pathway",
        "yield prediction",
        "destructive overwrite",
        "host recommendation",
        "host compatibility proof",
        "synthesis ready",
        "wet-lab ready",
    ]
    assert [text for text in forbidden if text in combined] == []

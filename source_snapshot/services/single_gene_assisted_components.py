"""Single-Gene adapters for the shared, project-bound V2 assisted contract.

Host scope means supported project input, never biological host admission.
No sequence resolution, evidence acquisition or canonical assembly is implemented here.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from services.component_library_v2_adoption import v2_canonical_record
from services.formal_step3_component_authority import formal_host_species_identity
from services.plant_component_workflow_registry import validate_saved_selection
from services.plant_host_registry import SINGLE_GENE_COMPLETE_VECTOR, hosts_for_workflow

ROLE_MAP = {"promoter": "promoter", "five_prime_utr": "five_prime_utr"}
SELECTION_ROLES = {"promoter": "promoter", "five_prime_utr": "five_prime_region"}


def _require_single_gene_project(repository: Any, project_id: str) -> None:
    from services.plant_project_draft_repository import require_active_project

    if repository is None:
        raise ValueError("Single-Gene assisted input requires an active persisted project.")
    draft = repository.load(project_id)
    require_active_project(draft)
    if draft.workflow_type != "single_gene":
        raise ValueError("Assisted input requires a persisted Single-Gene project.")


def single_gene_assisted_role(component_id: str, *, host: str) -> str:
    row = v2_canonical_record(component_id)
    species = formal_host_species_identity(host)
    if species not in {r["scientific_name"] for r in hosts_for_workflow(SINGLE_GENE_COMPLETE_VECTOR)}:
        raise ValueError("Unsupported Single-Gene project host.")
    role = ROLE_MAP.get(row.get("component_type"))
    if row.get("library_tier") != "CORE" or row.get("admission_mode") != "USER_SEQUENCE_ASSISTED" or not role:
        raise ValueError("This identity is not eligible for Single-Gene Step3 assisted input.")
    return role


def validate_single_gene_assisted_reference(
    reference: Mapping[str, Any], *, sequence: str, role: str,
    project_id: str, host: str, repository: Any = None,
) -> dict[str, Any]:
    ref = dict(reference)
    resolution = dict(ref.get("assisted_resolution") or {})
    actual_role = single_gene_assisted_role(str(resolution.get("catalog_component_id") or ""), host=host)
    if actual_role != role or ref.get("source_type") != "USER_PROVIDED":
        raise ValueError("Assisted identity does not match the Single-Gene Step3 role.")
    return validate_saved_selection(
        ref, role=SELECTION_ROLES[role], sequence=sequence,
        current_project_id=project_id, project_repository=repository,
    )


def single_gene_assisted_input(
    component: Mapping[str, Any], *, project_id: str, host: str, repository: Any,
) -> dict[str, Any]:
    """Translate an already-resolved shared selection to the existing input shape."""
    from services.mvp_sequence_input import analyze_dna_component_input

    reference = dict(component.get("component_reference") or {})
    resolution = dict(reference.get("assisted_resolution") or {})
    role = single_gene_assisted_role(str(resolution.get("catalog_component_id") or ""), host=host)
    if repository is None or component.get("role") != SELECTION_ROLES[role]:
        raise ValueError("Single-Gene assisted input requires its original role and persisted project.")
    _require_single_gene_project(repository, project_id)
    sequence = str(component.get("raw_text") or "")
    reference = validate_single_gene_assisted_reference(
        reference, sequence=sequence, role=role, project_id=project_id, host=host, repository=repository,
    )
    record = analyze_dna_component_input(
        sequence, project_id=project_id, component_type=role,
        display_name=str(component.get("display_name") or ""),
        source_kind="user_recorded", source_name=str(resolution["user_sequence_source"]),
    )
    record.update(
        project_id=project_id,
        biological_role=role, source_input_method="paste",
        source_reference=resolution["user_sequence_source"],
        component_reference=reference, assisted_project_host=formal_host_species_identity(host),
    )
    return record


def retained_assisted_fields(record: Mapping[str, Any], *, sequence: str, role: str, project_id: str, host: str) -> dict[str, Any]:
    reference = record.get("component_reference") or {}
    if not reference.get("assisted_resolution"):
        return {}
    if formal_host_species_identity(host) != record.get("assisted_project_host"):
        raise ValueError("Assisted input host changed; return to the Component Library to confirm it again.")
    validated = validate_single_gene_assisted_reference(
        reference, sequence=sequence, role=role, project_id=project_id, host=host,
    )
    return {"component_reference": validated, "assisted_project_host": record["assisted_project_host"]}


def validate_single_gene_assisted_runtime(runtime: Mapping[str, Any], *, repository: Any = None) -> dict[str, dict[str, Any]]:
    """Revalidate each reference against its canonical asset, role and project."""
    assets = {a["asset_id"]: a for a in runtime.get("sequence_assets") or []}
    references = {}
    for component in runtime.get("components") or []:
        reference = component.get("component_reference") or {}
        if not reference.get("assisted_resolution"):
            continue
        if repository is not None:
            _require_single_gene_project(repository, str(runtime.get("project_id") or ""))
        asset = assets.get(component.get("sequence_asset_id"), {})
        references[component["component_id"]] = validate_single_gene_assisted_reference(
            reference, sequence=str(asset.get("nucleotide_sequence") or ""),
            role=str(component.get("biological_role") or ""),
            project_id=str(runtime.get("project_id") or ""),
            host=str(component.get("assisted_project_host") or ""), repository=repository,
        )
        resolution = references[component["component_id"]]["assisted_resolution"]
        if (
            component.get("project_id") != runtime.get("project_id")
            or asset.get("project_id") != runtime.get("project_id")
            or component.get("provenance_reference") != resolution["user_sequence_source"]
            or asset.get("provenance_reference") != resolution["user_sequence_source"]
            or component.get("source_kind") != asset.get("source_type")
            or component.get("source_file") != asset.get("source_name")
        ):
            raise ValueError("Single-Gene assisted canonical provenance binding does not match its resolution.")
    return references


def single_gene_assisted_export_features(runtime: Mapping[str, Any], features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach shared qualifiers by canonical ID; leave DNA/coordinates unchanged."""
    from services.plant_component_workflow_registry import selection_qualifiers

    if runtime.get("expression_units"):
        return features
    references = validate_single_gene_assisted_runtime(runtime)
    if not references:
        return features
    projected = deepcopy(features)
    for feature in projected:
        if reference := references.get(feature.get("component_id")):
            qualifiers = selection_qualifiers(reference)
            qualifiers.pop("component_id", None)  # retain the canonical feature identity
            feature["qualifiers"] = {**feature.get("qualifiers", {}), **qualifiers}
    return projected


def _validate_assisted_snapshot(
    snapshot: Mapping[str, Any], *, role: str, sequence_field: str,
    runtime: Mapping[str, Any], references: Mapping[str, dict[str, Any]],
) -> None:
    """Compare editable projections to the already validated canonical selection."""
    candidates = [c for c in runtime.get("components") or []
                  if c.get("biological_role") == role and c.get("component_id") in references]
    reference = snapshot.get("component_reference") or {}
    if not candidates and not reference.get("assisted_resolution"):
        return
    if len(candidates) != 1 or reference != references[candidates[0]["component_id"]]:
        raise ValueError("Single-Gene assisted input traceability differs from the canonical runtime.")
    component = candidates[0]
    # validate_saved_selection has already bound this complete reference (including
    # its resolution, identity, flags and sequence) to the canonical asset/project.
    expected = {
        "assisted_project_host": component["assisted_project_host"],
        "source_reference": reference["assisted_resolution"]["user_sequence_source"],
        "source_kind": component["source_kind"],
        sequence_field: reference["selected_sequence"],
    }
    if sequence_field == "normalized_sequence":
        expected.update(project_id=runtime["project_id"], role=role,
                        source_name=reference["assisted_resolution"]["user_sequence_source"],
                        source_kind="user_recorded")
    else:
        expected.update(biological_role=role, source_file=component["source_file"])
    for field, value in (("project_id", runtime["project_id"]), ("biological_role", role)):
        if field in snapshot:
            expected[field] = value
    for field, value in (("normalized_sequence", reference["selected_sequence"]),
                         ("length", reference["selected_length"]),
                         ("component_type", component["component_type"])):
        if field in snapshot:
            expected[field] = value
    for field, value in expected.items():
        if snapshot.get(field) != value:
            raise ValueError(f"Single-Gene assisted {field} binding differs from the canonical resolution.")


def _validate_assisted_runtime_copy(
    snapshot: Mapping[str, Any], *, runtime: Mapping[str, Any],
    references: Mapping[str, dict[str, Any]],
) -> None:
    """Bind restored cassette runtime copies without rebuilding canonical DNA."""
    if not snapshot:
        return
    copied = {c["component_id"]: c for c in snapshot.get("components") or []}
    copied_refs = {key: c.get("component_reference") for key, c in copied.items()
                   if (c.get("component_reference") or {}).get("assisted_resolution")}
    if copied_refs != references:
        raise ValueError("Single-Gene assisted runtime copy traceability differs from the canonical runtime.")
    assets = {a["asset_id"]: a for a in runtime.get("sequence_assets") or []}
    copied_assets = {a["asset_id"]: a for a in snapshot.get("sequence_assets") or []}
    for component in runtime.get("components") or []:
        if component.get("component_id") not in references:
            continue
        actual = copied[component["component_id"]]
        fields = ("project_id", "biological_role", "component_type", "sequence_asset_id",
                  "assisted_project_host", "provenance_reference", "source_kind", "source_file")
        asset = assets[component["sequence_asset_id"]]
        copied_asset = copied_assets.get(component["sequence_asset_id"], {})
        asset_fields = ("project_id", "nucleotide_sequence", "source_type",
                        "source_name", "provenance_reference")
        if (snapshot.get("project_id") != runtime.get("project_id")
            or any(actual.get(key) != component.get(key) for key in fields)
            or any(copied_asset.get(key) != asset.get(key) for key in asset_fields)):
            raise ValueError("Single-Gene assisted runtime copy binding differs from the canonical runtime.")


def validate_single_gene_assisted_result(result: Mapping[str, Any], *, repository: Any) -> None:
    """Refuse contradictory saved provenance; never regenerate files at save time."""
    from io import StringIO
    from Bio import SeqIO
    from services.plant_component_workflow_registry import selection_qualifiers

    runtime = result.get("runtime") or {}
    references = validate_single_gene_assisted_runtime(runtime, repository=repository)
    context = result.get("formal_project_context") or {}
    state = context.get("formal_state") or {}
    input_groups = [result.get("input_records") or {},
                    state.get("formal_element_source_records") or {},
                    (state.get("formal_cassette_result") or {}).get("input_records") or {}]
    for inputs in input_groups:
        for role, snapshot in inputs.items():
            _validate_assisted_snapshot(
                snapshot, role="five_prime_utr" if role == "five_prime" else role,
                sequence_field=("sequence" if role == "five_prime" and "sequence" in snapshot
                                else "normalized_sequence"),
                runtime=runtime, references=references,
            )
    cassettes = [result.get("formal_expression_cassette") or {},
                 state.get("formal_expression_cassette") or {}]
    for cassette in cassettes:
        for snapshot in cassette.get("components") or []:
            _validate_assisted_snapshot(
                snapshot, role=str(snapshot.get("biological_role") or ""),
                sequence_field="sequence", runtime=runtime, references=references,
            )
    runtime_copies = [(state.get("formal_cassette_result") or {}).get("runtime") or {}]
    for cassette in cassettes:
        runtime_copies.extend([cassette.get("runtime") or {},
                               (cassette.get("cassette") or {}).get("runtime") or {}])
    for snapshot in runtime_copies:
        _validate_assisted_runtime_copy(snapshot, runtime=runtime, references=references)
    if not references:
        return
    if runtime.get("project_id") != result.get("project_id"):
        raise ValueError("Single-Gene assisted project binding differs from the saved result.")
    project_hosts = [context.get("host_key"),
                     (context.get("project_definition") or {}).get("plant_host"),
                     (state.get("formal_project_definition") or {}).get("plant_host")]
    for component in runtime.get("components") or []:
        reference = references.get(component.get("component_id"))
        if not reference:
            continue
        if any(host and formal_host_species_identity(host) != component.get("assisted_project_host")
               for host in project_hosts):
            raise ValueError("Single-Gene assisted project host differs from the saved binding.")
        role = component["biological_role"]
        snapshots = [c for c in (result.get("formal_expression_cassette") or {}).get("components", []) if c.get("biological_role") == role]
        if len(snapshots) != 1 or snapshots[0].get("component_reference") != reference:
            raise ValueError("Single-Gene assisted cassette traceability does not match.")
        if role == "promoter" and ((result.get("input_records") or {}).get("promoter") or {}).get("component_reference") != reference:
            raise ValueError("Single-Gene assisted promoter input traceability does not match.")
    record = SeqIO.read(StringIO(result["exports"]["genbank"]["data"]), "genbank")
    for reference in references.values():
        expected = selection_qualifiers(reference)
        features = [f for f in record.features if f.qualifiers.get("catalog_component_id") == expected["catalog_component_id"]]
        if len(features) != 1 or any(features[0].qualifiers.get(k) != v for k, v in expected.items() if k != "component_id"):
            raise ValueError("Single-Gene assisted GenBank component traceability does not match.")

"""components/export_manager.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Sequence export utility for BioDesign Studio.

Public API
----------
generate_fasta_string(sequence, project_name) -> str
    Convert a raw DNA sequence into a FASTA-formatted string.

generate_genbank_string(sequence, features, project_name) -> str
    Convert a raw DNA sequence and its feature annotations into a
    GenBank-formatted string using Biopython.

build_export_payloads(sequence, features, project_name) -> dict
    Build normalized FASTA and GenBank export payloads with file names,
    MIME types, and serialized content.

build_design_session_export_payload(ds) -> dict
    Build the unified Step 6 export payload from the current DesignSession.

render_export_buttons()
    Streamlit UI component: reads the active DesignSession and renders
    legacy FASTA and GenBank download buttons from the unified payload.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import io
from typing import Any

import streamlit as st

from core.session_keys import SK


_EXACT_GENBANK_QUALIFIERS = frozenset({
    'sequence_sha256', 'user_sequence_sha256', 'feature_sha256', 'source_record_sha256',
    'resolution_id', 'source_asset_id', 'component_id', 'unit_id', 'project_id',
    'catalog_component_id', 'catalog_name', 'accession_version', 'source_accession',
    'user_sequence_source', 'reviewed_source_boundary',
})


def write_genbank_record(record: Any, handle: Any) -> None:
    """Serialize exact provenance tokens without splitting their values.

    GenBank parsers join continued quoted qualifiers with spaces. For these
    identifiers/digests/source labels, permit a long physical qualifier line
    instead. All other wrapping and escaping remains Biopython's behavior.
    The width override is instance-local and restored after each qualifier.
    """
    from Bio.SeqIO.InsdcIO import GenBankWriter

    class ExactProvenanceWriter(GenBankWriter):
        def _write_feature_qualifier(self, key, value=None, quote=None):
            width = self.MAX_WIDTH
            if key in _EXACT_GENBANK_QUALIFIERS and value is not None:
                self.MAX_WIDTH = max(width, self.QUALIFIER_INDENT + len(key) + 2 * len(str(value)) + 8)
            try:
                super()._write_feature_qualifier(key, value, quote)
            finally:
                self.MAX_WIDTH = width

    ExactProvenanceWriter(handle).write_file([record])


def generate_fasta_string(sequence: str, project_name: str) -> str:
    """Build a FASTA-formatted string from a DNA sequence."""
    sequence = sequence.strip().upper()
    if not sequence:
        raise ValueError("Cannot export an empty sequence.")

    safe_name = (project_name or "Untitled_Construct").strip().replace(" ", "_") or "Untitled_Construct"
    wrapped = [sequence[idx: idx + 80] for idx in range(0, len(sequence), 80)]
    return f">{safe_name}\n" + "\n".join(wrapped) + "\n"


def generate_genbank_string(
    sequence: str,
    features: list[dict[str, Any]],
    project_name: str,
    topology: str | None = None,
) -> str:
    """
    Build a GenBank-formatted string from a DNA sequence and its
    feature annotations.
    """
    from Bio.Seq import Seq
    from Bio.SeqFeature import CompoundLocation, SeqFeature, SimpleLocation
    from Bio.SeqRecord import SeqRecord

    sequence = sequence.strip().upper()
    if not sequence:
        raise ValueError("Cannot export an empty sequence.")

    safe_name = (project_name or "Untitled_Construct")[:16].replace(" ", "_")
    safe_id = (project_name or "Untitled_Construct").replace(" ", "_")

    record = SeqRecord(
        Seq(sequence),
        id=safe_id,
        name=safe_name,
        description=f"Exported from BioDesign Studio — {project_name}",
    )
    record.annotations["molecule_type"] = "DNA"
    if str(topology or "").strip().lower() in {"linear", "circular"}:
        record.annotations["topology"] = str(topology).strip().lower()

    bio_features: list[SeqFeature] = []
    for feat in (features or []):
        try:
            feat_type = str(feat.get("type", "misc_feature")) or "misc_feature"
            feat_name = str(feat.get("name", "unnamed"))
            raw_start = int(feat.get("start", 1))
            raw_end = int(feat.get("end", raw_start))
            bp_start = max(0, raw_start - 1)
            bp_end = min(len(sequence), raw_end)

            raw_location_parts = list(feat.get("location_parts") or [])
            if raw_location_parts:
                location_parts = [
                    SimpleLocation(
                        max(0, int(part.get("start", 1)) - 1),
                        min(len(sequence), int(part.get("end", part.get("start", 1)))),
                        strand=int(part.get("strand", feat.get("strand", 1)) or 1),
                    )
                    for part in raw_location_parts
                ]
                location = CompoundLocation(
                    location_parts,
                    operator=str(feat.get("location_operator") or "join"),
                )
            else:
                location = SimpleLocation(bp_start, bp_end, strand=int(feat.get("strand", 1) or 1))
            qualifiers = {"label": [feat_name]}
            raw_qualifiers = feat.get("qualifiers") if isinstance(feat.get("qualifiers"), dict) else {}
            for key, val in raw_qualifiers.items():
                if key and val is not None:
                    if isinstance(val, list):
                        qualifiers[str(key)] = [str(item) for item in val]
                    else:
                        qualifiers[str(key)] = [str(val)]

            for key, val in feat.items():
                if key not in (
                    "type",
                    "name",
                    "start",
                    "end",
                    "qualifiers",
                    "location_parts",
                    "location_operator",
                ) and val is not None:
                    qualifiers[key] = [str(val)]

            bio_features.append(
                SeqFeature(location=location, type=feat_type, qualifiers=qualifiers)
            )
        except Exception as feat_exc:
            import logging as _logging

            _logging.getLogger(__name__).warning(
                "Skipping malformed feature %r: %s", feat, feat_exc
            )
            continue

    record.features = bio_features

    buffer = io.StringIO()
    write_genbank_record(record, buffer)
    return buffer.getvalue()


def _resolve_sequence_from_design_session(ds) -> str:
    frame = ds.frame if isinstance(ds.frame, dict) else {}
    return str(frame.get("final_sequence") or ds.optimized_seq or ds.original_seq or "").strip().upper()


def _normalize_frame_feature(
    feature: dict[str, Any],
    sequence_length: int,
) -> dict[str, Any] | None:
    """Normalize mixed internal feature shapes into 1-based inclusive export features."""
    try:
        raw_start = int(feature.get("start", feature.get("Start", 0)))
        raw_end = int(feature.get("end", feature.get("End", raw_start)))
    except Exception:
        return None

    if raw_start <= 0:
        start = max(1, raw_start + 1)
        end = max(start, min(sequence_length, raw_end))
    else:
        start = max(1, raw_start)
        end = max(start, min(sequence_length, raw_end))

    return {
        "name": str(feature.get("name") or feature.get("label") or feature.get("Name") or "Feature"),
        "label": str(feature.get("label") or feature.get("name") or feature.get("Name") or "Feature"),
        "type": str(feature.get("type") or feature.get("Type") or "misc_feature"),
        "start": start,
        "end": end,
        "strand": int(feature.get("strand", 1) or 1),
    }


def _build_features_from_parts(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build 1-based inclusive export features from frame parts."""
    features: list[dict[str, Any]] = []
    cursor = 1
    for part in (parts or []):
        seq = str(part.get("seq") or "")
        if not seq:
            continue
        end = cursor + len(seq) - 1
        name = str(part.get("name") or "Part")
        features.append(
            {
                "name": name,
                "label": name,
                "type": str(part.get("type") or "misc_feature"),
                "start": cursor,
                "end": end,
                "strand": int(part.get("strand", 1) or 1),
            }
        )
        cursor = end + 1
    return features


def _build_design_session_features(ds, sequence: str) -> list[dict[str, Any]]:
    """Resolve the canonical export features from the current DesignSession only."""
    if not sequence:
        return []

    frame = ds.frame if isinstance(ds.frame, dict) else {}
    frame_parts = frame.get("parts") if isinstance(frame.get("parts"), list) else []
    frame_features = frame.get("features") if isinstance(frame.get("features"), list) else []

    if frame_parts:
        return _build_features_from_parts(frame_parts)

    normalized_features = [
        normalized
        for normalized in (
            _normalize_frame_feature(feature, len(sequence))
            for feature in frame_features
        )
        if normalized is not None
    ]
    if normalized_features:
        return normalized_features

    return [
        {
            "name": str(ds.gene_name or "CDS"),
            "label": str(ds.gene_name or "CDS"),
            "type": "cds",
            "start": 1,
            "end": len(sequence),
            "strand": 1,
        }
    ]


def _build_visualizer_features(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert canonical export features into 0-based visualizer features."""
    return [
        {
            "label": str(feature.get("label") or feature.get("name") or "Feature"),
            "start": max(0, int(feature.get("start", 1)) - 1),
            "end": int(feature.get("end", 1)),
            "type": str(feature.get("type") or "misc"),
            "strand": int(feature.get("strand", 1) or 1),
        }
        for feature in (features or [])
    ]


def build_export_payloads(
    sequence: str,
    features: list[dict[str, Any]],
    project_name: str,
) -> dict[str, dict[str, str]]:
    """Build normalized export payloads for common biological file formats."""
    sequence = sequence.strip().upper()
    if not sequence:
        raise ValueError("Cannot export an empty sequence.")

    safe_name = (project_name or "Untitled_Construct").strip().replace(" ", "_") or "Untitled_Construct"
    payloads = {
        "fasta": {
            "label": "Export FASTA (.fasta)",
            "file_name": f"{safe_name}.fasta",
            "mime": "text/plain",
            "data": generate_fasta_string(sequence, project_name),
        }
    }

    if features:
        payloads["genbank"] = {
            "label": "Export GenBank (.gb)",
            "file_name": f"{safe_name}.gb",
            "mime": "text/plain",
            "data": generate_genbank_string(sequence, features, project_name),
        }

    return payloads


def build_export_manifest(
    export_payload: dict[str, Any],
    report: dict[str, Any],
    validation_state: dict[str, Any],
    export_recommendation: dict[str, Any],
    delivery_ready: bool,
) -> dict[str, Any]:
    """Build a passive structured metadata manifest for the Step 6 export set."""
    sequence = str(export_payload.get("sequence") or "").strip().upper()
    safe_name = str(export_payload.get("safe_name") or "construct") or "construct"
    project_name = str(export_payload.get("project_name") or safe_name) or "construct"
    features = export_payload.get("genbank_features") if isinstance(export_payload.get("genbank_features"), list) else []
    export_formats = report.get("export_formats") if isinstance(report.get("export_formats"), dict) else {}
    validation_results = report.get("validation_results") if isinstance(report.get("validation_results"), dict) else {}
    primer_risk = validation_results.get("primer_risk_summary") if isinstance(validation_results.get("primer_risk_summary"), dict) else {}
    sequence_verification = report.get("sequence_verification") if isinstance(report.get("sequence_verification"), dict) else {}

    recommendation = str(export_recommendation.get("recommendation") or "Not set")
    documentation_only = recommendation != "Ready for Export"
    feature_types = Counter(str(feature.get("type") or "misc_feature") for feature in features if isinstance(feature, dict))

    artifacts = []
    for item in export_formats.get("available_formats") or []:
        if not isinstance(item, dict):
            continue
        artifacts.append(
            {
                "format": str(item.get("format") or ""),
                "label": str(item.get("label") or ""),
                "filename": str(item.get("filename") or ""),
                "mime": str(item.get("mime") or ""),
                "category": str(item.get("category") or ""),
                "available": bool(item.get("available")),
                "status": str(item.get("status") or ""),
                "display_status": str(item.get("display_status") or ""),
                "sequence_required": bool(item.get("sequence_required")),
                "use_case": str(item.get("use_case") or ""),
            }
        )

    return {
        "schema_version": "bds.export_manifest.v0.4",
        "platform": "BioDesign Studio",
        "generated_at": str(report.get("generated_at") or ""),
        "project": {
            "name": project_name,
            "safe_name": safe_name,
        },
        "sequence_length_bp": len(sequence),
        "sequence_sha256": hashlib.sha256(sequence.encode("utf-8")).hexdigest() if sequence else "",
        "coordinate_system": "Biological feature coordinates use 1-based inclusive positions.",
        "artifacts": artifacts,
        "features": {
            "count": len(features),
            "types": dict(feature_types),
            "items": [dict(feature) for feature in features if isinstance(feature, dict)],
        },
        "validation_summary": {
            "status": str(validation_state.get("status") or "not_run"),
            "is_complete": bool(validation_state.get("is_complete")),
            "is_stale": bool(validation_state.get("is_stale")),
            "is_running": bool(validation_state.get("is_running")),
            "is_failed": bool(validation_state.get("is_failed")),
            "critical_count": int(validation_state.get("critical_count") or 0),
            "warning_count": int(validation_state.get("warning_count") or 0),
            "info_count": int(validation_state.get("info_count") or 0),
        },
        "primer_risk_summary": {
            "recommended_count": int(primer_risk.get("recommended_count") or 0),
            "usable_with_risk_count": int(primer_risk.get("usable_with_risk_count") or 0),
            "not_recommended_count": int(primer_risk.get("not_recommended_count") or 0),
            "affected_fragments": list(primer_risk.get("affected_fragments") or []),
            "top_risk_reasons": list(primer_risk.get("top_risk_reasons") or []),
        },
        "export_recommendation": {
            "recommendation": recommendation,
            "tone": str(export_recommendation.get("tone") or ""),
            "conclusion": str(export_recommendation.get("conclusion") or ""),
            "action": str(export_recommendation.get("action") or ""),
            "critical_count": int(export_recommendation.get("critical_count") or 0),
            "warning_count": int(export_recommendation.get("warning_count") or 0),
            "primer_high_risk_count": int(export_recommendation.get("primer_high_risk_count") or 0),
            "primer_review_count": int(export_recommendation.get("primer_review_count") or 0),
            "primer_action_required_count": int(export_recommendation.get("primer_action_required_count") or 0),
            "affected_fragments": list(export_recommendation.get("affected_fragments") or []),
            "documentation_only": documentation_only,
            "ready_for_downstream_handoff": bool(delivery_ready),
        },
        "sequence_verification_summary": {
            "included": bool(sequence_verification.get("included")),
            "is_stale": bool(sequence_verification.get("is_stale")),
            "source": str(sequence_verification.get("source") or "Not configured"),
            "status": str(sequence_verification.get("status") or "not_run"),
            "message": str(sequence_verification.get("message") or ""),
            "top_hit": sequence_verification.get("top_hit"),
            "warnings": list(sequence_verification.get("warnings") or []),
        },
        "safety_notes": {
            "manifest_is_passive_metadata_only": True,
            "dashboard_snapshot_is_not_readiness_evidence": True,
            "documentation_only_when_risk_remains": True,
            "downstream_handoff_blocked_when_not_ready": True,
            "does_not_perform_online_blast": True,
            "does_not_include_sbol_xml_or_rdf": True,
        },
    }


def build_export_manifest_payload(
    manifest: dict[str, Any],
    safe_name: str,
) -> dict[str, str]:
    """Build a downloadable JSON payload for an export metadata manifest."""
    import json

    safe_file_name = (safe_name or "construct").strip().replace(" ", "_") or "construct"
    return {
        "label": "Download export manifest (.json)",
        "file_name": f"{safe_file_name}_export_manifest.json",
        "mime": "application/json",
        "data": json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str),
    }


def build_design_session_export_base_payload(ds) -> dict[str, Any]:
    """Build the canonical export state from the current DesignSession without report content."""
    sequence = _resolve_sequence_from_design_session(ds)
    project_name = str(ds.gene_name or "construct").strip() or "construct"
    safe_name = project_name.replace(" ", "_")
    genbank_features = _build_design_session_features(ds, sequence)
    plasmid_map_features = _build_visualizer_features(genbank_features)
    payloads = build_export_payloads(sequence, genbank_features, project_name) if sequence else {}

    return {
        "sequence": sequence,
        "project_name": project_name,
        "safe_name": safe_name,
        "genbank_features": genbank_features,
        "plasmid_map_features": plasmid_map_features,
        "plasmid_map_title": f"{project_name or 'Construct'} — {len(sequence):,} bp" if sequence else "",
        "payloads": payloads,
        "report_filename": f"{safe_name}_design_report.md",
        "png_filename": f"{safe_name}_plasmid_map.png",
        "manifest_filename": f"{safe_name}_export_manifest.json",
        "has_sequence": bool(sequence),
    }


def build_design_session_export_payload(ds) -> dict[str, Any]:
    """Build the unified export payload from the current DesignSession."""
    from services.report_service import generate_report_content

    export_payload = build_design_session_export_base_payload(ds)
    export_payload["report"] = generate_report_content(ds)
    return export_payload


def _resolve_active_export_payload() -> tuple[str, list[dict[str, Any]], str]:
    """Resolve sequence/features/project from the active DesignSession only."""
    from core.design_session import SessionController

    ds = SessionController().get()
    export_payload = build_design_session_export_payload(ds)

    sequence = export_payload["sequence"]
    project_name = export_payload["project_name"]

    frame = ds.frame if isinstance(getattr(ds, "frame", None), dict) else {}
    frame_features = frame.get("features") if isinstance(frame.get("features"), list) else []
    features = frame_features or export_payload["genbank_features"]

    st.session_state[SK.ACTIVE_SEQ] = sequence
    st.session_state[SK.ACTIVE_FEATURES] = features
    st.session_state[SK.PROJECT_NAME] = project_name

    return sequence, features, project_name


# ---------------------------------------------------------------------------
# Streamlit UI component
# ---------------------------------------------------------------------------

def render_export_buttons() -> None:
    """Render legacy FASTA and GenBank download buttons from the active DesignSession."""
    try:
        sequence, features, project_name = _resolve_active_export_payload()
        payloads = build_export_payloads(sequence, features, project_name)
    except ValueError:
        st.caption(
            "No assembled sequence was found in the current session. "
            "Complete construct generation first to enable FASTA and GenBank export."
        )
        return
    except ImportError:
        st.error(
            "GenBank export requires Biopython, but it is not currently installed. "
            "Run: `pip install biopython`"
        )
        return
    except Exception as exc:
        st.error(f"Unexpected export error: {exc}")
        return

    columns = st.columns(2)
    fasta_payload = payloads["fasta"]
    columns[0].download_button(
        label=fasta_payload["label"],
        data=fasta_payload["data"],
        file_name=fasta_payload["file_name"],
        mime=fasta_payload["mime"],
        help="Download the final construct sequence as FASTA for sequence tools and downstream review.",
        use_container_width=True,
    )

    genbank_payload = payloads.get("genbank")
    if genbank_payload:
        columns[1].download_button(
            label=genbank_payload["label"],
            data=genbank_payload["data"],
            file_name=genbank_payload["file_name"],
            mime=genbank_payload["mime"],
            help="Download the annotated construct as GenBank for Benchling, SnapGene, Geneious, or NCBI workflows.",
            use_container_width=True,
        )
    else:
        columns[1].button(
            "Export GenBank (.gb)",
            disabled=True,
            help="GenBank export requires annotated construct parts or features.",
            use_container_width=True,
        )


def render_export_button() -> None:
    """Backward-compatible wrapper for legacy callers."""
    render_export_buttons()

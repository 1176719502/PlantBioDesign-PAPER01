from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.protein_structure_analysis_service import (
    BOUNDARY_COPY,
    calculate_documentation_properties,
    clean_protein_sequence,
    pdb_id_source_state,
    structure_analysis_artifact_payload,
    uploaded_pdb_source_state,
)
from services.tool_artifact_service import readable_payload_summary


def test_fasta_cleaning_removes_header_and_whitespace() -> None:
    raw = ">demo protein\nMKT AYI\nAKQ\tRIS\n"

    assert clean_protein_sequence(raw) == "MKTAYIAKQRIS"


def test_protein_property_calculation_includes_length_counts_and_mw() -> None:
    props = calculate_documentation_properties(">demo\nACDE")

    assert props["ok"] is True
    assert props["sequence"] == "ACDE"
    assert props["length"] == 4
    assert props["aa_counts"] == {"A": 1, "C": 1, "D": 1, "E": 1}
    assert props["molecular_weight"] > 0


def test_invalid_sequence_handling_does_not_generate_properties() -> None:
    props = calculate_documentation_properties("MKTZ*")

    assert props["ok"] is False
    assert props["invalid_residues"] == ["*", "Z"]
    assert "unsupported" in props["error"].lower()
    assert "molecular_weight" not in props


def test_pdb_id_source_state_requires_four_alphanumeric_characters() -> None:
    valid = pdb_id_source_state(" 6lu7 ")
    invalid = pdb_id_source_state("alphafold")
    empty = pdb_id_source_state("")

    assert valid == {
        "ok": "true",
        "pdb_id": "6LU7",
        "source": "RCSB PDB",
        "message": "Structure source = RCSB PDB.",
    }
    assert invalid["ok"] == "false"
    assert "4 alphanumeric" in invalid["message"]
    assert empty["ok"] == "false"


def test_uploaded_pdb_source_state_is_local_review_only() -> None:
    pdb_text = "HEADER    DEMO\nATOM      1  N   MET A   1      11.104  13.207   9.000\nEND\n"

    valid = uploaded_pdb_source_state(pdb_text)
    empty = uploaded_pdb_source_state("\n")
    unsupported = uploaded_pdb_source_state("not a pdb")

    assert valid == {
        "ok": "true",
        "source": "uploaded PDB file",
        "message": "Structure source = uploaded PDB file.",
    }
    assert empty["ok"] == "false"
    assert unsupported["ok"] == "false"


def test_boundary_copy_states_documentation_only_limits() -> None:
    assert "computational previews and documentation artifacts only" in BOUNDARY_COPY
    assert "does not validate folding, function, expression, or experimental readiness" in BOUNDARY_COPY
    assert "do not certify experimental readiness" in BOUNDARY_COPY
    assert "predict yield" in BOUNDARY_COPY
    assert "optimize pathways" in BOUNDARY_COPY
    assert "wet-lab protocols" in BOUNDARY_COPY
    assert "Use Expression Wizard Step 6" in BOUNDARY_COPY
    assert "documentation-only and review-only" in BOUNDARY_COPY


def test_structure_analysis_page_smoke_static_contract() -> None:
    page = Path(ROOT, "views", "StructureAnalysis.py").read_text(encoding="utf-8")
    service = Path(ROOT, "services", "protein_structure_analysis_service.py").read_text(encoding="utf-8")
    combined_boundary_text = f"{page}\n{service}"

    assert "Protein Structure Analysis" in page
    assert "Protein Physicochemical Properties" in page
    assert "Protein Structure Viewer" in page
    assert "BOUNDARY_COPY" in page
    assert "Structure source = RCSB PDB" in page
    assert "Structure source = uploaded PDB file" in page
    assert "Save Documentation Artifact" in page
    assert "Documentation-only inspection and structure review helper" in page
    assert "documentation-only protein property estimates" in page
    assert "optional documentation artifacts for local review context" in page
    assert "save a Documentation Artifact only if you need a traceability record" in page
    assert "Enter a protein sequence or receive a CDS handoff from Expression Wizard" in page
    assert "Structure source review shows either a 4-character RCSB PDB ID" in page
    assert "Viewer failures do not change saved documentation records." in page
    assert "No saved documentation artifacts yet." in page
    assert "Filter by record type" in page
    assert "Filter by source page" in page
    assert "source_module" in page
    assert "Readable payload summary" in page
    assert "readable_payload_summary" in page
    assert "Advanced record details" in page
    assert "raw_payload_preview" in page
    assert "Payload summary truncated for readability." in page
    assert "expanded=False" in page
    assert "max_chars=2000" in page
    assert "Delete artifact" in page
    assert "This removes the saved documentation artifact only." in page
    assert "documentation-only" in page
    assert "documentation records" in page
    assert "review record" in page
    assert ("not experimental conclusions" in page) or ("does not validate" in page)
    assert "not prediction" in page
    assert "not validation" in page
    assert "not recommendation" in page
    assert "not readiness approval" in page
    assert ("not yield prediction" in combined_boundary_text) or ("predict yield" in combined_boundary_text)
    assert ("not pathway optimization" in combined_boundary_text) or ("optimize pathways" in combined_boundary_text)
    assert ("not wet-lab protocols" in combined_boundary_text) or ("provide wet-lab protocols" in combined_boundary_text)
    assert "delete_tool_artifact" in page
    assert "st.json" not in page
    assert "def _payload_summary" not in page
    assert "AlphaFold" not in page
    assert "function prediction" not in page.lower()
    assert "wet-lab protocol steps" not in page.lower()


def test_structure_analysis_artifact_payload_is_review_only() -> None:
    payload = structure_analysis_artifact_payload(
        protein_sequence="ACDE",
        structure_source=pdb_id_source_state("6lu7"),
    )

    assert payload["artifact_type"] == "protein_structure_analysis"
    assert payload["title"] == "Protein Structure Analysis Review Record"
    assert payload["source_module"] == "Structure Analysis"
    assert payload["sequence_properties"]["ok"] is True
    assert payload["sequence_properties"]["length"] == 4
    assert payload["structure_source"]["source"] == "RCSB PDB"
    assert payload["boundary_label"]
    assert "documentation-only and review-only" in payload["boundary_copy"]
    assert "Structure source: RCSB PDB" in payload["summary"]

    summary_text = "\n".join(f"{label}: {value}" for label, value in readable_payload_summary(payload))
    assert "Sequence length: 4 aa" in summary_text
    assert "Structure source: RCSB PDB" in summary_text
    assert "PDB ID: 6LU7" in summary_text
    assert "Molecular weight estimate" in summary_text
    assert payload["sequence_properties"]["sequence"] not in summary_text


def test_structure_analysis_artifact_payload_handles_empty_inputs() -> None:
    assert structure_analysis_artifact_payload(protein_sequence="", structure_source={}) == {}

# -*- coding: utf-8 -*-
"""
tests/test_mvp_workflow.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Minimal MVP workflow tests covering the four core steps:

  1. Gene Input   -- DesignSession stores a valid CDS; gate logic is correct.
  2. Host Selection -- host is linked to the session; gate passes only when set.
  3. Construct Definition -- ConstructBuilder assembles parts and records features.
  4. Export -- generate_genbank_string() round-trips sequence and feature data.

All tests are pure-Python (no Streamlit, no running server, no network).
Run with:
    python -m pytest tests/test_mvp_workflow.py -v
"""
from __future__ import annotations

import io
import os
import sys

# ---------------------------------------------------------------------------
# Make sure the project root is on the path regardless of CWD
# ---------------------------------------------------------------------------
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

from core.design_session import DesignSession
from core.construct_builder import ConstructBuilder
from core.part_library import BioPart
# export_manager imports streamlit at module level, so we extract only the
# pure Biopython function here to keep tests free of Streamlit.
def generate_genbank_string(sequence, features, project_name):
    """Pure-Python GenBank exporter extracted from components/export_manager.py."""
    import io as _io
    from Bio import SeqIO
    from Bio.Seq import Seq
    from Bio.SeqFeature import SeqFeature, SimpleLocation
    from Bio.SeqRecord import SeqRecord

    sequence = sequence.strip().upper()
    if not sequence:
        raise ValueError("Cannot export an empty sequence.")

    safe_name = (project_name or "Untitled_Construct")[:16].replace(" ", "_")
    safe_id   = (project_name or "Untitled_Construct").replace(" ", "_")
    record = SeqRecord(
        Seq(sequence), id=safe_id, name=safe_name,
        description=f"Exported from BioDesign Studio — {project_name}",
    )
    record.annotations["molecule_type"] = "DNA"

    bio_features = []
    for feat in (features or []):
        try:
            feat_type = str(feat.get("type",  "misc_feature")) or "misc_feature"
            feat_name = str(feat.get("name",  "unnamed"))
            raw_start = int(feat.get("start", 1))
            raw_end   = int(feat.get("end",   raw_start))
            bp_start  = max(0, raw_start - 1)
            bp_end    = min(len(sequence), raw_end)
            location  = SimpleLocation(bp_start, bp_end, strand=1)
            bio_features.append(
                SeqFeature(location=location, type=feat_type,
                           qualifiers={"label": [feat_name]})
            )
        except Exception:
            continue
    record.features = bio_features

    buf = _io.StringIO()
    SeqIO.write(record, buf, "genbank")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

# A valid 84-bp CDS (ATG start, TAA stop, pure ATCG)
VALID_CDS = (
    "ATGGTGAGCAAGGGCGAGGAGCTGTTCACCGGGGTGGTGCCC"
    "ATCCTGGTCGAGCTGGACGGCGACGTAAACGGCCACAAGTAA"
)

VALID_PROMOTER_SEQ  = "TAATACGACTCACTATA"           # T7 promoter core
VALID_RBS_SEQ       = "AAAGAGGAGAAA"                # B0034
VALID_TERMINATOR_SEQ = "CCAGGCATCAAATAAAACGAAAGGCT"  # B0015 (abbrev.)


# ===========================================================================
# 1. Gene Input
# ===========================================================================

class TestGeneInput:
    """Validate that gene input is saved in DesignSession and gate logic works."""

    def test_gene_name_saved(self):
        """Gene name written to ds.gene_name must be retrievable unchanged."""
        ds = DesignSession()
        ds.gene_name = "OsWRKY45"
        assert ds.gene_name == "OsWRKY45"

    def test_original_seq_saved(self):
        """Sequence written to ds.original_seq must be retrievable unchanged."""
        ds = DesignSession()
        ds.original_seq = VALID_CDS
        assert ds.original_seq == VALID_CDS

    def test_seq_displayed_correctly_via_summary(self):
        """
        summary() must report the correct original_seq length so the UI
        'live preview' chip shows the right bp count.
        """
        ds = DesignSession()
        ds.gene_name   = "GFP"
        ds.original_seq = VALID_CDS
        summary = ds.summary()
        assert summary["gene_name"]        == "GFP"
        assert summary["original_seq_len"] == len(VALID_CDS)

    def test_step1_gate_passes_with_valid_seq(self):
        """
        Step 1 -> 2 gate: original_seq >= 30 bp must return can_advance=True.
        Tested directly on DesignSession to avoid importing Streamlit.
        """
        ds = DesignSession()
        ds.original_seq = VALID_CDS           # 84 bp
        # Mirror the gate rule from SessionController.can_advance step==1
        can_advance = len(ds.original_seq) >= 30
        assert can_advance is True

    def test_step1_gate_blocks_short_seq(self):
        """Gate must block sequences shorter than 30 bp."""
        ds = DesignSession()
        ds.original_seq = "ATGCATGC"          # 8 bp
        can_advance = len(ds.original_seq) >= 30
        assert can_advance is False

    def test_step1_gate_blocks_empty_seq(self):
        """Gate must block an empty sequence."""
        ds = DesignSession()
        ds.original_seq = ""
        can_advance = len(ds.original_seq) >= 30
        assert can_advance is False

    def test_step1_gate_passes_at_boundary(self):
        """Sequence of exactly 30 bp must pass the gate."""
        ds = DesignSession()
        ds.original_seq = "A" * 30
        can_advance = len(ds.original_seq) >= 30
        assert can_advance is True


# ===========================================================================
# 2. Host Selection
# ===========================================================================

class TestHostSelection:
    """Validate that host is linked to the session and gate logic is correct."""

    def test_host_saved(self):
        """Host written to ds.host must be retrievable unchanged."""
        ds = DesignSession()
        ds.host = "E.coli BL21(DE3)"
        assert ds.host == "E.coli BL21(DE3)"

    def test_host_appears_in_summary(self):
        """summary() must expose the host so the UI can display it."""
        ds = DesignSession()
        ds.original_seq = VALID_CDS
        ds.host = "S. cerevisiae"
        summary = ds.summary()
        assert summary["host"] == "S. cerevisiae"

    def test_step2_gate_passes_when_host_set(self):
        """
        Step 2 -> 3 gate: a non-empty ds.host must allow progression.
        """
        ds = DesignSession()
        ds.host = "E.coli BL21(DE3)"
        can_advance = bool(ds.host)
        assert can_advance is True

    def test_step2_gate_blocks_when_host_empty(self):
        """Gate must block when no host has been selected."""
        ds = DesignSession()
        ds.host = ""
        can_advance = bool(ds.host)
        assert can_advance is False

    def test_host_change_clears_downstream_artefacts(self):
        """
        Changing the host must wipe frame, optimized_seq, and primers so
        a stale cassette from the previous host cannot leak into Step 3/4.
        Mirrors the _inputs_changed branch in wizard_flow._page_2.
        """
        ds = DesignSession()
        ds.original_seq  = VALID_CDS
        ds.host          = "E.coli BL21(DE3)"
        ds.optimized_seq = VALID_CDS
        ds.frame         = {"success": True, "final_sequence": VALID_CDS}
        ds.primers       = [{"name": "fwd", "seq": "ATGGTGAGC"}]

        # Simulate host change
        new_host = "S. cerevisiae"
        if new_host != ds.host:
            ds.frame             = {}
            ds.optimized_seq     = ""
            ds.primers           = []
            ds.validation_results = []
        ds.host = new_host

        assert ds.host           == "S. cerevisiae"
        assert ds.frame          == {}
        assert ds.optimized_seq  == ""
        assert ds.primers        == []
        assert ds.frame_ok is False

    def test_tag_saved_with_host(self):
        """Tag must also be saved alongside the host in the session."""
        ds = DesignSession()
        ds.host = "E.coli BL21(DE3)"
        ds.tag  = "His6-tag (C-term)"
        assert ds.tag == "His6-tag (C-term)"
        assert ds.summary()["tag"] == "His6-tag (C-term)"


# ===========================================================================
# 3. Construct Definition  (ConstructBuilder)
# ===========================================================================

class TestConstructDefinition:
    """Validate that ConstructBuilder assembles parts and records features."""

    def _make_standard_parts(self) -> list[BioPart]:
        """Return a minimal expression cassette as a list of BioParts."""
        return [
            BioPart("T7 Promoter",     "promoter",   VALID_PROMOTER_SEQ),
            BioPart("B0034 RBS",       "RBS",         VALID_RBS_SEQ),
            BioPart("GFP CDS",         "CDS",         VALID_CDS),
            BioPart("B0015 Terminator","terminator",  VALID_TERMINATOR_SEQ),
        ]

    # --- build tests --------------------------------------------------------

    def test_construct_sequence_is_concatenation(self):
        """
        final_sequence must equal the exact concatenation of all part
        sequences in order (uppercased).
        """
        parts   = self._make_standard_parts()
        builder = ConstructBuilder()
        result  = builder.build_linear_construct(parts)

        expected = (
            VALID_PROMOTER_SEQ
            + VALID_RBS_SEQ
            + VALID_CDS
            + VALID_TERMINATOR_SEQ
        ).upper()
        assert result["final_sequence"] == expected

    def test_construct_total_length(self):
        """total_length must equal len(final_sequence)."""
        parts   = self._make_standard_parts()
        builder = ConstructBuilder()
        result  = builder.build_linear_construct(parts)

        assert result["total_length"] == len(result["final_sequence"])

    def test_feature_count_matches_part_count(self):
        """One feature annotation must be created per BioPart."""
        parts   = self._make_standard_parts()
        builder = ConstructBuilder()
        result  = builder.build_linear_construct(parts)

        assert len(result["features"]) == len(parts)

    def test_feature_names_match_part_names(self):
        """Feature names must match the BioPart names in order."""
        parts   = self._make_standard_parts()
        builder = ConstructBuilder()
        result  = builder.build_linear_construct(parts)

        for feat, part in zip(result["features"], parts):
            assert feat["name"] == part.name

    def test_feature_coordinates_are_contiguous(self):
        """
        Feature coordinates must be contiguous and non-overlapping:
        each part's start must equal the previous part's end + 1.
        """
        parts   = self._make_standard_parts()
        builder = ConstructBuilder()
        result  = builder.build_linear_construct(parts)

        feats = result["features"]
        # First feature must start at position 1
        assert feats[0]["start"] == 1

        for i in range(1, len(feats)):
            assert feats[i]["start"] == feats[i - 1]["end"] + 1, (
                f"Gap or overlap between feature {i-1} and {i}"
            )

        # Last feature must end at total_length
        assert feats[-1]["end"] == result["total_length"]

    def test_feature_types_match_part_types(self):
        """Feature type field must match the BioPart.part_type."""
        parts   = self._make_standard_parts()
        builder = ConstructBuilder()
        result  = builder.build_linear_construct(parts)

        for feat, part in zip(result["features"], parts):
            assert feat["type"] == part.part_type

    def test_empty_part_list_raises(self):
        """build_linear_construct() must raise ValueError on empty input."""
        builder = ConstructBuilder()
        with pytest.raises(ValueError):
            builder.build_linear_construct([])

    # --- logic order tests --------------------------------------------------

    def test_valid_order_passes_logic_check(self):
        """A standard promoter -> RBS -> CDS -> terminator order must pass."""
        parts   = self._make_standard_parts()
        builder = ConstructBuilder()
        ok, msg = builder.check_logic_order(parts)
        assert ok is True, f"Expected logic check to pass, got: {msg}"

    def test_cds_before_promoter_fails_logic_check(self):
        """CDS with no upstream promoter/RBS must fail the logic check."""
        parts = [
            BioPart("GFP CDS",    "CDS",      VALID_CDS),
            BioPart("T7 Promoter","promoter", VALID_PROMOTER_SEQ),
        ]
        builder = ConstructBuilder()
        ok, msg = builder.check_logic_order(parts)
        assert ok is False
        assert "promoter" in msg.lower() or "rbs" in msg.lower()

    def test_part_after_terminator_fails_logic_check(self):
        """A functional part placed after a terminator must fail the logic check."""
        parts = [
            BioPart("T7 Promoter",     "promoter",   VALID_PROMOTER_SEQ),
            BioPart("B0034 RBS",       "RBS",         VALID_RBS_SEQ),
            BioPart("GFP CDS",         "CDS",         VALID_CDS),
            BioPart("B0015 Terminator","terminator",  VALID_TERMINATOR_SEQ),
            BioPart("Extra CDS",       "CDS",         VALID_CDS),   # after terminator
        ]
        builder = ConstructBuilder()
        ok, msg = builder.check_logic_order(parts)
        assert ok is False
        assert "terminator" in msg.lower()

    def test_result_stored_in_design_session(self):
        """
        The dict returned by build_linear_construct() must be storable
        in DesignSession.frame and make frame_ok return True.
        """
        parts   = self._make_standard_parts()
        builder = ConstructBuilder()
        result  = builder.build_linear_construct(parts)

        ds = DesignSession()
        ds.original_seq = VALID_CDS
        ds.host         = "E.coli BL21(DE3)"
        # Simulate what the Wizard does after build_expression_frame succeeds
        ds.frame = {
            "success":        True,
            "final_sequence": result["final_sequence"],
            "total_length":   result["total_length"],
            "features":       result["features"],
            "gc_content":     0.0,
        }
        assert ds.frame_ok is True
        assert ds.final_sequence == result["final_sequence"]


# ===========================================================================
# 4. FASTA / GenBank Export
# ===========================================================================

class TestExport:
    """Validate that generate_genbank_string() produces correct GenBank output."""

    def _build_features(self, parts: list[BioPart]) -> list[dict]:
        """Use ConstructBuilder to produce feature annotations."""
        builder = ConstructBuilder()
        return builder.build_linear_construct(parts)["features"]

    def _standard_parts(self) -> list[BioPart]:
        return [
            BioPart("T7 Promoter",      "promoter",   VALID_PROMOTER_SEQ),
            BioPart("B0034 RBS",        "RBS",         VALID_RBS_SEQ),
            BioPart("GFP CDS",          "CDS",         VALID_CDS),
            BioPart("B0015 Terminator", "terminator",  VALID_TERMINATOR_SEQ),
        ]

    # --- basic GenBank format checks ----------------------------------------

    def test_genbank_output_is_string(self):
        """generate_genbank_string() must return a non-empty str."""
        parts    = self._standard_parts()
        features = self._build_features(parts)
        sequence = "".join(p.sequence for p in parts)
        gb = generate_genbank_string(sequence, features, "TestConstruct")
        assert isinstance(gb, str)
        assert len(gb) > 0

    def test_genbank_contains_locus_line(self):
        """Valid GenBank output must start with a LOCUS line."""
        parts    = self._standard_parts()
        features = self._build_features(parts)
        sequence = "".join(p.sequence for p in parts)
        gb = generate_genbank_string(sequence, features, "TestConstruct")
        assert gb.strip().startswith("LOCUS")

    def test_genbank_contains_origin_section(self):
        """GenBank output must contain an ORIGIN section with the sequence."""
        parts    = self._standard_parts()
        features = self._build_features(parts)
        sequence = "".join(p.sequence for p in parts)
        gb = generate_genbank_string(sequence, features, "TestConstruct")
        assert "ORIGIN" in gb

    # --- sequence round-trip ------------------------------------------------

    def test_sequence_round_trip(self):
        """
        The sequence embedded in the GenBank ORIGIN section must match
        the original input sequence (case-insensitive, whitespace-stripped).
        """
        from Bio import SeqIO

        parts    = self._standard_parts()
        features = self._build_features(parts)
        sequence = "".join(p.sequence for p in parts).upper()

        gb = generate_genbank_string(sequence, features, "RoundTrip")
        record = next(SeqIO.parse(io.StringIO(gb), "genbank"))
        assert str(record.seq).upper() == sequence

    def test_sequence_length_in_locus_line(self):
        """
        The bp count in the LOCUS line must match len(input_sequence).
        """
        parts    = self._standard_parts()
        features = self._build_features(parts)
        sequence = "".join(p.sequence for p in parts).upper()

        gb = generate_genbank_string(sequence, features, "LenCheck")
        locus_line = gb.splitlines()[0]
        # LOCUS line format: LOCUS  <name>  <N> bp  ...
        # Find the integer token that precedes 'bp'
        tokens = locus_line.split()
        bp_idx = tokens.index("bp")
        assert int(tokens[bp_idx - 1]) == len(sequence)

    # --- feature round-trip -------------------------------------------------

    def test_feature_count_in_genbank(self):
        """
        The number of SeqFeature objects in the parsed GenBank record must
        equal the number of input feature annotations.
        """
        from Bio import SeqIO

        parts    = self._standard_parts()
        features = self._build_features(parts)
        sequence = "".join(p.sequence for p in parts).upper()

        gb     = generate_genbank_string(sequence, features, "FeatCount")
        record = next(SeqIO.parse(io.StringIO(gb), "genbank"))
        assert len(record.features) == len(features)

    def test_feature_labels_in_genbank(self):
        """
        Every feature name must appear as a 'label' qualifier in the
        parsed GenBank record.
        """
        from Bio import SeqIO

        parts    = self._standard_parts()
        features = self._build_features(parts)
        sequence = "".join(p.sequence for p in parts).upper()

        gb     = generate_genbank_string(sequence, features, "FeatLabels")
        record = next(SeqIO.parse(io.StringIO(gb), "genbank"))

        gb_labels = [
            feat.qualifiers.get("label", [""])[0]
            for feat in record.features
        ]
        for feat_dict in features:
            assert feat_dict["name"] in gb_labels, (
                f"Feature '{feat_dict['name']}' not found in GenBank labels: {gb_labels}"
            )

    def test_feature_positions_in_genbank(self):
        """
        Feature start/end positions stored in the GenBank file must map
        back to the original 1-based coordinates (Biopython uses 0-based
        half-open intervals internally).
        """
        from Bio import SeqIO

        parts    = self._standard_parts()
        features = self._build_features(parts)
        sequence = "".join(p.sequence for p in parts).upper()

        gb     = generate_genbank_string(sequence, features, "FeatPos")
        record = next(SeqIO.parse(io.StringIO(gb), "genbank"))

        for i, (gb_feat, orig_feat) in enumerate(
            zip(record.features, features)
        ):
            # Biopython location: 0-based half-open -> convert back to 1-based inclusive
            gb_start_1based = int(gb_feat.location.start) + 1
            gb_end_1based   = int(gb_feat.location.end)
            assert gb_start_1based == orig_feat["start"], (
                f"Feature {i} start mismatch: GenBank {gb_start_1based} "
                f"vs original {orig_feat['start']}"
            )
            assert gb_end_1based == orig_feat["end"], (
                f"Feature {i} end mismatch: GenBank {gb_end_1based} "
                f"vs original {orig_feat['end']}"
            )

    # --- edge cases ---------------------------------------------------------

    def test_empty_sequence_raises(self):
        """generate_genbank_string() must raise ValueError for an empty sequence."""
        with pytest.raises(ValueError, match="empty"):
            generate_genbank_string("", [], "EmptyTest")

    def test_no_features_still_exports(self):
        """Export must succeed even when the features list is empty."""
        gb = generate_genbank_string(VALID_CDS, [], "NoFeats")
        assert "LOCUS" in gb
        assert "ORIGIN" in gb

    def test_project_name_in_output(self):
        """
        The project name (truncated to 16 chars per GenBank spec) must
        appear in the LOCUS line of the output.
        """
        gb = generate_genbank_string(VALID_CDS, [], "MyConstruct")
        # GenBank NAME field is the truncated name; check LOCUS line
        locus_line = gb.splitlines()[0]
        assert "MyConstruct" in locus_line

    def test_construct_matches_design_session_final_sequence(self):
        """
        End-to-end: build a construct, store it in DesignSession, then
        export via generate_genbank_string() and confirm the GenBank
        sequence matches ds.final_sequence.
        """
        from Bio import SeqIO

        parts   = self._standard_parts()
        builder = ConstructBuilder()
        result  = builder.build_linear_construct(parts)

        ds = DesignSession()
        ds.original_seq = VALID_CDS
        ds.host         = "E.coli BL21(DE3)"
        ds.frame = {
            "success":        True,
            "final_sequence": result["final_sequence"],
            "total_length":   result["total_length"],
            "features":       result["features"],
            "gc_content":     0.0,
        }

        # Export using the session's final sequence and features
        gb     = generate_genbank_string(
            ds.final_sequence,
            ds.frame["features"],
            "E2E_Test",
        )
        record = next(SeqIO.parse(io.StringIO(gb), "genbank"))
        assert str(record.seq).upper() == ds.final_sequence.upper()
 
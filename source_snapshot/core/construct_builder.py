"""
core/construct_builder.py

Core logic layer for assembling biological constructs.
Handles sequence concatenation and basic logic-order validation.
No UI dependencies; pure Python only.
"""

from core.part_library import BioPart


# ---------------------------------------------------------------------------
# Constants - define the canonical expression order for validation
# ---------------------------------------------------------------------------

# A reasonable linear expression order for a typical prokaryotic expression cassette:
#   promoter -> (operator) -> RBS -> CDS / reporter -> terminator
# We assign each part type a "rank" in the canonical order.
# Lower rank = should appear earlier in the sequence.
_CANONICAL_ORDER_RANK: dict[str, int] = {
    "promoter":  1,
    "operator":  2,
    "RBS":       3,
    "CDS":       4,
    "reporter":  4,   # reporters are functionally equivalent to CDS
    "terminator": 5,
    "vector":    0,   # vector backbone; typically not inline, but neutral
    "other":     0,   # unknown parts; skip rank checking
}


# ---------------------------------------------------------------------------
# ConstructBuilder
# ---------------------------------------------------------------------------

class ConstructBuilder:
    """
    Assembles a list of BioPart objects into a linear DNA construct.

    Responsibilities
    ----------------
    - Concatenate part sequences in the given order.
    - Track the genomic coordinates of every part within the final sequence.
    - Perform a lightweight biological-logic sanity check on part order.
    """

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def build_linear_construct(self, part_list: list[BioPart]) -> dict:
        """
        Concatenate a list of BioPart sequences into a single linear construct.

        Parameters
        ----------
        part_list : list[BioPart]
            Ordered list of BioPart objects to assemble, from 5' to 3'.

        Returns
        -------
        dict with three keys:
            final_sequence : str
                The complete concatenated DNA sequence.
            total_length : int
                Length of final_sequence in base pairs.
            features : list[dict]
                Per-part annotation records, each containing:
                  - name  (str)  : part name
                  - type  (str)  : part_type string
                  - start (int)  : 1-based start position in final_sequence
                  - end   (int)  : 1-based end position (inclusive)

        Raises
        ------
        ValueError
            If part_list is empty.
        """
        # --- 1. Guard: list must not be empty ---
        if not part_list:
            raise ValueError(
                "part_list is empty. Provide at least one BioPart to assemble."
            )

        # --- 2. Concatenate sequences and record positions ---
        fragments: list[str] = []   # will be joined once at the end (efficient)
        features:  list[dict] = []
        cursor: int = 1             # 1-based position tracker

        for part in part_list:
            # Use the normalised (uppercase, whitespace-stripped) sequence
            seq: str = part.sequence.upper().strip()

            # Calculate start / end positions (both 1-based, end is inclusive)
            start: int = cursor
            end:   int = cursor + len(seq) - 1

            # Record feature annotation for this part
            features.append({
                "name":  part.name,
                "type":  part.part_type,
                "start": start,
                "end":   end,
            })

            fragments.append(seq)
            cursor = end + 1    # advance cursor past this part

        # --- 3. Build the final sequence string in one join call ---
        final_sequence: str = "".join(fragments)

        return {
            "final_sequence": final_sequence,
            "total_length":   len(final_sequence),
            "features":       features,
        }

    # -----------------------------------------------------------------------

    def check_logic_order(self, part_list: list[BioPart]) -> tuple[bool, str]:
        """
        Perform a lightweight biological-logic sanity check on part ordering.

        Rules checked
        -------------
        1. A CDS or reporter should be preceded by a promoter or RBS somewhere
           earlier in the list.
        2. No functional part (promoter, RBS, CDS, reporter) should appear
           *after* a terminator; that would place it outside the expression
           cassette.
        3. A promoter should not appear after a terminator.

        Parameters
        ----------
        part_list : list[BioPart]
            The ordered list of parts to validate.

        Returns
        -------
        tuple[bool, str]
            (True,  "Logic order check passed.")  if no issues are detected.
            (False, "Warning: <reason>")          if a logic problem is found.
        """
        # An empty list is technically valid (no rules can be violated)
        if not part_list:
            return True, "Logic order check passed (empty list)."

        # Collect the part types in order for easy scanning
        types: list[str] = [p.part_type for p in part_list]

        # --- Rule 1: CDS / reporter needs an upstream promoter or RBS ---
        for idx, ptype in enumerate(types):
            if ptype in ("CDS", "reporter"):
                # Check if any part *before* this index is a promoter or RBS
                upstream_types = set(types[:idx])
                has_driver = bool(upstream_types & {"promoter", "RBS"})
                if not has_driver:
                    return (
                        False,
                        f"Warning: '{part_list[idx].name}' ({ptype}) has no upstream "
                        "promoter or RBS. This construct may not be expressed.",
                    )

        # --- Rule 2: Nothing meaningful should appear after a terminator ---
        functional_types = {"promoter", "RBS", "CDS", "reporter"}
        terminator_seen_at: int = -1

        for idx, ptype in enumerate(types):
            if ptype == "terminator":
                # Record the position of the *first* terminator
                if terminator_seen_at == -1:
                    terminator_seen_at = idx
            elif ptype in functional_types and terminator_seen_at != -1:
                # A functional part appears after the terminator
                return (
                    False,
                    f"Warning: '{part_list[idx].name}' ({ptype}) appears after a "
                    "terminator. Parts placed downstream of a terminator are "
                    "unlikely to be transcribed.",
                )

        # --- Rule 3: Promoter should not follow a terminator (redundant but explicit) ---
        # Already covered by Rule 2 since 'promoter' is in functional_types.
        # Kept here as a comment for clarity.

        # --- All checks passed ---
        return True, "Logic order check passed."


# ---------------------------------------------------------------------------
# Quick self-test  (run with: python -m core.construct_builder)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from core.part_library import BioPart

    # Build a minimal expression cassette: Promoter → RBS → CDS → Terminator
    parts = [
        BioPart(name="T7 Promoter",      part_type="promoter",   sequence="TAATACGACTCACTATA"),
        BioPart(name="B0034 RBS",         part_type="RBS",        sequence="AAAGAGGAGAAA"),
        BioPart(name="GFP CDS",           part_type="CDS",        sequence="ATGGTGAGCAAGGGCGAGGAG"),
        BioPart(name="B0015 Terminator",  part_type="terminator", sequence="CCAGGCATCAAA"),
    ]

    builder = ConstructBuilder()

    # --- Test: build construct ---
    result = builder.build_linear_construct(parts)
    print("=== build_linear_construct ===")
    print(f"Total length : {result['total_length']} bp")
    print(f"Final sequence: {result['final_sequence']}")
    print("Features:")
    for feat in result["features"]:
        print(f"  {feat['name']:25s} | {feat['type']:12s} | pos {feat['start']:>4d} – {feat['end']:>4d}")

    # --- Test: logic order check (should pass) ---
    ok, msg = builder.check_logic_order(parts)
    print(f"\nLogic check: {'PASS' if ok else 'FAIL'} — {msg}")

    # --- Test: bad order — CDS before promoter ---
    bad_parts = [
        BioPart(name="GFP CDS",  part_type="CDS",      sequence="ATGGTGAGCAAG"),
        BioPart(name="T7 Promo", part_type="promoter", sequence="TAATACGACTCA"),
    ]
    ok2, msg2 = builder.check_logic_order(bad_parts)
    print(f"Bad-order check: {'PASS' if ok2 else 'FAIL'} — {msg2}")

    # --- Test: empty list raises ValueError ---
    try:
        builder.build_linear_construct([])
    except ValueError as exc:
        print(f"\nEmpty-list guard: OK — {exc}")

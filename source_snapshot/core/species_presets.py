# core/species_presets.py
"""
Species-specific parameter presets for BioDesign Studio.

This is the single source of truth for organism-specific defaults.
All modules should call get_preset(host_name) instead of hard-coding
organism parameters directly.

Supported organisms (MVP)
--------------------------
  - Rice          (Oryza sativa)
  - Arabidopsis   (Arabidopsis thaliana)
  - E.coli        (Escherichia coli)

Fallback
--------
  Any unrecognised host_name returns GENERIC_PRESET, which uses
  safe, broadly applicable defaults.

Usage
-----
    from core.species_presets import get_preset

    preset = get_preset("Rice")
    gc_min, gc_max = preset["gc_target_range"]
    promoter      = preset["preferred_promoter"]

No Streamlit imports — this module is safe to use in unit tests.
"""
from __future__ import annotations
from typing import Any, Dict


# ---------------------------------------------------------------------------
# Preset definitions
# ---------------------------------------------------------------------------

PRESETS: Dict[str, Dict[str, Any]] = {
    "Rice": {
        "display_name":         "Oryza sativa (Rice)",
        "organism_group":       "plant_monocot",
        # Genetic code — NCBI table ID (1 = standard)
        "codon_table_id":       1,
        # Key used to look up the codon frequency table in core/codon_optimizer.py
        "codon_table_key":      "Rice",
        # Regulatory element recommendations
        "preferred_promoter":   "CaMV 35S / OsActin1",
        "preferred_terminator": "NOS terminator",
        "preferred_rbs":        "Kozak sequence (GCCACCATG)",
        # Typical GC target range (%) for monocot codon optimisation
        "gc_target_range":      (45, 65),
        # Common cloning vectors for this host
        "suggested_vectors":    ["pCAMBIA1300", "pCAMBIA2300", "pMDC32"],
        # Agrobacterium-mediated transformation is default for rice
        "transformation_method": "Agrobacterium tumefaciens (floral dip / callus)",
        # Antibiotic selection marker commonly used
        "selection_marker":     "Hygromycin B",
        # Notes shown to the user
        "notes": (
            "Monocot — use monocot-optimised codon tables. "
            "CaMV 35S promoter has reduced activity in rice; "
            "OsActin1 is strongly preferred for constitutive expression."
        ),
    },

    "Arabidopsis": {
        "display_name":         "Arabidopsis thaliana (Arabidopsis)",
        "organism_group":       "plant_dicot",
        "codon_table_id":       1,
        "codon_table_key":      "Arabidopsis",
        "preferred_promoter":   "CaMV 35S / AtUBQ10",
        "preferred_terminator": "NOS terminator / AtACT2 terminator",
        "preferred_rbs":        "Kozak sequence (GCCACCATG)",
        "gc_target_range":      (42, 60),
        "suggested_vectors":    ["pMDC32", "pB2GW7", "pK2GW7", "pEarleyGate"],
        "transformation_method": "Agrobacterium tumefaciens (floral dip)",
        "selection_marker":     "Kanamycin / Basta",
        "notes": (
            "Model dicot — CaMV 35S is highly effective for constitutive expression. "
            "T-DNA binary vectors are standard. "
            "Floral dip transformation is straightforward."
        ),
    },

    "E.coli": {
        "display_name":         "Escherichia coli (E. coli)",
        "organism_group":       "bacteria_gram_negative",
        "codon_table_id":       11,  # bacterial / plant plastid code
        "codon_table_key":      "E.coli",
        "preferred_promoter":   "T7 / Trc / lac",
        "preferred_terminator": "T7 terminator / rrnB T1-T2",
        "preferred_rbs":        "Shine-Dalgarno (AGGAGG)",
        "gc_target_range":      (50, 55),
        "suggested_vectors":    ["pET-28a", "pET-21a", "pGEX-4T", "pBAD"],
        "transformation_method": "Chemical transformation / Electroporation",
        "selection_marker":     "Ampicillin / Kanamycin",
        "notes": (
            "Standard prokaryotic expression host. "
            "Use T7 promoter system (BL21-DE3) for high-level protein expression. "
            "Avoid rare arginine codons (AGA, AGG) for high-yield expression."
        ),
    },
}

# ---------------------------------------------------------------------------
# Generic fallback — returned for any unrecognised host
# ---------------------------------------------------------------------------

GENERIC_PRESET: Dict[str, Any] = {
    "display_name":         "Generic / Unknown Host",
    "organism_group":       "unknown",
    "codon_table_id":       1,
    "codon_table_key":      None,          # caller must handle None gracefully
    "preferred_promoter":   "Not specified",
    "preferred_terminator": "Not specified",
    "preferred_rbs":        "Not specified",
    "gc_target_range":      (40, 60),
    "suggested_vectors":    [],
    "transformation_method": "Not specified",
    "selection_marker":     "Not specified",
    "notes":                "No species-specific preset found. Using generic defaults.",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_preset(host_name: str) -> Dict[str, Any]:
    """Return the species preset dict for *host_name*.

    Lookup is case-insensitive and also matches common aliases
    (e.g. "ecoli", "e. coli", "e.coli", "arabidopsis thaliana").
    Returns GENERIC_PRESET (a copy) if no match is found — never raises.

    Parameters
    ----------
    host_name : str
        Any host string, e.g. from DesignSession.host or the species switcher.

    Returns
    -------
    dict
        A copy of the matching preset dict (safe to mutate).
    """
    if not host_name:
        return dict(GENERIC_PRESET)

    # Direct lookup first (exact key match)
    if host_name in PRESETS:
        return dict(PRESETS[host_name])

    # Case-insensitive alias matching
    _ALIASES: Dict[str, str] = {
        # Rice
        "rice":                     "Rice",
        "oryza sativa":             "Rice",
        "oryza":                    "Rice",
        "o. sativa":                "Rice",
        # Arabidopsis
        "arabidopsis":              "Arabidopsis",
        "arabidopsis thaliana":     "Arabidopsis",
        "a. thaliana":              "Arabidopsis",
        "at":                       "Arabidopsis",
        # E. coli
        "e.coli":                   "E.coli",
        "e. coli":                  "E.coli",
        "ecoli":                    "E.coli",
        "escherichia coli":         "E.coli",
        "e.coli bl21(de3)":         "E.coli",
        "e.coli bl21":              "E.coli",
        "e. coli bl21(de3)":        "E.coli",
        "e.coli dh5alpha":          "E.coli",
    }

    canonical = _ALIASES.get(host_name.strip().lower())
    if canonical and canonical in PRESETS:
        return dict(PRESETS[canonical])

    # Partial substring match as last resort
    host_lower = host_name.lower()
    for keyword, canonical_key in (("rice", "Rice"), ("arabidopsis", "Arabidopsis"),
                                    ("coli", "E.coli")):
        if keyword in host_lower:
            return dict(PRESETS[canonical_key])

    return dict(GENERIC_PRESET)


def list_supported_hosts() -> list[str]:
    """Return the list of canonical host names with defined presets."""
    return list(PRESETS.keys())

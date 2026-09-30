"""Build the reviewed Plant Component Registry V1 data expansion.

This is a deterministic curation helper.  It reads byte-preserved public
GenBank source records, reproduces each documented boundary, and refreshes the
single authoritative Registry document, per-component FASTA files, and source
manifest.  It does not grant formal workflow admission.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from Bio import SeqIO


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_ROOT = ROOT / "data" / "plant_component_registry_v1"
REGISTRY_PATH = REGISTRY_ROOT / "registry.batch1.json"
SOURCE_ROOT = REGISTRY_ROOT / "source_records"
SEQUENCE_ROOT = REGISTRY_ROOT / "sequences"
MANIFEST_PATH = REGISTRY_ROOT / "source_manifest.csv"

BASE_IDS = {
    "PCLV1-PRO-35S-835",
    "PCLV1-3REG-NOS-256",
    "PCLV1-3REG-NOS-253",
    "PCLV1-CDS-NPTII",
    "PCLV1-CDS-GUSA",
    "PCLV1-CDS-CYP76AD1",
    "PCLV1-CDS-DODA1",
    "PCLV1-CDS-CDOPA5GT",
    "PCLV1-PRO-UBQ10",
    "PCLV1-PRO-UBI1",
    "PCLV1-TER-OCS",
    "PCLV1-VEC-PBIN19",
    "PCLV1-PRO-FMVT",
}


@dataclass(frozen=True)
class ComponentSpec:
    component_id: str
    display_name: str
    component_type: str
    component_role: str
    accession_version: str
    source_organism: str
    target_host_species: tuple[str, ...]
    host_group: tuple[str, ...]
    primary_reference: str
    evidence_level: str
    start: int
    end: int
    strand: str
    reverse_complemented: bool
    feature_type: str
    feature_label: str
    boundary_method: str
    plasmid_id: str | None
    aliases: tuple[str, ...]
    evidence_context: str
    limitations: str
    review_status: str
    notes: str


SPECS = (
    ComponentSpec(
        "PCLV1-PRO-35S2-758",
        "Duplicated CaMV 35S promoter (758 bp feature)",
        "promoter",
        "duplicated constitutive viral promoter",
        "DQ370426.1",
        "Cauliflower mosaic virus",
        (),
        ("plant expression context",),
        "NCBI GenBank DQ370426.1; Zhang and Galbraith direct submission (2006)",
        "E1",
        1,
        758,
        "+",
        False,
        "regulatory",
        "cauliflower mosaic virus 35S promoter; duplicated",
        "GenBank regulatory feature coordinates",
        "pCsGFPBT",
        ("2x35S", "CaMV35S2"),
        "The deposited binary-vector record directly annotates bases 1..758 as a duplicated CaMV 35S promoter.",
        "The record supports sequence identity and source-vector context only; expression magnitude, host range, and experimental performance were not assessed.",
        "source_and_boundary_reviewed",
        "Catalog context only; no automatic promoter ranking or host recommendation is implied.",
    ),
    ComponentSpec(
        "PCLV1-PRO-RD29A-824",
        "AtRD29A promoter region (824 bp deposited record)",
        "promoter",
        "stress-responsive promoter",
        "AY973635.1",
        "Arabidopsis thaliana",
        ("Arabidopsis thaliana",),
        ("dicot",),
        "NCBI GenBank AY973635.1; Zhang, Si and Wang, Zuo Wu Xue Bao 31, 159-164 (2005)",
        "E2",
        1,
        824,
        "+",
        False,
        "regulatory",
        "rd29A promoter",
        "Record-spanning GenBank regulatory feature with fuzzy endpoints normalized to deposited bases 1..824",
        None,
        ("AtRD29A", "RD29A"),
        "The complete deposited record is annotated as the Arabidopsis rd29A promoter region.",
        "Both feature endpoints are fuzzy in the source annotation. Stress responsiveness is literature context, not a prediction for a new construct or host.",
        "manual_context_review_required",
        "The normalized whole-record boundary is reproducible; endpoint interpretation remains explicitly review-marked.",
    ),
    ComponentSpec(
        "PCLV1-PRO-E8-2164",
        "Tomato E8 promoter (2164 bp feature)",
        "promoter",
        "fruit-associated ethylene-responsive promoter",
        "KJ561284.1",
        "Solanum lycopersicum",
        ("Solanum lycopersicum",),
        ("dicot",),
        "NCBI GenBank KJ561284.1; Hong et al. direct submission (2014); Deikman and Fischer, EMBO J. 7, 3315-3320 (1988)",
        "E1",
        1,
        2164,
        "+",
        False,
        "regulatory",
        "E8 tomato fruit specific promoter",
        "GenBank regulatory feature coordinates",
        None,
        ("E8", "SlE8"),
        "The deposited record directly annotates bases 1..2164 as the tomato E8 promoter and includes a linked 5' UTR feature.",
        "Fruit-associated and ethylene-responsive wording is source/literature context. Developmental timing, cultivar transferability, and expression performance were not assessed.",
        "source_and_boundary_reviewed",
        "This is a provenance-supported catalog record, not a recommendation for fruit-specific expression.",
    ),
    ComponentSpec(
        "PCLV1-PRO-LEB4-2697",
        "Vicia faba legumin B LeB4 upstream region",
        "promoter",
        "seed-associated legumin promoter region",
        "X03677.1",
        "Vicia faba",
        ("Vicia faba",),
        ("dicot",),
        "NCBI GenBank X03677.1; Baumlein et al., Nucleic Acids Res. 14, 2707-2720 (1986), PMID:3960730",
        "E2",
        1,
        2697,
        "+",
        False,
        "derived_upstream_region",
        "LeB4 sequence upstream of the putative cap site",
        "Deposited record start through the base preceding the annotated putative cap site",
        None,
        ("LeB4 promoter", "legumin B promoter"),
        "The boundary is derived from the deposited record start and the annotated putative cap site; the record also annotates the legumin box and TATA box.",
        "The source record does not annotate the full 1..2697 interval as one promoter feature. Seed-associated function and the chosen upstream extent require manual context review.",
        "manual_context_review_required",
        "Boundary derivation is explicit and reproducible; no cross-species activity conclusion is made.",
    ),
    ComponentSpec(
        "PCLV1-5UTR-E8-39",
        "Tomato E8 native 5' UTR (39 bp feature)",
        "five_prime_utr",
        "native plant 5' untranslated region",
        "KJ561284.1",
        "Solanum lycopersicum",
        ("Solanum lycopersicum",),
        ("dicot",),
        "NCBI GenBank KJ561284.1; Hong et al. direct submission (2014)",
        "E1",
        2165,
        2203,
        "+",
        False,
        "5'UTR",
        "E8 5' UTR",
        "GenBank 5'UTR feature coordinates",
        None,
        ("E8 5'UTR",),
        "The deposited E8 promoter-region record directly annotates bases 2165..2203 as a 5' UTR.",
        "The record supports native transcript context only. Translation efficiency, Kozak strength, and portability were not assessed.",
        "source_and_boundary_reviewed",
        "Native sequence context is preserved as a review record; no translation enhancement claim is made.",
    ),
    ComponentSpec(
        "PCLV1-5UTR-TEV-136",
        "Tobacco etch virus translation leader (136 bp feature)",
        "five_prime_utr",
        "viral translation leader used in a plant binary vector",
        "DQ370426.1",
        "Tobacco etch virus",
        (),
        ("plant translation context",),
        "NCBI GenBank DQ370426.1; Zhang and Galbraith direct submission (2006)",
        "E1",
        759,
        894,
        "+",
        False,
        "5'UTR",
        "translation leader sequence; 5'UTR from tobacco etch virus",
        "GenBank 5'UTR feature coordinates",
        "pCsGFPBT",
        ("TEV leader", "TEV 5'UTR"),
        "The deposited plant binary-vector record directly annotates bases 759..894 as a TEV-derived translation leader/5' UTR.",
        "The sequence is cataloged from one deposited construct. Translation enhancement, host range, and compatibility with a new coding sequence were not assessed.",
        "source_and_boundary_reviewed",
        "Translation-related role follows the source annotation and does not constitute an optimization claim.",
    ),
    ComponentSpec(
        "PCLV1-5UTR-CYP76AD1-258",
        "Beta vulgaris CYP76AD1 native 5' UTR",
        "five_prime_utr",
        "native plant mRNA 5' untranslated region",
        "HQ656023.1",
        "Beta vulgaris",
        ("Beta vulgaris",),
        ("dicot",),
        "NCBI GenBank HQ656023.1; Hatlestad et al., Nat. Genet. 44, 816-820 (2012)",
        "E2",
        1,
        258,
        "+",
        False,
        "derived_5'UTR",
        "sequence preceding the annotated CYP76AD1 CDS",
        "Complete-mRNA record start through the base preceding the annotated CDS",
        None,
        ("CYP76AD1 5'UTR",),
        "The source is an mRNA record described as complete CDS; bases 1..258 precede the annotated CDS.",
        "NCBI does not provide a separate 5'UTR feature on this record. Transcript completeness at the 5' end and translation effects require manual review.",
        "manual_context_review_required",
        "This inferred native 5' UTR is retained for provenance review, not translation scoring.",
    ),
    ComponentSpec(
        "PCLV1-5UTR-DODA1-59",
        "Beta vulgaris DODA1 native 5' UTR",
        "five_prime_utr",
        "native plant mRNA 5' untranslated region",
        "HQ656027.1",
        "Beta vulgaris",
        ("Beta vulgaris",),
        ("dicot",),
        "NCBI GenBank HQ656027.1; Hatlestad et al., Nat. Genet. 44, 816-820 (2012)",
        "E2",
        1,
        59,
        "+",
        False,
        "derived_5'UTR",
        "sequence preceding the annotated DODA1 CDS",
        "Complete-mRNA record start through the base preceding the annotated CDS",
        None,
        ("DODA1 5'UTR",),
        "The source is an mRNA record described as complete CDS; bases 1..59 precede the annotated CDS.",
        "NCBI does not provide a separate 5'UTR feature on this record. Transcript completeness at the 5' end and translation effects require manual review.",
        "manual_context_review_required",
        "This inferred native 5' UTR is retained for provenance review, not translation scoring.",
    ),
    ComponentSpec(
        "PCLV1-5UTR-CDOPA5GT-21",
        "Mirabilis jalapa cDOPA5GT native 5' UTR",
        "five_prime_utr",
        "native plant mRNA 5' untranslated region",
        "AB182643.1",
        "Mirabilis jalapa",
        ("Mirabilis jalapa",),
        ("dicot",),
        "NCBI GenBank AB182643.1; Sasaki et al., Plant Cell Physiol. 46, 666-670 (2005)",
        "E2",
        1,
        21,
        "+",
        False,
        "derived_5'UTR",
        "sequence preceding the annotated cDOPA5GT CDS",
        "Complete-mRNA record start through the base preceding the annotated CDS",
        None,
        ("cDOPA5GT 5'UTR",),
        "The source is an mRNA record described as complete CDS; bases 1..21 precede the annotated CDS.",
        "NCBI does not provide a separate 5'UTR feature on this record. Transcript completeness at the 5' end and translation effects require manual review.",
        "manual_context_review_required",
        "This inferred native 5' UTR is retained for provenance review, not translation scoring.",
    ),
    ComponentSpec(
        "PCLV1-3REG-CAMV35S-212",
        "CaMV 35S polyadenylation region (212 bp feature)",
        "three_prime_regulatory_region",
        "viral 3' regulatory region",
        "DQ370426.1",
        "Cauliflower mosaic virus",
        (),
        ("plant expression context",),
        "NCBI GenBank DQ370426.1; Zhang and Galbraith direct submission (2006)",
        "E1",
        1624,
        1835,
        "+",
        False,
        "regulatory",
        "cauliflower mosaic virus 35S poly(A) signal",
        "GenBank regulatory feature coordinates",
        "pCsGFPBT",
        ("CaMV 35S poly(A)", "35S 3' regulatory region"),
        "The deposited binary-vector record directly annotates bases 1624..1835 as a CaMV 35S poly(A) signal.",
        "The feature is cataloged as a 3' regulatory region, not globally renamed a terminator. Processing efficiency and host transferability were not assessed.",
        "source_and_boundary_reviewed",
        "Terminology follows the deposited feature and Registry boundary policy.",
    ),
    ComponentSpec(
        "PCLV1-3REG-E8-140",
        "Tomato E8 transcript 3' region",
        "three_prime_regulatory_region",
        "native plant transcript 3' region",
        "X13437.1",
        "Solanum lycopersicum",
        ("Solanum lycopersicum",),
        ("dicot",),
        "NCBI GenBank X13437.1; Deikman and Fischer, EMBO J. 7, 3315-3320 (1988), PMID:3208738",
        "E2",
        2711,
        2850,
        "+",
        False,
        "derived_3'transcript_region",
        "E8 sequence after the annotated CDS through the primary-transcript endpoint",
        "Annotated CDS end plus one through annotated primary-transcript end",
        None,
        ("E8 3' region",),
        "The boundary is derived from the annotated final CDS base, primary-transcript endpoint, poly(A) signal, and poly(A) site.",
        "NCBI does not label the complete interval as one terminator or 3'UTR feature. Transcript processing function and portability require manual review.",
        "manual_context_review_required",
        "Cataloged as a 3' regulatory region; no terminator equivalence or performance conclusion is asserted.",
    ),
    ComponentSpec(
        "PCLV1-3REG-LEB4-123",
        "Vicia faba legumin B transcript 3' region",
        "three_prime_regulatory_region",
        "native seed-gene transcript 3' region",
        "X03677.1",
        "Vicia faba",
        ("Vicia faba",),
        ("dicot",),
        "NCBI GenBank X03677.1; Baumlein et al., Nucleic Acids Res. 14, 2707-2720 (1986), PMID:3960730",
        "E2",
        4404,
        4526,
        "+",
        False,
        "derived_3'transcript_region",
        "LeB4 sequence after the annotated CDS through the primary-transcript endpoint",
        "Annotated CDS end plus one through annotated primary-transcript end",
        None,
        ("LeB4 3' region", "legumin B 3' region"),
        "The boundary is derived from the annotated CDS and primary-transcript endpoints; multiple poly(A) signals and a poly(A) site occur in the interval.",
        "NCBI does not label the complete interval as one terminator or 3'UTR feature. Processing function and portability require manual review.",
        "manual_context_review_required",
        "Cataloged as a 3' regulatory region; no terminator equivalence or performance conclusion is asserted.",
    ),
    ComponentSpec(
        "PCLV1-TER-HSP18-2-250",
        "Arabidopsis HSP18.2 terminator (250 bp feature)",
        "terminator",
        "Arabidopsis HSP18.2 transcription terminator",
        "PP558908.1",
        "Arabidopsis thaliana",
        ("Arabidopsis thaliana",),
        ("dicot",),
        "NCBI GenBank PP558908.1; Nagaya et al., Plant Cell Physiol. 51, 328-332 (2010), PMID:20040586, DOI:10.1093/pcp/pcp188",
        "E1",
        852,
        1101,
        "+",
        False,
        "regulatory",
        "HSP18.2 terminator",
        "GenBank regulatory terminator feature coordinates",
        "L0_hspt",
        ("HSP18.2 terminator", "tHSP18.2"),
        "PP558908.1 directly annotates bases 852..1101 as an HSP18.2 terminator; Nagaya et al. independently studied an Arabidopsis HSP18.2 terminator in plant cells.",
        "The GenBank feature fixes sequence identity and boundary. The cited study is retained as component-level literature context; its measured expression effects are not generalized to other constructs, hosts, tissues, or conditions.",
        "source_and_boundary_reviewed",
        "Catalog provenance and literature context do not grant formal workflow admission or imply expression performance.",
    ),
    ComponentSpec(
        "PCLV1-TER-RBCS-E9-295",
        "Pea rbcS E9 terminator (295 bp feature)",
        "terminator",
        "pea rbcS E9 transcription terminator",
        "AF309825.2",
        "Pisum sativum",
        ("Arabidopsis thaliana", "Nicotiana tabacum"),
        ("dicot",),
        "NCBI GenBank AF309825.2; Zuo, Niu and Chua, Plant J. 24, 265-273 (2000), PMID:11069700, DOI:10.1046/j.1365-313x.2000.00868.x",
        "E1",
        1882,
        2176,
        "+",
        False,
        "regulatory",
        "pea rbcS E9",
        "GenBank regulatory terminator feature coordinates",
        "pER8",
        ("rbcS E9 terminator", "pea E9 terminator"),
        "AF309825.2 directly annotates bases 1882..2176 as the pea rbcS E9 terminator in the published pER8 plant expression vector.",
        "The record supports exact identity, boundary, and source-vector context. Termination efficiency, expression effects, portability, and suitability outside the cited vector/study contexts were not assessed.",
        "source_and_boundary_reviewed",
        "The crop-derived terminator is retained as a provenance catalog record, not a recommendation or performance claim.",
    ),
    ComponentSpec(
        "PCLV1-CDS-HPTII",
        "hptII selectable marker CDS",
        "cds",
        "selectable marker CDS",
        "AF234296.1",
        "Escherichia coli",
        (),
        ("plant transformation context",),
        "NCBI GenBank AF234296.1; Hajdukiewicz, Svab and Maliga, Plant Mol. Biol. 25, 989-994 (1994), PMID:7919218",
        "E1",
        6873,
        7898,
        "-",
        True,
        "CDS",
        "hptII hygromycin phosphotransferase",
        "GenBank CDS feature coordinates",
        "pCAMBIA-1300",
        ("hpt", "hph", "hygromycin phosphotransferase"),
        "The pCAMBIA-1300 record directly annotates the reverse-strand hptII CDS used in a plant binary-vector context.",
        "Selection behavior depends on host, expression cassette, and experimental conditions; none is predicted or certified here.",
        "source_and_boundary_reviewed",
        "Reverse-complement extraction preserves the feature coding orientation.",
    ),
    ComponentSpec(
        "PCLV1-CDS-BAR",
        "bar phosphinothricin acetyltransferase CDS",
        "cds",
        "selectable marker CDS",
        "X17220.1",
        "Streptomyces hygroscopicus",
        (),
        ("plant transformation context",),
        "NCBI GenBank X17220.1; White et al., Nucleic Acids Res. 18, 1062 (1990), PMID:2315036",
        "E1",
        31,
        582,
        "+",
        False,
        "CDS",
        "phosphinothricin acetyltransferase",
        "GenBank CDS feature coordinates",
        None,
        ("bar", "PAT"),
        "The source record directly annotates the bar CDS and cites its use as a selectable marker for plant transformation.",
        "Selection behavior, regulatory compliance, host performance, and experimental conditions were not assessed.",
        "source_and_boundary_reviewed",
        "The catalog records sequence provenance only and does not recommend a selection system.",
    ),
    ComponentSpec(
        "PCLV1-CDS-SGFP",
        "synthetic GFP reporter CDS",
        "cds",
        "reporter CDS",
        "DQ370426.1",
        "Synthetic construct",
        (),
        ("plant expression context",),
        "NCBI GenBank DQ370426.1; Zhang and Galbraith direct submission (2006)",
        "E1",
        895,
        1623,
        "+",
        False,
        "CDS",
        "sGFP",
        "GenBank CDS feature coordinates",
        "pCsGFPBT",
        ("sGFP", "synthetic GFP"),
        "The deposited plant binary-vector record directly annotates the sGFP CDS and identifies it as a modified GFP reporter.",
        "Fluorescence, localization, expression level, and host performance were not assessed from the sequence record.",
        "source_and_boundary_reviewed",
        "Reporter role follows the source annotation; no assay outcome is claimed.",
    ),
    ComponentSpec(
        "PCLV1-VEC-PCAMBIA1300",
        "pCAMBIA-1300 complete binary-vector source",
        "vector_backbone",
        "complete plant transformation vector source",
        "AF234296.1",
        "Binary vector pCAMBIA-1300",
        (),
        ("plant transformation vector",),
        "NCBI GenBank AF234296.1; Hajdukiewicz, Svab and Maliga, Plant Mol. Biol. 25, 989-994 (1994), PMID:7919218",
        "E1",
        1,
        8958,
        "+",
        False,
        "source",
        "complete pCAMBIA-1300 sequence",
        "Complete deposited circular source record",
        "pCAMBIA-1300",
        ("pCAMBIA1300",),
        "The complete circular sequence and T-DNA border features are preserved from AF234296.1.",
        "This is a complete vector source, not an empty backbone. T-DNA replacement boundaries, workflow compatibility, and experimental suitability require separate professional review.",
        "source_and_boundary_reviewed",
        "Catalog provenance does not grant formal workflow admission.",
    ),
    ComponentSpec(
        "PCLV1-VEC-PPZP201",
        "pPZP201 complete binary-vector source",
        "vector_backbone",
        "complete plant transformation vector source",
        "U10489.1",
        "Cloning vector pPZP201",
        (),
        ("plant transformation vector",),
        "NCBI GenBank U10489.1; Hajdukiewicz, Svab and Maliga, Plant Mol. Biol. 25, 989-994 (1994), PMID:7919218",
        "E1",
        1,
        7132,
        "+",
        False,
        "source",
        "complete pPZP201 sequence",
        "Complete deposited circular source record",
        "pPZP201",
        ("pPZP-201",),
        "The complete circular record is deposited as a binary cloning vector for plant transformation.",
        "The record lacks detailed INSDC feature annotations. T-DNA replacement boundaries, workflow compatibility, and experimental suitability require manual review.",
        "manual_context_review_required",
        "Whole-record identity is verified; feature-level interpretation is intentionally not supplied.",
    ),
    ComponentSpec(
        "PCLV1-VEC-PCSGFPBT",
        "pCsGFPBT complete binary-vector source",
        "vector_backbone",
        "complete reporter plant binary-vector source",
        "DQ370426.1",
        "Binary vector pCsGFPBT",
        (),
        ("plant transformation vector",),
        "NCBI GenBank DQ370426.1; Zhang and Galbraith direct submission (2006)",
        "E1",
        1,
        11437,
        "+",
        False,
        "source",
        "complete pCsGFPBT sequence",
        "Complete deposited circular source record",
        "pCsGFPBT",
        ("pCs-GFP-BT",),
        "The complete circular record includes annotated T-DNA borders, reporter cassette elements, and pCAMBIA-derived vector sequence.",
        "This is a populated reporter vector, not an empty backbone. Replacement boundaries, workflow compatibility, and experimental suitability require separate professional review.",
        "source_and_boundary_reviewed",
        "Catalog provenance does not grant formal workflow admission.",
    ),
    ComponentSpec(
        "PCLV1-VEC-PGWB8",
        "pGWB8 complete Gateway binary-vector source",
        "vector_backbone",
        "complete Gateway plant binary-vector source",
        "AB289771.1",
        "Gateway binary vector pGWB8",
        (),
        ("plant transformation vector",),
        "NCBI GenBank AB289771.1; Nakagawa et al., J. Biosci. Bioeng. 104, 34-41 (2007), PMID:17697981",
        "E1",
        1,
        17254,
        "+",
        False,
        "source",
        "complete pGWB8 sequence",
        "Complete deposited circular source record",
        "pGWB8",
        ("Gateway pGWB8",),
        "The complete circular record includes annotated T-DNA borders, Gateway cassette features, selectable-marker cassettes, and vector replication regions.",
        "This is a populated Gateway vector, not an empty backbone. Recombination operations, replacement boundaries, workflow compatibility, and experimental suitability require separate review.",
        "source_and_boundary_reviewed",
        "Catalog provenance does not grant formal workflow admission.",
    ),
)


def _sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_sequence(sequence: str) -> str:
    return hashlib.sha256(sequence.encode("ascii")).hexdigest()


def _extract(spec: ComponentSpec) -> str:
    source_path = SOURCE_ROOT / f"{spec.accession_version}.gb"
    record = SeqIO.read(source_path, "genbank")
    if spec.start < 1 or spec.end > len(record.seq) or spec.start > spec.end:
        raise ValueError(f"{spec.component_id}: invalid boundary for {spec.accession_version}")
    sequence = record.seq[spec.start - 1 : spec.end]
    if spec.reverse_complemented:
        sequence = sequence.reverse_complement()
    return str(sequence).upper()


def _record(spec: ComponentSpec) -> dict[str, object]:
    source_path = SOURCE_ROOT / f"{spec.accession_version}.gb"
    sequence = _extract(spec)
    accession = spec.accession_version.rsplit(".", 1)[0]
    return {
        "schema_version": "plant-component-registry-v1",
        "component_id": spec.component_id,
        "display_name": spec.display_name,
        "component_type": spec.component_type,
        "component_role": spec.component_role,
        "sequence": sequence,
        "sequence_length": len(sequence),
        "sequence_sha256": _sha256_sequence(sequence),
        "source_organism": spec.source_organism,
        "target_host_species": list(spec.target_host_species),
        "host_group": list(spec.host_group),
        "accession": accession,
        "accession_version": spec.accession_version,
        "plasmid_id": spec.plasmid_id,
        "primary_reference": spec.primary_reference,
        "evidence_level": spec.evidence_level,
        "evidence_context": spec.evidence_context,
        "feature_boundary_method": {
            "method": spec.boundary_method,
            "feature_type": spec.feature_type,
            "feature_label": spec.feature_label,
            "strand": spec.strand,
            "start_one_based": spec.start,
            "end_one_based_inclusive": spec.end,
            "crosses_origin": False,
            "reverse_complemented": spec.reverse_complemented,
            "extraction": "zero-based half-open slice from parsed GenBank record",
        },
        "source_record": f"data/plant_component_registry_v1/source_records/{spec.accession_version}.gb",
        "source_record_sha256": _sha256_bytes(source_path),
        "redistribution_status": "PUBLIC_NCBI_RECORD_RIGHTS_CAVEAT_RECORDED",
        "workflow_fit": "Provenance-supported Registry catalog record; not admitted to formal workflow selection.",
        "aliases": list(spec.aliases),
        "limitations": spec.limitations,
        "review_status": spec.review_status,
        "notes": spec.notes,
    }


def _augment_existing(record: dict[str, object]) -> dict[str, object]:
    evidence_level = str(record["evidence_level"])
    if evidence_level == "E1":
        evidence_context = (
            "Source accession, byte-preserved local record, sequence hash, and direct feature "
            "boundary were checked for Registry traceability."
        )
        limitations = (
            "The record supports sequence identity and cited source context only; biological "
            "performance, cross-host transferability, and experimental suitability were not assessed."
        )
        review_status = "source_and_boundary_reviewed"
    else:
        evidence_context = (
            "Source accession, byte-preserved local record, sequence hash, and documented boundary "
            "interpretation were checked for Registry traceability."
        )
        limitations = (
            "The sequence/source relationship is reviewable, but biological role, cross-host "
            "transferability, and experimental suitability retain documented context limitations."
        )
        review_status = "source_sequence_reviewed_context_limited"
    record.setdefault("evidence_context", evidence_context)
    record.setdefault("limitations", limitations)
    record.setdefault("review_status", review_status)
    return record


def _write_fasta(record: dict[str, object]) -> None:
    sequence = str(record["sequence"])
    lines = [
        f">{record['component_id']} {record['display_name']}",
        *(sequence[index : index + 70] for index in range(0, len(sequence), 70)),
    ]
    (SEQUENCE_ROOT / f"{record['component_id']}.fasta").write_text(
        "\n".join(lines) + "\n", encoding="ascii", newline="\n"
    )


def build() -> None:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    base_records = [
        record
        for record in payload["records"]
        if str(record.get("component_id")) in BASE_IDS
    ]
    observed_base_ids = {str(record["component_id"]) for record in base_records}
    if observed_base_ids != BASE_IDS or len(base_records) != len(BASE_IDS):
        raise ValueError("Existing Registry baseline does not match the reviewed 13-record input")

    records = [_augment_existing(dict(record)) for record in base_records]
    records.extend(_record(spec) for spec in SPECS)
    ids = [str(record["component_id"]) for record in records]
    if len(records) != 34 or len(ids) != len(set(ids)):
        raise ValueError("Expansion must produce exactly 34 unique component IDs")

    payload = {
        "registry_version": "v1-publication-minimum-expansion-20260824-draft",
        "records": records,
    }
    REGISTRY_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    for record in records:
        fasta_path = SEQUENCE_ROOT / f"{record['component_id']}.fasta"
        if fasta_path.exists():
            existing_sequence = "".join(
                line.strip()
                for line in fasta_path.read_text(encoding="ascii").splitlines()
                if not line.startswith(">")
            )
            if existing_sequence != record["sequence"]:
                raise ValueError(f"{record['component_id']}: existing FASTA sequence drift")
        else:
            _write_fasta(record)

    fields = (
        "component_id",
        "accession_version",
        "source_record",
        "source_record_sha256",
        "evidence_level",
        "redistribution_status",
    )
    with MANIFEST_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for record in records:
            writer.writerow({field: record[field] for field in fields})


if __name__ == "__main__":
    build()

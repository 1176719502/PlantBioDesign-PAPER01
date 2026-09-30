"""
core/seed_database.py
Seeds the unified SQLite DB with real biological parts.
Safe to run multiple times; only missing seed keys are inserted. Call seed_all() on startup.
"""
import os
import sqlite3

from core.config import DB_PATH

SEED_VERSION = 10000
SEED_RELEASE_TIMESTAMP = "2026-07-22T00:00:00+00:00"
SEED_RELEASE_DATE = "2026-07-22"
NOW = SEED_RELEASE_TIMESTAMP


def _insert_seed_rows(
    cursor: sqlite3.Cursor,
    table: str,
    key_column: str,
    insert_sql: str,
    rows: list[tuple],
) -> bool:
    """Insert only missing seed keys so ignored AUTOINCREMENT inserts do not advance sequences."""
    existing_keys = {
        row[0]
        for row in cursor.execute(
            f"SELECT {key_column} FROM {table}"
        ).fetchall()
    }
    pending_rows = [row for row in rows if row[0] not in existing_keys]
    if pending_rows:
        cursor.executemany(insert_sql, pending_rows)
    return bool(pending_rows)


def seed_all(connection: sqlite3.Connection | None = None) -> bool:
    """Insert all seed data by stable key without updating existing rows."""
    if connection is None and not os.path.exists(DB_PATH):
        print(f"[Seed] DB not found at {DB_PATH} — run app once to initialise.")
        return False
    owns_connection = connection is None
    conn = connection or sqlite3.connect(DB_PATH)
    c = conn.cursor()
    changed = False
    changed |= _seed_promoters(c)
    changed |= _seed_genes(c)
    changed |= _seed_terminators(c)
    changed |= _seed_tags(c)
    changed |= _seed_rbs(c)
    changed |= _seed_plasmids(c)
    changed |= _seed_strains(c)
    changed |= _seed_primers(c)
    if changed and owns_connection:
        conn.commit()
    if owns_connection:
        conn.close()
    print("[Seed] Parts library seeded successfully.")
    return changed


def _seed_promoters(c):
    rows = [
        ("PRO_CAMV35S", "CaMV 35S Promoter", "Promoter", "", 400,
         "Dicot,Universal Plant,Tobacco,Arabidopsis,Tomato",
         "Constitutive", "No", "Strong",
         "Cauliflower Mosaic Virus 35S promoter. Constitutive strong expression "
         "in most dicots. Most widely used promoter in plant biotechnology.",
         "GenBank: V00141.1", "Well-characterised", "#1e88e5",
         "AAAC", "AATG", NOW, NOW),
        ("PRO_ZMUBI1", "Maize Ubiquitin-1 Promoter", "Promoter", "", 1950,
         "Monocot,Maize,Rice,Wheat,Barley,Sugarcane",
         "Constitutive", "No", "Strong",
         "ZmUbi1 promoter with first intron. Preferred constitutive promoter for "
         "monocot transformation. Intron enhances expression 10-50x.",
         "GenBank: S94464.1", "Well-characterised", "#43a047",
         "AAAC", "AATG", NOW, NOW),
        ("PRO_OSACT1", "Rice Actin-1 Promoter", "Promoter", "", 1300,
         "Monocot,Rice,Maize,Barley",
         "Constitutive", "No", "Strong",
         "OsAct1 promoter with first intron. Strong constitutive expression in "
         "monocots. Widely used for rice transformation.",
         "GenBank: S44221.1", "Well-characterised", "#00897b",
         "AAAC", "AATG", NOW, NOW),
        ("PRO_NOS", "Nopaline Synthase Promoter", "Promoter", "", 290,
         "Agrobacterium,Plant,Dicot",
         "Constitutive (weak)", "No", "Medium",
         "NOS promoter from Agrobacterium Ti-plasmid. Drives selectable marker "
         "genes in plant transformation constructs. Weaker than CaMV 35S.",
         "GenBank: V00087.1", "Well-characterised", "#8e24aa",
         "AAAC", "AATG", NOW, NOW),
        ("PRO_PBAD", "Arabinose-Inducible Promoter (pBAD)", "Promoter", "", 202,
         "E. coli,Bacteria",
         "Inducible", "Yes - L-arabinose", "Inducible (medium-strong)",
         "E. coli araBAD operon promoter. Induced by L-arabinose, repressed by "
         "glucose. Inducer: 0.002-0.2% L-arabinose.",
         "BioBrick: BBa_I0500", "Well-characterised", "#f4511e",
         "AAAC", "AATG", NOW, NOW),
        ("PRO_PT7", "T7 RNA Polymerase Promoter", "Promoter",
         "TAATACGACTCACTATA", 17,
         "E. coli,BL21(DE3),Bacteria",
         "Constitutive (T7 RNAP required)", "Yes - IPTG via T7 RNAP",
         "Very Strong",
         "T7 phage promoter. Used in pET vectors with BL21(DE3). Highest "
         "recombinant protein yields in E. coli. Induced by IPTG.",
         "BioBrick: BBa_I712074", "Well-characterised", "#e53935",
         "AAAC", "AATG", NOW, NOW),
        ("PRO_PLAC", "lac Promoter (Plac)", "Promoter", "", 107,
         "E. coli,Bacteria",
         "Inducible", "Yes - IPTG", "Medium",
         "E. coli lactose operon promoter. Induced by IPTG, repressed by LacI. "
         "Basis for many prokaryotic expression vector systems.",
         "BioBrick: BBa_R0010", "Well-characterised", "#fb8c00",
         "AAAC", "AATG", NOW, NOW),
    ]
    changed = _insert_seed_rows(
        c, "promoters", "id",
        "INSERT INTO promoters "
        "(id,name,type,sequence,length,chassis_compatibility,tissue_specificity,"
        "inducible,strength,description,source_id,evidence_level,color,"
        "overhangs_5,overhangs_3,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    print(f"  Promoters: {len(rows)} records processed.")
    return changed


def _seed_genes(c):
    rows = [
        ("GENE_SPCAS9", "SpCas9 (Streptococcus pyogenes Cas9)",
         "Nuclease", "", 4107,
         "Universal,E. coli,Plant,Mammalian", "CRISPR-Cas Nuclease",
         "Most widely used CRISPR-Cas9 nuclease. Creates blunt-ended DSBs 3 bp "
         "upstream of NGG PAM. 4107 bp CDS (1368 aa). Requires codon optimisation "
         "for plant expression. NLS required for nuclear targeting.",
         "GenBank: NC_002737.2", "Well-characterised", "#d32f2f",
         "AATG", "TTTT", NOW, NOW),
        ("GENE_UIDA", "uidA - Beta-glucuronidase (GUS Reporter)",
         "Reporter", "", 1812,
         "Universal,Plant,E. coli,Bacteria", "Reporter Gene",
         "E. coli GUS reporter. Detected histochemically (X-Gluc, blue staining) "
         "or fluorometrically (4-MUG). Gold standard reporter for plant "
         "transformation screening.",
         "GenBank: M14641.1", "Well-characterised", "#1565c0",
         "AATG", "TTTT", NOW, NOW),
        ("GENE_MGFP5", "mGFP5 - ER-localized Green Fluorescent Protein",
         "Reporter", "", 720,
         "Eukaryote,Plant,Mammalian", "Reporter Gene",
         "GFP variant optimised for plant expression. Targeted to ER via "
         "N-terminal signal peptide and C-terminal HDEL retention signal. "
         "Ex 395/473 nm, Em 509 nm.",
         "GenBank: U87973.1", "Well-characterised", "#2e7d32",
         "AATG", "TTTT", NOW, NOW),
        ("GENE_HPTII", "hptII - Hygromycin B Phosphotransferase",
         "Selection Marker", "", 1026,
         "Universal,Plant,E. coli,Mammalian",
         "Antibiotic Resistance / Selectable Marker",
         "HygR from E. coli. Confers resistance to hygromycin B. Standard "
         "selectable marker for plant and mammalian transformation. "
         "Selection: 15-50 mg/L hygromycin B.",
         "GenBank: V01499.1", "Well-characterised", "#6a1b9a",
         "AATG", "TTTT", NOW, NOW),
        ("GENE_BAR", "bar - Phosphinothricin Acetyltransferase (Basta/PPT)",
         "Selection Marker", "", 552,
         "Plant,Monocot,Dicot", "Herbicide Resistance / Selectable Marker",
         "PAT from Streptomyces hygroscopicus. Confers resistance to "
         "glufosinate-ammonium (Basta/PPT). Commercial herbicide-tolerance trait. "
         "Selection: 2-10 mg/L PPT.",
         "GenBank: X17220.1", "Well-characterised", "#558b2f",
         "AATG", "TTTT", NOW, NOW),
        ("GENE_NPTII", "nptII - Neomycin Phosphotransferase II (KanR)",
         "Selection Marker", "", 795,
         "Universal,Plant,E. coli",
         "Antibiotic Resistance / Selectable Marker",
         "NPT II from Tn5. Confers resistance to kanamycin and G418. Most common "
         "selectable marker in Agrobacterium-mediated plant transformation. "
         "Selection: 50-100 mg/L kanamycin.",
         "BioBrick: BBa_P1003", "Well-characterised", "#f57f17",
         "AATG", "TTTT", NOW, NOW),
        ("GENE_LUC", "luc - Firefly Luciferase Reporter",
         "Reporter", "", 1653,
         "Universal,Plant,Mammalian,E. coli", "Reporter Gene",
         "Firefly luciferase (Photinus pyralis). Bioluminescent reporter requiring "
         "luciferin and ATP. Used for promoter activity assays. High sensitivity "
         "and wide dynamic range.",
         "GenBank: M15077.1", "Well-characterised", "#fdd835",
         "AATG", "TTTT", NOW, NOW),
        ("GENE_DREB1A", "DREB1A - Drought/Cold Tolerance Transcription Factor",
         "Transcription Factor", "", 660,
         "Plant,Arabidopsis,Rice,Wheat", "Stress Tolerance",
         "Dehydration-responsive element binding protein 1A from Arabidopsis. "
         "Activates stress-responsive genes under drought, cold, and salt stress. "
         "Used in crop improvement for abiotic stress tolerance.",
         "GenBank: AB007791.1", "Well-characterised", "#0277bd",
         "AATG", "TTTT", NOW, NOW),
    ]
    changed = _insert_seed_rows(
        c, "genes", "id",
        "INSERT INTO genes "
        "(id,name,type,sequence,length,chassis_compatibility,function_category,"
        "description,source_id,evidence_level,color,overhangs_5,overhangs_3,"
        "created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    print(f"  Genes: {len(rows)} records processed.")
    return changed


def _seed_terminators(c):
    rows = [
        ("TER_NOS", "Nopaline Synthase Terminator (NOS-ter)",
         "Terminator", "", 260,
         "Plant,Dicot,Agrobacterium", "High",
         "NOS 3' terminator from Agrobacterium Ti-plasmid. Most widely used "
         "transcriptional terminator in plant expression vectors.",
         "GenBank: V00087.1", "Well-characterised", "#c62828",
         "TTTT", "AAAC", NOW, NOW),
        ("TER_35S", "CaMV 35S Terminator",
         "Terminator", "", 200,
         "Plant,Universal", "High",
         "CaMV 35S polyA signal and terminator. Alternative to NOS terminator "
         "in plant vectors. Efficient 3' mRNA processing.",
         "GenBank: V00141.1", "Well-characterised", "#b71c1c",
         "TTTT", "AAAC", NOW, NOW),
        ("TER_T7", "T7 Phage Terminator (Te)",
         "Terminator", "", 60,
         "E. coli,Bacteria", "Very High",
         "T7 phage Te terminator. Stable stem-loop followed by poly-U. "
         "Terminates T7 RNAP and E. coli RNAP efficiently. Standard in pET vectors.",
         "BioBrick: BBa_B0010", "Well-characterised", "#e53935",
         "TTTT", "AAAC", NOW, NOW),
        ("TER_RNBT1", "rrnB T1 Terminator (E. coli)",
         "Terminator", "", 90,
         "E. coli,Bacteria", "High",
         "E. coli rrnB ribosomal RNA operon T1 terminator. Efficient "
         "Rho-independent terminator. Widely used in bacterial expression constructs.",
         "BioBrick: BBa_B0010", "Well-characterised", "#ef5350",
         "TTTT", "AAAC", NOW, NOW),
        ("TER_35SPOLY", "CaMV 35S Polyadenylation Signal",
         "Terminator", "", 180,
         "Plant,Eukaryote", "High",
         "CaMV 35S RNA polyadenylation signal. Directs efficient 3' cleavage and "
         "polyadenylation in plant cells.",
         "GenBank: V00141.1", "Well-characterised", "#d32f2f",
         "TTTT", "AAAC", NOW, NOW),
    ]
    changed = _insert_seed_rows(
        c, "terminators", "id",
        "INSERT INTO terminators "
        "(id,name,type,sequence,length,chassis_compatibility,efficiency,"
        "description,source_id,evidence_level,color,overhangs_5,overhangs_3,"
        "created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    print(f"  Terminators: {len(rows)} records processed.")
    return changed


def _seed_plasmids(c):
    rows = [
        ("pCAMBIA1300", "", "pCAMBIA", 8958,
         "Kanamycin (bacterial) / Hygromycin (plant)", "Plant",
         SEED_RELEASE_DATE, "Available",
         "Agrobacterium binary vector. hptII selectable marker (hygromycin), "
         "LB/RB T-DNA borders, MCS. Widely used for stable plant transformation."),
        ("pCAMBIA2300", "", "pCAMBIA", 7900,
         "Kanamycin", "Plant",
         SEED_RELEASE_DATE, "Available",
         "Agrobacterium binary vector with nptII selectable marker. T-DNA MCS. "
         "Suitable for Arabidopsis, tobacco, and rice transformation."),
        ("pET-28a(+)", "", "pET", 5369,
         "Kanamycin", "E. coli",
         SEED_RELEASE_DATE, "Available",
         "T7 promoter bacterial expression vector. N-terminal 6xHis-tag, T7-tag, "
         "thrombin cleavage site. Use with BL21(DE3). GenBank reference vector."),
        ("pET-21a(+)", "", "pET", 5443,
         "Ampicillin", "E. coli",
         SEED_RELEASE_DATE, "Available",
         "T7 promoter expression vector. C-terminal 6xHis-tag. Ampicillin "
         "resistance. High-level expression in BL21(DE3)."),
        ("pUC19", "", "pUC", 2686,
         "Ampicillin", "E. coli",
         SEED_RELEASE_DATE, "Available",
         "High-copy cloning vector. lacZ-alpha blue/white selection. MCS with "
         "13 unique restriction sites. GenBank: L09137."),
        ("pGreen0029", "", "pGreen", 3800,
         "Kanamycin", "Plant",
         SEED_RELEASE_DATE, "Available",
         "Minimal Agrobacterium binary vector. Requires pSoup helper plasmid. "
         "Compact backbone ideal for large insert cloning."),
    ]
    changed = _insert_seed_rows(
        c, "plasmids", "name",
        "INSERT INTO plasmids "
        "(name,sequence,backbone,size_bp,antibiotic_marker,species,"
        "entry_date,status,notes) "
        "VALUES (?,?,?,?,?,?,?,?,?)", rows)
    print(f"  Plasmids: {len(rows)} records processed.")
    return changed


def _seed_strains(c):
    rows = [
        ("EHA105",
         "Agrobacterium tumefaciens",
         "C58 background, super-virulent pTiBo542 Ti-plasmid disarmed, RifR",
         "-80C Freezer Box A1",
         SEED_RELEASE_DATE,
         "Super-virulent Agrobacterium strain. Preferred for monocot "
         "(rice, maize) and recalcitrant dicot transformation."),
        ("GV3101",
         "Agrobacterium tumefaciens",
         "C58 background, pMP90 helper plasmid, RifR, GentR",
         "-80C Freezer Box A2",
         SEED_RELEASE_DATE,
         "GV3101(pMP90) — standard strain for Arabidopsis floral dip "
         "transformation and transient N. benthamiana infiltration."),
        ("DH5alpha",
         "Escherichia coli",
         "recA1 endA1 gyrA96 thi-1 hsdR17 relA1 supE44 lambda-",
         "-80C Freezer Box B1",
         SEED_RELEASE_DATE,
         "General-purpose cloning strain. High transformation efficiency, "
         "blue/white screening capable. Not suitable for protein expression."),
        ("BL21(DE3)",
         "Escherichia coli",
         "F- ompT hsdSB(rB- mB-) gal dcm (DE3) lambda prophage with T7 RNAP",
         "-80C Freezer Box B2",
         SEED_RELEASE_DATE,
         "Standard strain for T7 promoter-based protein expression (pET vectors). "
         "Lon and OmpT protease deficient. Induce with IPTG."),
        ("Top10",
         "Escherichia coli",
         "F- mcrA delta(mrr-hsdRMS-mcrBC) phi80lacZdeltaM15 recA1 araD139",
         "-80C Freezer Box B3",
         SEED_RELEASE_DATE,
         "High-efficiency chemically competent cloning strain. Suitable for "
         "unstable or repetitive sequences. Used with pBAD vectors."),
    ]
    changed = _insert_seed_rows(
        c, "strains", "name",
        "INSERT INTO strains "
        "(name,species,genotype,storage_location,entry_date,notes) "
        "VALUES (?,?,?,?,?,?)", rows)
    print(f"  Strains: {len(rows)} records processed.")
    return changed


def _seed_primers(c):
    rows = [
        ("M13_Fwd_20", "GTAAAACGACGGCCAGT", 52.0, 52.9, "Universal",
         SEED_RELEASE_TIMESTAMP, "Validated",
         "Universal M13 forward sequencing primer (-20). Used for colony PCR "
         "and sequencing from pUC/pGEM vectors."),
        ("M13_Rev", "CAGGAAACAGCTATGAC", 48.0, 47.1, "Universal",
         SEED_RELEASE_TIMESTAMP, "Validated",
         "Universal M13 reverse sequencing primer. Used for colony PCR and "
         "sequencing from pUC/pGEM vectors."),
        ("T7_Promoter_Primer", "TAATACGACTCACTATA", 44.0, 41.2, "E. coli",
         SEED_RELEASE_TIMESTAMP, "Validated",
         "T7 promoter sequencing primer. Sequences inserts cloned downstream "
         "of T7 promoter in pET vectors."),
        ("SP6_Primer", "ATTTAGGTGACACTATAG", 46.0, 38.9, "Universal",
         SEED_RELEASE_TIMESTAMP, "Validated",
         "SP6 RNA polymerase promoter primer for sequencing and in vitro "
         "transcription from pGEM/pBluescript vectors."),
        ("NOS_Term_Fwd", "GAATCCTGTTGCCGGTCTTGCG", 62.0, 54.5, "Plant",
         SEED_RELEASE_TIMESTAMP, "Validated",
         "Forward sequencing primer for NOS terminator region. Used to verify "
         "correct insertion of gene of interest upstream of NOS-ter."),
        ("35S_Promoter_Fwd", "CGCACAATCCCACTATCCTTCG", 60.0, 54.5, "Plant",
         SEED_RELEASE_TIMESTAMP, "Validated",
         "Forward primer within CaMV 35S promoter region. Used to confirm "
         "promoter-GOI junction in plant expression cassettes."),
    ]
    changed = _insert_seed_rows(
        c, "primers", "name",
        "INSERT INTO primers "
        "(name,sequence,tm,gc_content,species,design_date,status,notes) "
        "VALUES (?,?,?,?,?,?,?,?)", rows)
    print(f"  Primers: {len(rows)} records processed.")
    return changed


def _seed_tags(c):
    rows = [
        ("TAG_6XHIS", "6x His-Tag", "Purification Tag",
         "CACCACCACCACCACCAC", 18, "Universal,E. coli,Plant,Mammalian",
         "Affinity Purification",
         "6x Histidine tag for Ni-NTA affinity purification. Most widely used protein purification tag.",
         "Synthetic", "Well-characterised", "#8d6e63", "AATG", "TTTT", NOW, NOW),
        ("TAG_FLAG", "FLAG Tag (DYKDDDDK)", "Epitope Tag",
         "GACTACAAAGACGATGACGATAAG", 24, "Universal,Plant,Mammalian,E. coli",
         "Immunodetection",
         "8-aa FLAG epitope tag. Detected by anti-FLAG M2 antibody. N-terminal placement preferred.",
         "Sigma-Aldrich", "Well-characterised", "#795548", "AATG", "TTTT", NOW, NOW),
        ("TAG_HA", "HA Tag (YPYDVPDYA)", "Epitope Tag",
         "TATCCGTATGATGTACCAGATTACGCG", 27, "Universal,Plant,Mammalian",
         "Immunodetection",
         "9-aa hemagglutinin epitope from influenza HA. Detected by anti-HA antibody (12CA5, 3F10).",
         "Synthetic", "Well-characterised", "#6d4c41", "AATG", "TTTT", NOW, NOW),
        ("TAG_MYC", "c-Myc Tag", "Epitope Tag",
         "GAACAAAAACTCATCTCAGAAGAGGATCTG", 30, "Universal,Mammalian,Plant",
         "Immunodetection",
         "10-aa c-Myc epitope tag. Detected by anti-Myc antibody (9E10). Used in Co-IP experiments.",
         "Synthetic", "Well-characterised", "#5e35b1", "AATG", "TTTT", NOW, NOW),
        ("TAG_GST", "GST Tag", "Purification Tag",
         "", 690, "E. coli,Bacteria",
         "Affinity Purification",
         "26 kDa GST fusion for glutathione-Sepharose purification. Promotes protein solubility.",
         "GenBank: M14654", "Well-characterised", "#2e7d32", "AATG", "TTTT", NOW, NOW),
        ("TAG_NLS", "SV40 Nuclear Localization Signal", "Localization Signal",
         "CCAAAGAAGAAGCGGAAGGTG", 21, "Eukaryote,Plant,Mammalian",
         "Subcellular Targeting",
         "SV40 Large T-antigen NLS (PKKKRKV). Directs fusion protein to nucleus. Essential for Cas9.",
         "GenBank: J02400", "Well-characterised", "#e91e63", "AATG", "TTTT", NOW, NOW),
        ("TAG_KDEL", "KDEL ER Retention Signal", "Localization Signal",
         "AAAGACGAGCTG", 12, "Eukaryote,Plant,Mammalian",
         "Subcellular Targeting",
         "C-terminal KDEL for ER retention. Targets proteins to the endoplasmic reticulum lumen.",
         "Synthetic", "Well-characterised", "#00838f", "AATG", "TTTT", NOW, NOW),
        ("TAG_MCHERRY", "mCherry Fluorescent Protein", "Fluorescent Tag",
         "", 711, "Universal,Plant,Mammalian",
         "Fluorescence Imaging",
         "Red fluorescent protein (Ex 587 nm, Em 610 nm). Monomer, photostable. Ideal co-localisation with GFP.",
         "GenBank: AY678264", "Well-characterised", "#e53935", "AATG", "TTTT", NOW, NOW),
    ]
    changed = _insert_seed_rows(
        c, "tags", "id",
        "INSERT INTO tags "
        "(id,name,type,sequence,length,chassis_compatibility,function_type,"
        "description,source_id,evidence_level,color,"
        "overhangs_5,overhangs_3,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    print(f"  Tags: {len(rows)} records processed.")
    return changed


def _seed_rbs(c):
    """Seed RBS/Kozak sequences into the tags table (type=RBS)."""
    rows = [
        ("RBS_STRONG_SD", "Strong Shine-Dalgarno (AGGAGGT)", "RBS",
         "AGGAGGT", 7, "E. coli,Bacteria", "Translation Initiation",
         "Strong SD for high-level expression in E. coli. 7 bp spacer to ATG.",
         "BioBrick: BBa_B0034", "Well-characterised", "#9c27b0", "AAAC", "AATG", NOW, NOW),
        ("RBS_MED_SD", "Standard Shine-Dalgarno (AGGAGG)", "RBS",
         "AGGAGG", 6, "E. coli,Bacteria", "Translation Initiation",
         "Standard SD for moderate expression in E. coli.",
         "BioBrick: BBa_B0032", "Well-characterised", "#8e24aa", "AAAC", "AATG", NOW, NOW),
        ("RBS_WEAK_SD", "Weak Shine-Dalgarno (AGGAG)", "RBS",
         "AGGAG", 5, "E. coli,Bacteria", "Translation Initiation",
         "Weak SD for fine-tuned low expression. Reduces metabolic burden for toxic proteins.",
         "BioBrick: BBa_B0031", "Well-characterised", "#7b1fa2", "AAAC", "AATG", NOW, NOW),
        ("RBS_KOZAK_OPT", "Optimal Kozak Sequence (GCCACCatg)", "RBS",
         "GCCACCATG", 9, "Eukaryote,Plant,Mammalian", "Translation Initiation",
         "Optimal Kozak consensus for eukaryotic translation. GCCACCatg maximises ribosome binding.",
         "Kozak 1987", "Well-characterised", "#1565c0", "AAAC", "AATG", NOW, NOW),
        ("RBS_KOZAK_MIN", "Minimal Kozak Sequence (ACCatg)", "RBS",
         "ACCATG", 6, "Eukaryote,Plant,Mammalian", "Translation Initiation",
         "Minimal Kozak context. Sufficient for moderate translation initiation in plants.",
         "Kozak 1987", "Well-characterised", "#1976d2", "AAAC", "AATG", NOW, NOW),
        ("RBS_YEAST_OPT", "Yeast Optimal Kozak", "RBS",
         "AAAAATGTCT", 10, "Yeast,Saccharomyces cerevisiae", "Translation Initiation",
         "Optimal translation initiation context for S. cerevisiae.",
         "Hamilton 2003", "Well-characterised", "#00695c", "AAAC", "AATG", NOW, NOW),
    ]
    changed = _insert_seed_rows(
        c, "tags", "id",
        "INSERT INTO tags "
        "(id,name,type,sequence,length,chassis_compatibility,function_type,"
        "description,source_id,evidence_level,color,"
        "overhangs_5,overhangs_3,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    print(f"  RBS/Kozak: {len(rows)} records processed.")
    return changed


if __name__ == "__main__":
    seed_all()

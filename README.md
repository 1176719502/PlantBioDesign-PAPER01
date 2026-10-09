# Plant BioDesign PAPER-01 publication snapshot

This public repository contains the PAPER-01 publication distribution bundle. It preserves a selected software snapshot and reconstruction metadata from the frozen submission sources. It is separate from V1.1 development and does not claim experimental expression or biological validation.

## Source and distribution identities

| Identity | Commit |
| --- | --- |
| Original frozen software source | `8ead74c060c32e653e746030e557398637a2c2fc` |
| Adopted R2.1 submission-package source | `42bfb04c215fcfe76334f4e5a40f9cde60ea2133` |
| This public repository snapshot reviewed on 2026-10-09 | `b2696fd618c087fb0fd6b92bc6b78e8e71785dc7` |

The original software tree is `53f8d4446f719678db363e4e373ddc88123fd80c`, with tag `paper-01-submission-snapshot-20260930`. The adopted package tree is `ee02bffe24c213aa3a9210a66bdd45249ef283c6`. These are distinct provenance roles; the public distribution repository does not reproduce either source repository's Git history. See [SOFTWARE_SNAPSHOT.md](SOFTWARE_SNAPSHOT.md).

## Download, install and run

Download the [fixed publication snapshot ZIP](https://github.com/1176719502/PlantBioDesign-PAPER01/archive/b2696fd618c087fb0fd6b92bc6b78e8e71785dc7.zip) and extract it. Open PowerShell in the repository root containing `source_snapshot/`, then follow [REPRODUCIBILITY.md](REPRODUCIBILITY.md).

Runtime files are under **`source_snapshot/`**. `requirements-runtime.lock`, `requirements.txt`, `START.bat` and `app.py` are not repository-root files. The reproducibility guide uses the explicit isolated interpreter and runtime commands; it does not require double-clicking the existing launcher.

## Installation and known behavior

- The Windows x64 / CPython 3.12 hash-locked list in `source_snapshot/requirements-runtime.lock` omits ReportLab. The separate `source_snapshot/requirements.txt` includes `reportlab==4.2.2` and a different dependency set. The two installation lists are not equivalent environments.
- The guide documents the locked path and its limitation. Installing the other requirements file has not been newly validated here and does not establish that report fidelity or project editing defects are fixed.
- This snapshot contains the pCAMBIA source file at the catalog contract's referenced path, `source_snapshot/case_inputs/rice_hsa/raw/AF234296.1.gb`. That differs from the early PlantBioDesign package, where the path is absent. Path presence is a static check; successful browser catalog selection has not been newly tested here.
- Existing operation records describe source-summary and reopen-editing limitations. Unadopted R5 or V1.1 fixes are not part of these installation instructions.

## Included materials

- [source_snapshot/](source_snapshot/): selected frozen software files.
- [metadata/](metadata/): component-state metadata.
- [supplement/](supplement/): MT-01 and MT-02 reconstruction metadata.
- [reproducibility/](reproducibility/): provenance records and source exclusions.
- [REPRODUCIBILITY.md](REPRODUCIBILITY.md): explicit startup and region-verification guide.
- [DATA_CODE_AVAILABILITY.md](DATA_CODE_AVAILABILITY.md): data/code availability scope.
- [PAPER01_GITHUB_PUBLICATION_MANIFEST.txt](PAPER01_GITHUB_PUBLICATION_MANIFEST.txt) and [PAPER01_GITHUB_PUBLICATION_SHA256.txt](PAPER01_GITHUB_PUBLICATION_SHA256.txt): integrity inventories.

The frozen component classifications are 171 total: 17 DIRECT_USE, 24 USER_SEQUENCE_ASSISTED, 95 REFERENCE_ONLY and 35 RETIRED. The design-facing core is 41; formal direct-admitted identities remain 2.

Complete MT-01/MT-02 derived sequence payloads are not redistributed. Use the versioned accessions, coordinates and hashes in the supplement for independent region reconstruction; this is not evidence of whole-plasmid reconstruction or biological performance.

## Licensing and review scope

The existing MIT license text and historical third-party inventory remain unchanged; the supplementary scope and provenance notices below qualify their interpretation. The Chinese manual is a separate candidate awaiting its own publication confirmation; this patch does not add it or its screenshots.

This documentation revision clarifies paths and identities. It does not change frozen software, package source proofs, sequence contracts or metadata, and adds no new Windows installation or browser workflow acceptance result.

## Public-content provenance and license boundaries (2026-10-09)

### Frozen package and current documentation

The paper-frozen software and the V1.1 development checkout are separate versions. This repository does not distribute the current V1.1 development work or imply that its fixes have been adopted. The fixed ZIP above identifies commit `b2696fd618c087fb0fd6b92bc6b78e8e71785dc7`; the public-content audit used the later documentation HEAD `d2a44c8914b866fd6116032ce9c60458259e0f74`. Current `main` documentation supplements the historical package, but does not enter an older commit's fixed ZIP or change its source commit, tag, or bytes.

`PAPER01_GITHUB_PUBLICATION_SHA256.txt and PAPER01_GITHUB_PUBLICATION_MANIFEST.txt` describe the historical package, not a regenerated inventory of current `main`. The current root README has later documentation bytes. Added provenance notes are outside the historical inventories; in PAPER01, `source_snapshot/tools/MUSCLE_PROVENANCE.md` is a later documentation addition, not a file copied from the frozen software source. Verify historical package hashes against the fixed package, and read these later notices separately. The historical inventories and source-tree proofs are retained without rewriting their hashes.

### MIT scope and third-party software

The [MIT license](source_snapshot/LICENSE) applies only to original software material that the project has the right to license. It does not automatically apply to database-derived sequences or records, fonts, third-party programs, or other third-party materials. Retain their own source, copyright, and license notices; this supplement does not assert that every project contribution's ownership chain has been independently proven.

The [third-party inventory](source_snapshot/THIRD_PARTY_NOTICES.md) records a historical Windows base-runtime lock and wheel review, rather than the actual bundled contents of this source repository or a complete future runtime package. Biopython 1.87 and Streamlit 1.55.0 are declared dependencies; their program bodies, wheels, and Python site-packages are not bundled in the audited repositories or PAPER01 release ZIP. Imports and requirements entries do not establish redistribution of those programs.

- [Biopython 1.87 license](https://raw.githubusercontent.com/biopython/biopython/biopython-187/LICENSE.rst): Biopython License Agreement; some individual files offer BSD-3-Clause as an alternative. Do not describe the entire package as BSD-only. Actual redistribution requires retention of applicable copyrights and supporting license/copyright statements; contributor names cannot be used for promotion without permission.
- [Streamlit 1.55.0 license](https://raw.githubusercontent.com/streamlit/streamlit/1.55.0/LICENSE): Apache-2.0. Actual redistribution requires its license, applicable notices, and modification notices where relevant. The audited tag's root NOTICE URL returned 404; this is not evidence that every nested component lacks notice requirements.
- Noto Sans SC retains its own [OFL 1.1 text](source_snapshot/assets/fonts/noto_sans_sc/OFL.txt) and [provenance](source_snapshot/assets/fonts/noto_sans_sc/PROVENANCE.md), rather than project MIT.

Any future bundle containing dependency program bodies must be checked against its actual direct, transitive, and nested component inventory. The historical notice inventory is not a completed license clearance for such a bundle.

### Sequence sources, counting scope and reuse

The 2026-10-09 audit counted 69 sequence-file paths and 122 candidate rows in this repository. Across the two repositories, 130 sequence-file paths deduplicated to **49 sequence contents**; the two copies of the candidate inventory deduplicated to **122 candidate source identities and 122 candidate sequences**. The 49 figure concerns the file-sequence set, not the combined file-and-candidate set (170 sequence contents). Deduplication used sequence-string hashes; reverse complements, coordinate fragments, and related variants were not forced into one biological identity.

The audit verified 82 real accession records online (81 INSDC/ENA and one NCBI RefSeq), checked all 122 candidates against their declared hashes and source regions, and checked all 34 Registry entries, referencing 20 unique source files. Preserve the versioned accession, original submitter/reference attribution, extraction coordinates, strand or joined-region transformations, and hashes in the [source manifest](source_snapshot/data/plant_component_registry_v1/source_manifest.csv), [Registry](source_snapshot/data/plant_component_registry_v1/registry.batch1.json), and [candidate inventory](source_snapshot/data/plant_component_registry_v1/intake_20260827/candidate_inventory.csv). Other source records include [pBI121 provenance](source_snapshot/data/real_assets/pbi121/provenance/source_manifest.json) and [betalain CDS provenance](source_snapshot/data/real_cases/betalain_three_enzyme/provenance/source_manifest.json). A Direct Submission or patent reference is a source record, not a reason to invent a paper or DOI. Synthetic test inputs are outside the real-accession claim.

[INSDC policy](https://www.insdc.org/policy/) provides unrestricted database access and redistribution and calls for citation of original submissions. The [NCBI molecular-database policy](https://www.ncbi.nlm.nih.gov/home/about/policies/) states that NCBI imposes no use or distribution restrictions, while warning that third-party patent, copyright, and other rights may remain. These policies support the audited sequence-data redistribution; they do not relicense the records under project MIT or clear every third-party right. Reading source data, publicly redistributing data, commercial exploitation, biological material transfer, and implementing a patented invention are distinct matters.

| Verified accession | Patent provenance present in the database record |
| --- | --- |
| [AF354045.1](https://www.ebi.ac.uk/ena/browser/view/AF354045.1) | PCT/US98/19217 |
| [AF354046.1](https://www.ebi.ac.uk/ena/browser/view/AF354046.1) | PCT/US98/19217 |
| [AF354047.1](https://www.ebi.ac.uk/ena/browser/view/AF354047.1) | PCT/US98/19217 |
| [MP385296.1](https://www.ebi.ac.uk/ena/browser/view/MP385296.1) | WO2019211296-A1, sequence 60 |

These references are confirmed source facts, not a finding that redistribution is prohibited or that a patent is enforceable. Patent claims, jurisdiction, grant status, and current legal status have not been assessed. Public sequence access does not establish freedom to operate or an unrestricted commercial implementation license. The audit does not constitute clearance of every embedded dataset or the full project history.

### Included MUSCLE binary

The included `source_snapshot/tools/muscle.exe` identifies itself as MUSCLE 3.8.31. The [MUSCLE provenance note](source_snapshot/tools/MUSCLE_PROVENANCE.md) records the version-specific official public-domain statement, unchanged binary hash, unresolved acquisition source, and follow-up evidence. It is not governed by project MIT; the GPL of later MUSCLE versions must not be applied to it solely by name.

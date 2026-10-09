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

The software's existing [MIT license](source_snapshot/LICENSE) and [third-party notices](source_snapshot/THIRD_PARTY_NOTICES.md) remain unchanged. The Chinese manual is a separate candidate awaiting its own publication confirmation; this patch does not add it or its screenshots.

This documentation revision clarifies paths and identities. It does not change frozen software, package source proofs, sequence contracts or metadata, and adds no new Windows installation or browser workflow acceptance result.

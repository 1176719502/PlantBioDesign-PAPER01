# MT-01 pGrDL_SP deterministic-region contract

This directory contains the versioned, machine-readable contract for `MT-01`.
It identifies the public source as `KX758647.1` and reproduces only the linear
source-forward interval `571..4649` (`[570,4649)`), not the complete circular
`pGrDL_SP` vector.

No complete source record, complete 7,086 bp source sequence, complete 4,079 bp
extracted sequence, or encoded equivalent is stored here. Reproduction requires
an explicit repository-external source file or an explicit NCBI fetch to a
repository-external cache, followed by `tools/real_case_contracts/mt01_extract_and_verify.py`.

The contracts separate source facts, deterministic derivations, inferences,
unknowns, component inputs, source annotations, unannotated intervals, hashes,
and redistribution limits. The `E1`/`E2` Registry evidence enum is not reused;
this case uses `DETERMINISTIC_ACCESSION_DERIVATION` as a case-local evidence
classification.

Status: `DATA_CONTRACT_READY_FOR_RUNTIME_INTEGRATION`. This status is a data
contract boundary, not an experimental validation or readiness conclusion.

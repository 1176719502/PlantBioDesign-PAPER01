# MT-02 pDOE-13 deterministic-region contract

This directory contains the versioned, machine-readable contract for `MT-02`.
It identifies the public source as `KM507054.1` and specifies only the linear
source-forward interval `111..6719` (`[110,6719)`), not the complete circular
`pDOE-13` vector.

No complete source record, complete 13,268 bp source sequence, complete 6,609 bp
canonical sequence, split reconstructable equivalent, or encoded equivalent is
stored here. Offline verification requires the audited repository-external
GenBank source and `tools/real_case_contracts/mt02_extract_and_verify.py`.

The contract distinguishes one accessory p19 TU from two target/reporter TUs.
It preserves source annotations as an overlapping display layer while deriving
a separate 40-interval atomic partition that covers each canonical nucleotide
exactly once. Four retained intervals totaling 24 bp remain conservatively
classified as unannotated component sequence.

Status: `MT02_DATA_CONTRACT_PENDING_FULL_PYTEST_GATE`. The scientific and
deterministic contract checks pass, but the exact full suite includes two
historical live-worktree guards that reject these required uncommitted files.
Runtime, persistence, cold reopen, UI, and browser export integration remain
separately authorized work.

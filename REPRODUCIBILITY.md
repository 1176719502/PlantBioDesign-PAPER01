# Reproducibility

The minimal runnable source snapshot derives solely from software commit 8ead74c060c32e653e746030e557398637a2c2fc and tree 53f8d4446f719678db363e4e373ddc88123fd80c. It retains runtime code, runtime data, dependencies, launch scripts, tests, tools, examples, and licensed runtime assets. Development-only agent configuration, dormant archives, screenshots, audit outputs, and task ledgers are excluded path by path in reproducibility/SOURCE_EXCLUSIONS.tsv.

To verify source provenance, compare reproducibility/FROZEN_TRACKED_TREE.txt and the authority proof with the tagged commit. To reproduce the software environment, install requirements-runtime.lock or requirements.txt and launch through START.bat or Streamlit app.py as appropriate.

For MT-01 and MT-02, obtain the public GenBank records using the accessions and coordinates in the S3/S4 metadata, reconstruct using the reported orientation and TU information, and verify the reconstructed length and SHA-256. No local worktree or audit-directory path is required.
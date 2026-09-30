# Plant Vector Asset Contracts V1

This directory is the offline authority for plant vector identity, asset kind,
approved operation, and formal workflow admission. The plant component Registry
remains a compatibility catalog and does not grant direct-design permission.

`contracts.json` contains the four reviewed assets. `contracts.schema.json`
defines their closed field and enum surface. Runtime code must load this file
through `core.vector_asset_contracts_v1`; callers must not copy operation
coordinates into UI constants, session state, or project JSON.

Unknown uploaded vectors are not entries in this file. Runtime classification
assigns them `unverified_uploaded_vector` and read-only behavior.

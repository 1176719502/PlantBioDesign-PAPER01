# BioDesign Studio

BioDesign Studio is a local-first documentation workspace for synthetic biology design records, pathway project notes, traceability review, and documentation-only export/import packages.

## Formal Runtime Baseline

When this repository contains historical notes that disagree, use the formal runtime below as the current engineering baseline:

- Formal entry: `app.py`
- Formal default port: `8528`
- Formal visible pages: Project Home, Six-Step Design Workspace, Results and Export, Plant Component Library
- `mvp_app.py` remains a compatibility entry and should not be used as the default startup target

## Current Product Direction

The active product line is the **expression-vector-first design-preparation MVP**. BioDesign Studio helps users create and review expression design records, inspect cassette/vector slot context, read source/provenance status, collect manual follow-up notes, and prepare documentation-only handoff review material.

Pathway projects remain useful for grouping, traceability, review notes, documentation snapshots, and package preview context. They are supporting project-workspace surfaces, not the whole product identity.

Current baseline and terminology entry points:

- `docs/qa/V2_6_R286_EXPRESSION_VECTOR_MVP_CLEAN_BASELINE_MILESTONE_CHECKPOINT.md` - latest expression-vector MVP clean baseline checkpoint.
- `docs/biodesign_studio_glossary.md` - refreshed global glossary for expression-vector, Component Library, source/provenance, handoff, and documentation-boundary terms.
- `docs/qa/V2_6_R299_GLOBAL_GLOSSARY_ENCODING_READABILITY_CLEANUP.md` - glossary readability and encoding cleanup QA.
- `docs/qa/V2_6_R298_COMPONENT_LIBRARY_REVIEW_QUEUE_SOURCE_HANDOFF_CLARITY_QA.md` - Component Library source/provenance handoff clarity QA.

## Main Workflow

The current expression-vector-first mainline is:

```text
Expression Wizard
-> expression design record
-> cassette/vector slot readback
-> Component Library source/provenance and manual follow-up review
-> Handoff Review expression-vector package preview
-> documentation-only review notes, traceability, and project context
```

Core surfaces include:

- Expression Wizard as the first-stage expression design record path.
- Component Library for slot/source/provenance readback and manual follow-up context.
- Handoff Review for expression-vector package preview and project-level review context.
- Pathway Projects and Pathway Workspace for grouping, notes, linked design records, documentation snapshots, reports, traceability, and package preview context.
- Design Library and Saved Designs for reviewing saved design records.
- Documentation snapshots for preserving local project documentation state.
- Reports and traceability summaries for documentation review.
- Documentation-only export/import packages with import preview and duplicate guard checks.

## Local Streamlit Startup

Preferred empty-environment setup on Windows:

```powershell
py -3.12 -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install --upgrade pip
.\.venv312\Scripts\python.exe -m pip install -r requirements.txt
.\.venv312\Scripts\python.exe scripts\test_imports.py
```

Formal startup from the project root:

```powershell
.\.venv312\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.headless false --server.port 8528
```

Windows launcher wrappers:

- `START.bat` launches the formal runtime for `app.py` on port `8528`.
- `Stop_BioDesign_Formal.bat` stops only the owned formal runtime process recorded by the launcher state file.
- `Start_BioDesign_MVP.bat` remains a compatibility launcher for `mvp_app.py` and prints that it is using the MVP entry.

For normal local review, do not start Redis, Docker, FastAPI, or RQ workers unless a separate task explicitly asks for asynchronous infrastructure.

## Product Boundaries

BioDesign Studio is documentation software. It does not provide:

- Wet-lab automation.
- Experimental validation.
- Biological readiness approval.
- Biological outcome prediction.
- Pathway optimization.
- Automated recommendation of biological actions.
- Protocol generation.
- Autonomous DBTL execution.

Export and import packages are documentation-only. Saved Dashboard snapshots, Design Library entries, Pathway Workspace records, reports, and traceability summaries are local review records; they do not certify biological use.

## Documentation Sources

Use these files as current documentation entry points:

- `README.md` - product overview and current documentation-workspace direction.
- `PROJECT_IDENTITY.md` - product identity and scope boundary.
- `PROJECT_POSITIONING.md` - positioning note for current product narrative.
- `AGENTS.md` - coding policy and active implementation guardrails.
- `docs/dev/CODEX_AUTONOMOUS_WORKFLOW.md` - default loop for autonomous Codex tasks, including docs-only, test-and-fix, cleanup, and feature-batch work.
- `docs/README.md` - documentation index.
- `docs/biodesign_studio_glossary.md` - refreshed global glossary for current product terminology.
- `docs/status/00_PRODUCT_DIRECTION_AND_FEATURE_MAP.md` - current product direction and feature map.
- `docs/status/V2_6_STABLE_BASELINE_HANDOFF.md` - V2.6 stable baseline handoff and resume notes.
- `docs/qa/V2_6_R286_EXPRESSION_VECTOR_MVP_CLEAN_BASELINE_MILESTONE_CHECKPOINT.md` - latest expression-vector MVP clean baseline checkpoint.
- `docs/qa/V2_6_R298_COMPONENT_LIBRARY_REVIEW_QUEUE_SOURCE_HANDOFF_CLARITY_QA.md` - Component Library source/provenance handoff clarity QA.
- `docs/qa/V2_6_R299_GLOBAL_GLOSSARY_ENCODING_READABILITY_CLEANUP.md` - glossary readability cleanup QA.
- `docs/qa/V2_6_R32_STABILIZATION_CHECKPOINT.md` - R32 stabilization checkpoint and regression baseline summary.
- `docs/qa/V2_6_R35_DEMO_NEXT_DEVELOPMENT_HANDOFF.md` - demo-facing handoff for the current V2.6 baseline.
- `docs/qa/V2_6_R4A_DEMO_WORKFLOW_NAVIGATION_CLARITY.md` - docs-first V2.6 workflow clarity checkpoint.
- `docs/archive/historical-root/V0.1_ACCEPTANCE_REPORT.md` - historical v0.1 acceptance record for the earlier Expression Wizard MVP.
- `docs/qa/local_mvp_runbook.md` - historical/local QA reference for earlier MVP startup paths.

## Historical Material

Historical release notes, frozen MVP records, older roadmap material, and archived planning notes are preserved for traceability. Treat them as historical unless a task explicitly reopens that scope.

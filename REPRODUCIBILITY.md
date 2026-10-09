# Reproducibility

## 1. Repository layout and locked startup

The selected runtime snapshot is in `source_snapshot/`. Run installation commands from the repository root, using the paths below. The source identity is recorded in [SOFTWARE_SNAPSHOT.md](SOFTWARE_SNAPSHOT.md).

Run these commands in PowerShell from the repository root after extracting the fixed repository snapshot. Use Windows x64 and 64-bit CPython 3.12. Keep the PowerShell window open while the app runs.

Install the locked environment:

```powershell
$ErrorActionPreference = 'Stop'
$reviewSoftware = Join-Path (Get-Location).Path 'source_snapshot'
$reviewRoot = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'PlantBioDesignReview\publication-package'
$reviewEnv = Join-Path $reviewRoot 'env'
$reviewPython = Join-Path $reviewEnv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath (Join-Path $reviewSoftware 'app.py'))) {
    throw 'Open PowerShell in the extracted repository root first.'
}
py -3.12 -c "import platform, struct, sys; sys.exit(0 if platform.python_implementation() == 'CPython' and platform.machine().lower() in ('amd64', 'x86_64') and struct.calcsize('P') == 8 else 1)"
if ($LASTEXITCODE -ne 0) { throw '64-bit CPython 3.12 for Windows x64 is required.' }
New-Item -ItemType Directory -Path $reviewRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath $reviewEnv)) {
    py -3.12 -m venv $reviewEnv
    if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed.' }
}
if (-not (Test-Path -LiteralPath $reviewPython)) { throw 'The environment interpreter is missing.' }
& $reviewPython -m pip install --only-binary=:all: --require-hashes -r (Join-Path $reviewSoftware 'requirements-runtime.lock')
if ($LASTEXITCODE -ne 0) { throw 'Locked installation failed. Keep the error log.' }
& $reviewPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed.' }
```

Start or restart using the same source folder and runtime directory:

```powershell
$ErrorActionPreference = 'Stop'
$reviewSoftware = Join-Path (Get-Location).Path 'source_snapshot'
$reviewRoot = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'PlantBioDesignReview\publication-package'
$reviewPython = Join-Path $reviewRoot 'env\Scripts\python.exe'
$reviewRuntime = Join-Path $reviewRoot 'runtime'
$reviewPort = 8632
if (-not (Test-Path -LiteralPath $reviewPython)) { throw 'Install the environment first.' }
if (-not (Test-Path -LiteralPath (Join-Path $reviewSoftware 'app.py'))) { throw 'Return to the extracted repository root.' }
if (Get-NetTCPConnection -LocalPort $reviewPort -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8632 is occupied. Check the existing instance before starting another.'
}
New-Item -ItemType Directory -Path $reviewRuntime -Force | Out-Null
$env:BIODESIGN_DB_PATH = Join-Path $reviewRuntime 'biodesign_unified.db'
$env:BIODESIGN_PLANT_PROJECT_DRAFT_DIR = Join-Path $reviewRuntime 'project_drafts'
$env:BIODESIGN_BACKUP_DIR = Join-Path $reviewRuntime 'backups'
$env:BIODESIGN_PYDNA_CONFIG_DIR = Join-Path $reviewRuntime 'pydna\config'
$env:BIODESIGN_PYDNA_DATA_DIR = Join-Path $reviewRuntime 'pydna\data'
$env:BIODESIGN_PYDNA_LOG_DIR = Join-Path $reviewRuntime 'pydna\logs'
$env:PYTHONDONTWRITEBYTECODE = '1'
Push-Location -LiteralPath $reviewSoftware
try {
    & $reviewPython -m streamlit run app.py --server.address 127.0.0.1 --server.port $reviewPort --server.headless true --server.fileWatcherType none
} finally {
    Pop-Location
}
```

Open [http://127.0.0.1:8632](http://127.0.0.1:8632). Save your project before pressing `Ctrl+C` to stop your instance. Reuse the same runtime directory to reopen its saved projects. Change the port variable and browser URL together when using another free port. These commands have been reviewed for paths and control flow; this documentation revision has not replayed them on Windows.

The locked list omits ReportLab. The alternative `source_snapshot/requirements.txt` includes it but declares a different environment; these lists must not be presented as interchangeable. This guide preserves the locked installation and discloses the formal-report limitation. The existing `source_snapshot/START.bat` invokes a separate launcher; this revision does not replay that launcher or assert it uses the isolated environment above.

## 2. Verify software provenance

The selected source derives from frozen software commit `8ead74c060c32e653e746030e557398637a2c2fc`, tree `53f8d4446f719678db363e4e373ddc88123fd80c`. Consult [reproducibility/FROZEN_TRACKED_TREE.txt](reproducibility/FROZEN_TRACKED_TREE.txt), [reproducibility/SOFTWARE_AUTHORITY_PROOF.md](reproducibility/SOFTWARE_AUTHORITY_PROOF.md) and [reproducibility/PACKAGE_AUTHORITY_PROOF.md](reproducibility/PACKAGE_AUTHORITY_PROOF.md). The complete frozen-tree listing includes paths excluded from this distribution; it is not a list of files present under `source_snapshot/`.

Development-only configuration, dormant archives, screenshots, audit outputs and task ledgers were excluded according to [reproducibility/SOURCE_EXCLUSIONS.tsv](reproducibility/SOURCE_EXCLUSIONS.tsv). Prior audit JSON/proof files remain historical records; a documentation change does not rerun the original audit.

## 3. Reconstruct MT-01 and MT-02 regions

Use [supplement/S3_MT01_METADATA_SAFE.csv](supplement/S3_MT01_METADATA_SAFE.csv) and [supplement/S4_MT02_METADATA_SAFE.csv](supplement/S4_MT02_METADATA_SAFE.csv) for versioned accession, coordinates, orientation and reported SHA-256 values. Obtain the exact source record versions independently. Complete derived sequence payloads are omitted under the distribution scope.

After reconstruction, compare the reported length and SHA-256 over the normalized uppercase nucleotide string. A whole-file FASTA or GenBank checksum includes formatting and annotations and is not the nucleotide-string checksum. Region reconstruction does not establish whole-plasmid reproduction or biological validation.

## 4. Check the distribution inventory

Use [PAPER01_GITHUB_PUBLICATION_MANIFEST.txt](PAPER01_GITHUB_PUBLICATION_MANIFEST.txt) for paths, sizes and source roles, and [PAPER01_GITHUB_PUBLICATION_SHA256.txt](PAPER01_GITHUB_PUBLICATION_SHA256.txt) for byte hashes. The documentation patch updates changed-document hashes; source-file rows and original source-proof files remain unchanged. This revision checks document paths and selected published file hashes, not all runtime behavior or every sequence record.

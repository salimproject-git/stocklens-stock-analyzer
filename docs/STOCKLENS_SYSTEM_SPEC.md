# StockLens - System Specification

**Version:** 0.1
**Status:** PROPOSED
**Scope:** Raw data acquisition, raw storage, ingestion metadata, and canonical PostgreSQL boundary

## 1. Purpose

This document defines the raw-data pipeline for StockLens. It does not define proprietary formulas, valuation assumptions, classification rules, scoring, or backtest thresholds.

## 2. Raw Data Flow

```text
Sectors API
    |
    v
Phyton/01_download_sectors.py
    |
    v
Data/Raw/{TICKER}/... (local staging/cache)
    |
    v
supabase/upload_raw_to_supabase_storage.py
    |
    v
Private Supabase Storage bucket: stocklens_raw
    |
    v
public.ingestion_files metadata
    |
    v
Canonical PostgreSQL import pipeline
```

`Phyton/01_download_sectors.py` remains the API acquisition layer. The uploader never calls Sectors.app and never changes local JSON.

## 3. Local Raw Staging

`Data/Raw/{TICKER}` contains AS-IS JSON responses produced by the existing collector. The local directory remains a staging/cache copy and can support the collector's existing caching and incremental behavior.

The uploader reads JSON recursively, validates that each file is valid UTF-8 JSON, computes SHA-256, and maps the local path to a logical Storage path.

Examples:

```text
Data/Raw/ASII/company_report_info.json
-> sectors/ASII/info/company_report_info.json

Data/Raw/ASII/company_report_annual.json
-> sectors/ASII/annual/company_report_annual.json

Data/Raw/ASII/quarterly/2026-06-30.json
-> sectors/ASII/quarterly/2026-06-30.json

Data/Raw/ASII/daily/2026-09-01_2026-09-22.json
-> sectors/ASII/daily/2026-09-01_2026-09-22.json
```

## 4. Supabase Storage

- Bucket: `stocklens_raw`
- Visibility: private
- MIME type: `application/json`
- Object key: logical path under `sectors/{TICKER}/...`
- Credential: server-side `SUPABASE_SERVICE_ROLE_KEY` only

The service-role key must not be sent to the frontend, committed to Git, or exposed in public logs.

The uploader sends `x-upsert: false` and therefore does not silently replace an existing object.

## 5. Idempotent Upload Rules

For each local JSON file:

1. Calculate SHA-256 before upload.
2. Look for existing `ingestion_files` metadata by logical Storage path.
3. If metadata checksum matches and the Storage object exists, report `SKIP`.
4. If metadata exists with a different checksum, fail safely.
5. If the object exists without matching metadata, fail safely.
6. If neither object nor metadata exists, upload with `application/json` and write `UPLOADED` metadata.

A second run must not create a second Storage object for the same logical path. Metadata is audit history associated with an ingestion run; the Storage object is the canonical raw archive copy.

## 6. Ingestion Metadata

`public.ingestion_files` records:

- `ingestion_run_id`;
- source file category;
- Storage bucket and logical path;
- SHA-256 checksum;
- record count when inferable;
- first/last record date for daily and quarterly payloads when safely inferable;
- `UPLOADED`, `SKIPPED`, or `FAILED` status;
- creation timestamp.

The uniqueness rule `(ingestion_run_id, storage_path)` prevents duplicate metadata for the same run and path. Indexes support run, path, and checksum lookup.

## 7. Ingestion Runs

The uploader accepts an existing `--ingestion-run-id`. If no run ID is provided, it creates a run using `SECTORS_APP`, the ticker, status `RUNNING`, and collector version `raw-storage-uploader-0.1`.

The run becomes `SUCCESS` only when every discovered JSON file is handled. Any failure marks the run `FAILED` and no later file is silently treated as successful.

## 8. Canonical Database Boundary

Raw Storage is not the canonical query model for the application. The intended next boundary is:

```text
private raw object
    + ingestion_files metadata
        -> normalization/validation
            -> canonical PostgreSQL rows
```

The existing `raw_ingestion_payloads` table is intentionally retained during migration. It is not removed by this change. It can continue to support the MVP/legacy bootstrap path while the Storage-backed pipeline is audited.

## 9. Scope Exclusions

This specification does not document or implement:

- growth formulas;
- valuation formulas or assumptions;
- quality/liquidity formulas;
- classification or scoring rules;
- backtest thresholds or methodology;
- frontend changes;
- calculation result tables.

Those areas require separate, explicitly versioned implementation work.

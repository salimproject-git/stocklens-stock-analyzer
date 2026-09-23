# StockLens Supabase MVP

> Execution status: start with schema migration only. Do not run the importer until the empty-project schema checks in this README pass.

This is an MVP validation schema, not the final StockLens architecture. The raw-storage pipeline is now added through migration `0002_raw_storage.sql`. Calculation and backtest tables remain future schema evolution.

Panduan ini menjalankan alur Sectors.app -> Python lokal -> Supabase PostgreSQL.

## 1. Buat project dan jalankan schema

1. Buat project baru di Supabase Dashboard.
2. Buka SQL Editor.
3. Jalankan seluruh file `supabase/migrations/0001_stocklens_mvp.sql`.
4. Pastikan table `data_sources` berisi row `SECTORS_APP`.
5. Stop here and verify the schema before setting credentials or running Python.

Before Phase 2, run these checks in SQL Editor:

```sql
select table_name
from information_schema.tables
where table_schema = 'public'
order by table_name;

select id, source_code, source_name, base_url
from public.data_sources
where source_code = 'SECTORS_APP';

select 'companies' as table_name, count(*) as row_count from public.companies
union all select 'instruments', count(*) from public.instruments
union all select 'ingestion_runs', count(*) from public.ingestion_runs
union all select 'raw_ingestion_payloads', count(*) from public.raw_ingestion_payloads
union all select 'financial_periods', count(*) from public.financial_periods
union all select 'financial_facts', count(*) from public.financial_facts
union all select 'prices_daily', count(*) from public.prices_daily;
```

Expected result: all MVP tables exist, `SECTORS_APP` exists, and all data tables still contain zero rows. Share this result for review before running the importer.

## 2. Add raw-storage metadata

After `0001_stocklens_mvp.sql` has been verified, run `supabase/migrations/0002_raw_storage.sql` in a new SQL Editor query. This migration only creates `public.ingestion_files`, indexes, RLS, and the `service_role` grant. It does not drop, truncate, or alter existing tables.

## 3. Upload existing local raw JSON

The uploader does not call Sectors.app. It only reads `Data/Raw/{TICKER}` and uploads JSON to the private `stocklens_raw` bucket.

Set credentials only in the local PowerShell session:

```powershell
$env:SUPABASE_URL='https://YOUR_PROJECT_REF.supabase.co'
$env:SUPABASE_SERVICE_ROLE_KEY='YOUR_SERVICE_ROLE_KEY'
```

Run the ASII test:

```powershell
python .\supabase\upload_raw_to_supabase_storage.py ASII
```

To reuse an existing run:

```powershell
python .\supabase\upload_raw_to_supabase_storage.py ASII --ingestion-run-id YOUR_RUN_ID
```

The logical path is `sectors/{TICKER}/{CATEGORY}/{FILE}.json`. Existing objects with the same checksum are reported as `SKIP`. Existing objects with a different checksum fail safely; the uploader never silently overwrites.

## 4. Idempotency test

Run the ASII command twice. The first run should report `UPLOAD` and create `ingestion_files` rows. The second run should report `SKIP` and must not create duplicate Storage objects. Check metadata with:

```sql
select storage_bucket, storage_path, checksum_sha256, status, ingestion_run_id
from public.ingestion_files
where storage_path like 'sectors/ASII/%'
order by storage_path, created_at;
```

The unique key is `(ingestion_run_id, storage_path)`. If the second run creates a new ingestion run, it creates separate audit metadata for that run but does not create a duplicate Storage object.

## 5. Siapkan Python

Dari root repository:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install requests
```

Jika aktivasi ditolak:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 6. Canonical import pipeline

Ambil `SUPABASE_URL` dan key `service_role` dari Project Settings -> API. Ambil `SECTORS_API_KEY` dari Sectors.app.

```powershell
$env:SUPABASE_URL='https://YOUR_PROJECT_REF.supabase.co'
$env:SUPABASE_SERVICE_ROLE_KEY='YOUR_SERVICE_ROLE_KEY'
$env:SECTORS_API_KEY='YOUR_SECTORS_API_KEY'
```

Jangan pernah memasukkan service-role key ke frontend, Git, README publik, atau screenshot.

The raw-first canonical path is:

```text
Phyton/01_download_sectors.py
    -> Data/Raw/{TICKER}
    -> upload_raw_to_supabase_storage.py
    -> private Supabase Storage: stocklens_raw
    -> public.ingestion_files
    -> canonical PostgreSQL import pipeline
```

## 7. Verifikasi SQL

```sql
select * from public.ingestion_runs order by started_at desc;

select i.ticker, c.legal_name
from public.instruments i
join public.companies c on c.id = i.company_id;

select i.ticker, fp.period_label, ff.metric_code, ff.value_numeric
from public.financial_facts ff
join public.financial_periods fp on fp.id = ff.financial_period_id
join public.instruments i on i.id = fp.instrument_id
order by fp.period_end desc;

select i.ticker, p.trading_date, p.close_price
from public.prices_daily p
join public.instruments i on i.id = p.instrument_id
order by p.trading_date desc;
```

## 9. Hit REST API Supabase

Untuk test lokal saja:

```powershell
$headers = @{
  apikey = $env:SUPABASE_SERVICE_ROLE_KEY
  Authorization = ('Bearer ' + $env:SUPABASE_SERVICE_ROLE_KEY)
}
Invoke-RestMethod `
  -Uri ($env:SUPABASE_URL + '/rest/v1/instruments?select=ticker,provider_symbol&ticker=eq.AUTO') `
  -Headers $headers
```

## Tempat menyimpan data

- Row canonical aplikasi: Supabase PostgreSQL.
- Raw JSON MVP: kolom `jsonb` pada `raw_ingestion_payloads`.
- Raw JSON production: private Supabase Storage bucket `stocklens_raw`, MIME type `application/json`, dengan path/checksum di PostgreSQL.
- CSV: hanya export/backup, bukan source of truth.

## Batasan MVP dan rencana evolution

Migration ini sengaja belum sama dengan final architecture. `ingestion_files` sudah tersedia untuk raw-storage metadata, tetapi belum ada `calculation_runs`, `methodology_versions`, `calc_*`, atau backtest tables. Financial model awal menggunakan `financial_periods` + `financial_facts`, dan legacy canonical seeder masih memakai `raw_ingestion_payloads.payload`.

Setelah raw upload pertama diaudit, gunakan migration baru untuk menambahkan quarterly/dividend semantics, canonical import dari Storage, calculation lineage, valuation, growth, classification, dan backtest. Jangan mengedit migration yang sudah dijalankan.

## Batasan MVP

Importer pertama mengisi overview, annual financials, dan daily prices. Quarterly, dividend events, calculation runs, valuation, growth, dan backtest ditambahkan setelah alur dasar berhasil.

## Canonical historical daily-price loader

Migration `0003_prices_source_ingestion_file.sql` adds nullable `source_ingestion_file_id` to `prices_daily` without removing legacy `source_payload_id`.

After the raw-storage upload run has created `ingestion_files` metadata, load local historical daily prices with an explicit run ID:

```powershell
python .\supabase\load_daily_prices_to_supabase.py AUTO --ingestion-run-id YOUR_RAW_STORAGE_RUN_ID
```

The loader reads only `Data/Raw/AUTO/daily/*.json`; it never calls Sectors API. It validates all files, deduplicates by trading date, resolves exactly one instrument using `IDX` + `AUTO`, verifies provenance for every daily file, and performs a preflight comparison before inserting anything.

Behavior is insert-only:

- missing date: `INSERT`;
- existing date with identical values: `SKIP`;
- existing date with different values: `CONFLICT`, no canonical rows are written;
- missing `ingestion_files` provenance: fail before writing.

Expected clean AUTO result from the current local archive:

```text
raw_file_count=28
raw_unique_record_count=1610
canonical_row_count=1610
earliest_canonical_date=2020-01-02
latest_canonical_date=2026-09-11
```

Verify independently:

```sql
select
  count(*) as row_count,
  count(distinct p.trading_date) as distinct_dates,
  min(p.trading_date) as earliest_date,
  max(p.trading_date) as latest_date
from public.prices_daily p
join public.instruments i on i.id = p.instrument_id
where i.exchange_code = 'IDX'
  and i.ticker = 'AUTO';

select count(*) as rows_with_storage_provenance
from public.prices_daily p
join public.instruments i on i.id = p.instrument_id
where i.exchange_code = 'IDX'
  and i.ticker = 'AUTO'
  and p.source_ingestion_file_id is not null;
```

## Canonical identity loader

After the raw-storage uploader has created an `ingestion_files` row for the
company information file, create the canonical AUTO identity without calling
the Sectors API:

```powershell
python .\supabase\load_identity_to_supabase.py AUTO --ingestion-run-id YOUR_RAW_STORAGE_RUN_ID
```

The loader reads only `Data/Raw/AUTO/company_report_info.json`, computes its
SHA-256 checksum, and requires the matching
`sectors/AUTO/info/company_report_info.json` metadata in the supplied run and
the `stocklens_raw` bucket. It resolves or inserts `companies`, `instruments`,
the `SECTORS_APP` taxonomy row in `sectors`, and the deterministic
`instrument_sector_classifications` relationship.

Existing identity rows are never silently overwritten. Identical rows are
skipped; non-null source differences are reported, and ticker/provider-symbol
or relationship conflicts fail safely. The loader does not use
`SECTORS_API_KEY` and does not modify the local JSON. The current
`instrument_sector_classifications` schema has no foreign key to
`ingestion_files`, so Storage provenance is verified before loading but
`source_payload_id` remains `NULL` for these new classification rows.

## Canonical annual financial loader

The annual loader reads only
`Data/Raw/{TICKER}/company_report_annual.json` and requires the matching raw
Storage provenance row for
`sectors/{TICKER}/annual/company_report_annual.json`. It does not call the
Sectors API and does not use the legacy seeder.

For this source, only a year is available. StockLens therefore uses the
documented calendar-year convention `period_end = YYYY-12-31`. This is a
StockLens-modeled period boundary, not a provider-reported date. The loader
keeps `period_start`, `report_date`, and `available_date` as `NULL`, and uses
`period_basis = UNKNOWN` and `statement_scope = UNKNOWN`.

## Canonical quarterly financial loader

The quarterly loader reads the explicit date index and one-record JSON files
under `Data/Raw/{TICKER}/quarterly`. It requires Storage provenance for every
file at `sectors/{TICKER}/quarterly/{period_end}.json`, then loads canonical
quarterly facts without calling the Sectors API.

Quarterly periods use the source period-end date directly:

```text
period_type = QUARTER
period_label = YYYY-QN
period_start = NULL
period_end = source period-end date
period_basis = STANDALONE
statement_scope = UNKNOWN
```

`period_basis = STANDALONE` is a StockLens modeling classification supported
by reconciliation of the quarterly flow values to the annual source; it is not
a provider field. The loader preserves null facts as `value_numeric = NULL`
with `quality_status = MISSING`, does not create quarterly EPS facts, and does
not load provider-derived metrics.

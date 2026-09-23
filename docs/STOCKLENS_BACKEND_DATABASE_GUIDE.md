# StockLens - Backend & Database Architecture Guide

**Version:** 0.2
**Status:** PROPOSED
**Scope:** Backend, ingestion, canonical database, calculation results, and API contract
**Last reviewed:** 22 September 2026

> Dokumen ini adalah target architecture dan implementation guide. Backend dan database production belum menjadi bagian dari aplikasi saat ini, sehingga dokumen ini sengaja tidak memakai status `LOCKED`.

## 1. Keputusan Review

### Kesimpulan

Jawaban AI yang menjadi input dokumen ini **sudah benar sebagai arah arsitektur**, terutama pada pemisahan raw data, canonical data, calculation layer, dan frontend. Namun, dokumen tersebut belum sepenuhnya sesuai dengan repository dan kebutuhan produk saat ini.

Dokumen ini memperbaiki hal-hal berikut:

1. Membedakan kondisi repository saat ini dari target production.
2. Memasukkan backtest sebagai domain produk, bukan menundanya dari schema awal.
3. Tidak menyebut Supabase, n8n, atau backend sebagai komponen yang sudah tersedia.
4. Mengganti rancangan financial table yang terlalu lebar dengan struktur period dan fact yang lebih tahan terhadap variasi source.
5. Melengkapi lineage, versioning, source semantics, dan provenance.
6. Menghindari penyimpanan nilai presentasi seperti `M Rp`, `B Rp`, dan `T Rp` sebagai unit database.
7. Menetapkan bahwa hasil calculation diproduksi di server-side pada target production, bukan oleh Next.js.

### Status terhadap proposal awal

| Area | Penilaian | Catatan |
|---|---|---|
| Raw archive terpisah dari canonical database | Sesuai | Sudah tercermin pada folder `Data/Raw` dan `Data/Converted`; target production mempertahankan pemisahan ini. |
| Sectors API sebagai external source | Sesuai sebagai target | Collector Python tersedia; backend production belum tersedia. |
| Company dan listed instrument dipisahkan | Sesuai | Perlu diterapkan saat schema dibangun. |
| Source facts dan calculated results dipisahkan | Sesuai | Calculation saat ini masih berada di TypeScript frontend untuk prototype. |
| Lineage dan methodology version | Sesuai sebagai prinsip | Table dan job production belum ada. |
| Financial annual/quarterly table terpisah | Perlu revisi | Lebih aman memakai `financial_periods` dan `financial_facts` agar metric dan period semantics tidak kaku. |
| Backtest ditunda dari schema v1 | Tidak sesuai produk | Backtest adalah tab dan domain inti pada product specification; schema minimalnya harus disiapkan bersama valuation. |
| Supabase PostgreSQL sudah menjadi database | Belum terbukti | Repository belum memiliki migration, schema, backend, atau koneksi Supabase. |
| Python / n8n sebagai ingestion layer | Sebagian sesuai | Script Python ada; n8n belum ditemukan di repository. Jangan menyebut n8n sebagai implementasi aktif sebelum workflow-nya ada. |
| Frontend bukan source of truth | Sesuai sebagai target | Pada fase sekarang, `mock-stock-details.ts` memang menjadi temporary runtime source of truth frontend. |

## 2. Dasar Audit Repository

Dokumen ini dibuat berdasarkan kondisi repository berikut:

- `docs/STOCKLENS_PRODUCT.md` mendefinisikan area Overview, Financials, Growth, Valuation, dan Historical Evidence.
- `DEVELOPMENT_GUIDE.md` menyatakan fase aktif masih frontend-only, menggunakan mock data, dan production flow yang direncanakan adalah Sectors API -> n8n -> database/canonical data -> backend API -> Next.js.
- Collector Sectors API berada di `Phyton/01_download_sectors.py`.
- Transformasi raw data ke CSV berada di `Phyton/02_convert_sectors_raw.py`.
- Raw archive menggunakan JSON dan manifest per ticker di `Data/Raw`.
- Dataset hasil konversi saat ini berada di `Data/Converted`, dengan file informasi perusahaan, financial annual, financial quarterly, price history, dan conversion audit.
- Runtime frontend masih membaca `frontend/src/data/mock-stock-details.ts`.
- Analytical helper saat ini berada di `frontend/src/lib/analysis`, termasuk growth, valuation, dan backtest.

### Konsekuensi

Repository saat ini memiliki **data preparation pipeline** dan prototype frontend, bukan backend production. Karena itu:

- file CSV/JSON di repository bukan schema database production;
- mock data bukan kontrak API final;
- helper TypeScript bukan tempat final untuk calculation engine;
- nama table di dokumen ini adalah target canonical schema, bukan klaim bahwa table tersebut sudah ada.

## 3. Scope dan Non-Scope

### Scope

Dokumen ini mengatur alur data dari external source sampai frontend, raw archive, ingestion, normalisasi, provenance, identity company/instrument/sector, canonical price/financial/dividend facts, calculation runs, methodology version, valuation, growth, quality, liquidity, classification, backtest result, boundary API, unit, period, nullability, idempotency, dan reproducibility.

### Non-scope

Dokumen ini tidak membuka atau menetapkan formula proprietary, scoring threshold final, detail strategi investasi, rekomendasi BUY/SELL, credential/API key, deployment topology final, atau detail UI component.

Formula dan rule harus berada di implementation layer yang memiliki version identifier. Database menyimpan input, output, status, dan provenance yang dibutuhkan untuk audit.

## 4. Target System Architecture

```text
External Data Source
        |
        v
Ingestion Worker / Workflow
        |
        +-- Raw Archive (AS-IS JSON + manifest)
        |
        v
Normalizer / Validator
        |
        v
Canonical PostgreSQL
  +-- Identity
  +-- Source Facts
  +-- Lineage
  +-- Calculation Results
        |
        v
Calculation Worker
  +-- Growth
  +-- Quality / Liquidity
  +-- Valuation
  +-- Classification
  +-- Backtest
        |
        v
Backend API
        |
        v
Next.js Frontend
```

### Prinsip ownership

| Layer | Tanggung jawab | Tidak boleh dilakukan |
|---|---|---|
| External source | Menyediakan data pihak ketiga | Dianggap selalu lengkap atau stabil |
| Ingestion | Fetch, retry, raw archive, manifest, dan run status | Mengubah raw response asli |
| Normalizer | Mapping field, unit conversion, validation, dan upsert canonical | Menyembunyikan nilai invalid tanpa audit |
| Canonical database | Menyimpan typed source facts yang dapat di-query | Menyimpan string display sebagai sumber utama |
| Calculation worker | Menghasilkan derived result versi tertentu | Menjadi satu-satunya tempat raw source disimpan |
| Backend API | Authorization, query, shaping response, dan format contract | Menyerahkan formula private ke browser |
| Next.js | Menampilkan data dan interaksi pengguna | Membaca CSV/local archive atau menjadi source of truth production |

## 5. Database Boundaries

### 5.1 Raw archive

Raw archive menyimpan payload source apa adanya, termasuk response error atau partial response yang relevan untuk audit. Archive boleh berada di object storage atau filesystem selama development.

Raw archive harus memiliki logical archive key, source name dan endpoint/task, ticker/provider symbol, fetched timestamp, checksum/content hash, collector version, request period/query scope, dan manifest status.

Jangan menjadikan absolute path seperti `D:\Stock Analyzer\Data\Raw\...` sebagai identifier permanen. Simpan logical key, misalnya:

```text
raw/sectors/AUTO/annual/2026-09-10.json
raw/sectors/AUTO/quarterly/2026-06-30.json
raw/sectors/AUTO/daily/2026-06-14_2026-09-11.json
```

### 5.2 Canonical database

Canonical database adalah data yang sudah dinormalisasi ke identity internal, typed, memiliki unit dan semantics yang jelas, memiliki provenance, dapat dipakai ulang oleh beberapa calculation job, dan tidak bergantung pada nama kolom atau format CSV provider.

### 5.3 Calculation result

Calculation result bukan source fact. Setiap result harus menunjuk ke instrument, calculation run, methodology version, observation/effective date, input cutoff atau source snapshot, dan status calculation.

## 6. Domain dan Table Inventory

### 6.1 System dan lineage

| Table | Grain | Fungsi utama |
|---|---|---|
| `data_sources` | one external provider/task | Registry provider, endpoint family, dan source type. |
| `ingestion_runs` | one execution scope | Status satu eksekusi ingestion, ticker scope, waktu, dan collector version. |
| `ingestion_files` | one raw/derived file per run | Logical archive key, checksum, record count, date range, dan processing status. |
| `calculation_runs` | one calculation execution | Status, code version, input cutoff, methodology, dan instrument scope. |
| `methodology_versions` | one analytical version | Identifier stabil untuk reproducibility tanpa menyimpan formula di table ini. |

### 6.2 Identity

| Table | Grain | Fungsi utama |
|---|---|---|
| `companies` | one legal issuer | Identitas perusahaan atau issuer. |
| `instruments` | one listed security | Saham yang diperdagangkan; memiliki ticker, exchange, provider symbol, dan relasi ke company. |
| `sectors` | one taxonomy node | Sector/subsector taxonomy yang digunakan source atau product. |
| `instrument_sector_classifications` | one instrument-sector relationship per effective period | Relasi sector yang bisa berubah sepanjang waktu. |

### 6.3 Canonical source facts

| Table | Grain | Fungsi utama |
|---|---|---|
| `prices_daily` | one instrument x trading date | OHLC, volume, market cap bila tersedia, serta source metadata. |
| `financial_periods` | one instrument x reporting period | Metadata annual/quarterly, report date, available date, period basis, dan statement scope. |
| `financial_facts` | one period x metric code | Nilai financial typed yang dapat bertambah tanpa migration setiap metric source bertambah. |
| `dividend_events` | one instrument x one source dividend event | Event dividend individual tanpa mencampurnya dengan aggregate analytical result. |

### 6.4 Calculated results

| Table | Grain | Fungsi utama |
|---|---|---|
| `calc_growth` | one instrument x observation period x growth metric | Growth series dan summary output yang dibutuhkan Growth tab. |
| `calc_quality` | one instrument x observation period x quality metric | Quality/profitability output. |
| `calc_liquidity` | one instrument x observation period x liquidity metric | Liquidity/cash conversion output. |
| `calc_valuation` | one instrument x valuation date x calculation run | Current valuation summary, intrinsic value, margin of safety, dan verdict code. |
| `calc_valuation_methods` | one valuation x one method | Hasil per valuation method tanpa membuka formula di API publik. |
| `calc_classification` | one instrument x classification date x classification type | Classification dan consensus output. |
| `backtest_cases` | one instrument x one historical analysis case | Snapshot kondisi pada analysis date dan reference ke calculation result. |
| `backtest_case_methods` | one case x one valuation method | Intrinsic value/method output yang dipakai case. |
| `backtest_observations` | one case x one horizon | Price outcome pada horizon 3/6/9/12 bulan atau horizon yang dikonfigurasi. |

Backtest termasuk schema target karena produk memang menampilkan Historical Evidence. Implementasi awal boleh menyimpan lebih sedikit detail, tetapi tidak boleh merancang database seolah backtest tidak ada.

## 7. Identity Model

```text
companies
    |
    +--< instruments
            |
            +--< prices_daily
            +--< financial_periods --< financial_facts
            +--< dividend_events
            +--< calc_growth / calc_quality / calc_liquidity
            +--< calc_valuation --< calc_valuation_methods
            +--< calc_classification
            +--< backtest_cases --< backtest_observations

sectors
    |
    +--< instrument_sector_classifications >-- instruments
```

### Aturan identity

- Primary key internal memakai UUID atau integer generated database.
- Ticker bukan permanent primary key.
- Unique key minimal untuk instrument adalah `(exchange_code, ticker)`.
- `provider_symbol` disimpan terpisah karena format provider dapat berbeda dari ticker IDX.
- Company dan instrument tidak boleh digabung hanya karena saat ini satu ticker merepresentasikan satu saham.
- Nama sector/subsector dari source tidak boleh langsung menjadi classification hasil analytical engine.
- Hubungan sector memakai `effective_from` dan `effective_to` bila source mendukung sejarahnya.

## 8. Canonical Source Design

### 8.1 `prices_daily`

Kolom konseptual minimum:

```text
id
instrument_id
trading_date
open_price
high_price
low_price
close_price
volume
market_cap
currency_code
source_file_id
source_record_key
observed_at
created_at
```

Grain dijaga dengan unique constraint `(instrument_id, trading_date, price_variant)` bila suatu hari ada lebih dari satu price variant. Jangan diam-diam mengganti historical close tanpa provenance atau revision policy.

### 8.2 `financial_periods`

Kolom konseptual minimum:

```text
id
instrument_id
period_type          -- ANNUAL atau QUARTER
period_label         -- 2025 atau 2026-Q2
period_start
period_end
report_date
available_date
period_basis         -- STANDALONE, YTD, atau UNKNOWN
statement_scope      -- CONSOLIDATED, STANDALONE, atau UNKNOWN
source_file_id
source_record_key
```

`period_type` tidak boleh dipakai untuk menebak `period_basis`. Data quarterly bisa standalone atau YTD; semantics harus datang dari source atau diberi `UNKNOWN`, bukan ditebak oleh frontend.

### 8.3 `financial_facts`

Kolom konseptual minimum:

```text
id
financial_period_id
metric_code
value_numeric
unit_code
currency_code
value_sign_semantics
source_field
source_file_id
quality_status
```

Contoh `metric_code` dapat mencakup `revenue`, `cogs`, `interest_expense`, `net_income`, `operating_cash_flow`, `current_assets`, `current_liabilities`, `total_liabilities`, `total_equity`, `shares_outstanding`, dan `eps` bila tersedia.

`metric_code` adalah vocabulary internal yang terdokumentasi. Nama kolom display seperti `Revenue (M Rp)` bukan nama canonical metric.

Keuntungan desain ini dibanding table annual/quarterly yang wide:

- metric baru tidak memerlukan penambahan kolom table;
- annual dan quarterly menggunakan semantics yang sama;
- source yang tidak menyediakan metric dapat disimpan sebagai absent/null tanpa fabricated value;
- source field dan unit conversion tetap dapat diaudit;
- calculation dapat mengambil metric berdasarkan code dan period.

### 8.4 `dividend_events`

Kolom konseptual minimum:

```text
id
instrument_id
event_type
event_date
amount_per_share
currency_code
source_date_semantics
source_file_id
source_record_key
```

`event_date` tidak boleh dinamai `payment_date` kecuali source memang mendefinisikannya sebagai payment date. Annual dividend total dan dividend yield adalah derived result, bukan source event.

## 9. Data Type, Unit, dan Nullability

- Simpan angka sebagai numeric/decimal, bukan string berformat.
- Simpan tanggal sebagai date/timestamp sesuai semantics, bukan string presentation.
- Simpan percentage sebagai numeric dengan satu konvensi yang terdokumentasi; jangan mencampur `34.1` dengan `0.341` tanpa unit metadata.
- Simpan multiple seperti P/E sebagai numeric tanpa suffix display.
- Simpan uang canonical dalam absolute IDR bila currency source adalah IDR.
- Formatting `M Rp`, `B Rp`, `T Rp`, pemisah ribuan, dan label UI dilakukan API/frontend.
- Nilai yang tidak tersedia disimpan `NULL` atau status unavailable; jangan diisi nol kecuali nol memang dilaporkan.
- Unit conversion dari source ke canonical harus menghasilkan audit record, bukan hanya mengganti angka.

### Catatan kondisi sekarang

CSV di `Data/Converted` memakai header seperti `Revenue (M Rp)`. Itu valid sebagai dataset kerja atau export, tetapi belum ideal sebagai canonical database production. Pada tahap ingest ke database, nilai tersebut harus memiliki unit metadata yang jelas atau dikonversi ke absolute IDR sesuai policy.

## 10. Lineage dan Idempotency

```text
data_sources
    |
    +--< ingestion_runs
              |
              +--< ingestion_files
                        |
                        +-- source_file_id pada canonical facts
```

`ingestion_runs` minimal mencatat source/task, ticker scope, started/completed time, status `RUNNING`, `SUCCESS`, `PARTIAL`, atau `FAILED`, collector version, error summary, dan request range.

`ingestion_files` minimal mencatat logical archive key, file type, checksum, record count, first/last record date, raw/normalized status, dan reference ke `ingestion_run`.

### Idempotency

Ingestion yang diulang dengan payload dan source key yang sama tidak boleh menghasilkan duplicate canonical facts. Gunakan business key yang relevan:

- price: `(instrument_id, trading_date, price_variant)`;
- financial fact: `(financial_period_id, metric_code, source_revision)`;
- dividend event: provider event key atau kombinasi instrument, event type, event date, dan amount bila provider tidak memiliki ID;
- sector relationship: instrument, sector, effective period.

Jika source melakukan restatement, jangan overwrite tanpa policy. Simpan revision/status atau tandai record yang superseded.

## 11. Calculation Architecture

### 11.1 `calculation_runs`

Satu run menyimpan:

```text
id
calculation_type
status
started_at
completed_at
code_version
source_cutoff_at
source_ingestion_run_id
methodology_version_id
instrument_scope
input_hash
error_summary
```

Setiap `calc_*` table wajib memiliki `calculation_run_id`. Jangan memakai satu result tanpa mengetahui kapan dan dengan versi apa result tersebut dibuat.

`source_cutoff_at`, `source_ingestion_run_id`, dan `input_hash` adalah minimum reproducibility untuk v1. Jika kebutuhan audit bertambah, tambahkan immutable source snapshot.

### 11.2 `methodology_versions`

Table ini hanya mengidentifikasi method, bukan menyimpan resep rahasia. Contoh identifier:

```text
growth_v1
quality_v1
valuation_v1
classification_v1
backtest_v1
```

Version harus berubah jika perubahan code atau parameter dapat mengubah hasil. Hasil lama tidak dihapus hanya karena methodology baru dirilis.

### 11.3 Common calculated columns

Semua calculation table sebaiknya memiliki pola berikut bila relevan:

```text
id
instrument_id
calculation_run_id
methodology_version_id
observation_date / period_end
metric_code atau result_code
value_numeric
unit_code
status_code
created_at
```

Field yang ditampilkan sebagai label, badge, atau text explanation adalah API presentation atau derived label. Database boleh menyimpan code stabil, tetapi jangan menjadikan label UI sebagai key.

## 12. Valuation dan Backtest

### 12.1 Valuation

`calc_valuation` menyimpan ringkasan pada satu valuation date: current price, intrinsic value summary, margin of safety, consensus/classification code, calculation run, methodology, dan data availability/status.

`calc_valuation_methods` menyimpan satu row per method, minimal dengan valuation ID, method code, intrinsic value bila tersedia, status `VALID`, `UNAVAILABLE`, atau `INVALID_INPUT`, serta optional reason code.

Nama method dan hasil boleh dikirim ke frontend, tetapi formula dan input weight tidak boleh diasumsikan tersedia di browser.

### 12.2 Backtest

`backtest_cases` menyimpan snapshot kondisi saat analysis dilakukan, bukan hanya hasil akhir. Kolom konseptualnya meliputi:

```text
id
instrument_id
analysis_period_end
analysis_date
analysis_price
sector_snapshot
stock_type_snapshot
revenue_yoy
net_income_yoy
eps_momentum_code
revenue_momentum_code
roe_trend_code
dividend_yield
ocf_to_net_income
calculation_run_id
methodology_version_id
```

`backtest_case_methods` menyimpan intrinsic value setiap method yang digunakan pada case.

`backtest_observations` menyimpan horizon dan outcome:

```text
case_id
horizon_months
observation_date
high_price
low_price
close_price
return_percent
outcome_code
```

Outcome seperti `WIN`, `RECOVERED`, `RISK`, dan `FLAT` adalah code hasil calculation, bukan keputusan investasi. API harus menampilkan historical evidence dengan disclaimer yang konsisten dengan product specification.

## 13. Backend API Boundary

Backend API menjadi satu-satunya boundary yang dipakai frontend production. Contoh endpoint konseptual:

```text
GET /api/market/stocks
GET /api/instruments/{ticker}/overview
GET /api/instruments/{ticker}/financials
GET /api/instruments/{ticker}/growth
GET /api/instruments/{ticker}/valuation
GET /api/instruments/{ticker}/historical-evidence
```

API contract harus:

- menerima ticker sebagai lookup input, lalu resolve ke internal instrument;
- mengembalikan `asOf`, source status, dan data availability;
- membedakan `null`, unavailable, dan error;
- mengirim numeric value dan unit secara eksplisit;
- mengirim stable code untuk verdict/status, bukan hanya text yang sulit divalidasi;
- melakukan formatting display hanya jika contract memang memerlukannya;
- tidak membocorkan credential, raw provider response, atau formula private;
- mendukung ticker yang tidak tersedia tanpa fallback diam-diam ke saham lain.

Frontend prototype boleh menggunakan mock fallback untuk demo, tetapi production API tidak boleh mengganti ticker yang tidak ditemukan dengan `AUTO` atau instrument lain.

## 14. Data Quality dan Validation

Normalizer harus memiliki validation result per record atau batch. Minimal validasi:

- instrument berhasil di-resolve;
- period type, period end, report date, dan available date valid;
- annual/quarterly semantics tidak tertukar;
- nilai numeric dapat diparse tanpa kehilangan sign;
- unit conversion menghasilkan unit canonical yang benar;
- duplicate business key ditangani;
- price memiliki date dan close yang valid bila source menyediakannya;
- source missing field tetap menjadi null/unavailable;
- calculated result tidak dibuat dari input yang invalid tanpa aturan eksplisit.

Conversion audit yang saat ini sudah dihasilkan oleh pipeline adalah dasar yang baik, tetapi pada target database audit tersebut perlu memiliki relasi ke ingestion file/run dan canonical record bila memungkinkan.

## 15. Development Phases

### Phase A - Contract dan schema foundation

- kunci vocabulary `metric_code`, unit, status, dan period semantics;
- buat migration untuk identity, lineage, prices, periods, facts, dan dividends;
- buat unique constraint serta indexes untuk ticker, date, period, dan metric;
- dokumentasikan source mapping Sectors API -> canonical metric.

### Phase B - Ingestion persistence

- pertahankan raw archive;
- persist ingestion run dan file metadata;
- ingest minimal satu ticker end-to-end;
- validasi idempotency dan conversion audit;
- pastikan tidak ada absolute local path sebagai logical key.

### Phase C - Calculation persistence

- pindahkan calculation yang dibutuhkan dari frontend ke worker/backend;
- persist calculation run dan methodology version;
- isi valuation, growth, quality, liquidity, classification;
- persist minimal backtest case dan observation.

### Phase D - API integration

- implement endpoint per research tab;
- ganti mock runtime source dengan API adapter;
- tangani loading, empty, unavailable, dan error state;
- uji beberapa ticker, bukan hanya `AUTO`.

### Phase E - Production hardening

- retry dan rate-limit policy;
- monitoring ingestion dan calculation;
- retention policy raw archive;
- access control dan secret management;
- migration rollback dan backup/restore test;
- data freshness monitoring.

## 16. Architecture Rules

1. Raw archive dan canonical database adalah dua boundary berbeda.
2. Canonical data menyimpan typed value, unit, date semantics, dan provenance.
3. Company, listed instrument, sector, dan sector relationship tidak digabung tanpa alasan.
4. Ticker adalah identifier bisnis, bukan permanent primary key.
5. Annual dan quarterly dibedakan, tetapi metric vocabulary tidak diduplikasi tanpa kebutuhan.
6. Quarterly tidak otomatis berarti YTD atau standalone.
7. Missing value tidak boleh diubah menjadi nol atau fabricated value.
8. Source event tidak boleh dicampur dengan aggregate analytical result.
9. Setiap calculated result menunjuk ke `calculation_run_id` dan methodology version.
10. Backtest adalah historical evidence dan bagian dari domain schema, bukan recommendation engine.
11. Formula private berada di server-side calculation layer, bukan di Next.js browser bundle.
12. Frontend production mengakses backend API, bukan CSV/JSON lokal.
13. Ingestion harus idempotent dan aman terhadap partial failure.
14. Schema yang belum dimigration tidak boleh disebut implemented atau locked.
15. Perubahan pada metric semantics, grain, identity, atau lineage diperlakukan sebagai architecture change.

## 17. Definition of Ready untuk Backend

Backend implementation siap dimulai setelah database engine, deployment owner, migration tool, exchange/currency/unit convention, source-to-canonical mapping, restatement policy, duplicate policy, API response contract, methodology versioning, backtest horizon, outcome semantics, dan secret management disepakati.

Minimal satu sample ticker harus dapat melewati alur ingestion -> canonical -> calculation -> API sebelum integrasi frontend dilakukan secara luas.

## 18. Final Mental Model

```text
Sectors API / External Source
        v
Raw JSON Archive + Manifest
        v
Ingestion Run + Validation + Normalization
        v
Canonical PostgreSQL
  identity / prices / financial facts / dividends
        v
Calculation Run + Methodology Version
  growth / quality / liquidity / valuation / classification / backtest
        v
Backend API
        v
Next.js Research UI
```

### Final recommendation

Gunakan dokumen ini sebagai **baseline target architecture**. Jangan menyalin proposal awal secara literal dan jangan memberi label `LOCKED` sebelum migration, ingestion persistence, calculation persistence, dan API contract benar-benar diimplementasikan serta diuji pada lebih dari satu ticker.

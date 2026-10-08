# Backend sebagai satu-satunya sumber data (framework)

Dokumen ini adalah **desain**, bukan implementasi. Belum ada kode, tabel, atau data
Supabase yang diubah karena dokumen ini. Tujuannya menyepakati **di mana setiap
angka dihitung** sebelum satu baris kode ditulis, supaya:

1. **frontend** dan **n8n** membaca angka yang **sama persis** dari satu tempat;
2. **AI summary** (n8n) menerima data yang sudah bersih, berlabel unit, dan
   ter-dedup, sehingga tidak perlu menebak apa pun;
3. tidak ada lagi perhitungan bisnis yang hanya hidup di dalam browser.

Rujukan: `docs/BACKTEST_ARCHITECTURE.md` (aturan backtest),
`docs/CONSENSUS_ARCHITECTURE.md` (aturan consensus: simpan vs hitung),
`docs/SUPABASE_MANUAL_RUNBOOK.md` (cara menjalankan),
`docs/FRONTEND_SAMPLE_VS_CURRENT_AUDIT.md` (selisih UI vs database),
`docs/DATA_RULES.md` (aturan data).

---

## 1. Masalah yang diselesaikan

Saat ini angka yang tampil di UI berasal dari **dua tempat**:

| Sumber | Contoh | Sifat |
|---|---|---|
| Tabel hasil kalkulasi Supabase | `GROWTH_REVENUE_CAGR_LONG`, 5 nilai IV, tipe saham, 1.797 kasus backtest | sudah tersimpan, ada provenance |
| Dihitung ulang di browser (`stock-detail-adapter.ts`) | EPS, BVPS, ROE, Gross/Net Margin, MoS, CAGR window, YoY kuartalan, win rate | tidak tersimpan, tidak bisa diaudit, tidak terlihat n8n |

Akibatnya:

- **n8n tidak bisa melihat** angka baris kedua. Kalau n8n menghitungnya sendiri,
  ada dua implementasi rumus yang bisa berbeda hasil.
- **Tidak bisa diaudit.** Tidak ada `calculation_run_id` untuk EPS yang tampil di
  kartu, jadi tidak bisa ditelusuri kembali ke input mana yang menghasilkannya.
- **Rumus bisa menyimpang tanpa ketahuan.** Contoh nyata yang sudah terjadi:
  label kolom tabel menulis `YoY Change` padahal menghitung perubahan total 6
  tahun (lihat addendum Financial History di
  `docs/FRONTEND_SAMPLE_VS_CURRENT_AUDIT.md`).

**Sasaran dokumen ini:** setiap angka **bisnis** punya satu rumah di database.
Frontend dan n8n sama-sama membacanya, lalu masing-masing **memformat** sesuai
kebutuhannya sendiri.

---

## 2. Prinsip: angka di backend, tampilan di UI

Pemisahan ini bukan preferensi gaya, melainkan syarat agar data bisa dipakai
bersama oleh UI (manusia) dan AI (mesin).

**Disimpan di database — "apa nilainya":**

- nilai mentah (`19906774000000`)
- rasio (`0.419673`)
- label unit yang tidak ambigu (`IDR`, `RATIO`, `SHARES`, `PERCENT`)
- status (`VALID` / `UNAVAILABLE` / `NOT_CALCULABLE`) dan `flags` alasan
- provenance (`calculation_run_id`, `methodology_version_id`)

**Dihitung di UI — "bagaimana menampilkannya":**

- pembulatan & locale (`19906774000000` → `19,91`)
- satuan tampilan (`Rp Trillion`)
- tanda & warna (`+132,53%`, hijau/merah)
- placeholder (`"Not available"`, `"—"`)
- tata letak, urutan baris, geometri chart

**Alasan aturan ini tidak boleh dilanggar:**

| Kalau formatting ikut disimpan | Akibatnya |
|---|---|
| `"19,91"` sebagai `text` | n8n **tidak bisa** menghitung apa pun dari string; AI menerima angka yang sudah mati |
| `"Rp Trillion"` sebagai nilai | n8n tidak tahu `19,91` itu triliun atau miliar → risiko salah **1.000×** |
| `"Not available"` sebagai nilai | perbedaan **"datanya nol"** vs **"datanya tidak ada"** hilang; AI akan mengarang |
| locale `id-ID` (koma) di database | mengganti bahasa UI menjadi migrasi data, bukan perubahan kode |
| `+132,53%` sebagai nilai | tanda `+` dan `%` mengunci satuan; n8n tidak bisa membandingkan dengan angka lain |

Kesimpulan: **angka di backend, tampilan di UI.** Kalau n8n butuh label unit, itu
diambil dari kolom `unit_code`, bukan dari string yang sudah diformat.

---


## 3. Kondisi aktual (terverifikasi)

### 3.1 Yang sudah tersimpan di database

| Tabel | Isi | Baris | Metric/method code |
|---|---|---|---|
| `calc_annual_growth_quality` | 18 metrik annual | 4.828 | CAGR, CoV, momentum, NWC, forensic, DPR, Yield, YEARS_* |
| `calc_annual_ratios` | 9 rasio annual (**baru**, migrasi `0029`) | 1.278 | `EPS`, `BVPS`, `ROE`, `GROSS_MARGIN`, `NET_MARGIN`, `TOTAL_ASSETS`, `TOTAL_ASSETS_DERIVED`, `*_CAGR_WINDOW` |
| `calc_quarterly_quality` | 4 rasio kuartalan | 4.128 | `QUALITY_GROSS_MARGIN`, `QUALITY_NET_MARGIN`, `QUALITY_OCF_TO_NET_INCOME`, `QUALITY_ROE` |
| `calc_quarterly_growth` | 5 metrik QoQ | 5.160 | `*_QOQ` |
| `calc_metrics_classification` | 6 flag + FINAL_TYPE + CONFIDENCE | 180 | `CLASSIFICATION_*` |
| `calc_valuation_inputs` | 38 metrik input | 912 | `PE_PROJECTED`, `PBV_PERCENTILE`, `SECTOR_WEIGHT_*`, dst. |
| `calc_valuation_methods` | 5 metode IV | 120 | `DDM`, `DISCOUNTED_EARNINGS`, `MEAN_REVERSION_PBV`, `PETER_LYNCH`, `TYPE_SECTOR_WEIGHTED` |
| `calc_backtest_cases` | 1.797 kasus | 1.797 | `mos_main`, `verdict`, `verdict_mos`, dst. |
| `calc_backtest_methods` | 7.150 IV kasus | 7.150 | 5 method code |
| `financial_facts`, `financial_periods` | fakta kanonik | 6.722 / 658 | 12 metric code |
| `prices_daily`, `dividend_facts` | harga & dividen | 32.002 / 101 | — |
| `projection_scenarios`, `projection_values` | skenario proyeksi | 20 / 199 | 10 metric code |

**Fakta kanonik yang tersedia (`financial_facts`), 13 metric code:**

```
REVENUE, COST_OF_REVENUE, INTEREST_EXPENSE_NON_OPERATING, EARNINGS,
OPERATING_CASH_FLOW, GROSS_PROFIT, CURRENT_ASSETS, TOTAL_CURRENT_ASSET,
CURRENT_LIABILITIES, TOTAL_LIABILITIES, TOTAL_EQUITY, OUTSTANDING_SHARES,
TOTAL_ASSETS
```

`TOTAL_ASSETS` ditambahkan pada 2026-10-02 (keputusan S1) sehingga angka laporan
punya rumah kanonis; 142 baris dimuat untuk 20 ticker.

**Yang TIDAK ada** meski ada di raw JSON provider: `operating_pnl`,
`ebit`, `ebitda`, `inventories`, `fixed_assets`,
`free_cash_flow`, `capital_expenditure`. `operating_pnl` sengaja tidak dimuat
(keputusan S2: template tidak punya baris Laba Operasi dan tidak ada konsumennya);
sisanya karena `ANNUAL_FIELDS` di
`supabase/load_annual_financials_to_supabase.py` memetakan hanya field yang
dibutuhkan, dan `tests/test_auto_loader_mapping.py` mengunci daftar itu.

#### 3.1.1 Field yang bergantung sektor (keputusan S3)

Provider **menghilangkan key** (bukan mengirim `null`) untuk baris yang tidak
dimiliki sebuah sektor. Bank `BRIS` tidak melaporkan `inventories`,
`current_assets`, `capital_expenditure`, maupun `non_current_liabilities`;
23 ticker non-finansial di `Data/Raw` melaporkan keempatnya. Karena itu
`load_annual_financials_to_supabase.py` memisahkan:

| Konstanta | Isi | Perlakuan |
|---|---|---|
| `REQUIRED_SOURCE_FIELDS` | 29 field yang provider laporkan untuk semua emiten | key wajib ada; kalau hilang → `ANNUAL_SOURCE_MISSING_FIELD` |
| `SECTOR_DEPENDENT_SOURCE_FIELDS` | `inventories`, `current_assets`, `capital_expenditure`, `non_current_liabilities` | key boleh tidak ada; fakta kanonis ditulis `value_numeric=null`, `quality_status='MISSING'` |
| `RAW_MONETARY_FIELDS` | gabungan keduanya | dokumentasi kontrak penuh |

Sebelum keputusan ini BRIS gagal dengan `ANNUAL_SOURCE_MISSING_FIELD: row 1
missing inventories` — ticker bank pertama yang pernah masuk pipeline, jadi
asumsi "semua emiten punya neraca yang sama" belum pernah diuji.

Loader kuartalan memakai `realized_capital_goods_investment` sebagai **alias
capex** untuk bank. Perbandingan key-nya (`QUARTERLY_FIELD_MISMATCH`) tetap
strict dan hanya mentoleransi tepat satu pertukaran itu
(`capital_expenditure` hilang + `realized_capital_goods_investment` muncul);
field baru tak dikenal tetap gagal keras.

Test: `tests/test_sector_agnostic_loaders.py`.

### 3.2 Yang dihitung di frontend (harus dipindah)

Semua di `frontend/src/lib/stock-detail-adapter.ts` kecuali yang disebut lain.

| Fungsi | Rumus | Baris kode |
|---|---|---|
| `buildFinancialHistory` | EPS, BVPS, ROE, GM, NM, CAGR window | 217 |
| `buildAnnualMetrics` | ROE, GM, NM tahun terakhir | 453 |
| `buildQuarterlyMetrics` | GM, NM, amount | 502 |
| `buildGrowthVisuals` | EPS, YoY revenue & EPS | 539 |
| `buildThesisValidator` | YoY per kuartal | 582 |
| `buildValuationMetrics` | EPS, BVPS, P/E, P/BV | 1006 |
| `computeMos` | `(IV − harga) / IV` | 87 |
| `buildGrowthSummary` | CAGR short + badge | 821 |
| `buildForensicMetrics` | 4 metrik + label | 951 |
| `buildDividendConsistency` | DPR, Yield, Avg (4Y) | 683 |
| `pickMainMethod` | tipe saham → method utama | 48 |
| `methodStatus` | IV ≤ 0 → status | 115 |
| `classifyFinancialMetric` (`lib/analysis/valuation.ts`) | ROE vs rata-rata, margin trend | 50 |
| `preferredMainMethodCode` (`lib/analysis/valuation.ts`) | tipe → kode method | 11 |
| `buildHistoricalEvidencePreview` (`lib/analysis/historical-evidence.ts`) | win rate | 94 |
| `aggregateBacktestOverview` (`lib/analysis/backtest-overview.ts`) | agregat outcome | 17 |
| `countMethodsAboveAnalysisPrice` (`lib/analysis/backtest.ts`) | konsensus `x/y` | 156 |
| `classifyMosMain` / `classifyCurrentValuationMos` | MoS → verdict | 55 / 61 |
| `analyzeHistoricalGrowth` (`lib/analysis/growth.ts`) | analisis kartu growth | 12 |

### 3.3 Yang tetap di frontend (jangan dipindah)

| Fungsi | Alasan |
|---|---|
| `formatRupiah`, `formatCagr`, `formatPercentSigned`, `formatDecimal` | pembulatan + locale `id-ID` |
| `toRpTrillion`, `formatInterestExpense` | konversi satuan tampilan |
| `mapVerdict`, `methodDisplayName`, `valuationMethodLabel` | pemetaan kode → teks Inggris |
| `badgeFromGrowth`, `trendToneFromValue`, `verdictToneClass` | ambang warna/status visual |
| `UNAVAILABLE = "Not available"` | string placeholder |
| seluruh komponen `.tsx` | render, layout, ikon |

Catatan: `buildMonthlyPricePoints` **agregasi** (close terakhir per bulan) adalah
keputusan bisnis dan harus pindah; sedangkan penskalaan sumbu chart tetap di UI.

---

## 4. Issue kritis: duplikasi run

**Ini harus diselesaikan sebelum n8n membaca apa pun.** Tabel hasil menyimpan
satu baris per **run**, bukan per instrumen. Kondisi saat ini:

| Tabel | Baris | Run | Instrumen | Faktor duplikat |
|---|---|---|---|---|
| `calc_annual_growth_quality` | 4.828 | 40 | 20 | **2×** |
| `calc_quarterly_quality` | 4.128 | 40 | 20 | **2×** |
| `calc_backtest_cases` | 1.797 | 100 | 20 | **5×** |

Bukti terukur untuk `AUTO`, metric `GROWTH_REVENUE_CAGR_LONG`:

| Cara baca | Baris dikembalikan | Benar? |
|---|---|---|
| `where instrument_id = AUTO` | **14** | ❌ |
| join ke run `QUARTERLY_GROWTH_QUALITY` terbaru | 7 | ✅ |

**Kenapa terjadi:** `calculation_runs.idempotency_key` mencakup *input snapshot*.
Begitu ada input baru ke dalam snapshot (mis. DPR/Yield butuh DPS dan harga
year-end), run baru dibuat — bukan menimpa run lama — karena unique key tabel
adalah `(calculation_run_id, instrument_id, financial_period_id, metric_code)`.

**Kenapa RPC aman tapi tabel mentah tidak:** RPC `get_stock_research_data` sudah
memaku bacaannya ke run terbaru (migrasi `0021` untuk valuasi, `0026` untuk
backtest, `0028` untuk growth/quality). Perbaikan itu **ada di RPC**, bukan di
tabel. Siapa pun yang query tabel langsung — termasuk n8n — akan kena duplikat.

**Konsekuensi kalau dibiarkan:** AI menerima CAGR dua kali. Summary bisa
menyebut angka yang sama dua kali dengan konteks berbeda, atau menghitung
rata-rata dari data ganda. Untuk backtest 5× lebih parah.

**Solusi yang diminta:** view `*_latest` per tabel hasil yang otomatis hanya
memuat run `SUCCEEDED` terbaru per instrumen, sehingga query langsung pun aman.

---

## 5. Target arsitektur

```
                    ┌─────────────────────────────┐
                    │  Supabase (satu sumber)     │
                    │                             │
   fakta kanonik ──▶│ financial_facts             │
                    │ prices_daily, dividend_facts│
                    │ projection_*                │
                    └──────────┬──────────────────┘
                               │ dihitung oleh Python
                               ▼
                    ┌─────────────────────────────┐
                    │  Tabel hasil + provenance   │
                    │  calc_annual_growth_quality │
                    │  calc_quarterly_quality     │
                    │  calc_valuation_methods     │
                    │  calc_metrics_classification│
                    │  calc_backtest_*            │
                    └──────────┬──────────────────┘
                               │ view *_latest (dedup run)
                               ▼
                 ┌─────────────┴─────────────┐
                 │                           │
                 ▼                           ▼
        ┌────────────────┐         ┌──────────────────┐
        │ RPC untuk UI   │         │ RPC untuk AI     │
        │ (JSON utk      │         │ (JSON siap       │
        │  render)       │         │  konsumsi)       │
        └───────┬────────┘         └────────┬─────────┘
                │                           │
                ▼                           ▼
        ┌────────────────┐         ┌──────────────────┐
        │ Next.js        │         │ n8n              │
        │ format + render│         │ AI summary +     │
        │                │         │ berita           │
        └────────────────┘         └──────────────────┘
```

**Aturan:** panah ke bawah hanya boleh satu arah. UI **tidak** menghitung ulang
apa pun yang sudah dihitung Python; n8n **tidak** menghitung ulang apa pun yang
sudah ada di RPC. Kalau ada angka yang tidak ada di RPC, itu bug kontrak — bukan
alasan untuk menghitung di sisi konsumen.

---


## 6. Rencana pengerjaan

Empat langkah. Setiap langkah berdiri sendiri dan bisa diuji terpisah.

### Langkah 1 — Metrik annual yang hilang

**Tujuan:** `calc_annual_growth_quality` memuat semua rasio tahunan yang saat ini
dihitung di browser.

**Metrik baru yang diminta:**

| Metric code | Rumus | Unit | Sumber |
|---|---|---|---|
| `EPS` | `EARNINGS / OUTSTANDING_SHARES` | IDR/share | fakta kanonik |
| `BVPS` | `TOTAL_EQUITY / OUTSTANDING_SHARES` | IDR/share | fakta kanonik |
| `ROE` | `EARNINGS / TOTAL_EQUITY` | RATIO | fakta kanonik |
| `GROSS_MARGIN` | `GROSS_PROFIT / REVENUE` | RATIO | fakta kanonik |
| `NET_MARGIN` | `EARNINGS / REVENUE` | RATIO | fakta kanonik |
| `TOTAL_ASSETS` | `TOTAL_LIABILITIES + TOTAL_EQUITY` | IDR | identitas, lihat S1 |
| `REVENUE_CAGR_WINDOW` | `(last/first)^(1/(n−1)) − 1` | RATIO | fakta kanonik |
| `EARNINGS_CAGR_WINDOW` | idem untuk `EARNINGS` | RATIO | fakta kanonik |

**Aturan yang wajib dipatuhi (semuanya sudah terbukti di repo):**

1. **Satu snapshot per tahun annual**, seperti 16 metrik yang sudah ada —
   `populate_growth_quality._prepare_outputs` sudah melakukannya. Jadi `ROE`
   tahun 2022 tersimpan pada snapshot 2022, bukan hanya tahun terakhir.
2. **`OUTSTANDING_SHARES` di-carry forward** dari tahun terakhir yang
   melaporkannya (BIRD 2025 `null`). Backend sudah punya `annual_share_count`
   di `derive_projection_scenario.py` yang mundur untuk alasan yang sama —
   **pakai ulang fungsi itu, jangan tulis logika baru.**
3. **CAGR ditolak bila salah satu ujung ≤ 0**, dengan flag `NEGATIVE_BASE`.
   ARII dan GOLD jendelanya dimulai dari kerugian; akar dari bilangan negatif
   tidak boleh dihasilkan.
4. **Pembagian ditolak dengan `DENOMINATOR_ZERO`**, bukan menghasilkan `null`
   tanpa alasan.
5. **`EPS_DERIVED_FROM_EARNINGS`** adalah flag **provenance**, bukan
   missing-input. Nilainya tetap sah. Jangan biarkan flag ini memblokir
   pembagian lain (kesalahan ini pernah terjadi pada DPR).
6. **Setiap metrik baru masuk `ANNUAL_RATIO_METRICS`** di
   `calculate_quarterly_growth_quality.py`, karena `populate_growth_quality.py`
   memverifikasi set-nya sama persis. (Metrik rasio masuk tuple baru ini, bukan
   `ANNUAL_GROWTH_METRICS`, karena keputusan S3 memisahkan tabelnya.)

**Catatan implementasi (2026-10-02):** keenam aturan di atas sudah dipatuhi. Satu
tambahan yang tidak ada di daftar semula: **jumlah saham** yang dipakai EPS/BVPS
adalah jumlah saham **tahun terakhir yang dilaporkan, presisi penuh** — mengikuti
rumus `=Proj_Shares` di baris `Shares Outstanding [Juta]` template, yang muncul di
**setiap kolom**. Aturan 2 tetap dipatuhi dengan memakai ulang logika mundur-ke-tahun-
sebelumnya, **tetapi bukan** fungsi `annual_share_count`: fungsi itu membulatkan ke
juta untuk kebutuhan lembar proyeksi, dan pembulatan itu membuat hanya 49/70 sel
workbook cocok (ITMG 0/14). Presisi penuh cocok **70/70**.

Dua kesalahan yang sudah terukur dan diperbaiki:

| Kesalahan | Sel workbook yang cocok |
|---|---|
| Membagi tiap tahun dengan jumlah saham tahun itu | **29/70** (ITMG 2021 EPS `6139,41` vs template `6010,73`) |
| Membulatkan jumlah saham ke juta | **49/70** (ITMG 0/14, BIRD 7/14) |
| Presisi penuh, satu angka untuk seluruh tabel | **70/70** ✅ |

Karena perubahan ini mengubah angka tersimpan, `QUARTERLY_GROWTH_QUALITY` dinaikkan
dari `1.0.0` ke `1.1.0` (bukan ditimpa).

**Definition of done:**

- `ANNUAL_RATIO_METRICS` memuat 9 metrik baru (8 yang diminta + `TOTAL_ASSETS_DERIVED`
  karena keputusan S1 menyimpan kedua angka aset).
- Dry-run `python supabase/populate_growth_quality.py --ticker GEMA` melaporkan
  **18 growth + 9 ratio = 27** metrik per snapshot. (Dokumen ini semula menulis
  `18 → 26`; angka 26 dihitung sebelum S1 memutuskan menyimpan versi turunan.)
- 20 ticker di-`--apply` ulang; nilai 16 metrik lama **bit-identik** (dibuktikan
  dengan fingerprint 2.272 baris, `4c726ce2e1f9911ab7f7316e572ff97a` sebelum dan
  sesudah).
- Verifikasi numerik terhadap ERAA (data uji yang sudah dipakai):
  Revenue `32,94 … 76,61`, EPS `18,50 … 74,98`, ROE `5,9% … 11,8%`,
  Gross Margin `8,6% … 10,9%`, BVPS `312,15 … 638,08`.

### Langkah 2 — MoS tersimpan

**Tujuan:** MoS berhenti dihitung di browser, dan perbedaannya dengan `gap_ratio`
tidak lagi ambigu.

**Masalah:** dua angka berbeda dari data yang sama.

| Angka | Rumus | AUTO DDM |
|---|---|---|
| `calc_valuation_methods.gap_ratio` | `(IV − harga) / harga` | `−0,5739` |
| MoS yang ditampilkan UI (`computeMos`, aturan D6) | `(IV − harga) / IV` | `−1,3467` |

**Yang diminta:** tambah kolom `mos` di `calc_valuation_methods` (dan
`calc_backtest_methods` bila perlu), dihitung dengan aturan D6:

- `IV > 0` → `(IV − harga) / IV`
- `IV = 0` → `NULL` + flag `MOS_DENOMINATOR_ZERO`
- `IV < 0` → `NULL` + flag `MOS_NOT_APPLICABLE` (divisor negatif membalik tanda;
  GEMA Peter Lynch `−22` vs harga `93` akan menghasilkan `+522%` yang menyesatkan)

**Catatan:** `calc_backtest_cases.mos_main` **sudah ada**. Yang belum ada hanya
kolom di level method.

### Langkah 3 — RPC untuk AI

**STATUS: SELESAI (2026-10-02), migrasi `0031`.**

Keputusan **S4 = dua pintu**: `get_stock_research_data` (UI + n8n) dan
`get_stock_backtest` (backtest) tetap terpisah. Yang ditambahkan ke pintu pertama:

| Bagian baru | Isi |
|---|---|
| `annual_ratios` | 9 rasio, masing-masing dengan `unit_code`, `calculation_status`, `flags` |
| `valuation_methods[].mos` | aturan D6, di samping `gap_ratio` |
| `stock_classification` | `final_type`, `system_recommendation`, `confidence`, `rule_flags` |
| `data_quality.warnings` | 5 peringatan yang diturunkan dari flag tersimpan |

Catatan implementasi yang tidak ada di rancangan semula:

1. **`annual_ratios` tidak menyaring `VALID`.** `annual_growth` menyaring; bagian
   baru ini sengaja tidak, karena rasio yang ditolak guard adalah informasi
   ("CAGR tahun ini tidak tersedia karena jendelanya mulai dari rugi"). Kalau
   disaring, tahun itu terlihat *tidak ada* alih-alih *tidak tersedia*.
2. **`unit_code` dibawa per baris**, bukan diturunkan dari nama metrik. Ini
   persis yang mencegah AI salah 1.000× antara miliar dan triliun.
3. **Tipe run classifier adalah `CLASSIFICATION_DESCRIPTIVE`**, bukan
   `METRICS_CLASSIFICATION`. Percobaan pertama memakai nama yang salah dan
   bagian klasifikasi keluar `null` tanpa error — sekarang dikunci di blok
   `$verify$` (`STOCKLENS_CLASSIFICATION_RUN_TYPE_WRONG`) dan di
   `tests/test_research_rpc_annual_ratios.py`.
4. **Grant `calc_metrics_classification` ditambahkan** (per-kolom). Tabel itu
   sebelumnya tidak punya grant untuk `stocklens_market_reader`, yang juga
   ditutup oleh advisor RLS.

**Kontrak yang diminta** (`get_stock_research_data(p_ticker text)`):

```
{
  "instrument":   { ticker, company_name, sector_name, subsector_name, currency_code },
  "as_of":        { generated_at, latest_period, latest_valuation_date },
  "provenance":   { calculation_run_id, methodology_version_id, code_version },
  "annual":       [ { period_label, metric_code, value, unit_code, status, flags } ],
  "quarterly":    [ ... ],
  "valuation":    [ { method_code, method_name, intrinsic_value, current_price,
                      gap_ratio, mos, verdict, stock_type, status, flags } ],
  "stock_type":   { final_type, system_recommendation, confidence, rule_flags },
  "backtest":     { total_cases, outcomes: {...}, win_rates: {...} },
  "data_quality": { warnings: [...] }
}
```

**Aturan wajib:**

1. **Dedup run** — pakai pola `latest_run` yang sudah ada di `0026`/`0028`.
2. **`unit_code` disertakan untuk setiap nilai.** Ini yang mencegah AI salah
   1.000× antara miliar dan triliun.
3. **`value` numerik, bukan string terformat.** n8n yang memutuskan cara
   menampilkannya.
4. **`status` + `flags` disertakan.** AI harus bisa membedakan "nol" dari
   "tidak ada", dan "ditolak guard" dari "input hilang".
5. **Read-only**, `security definer`, `set search_path = ''`, grant hanya ke
   `anon`/`authenticated` — mengikuti pola RPC yang sudah ada.
6. **Kolom `data_quality.warnings`** untuk hal seperti `OUTSTANDING_SHARES`
   carried forward, `high_price = 0` fallback, atau periode yang belum
   point-in-time.

### Langkah 4 — Rampingkan adapter

**STATUS: SELESAI (2026-10-02).** Perhitungan bisnis yang dipindahkan:

| Dulu dihitung di browser | Sekarang dibaca dari |
|---|---|
| `computeMos` | `calc_valuation_methods.mos` (aturan D6) |
| `ratioSeries(EARNINGS, TOTAL_EQUITY)` → ROE | `annual_ratios.ROE` |
| `ratioSeries(GROSS_PROFIT, REVENUE)` → Gross Margin | `annual_ratios.GROSS_MARGIN` |
| `ratioSeries(EARNINGS, REVENUE)` → Net Margin | `annual_ratios.NET_MARGIN` |
| `perShareSeries(EARNINGS)` → EPS | `annual_ratios.EPS` |
| `perShareSeries(TOTAL_EQUITY)` → BVPS | `annual_ratios.BVPS` |
| `windowCagr(factSeries(REVENUE))` | `annual_ratios.REVENUE_CAGR_WINDOW` |
| `windowCagr(factSeries(EARNINGS))` | `annual_ratios.EARNINGS_CAGR_WINDOW` |
| EPS di `buildGrowthVisuals` | `annual_ratios.EPS` |
| Gross/Net Margin di `buildQuarterlyMetrics` | `quarterly_quality.QUALITY_*` |
| Total Assets (tidak ditampilkan) | `financial_facts.TOTAL_ASSETS` |

Yang **tetap** di frontend (presentasi, bukan bisnis): pembulatan & locale,
`Rp Trillion`, tanda & warna, `"Not available"`, urutan baris, geometri chart.

Dua hal yang **sengaja tidak diubah**:

- **`windowCagrOf` tetap ada** sebagai fallback untuk baris yang backend-nya
  memang tidak menyimpan CAGR (Gross Profit). Hanya baris itu yang memakainya;
  Revenue dan Net Income memakai nilai tersimpan.
- **`lib/analysis/*.ts` belum dipensiunkan.** Isinya masih dipakai
  (`preferredMainMethodCode` menentukan main rule, `classifyFinancialMetric`
  mengisi label status kartu, `analyzeHistoricalGrowth` merangkum Growth tab,
  dan modul backtest dipakai tab Backtest). Memensiunkan sebagian akan
  memutus fungsi yang masih hidup, jadi langkah itu ditunda sampai setiap
  penggantinya punya rumah. Ini dicatat sebagai **sisa pekerjaan**, bukan
  diklaim selesai.

**Bukti tidak ada regresi:** `Testing/evidence_check/ui_vs_workbook_check.js`
membandingkan nilai yang **dirender UI** dengan **lima workbook asli**:
**70 dari 70 sel EPS/BVPS cocok**.


- Hapus semua perhitungan bisnis dari §3.2.
- Setiap kartu membaca nilai dari RPC, lalu memformat.
- `lib/analysis/*.ts` yang isinya hanya perhitungan bisnis dipensiunkan
  (`valuation.ts`, `growth.ts`, `historical-evidence.ts`, `backtest-overview.ts`,
  `backtest.ts` — sisakan yang benar-benar presentasi).
- **Perilaku UI harus tetap sama.** Uji regresi: nilai yang tampil sebelum dan
  sesudah refactor harus identik untuk 20 ticker.

---


## 7. Keputusan yang masih terbuka

Lima keputusan ini **belum diambil**. Chat yang mengerjakan implementasi harus
bertanya dulu, bukan memilih sendiri.

| # | Pertanyaan | Pilihan | Dampak |
|---|---|---|---|
| S1 | `TOTAL_ASSETS` diturunkan atau dimuat dari raw? | (a) turunkan `liabilities + equity`, (b) muat `total_assets` dari raw JSON | (a) tidak perlu re-ingest, tapi rekonstruksi. (b) butuh loader + test + migration + re-ingest 20 ticker. **Identitas `assets = liabilities + equity` sudah diverifikasi benar di 142/142 baris.** |
| S2 | `OPERATING_PNL` dimuat? | (a) muat dari raw, (b) tidak dipakai | Raw JSON punya `operating_pnl`, dan `operating_pnl = gross_profit − operating_expense` cocok di 141/142 baris (TLKM 2021 beda tipis). Workbook tidak punya baris ini. |
| S3 | Metrik baru pakai tabel yang ada atau tabel baru? | (a) `calc_annual_growth_quality`, (b) `calc_annual_ratios` | (a) konsisten dengan 16 metrik lain dan RPC sudah membacanya tanpa filter metric. (b) pemisahan lebih bersih tapi menambah tabel + grant + RPC. |
| S4 | Satu RPC untuk UI+AI atau dua? | (a) satu, (b) dua | (a) lebih sedikit kode, tapi bentuknya harus melayani dua kebutuhan. (b) `get_stock_research_data` tetap untuk UI, `get_stock_ai_payload` untuk n8n. |
| S5 | Hasil AI disimpan? | (a) tabel `ai_company_summaries`, (b) tidak disimpan | (a) popup bisa cache, bisa diaudit, bisa dibandingkan antar waktu. (b) lebih sederhana tapi setiap buka popup memanggil n8n lagi. |

### 7.1 Keputusan yang sudah diambil (2026-10-02)

Langkah 1 dan Langkah 2 sudah dikerjakan dengan keputusan berikut. S4 dan S5
**sengaja ditunda** karena keduanya baru berdampak di Langkah 3/4.

| # | Keputusan | Catatan |
|---|---|---|
| S1 | **Dua-duanya disimpan.** `TOTAL_ASSETS` = angka laporan (nilai resmi), `TOTAL_ASSETS_DERIVED` = `liabilities + equity` (audit). Selisih ditandai `TOTAL_ASSETS_RECONCILIATION_MISMATCH`. | Keputusan ini langsung menemukan bahwa identitas **tidak** persis di 142/142 baris: ARII, INKP, ITMG 2019 meleset 1 IDR. Lihat §8. |
| S2 | **Tidak dimuat.** `OPERATING_PNL` tidak ada sebagai baris di template dan tidak ada konsumennya. | `ANNUAL_FIELDS` tetap tidak memuat `operating_pnl`; `tests/test_auto_loader_mapping.py` mengunci itu. |
| S3 | **Tabel baru `calc_annual_ratios`** (migrasi `0029`). | 9 metric code: EPS, BVPS, ROE, GROSS_MARGIN, NET_MARGIN, TOTAL_ASSETS, TOTAL_ASSETS_DERIVED, REVENUE_CAGR_WINDOW, EARNINGS_CAGR_WINDOW. `unit_code` **per baris**, mengikuti `calc_valuation_inputs`. |
| Saham | **Jumlah saham tahun terakhir, presisi penuh** (rumus `=Proj_Shares` template). | Diuji ke 5 workbook asli: presisi penuh **70/70** sel cocok; per-tahun hanya 29/70; dibulatkan ke juta hanya 49/70. Perubahan angka menaikkan versi metodologi ke `1.1.0`. |
| S4 | **Dijawab: tetap DUA pintu** (2026-10-02). `get_stock_research_data` untuk UI dan `get_stock_backtest` untuk backtest, seperti sekarang. | Pemilik repo memutuskan backtest tetap terpisah karena n8n juga mengambilnya terpisah ("paling ku pisah antara perusahaannya, dan backtestnya"). Sumber datanya tetap satu; yang terpisah hanya cara mengantar. Konsekuensi: Langkah 3 **tidak** perlu menggabung payload, dan aturan "UI tidak berubah" di Langkah 4 jadi lebih mudah dipenuhi. |
| S5 | **Ditunda.** Rekomendasi: simpan di `ai_company_summaries`. | Baru relevan di Langkah 3/4. |

**Konsekuensi pada checklist §10:** karena S1 meminta dua angka disimpan, jumlah
metrik per snapshot menjadi **18 growth + 9 ratio = 27**, bukan `18 → 26` seperti
tertulis di Langkah 1. Angka 26 dihitung sebelum S1 diputuskan.

**Catatan untuk Langkah 3:** `calc_annual_ratios` sudah menyimpan `unit_code` per
baris. Kontrak AI di Langkah 3 cukup membacanya, tidak perlu menurunkan satuan
dari nama metrik.


---

## 8. Fakta yang sudah diverifikasi — jangan dihitung ulang

Semua ini sudah dicek ke database dan ke workbook asli.

**Unit.** `1 template unit = 1.000.000.000 IDR` (bukan 1 juta). Bukti:
`docs/reference/EXCEL_POSTGRES_VALIDATION.md` §"Unit reality check". Nilai `9,2`
di workbook AUTO 2026-Q2 = `9.224.000.000 IDR / 1e9`.

**Duplikasi run.** `calc_annual_growth_quality` 40 run untuk 20 instrumen;
`calc_backtest_cases` 100 run. Baca mentah = 2× dan 5× lipat. Lihat §4.

**`gap_ratio` ≠ MoS.** Lihat Langkah 2.

**Identitas neraca tidak persis 142/142.** `total_assets` (laporan) meleset **1
rupiah** dari `liabilities + equity` di **ARII, INKP, dan ITMG 2019** — 139 dari
142 baris persis sama, 3 sisanya berbeda 1 IDR dari nilai ratusan triliun. Ini
pembulatan sisi provider, bukan data rusak. Karena S1 menyimpan kedua angka,
ketiga baris itu kini ditandai `TOTAL_ASSETS_RECONCILIATION_MISMATCH` dan
terdeteksi otomatis. (Klaim lama "142/142" di §7 S1 dan di
`docs/FRONTEND_SAMPLE_VS_CURRENT_AUDIT.md` sudah dikoreksi.)

**Fakta kanonik kini 13 metric code.** `TOTAL_ASSETS` ditambahkan ke
`ANNUAL_FIELDS` (keputusan S1). `operating_pnl`, `ebit`, `ebitda` tetap tidak
dimuat.

**`OUTSTANDING_SHARES` kosong di tahun terakhir** untuk BIRD 2025. Backend
(`annual_share_count`) dan frontend sama-sama mundur ke tahun sebelumnya.

**Rentang periode.** Sebagian besar ticker punya 7 periode annual (2019–2025);
GOLD dan WIFI punya 8 (2018–2025). Tabel UI merender kolom dari `periods`, jadi
ticker dengan riwayat berbeda otomatis mendapat tabel lebih lebar.

**Kasus yang guard-nya aktif** (jangan dianggap bug):

| Ticker | Keadaan | Perilaku benar |
|---|---|---|
| ARII, GOLD | EPS awal negatif | CAGR `Not available`, bukan akar negatif |
| GOLD, JSMR, INDF | classifier tidak menemukan aturan pada tanggal kasus | `stock_type = null`, valuasi `VALUATION_UNAVAILABLE` |
| ARII, DSSA, GOLD | tidak punya dividen sama sekali | DPR/Yield kosong, dan itu sah |
| AUTO 2020 | EPS negatif | DPR `NULL` + `NEGATIVE_DENOMINATOR` (workbook menulis `−19846%`, yang oleh blueprint §5.7 sendiri disebut outlier) |

**Status metodologi.** `QUARTERLY_GROWTH_QUALITY` versi `1.0.0` masih `DRAFT`.
`BACKTEST_HISTORICAL` sudah sampai `1.4.0`. Jangan menimpa versi lama; naikkan
versi bila rumus berubah.

**Point-in-time.** `financial_periods.report_date` dan `available_date` **NULL**
untuk semua periode. Jadi tidak ada klaim point-in-time penuh; backtest memakai
akhir periode sebagai proksi dan menandainya `POINT_IN_TIME_UNAVAILABLE_DATE`.

**Akses.** Tabel `calc_*` punya RLS aktif tetapi **tanpa policy** untuk
`anon`/`authenticated`. `stocklens_market_reader` tidak punya grant untuk
`calc_metrics_classification`, `calc_valuation_inputs`, dan `calc_backtest_*`.

---

## 9. Aturan yang mengikat

1. **Jangan ubah `calc_valuation_*`** untuk keperluan backtest — backtest punya
   tabelnya sendiri. (Keputusan lama, masih berlaku.)
2. **Jangan hapus atau timpa baris registry metodologi.** Naikkan versi.
3. **Jangan tambah `--stock-type` manual.** Tipe dihitung classifier.
4. **Jangan pakai `anon` key untuk n8n.** n8n harus pakai `service_role` di sisi
   server.
5. **Jangan taruh `service_role` key di frontend.**
6. **Jangan menghitung ulang di sisi konsumen** (UI maupun n8n) apa pun yang
   sudah ada di RPC. Kalau angkanya tidak ada, itu bug kontrak.
7. **Jangan simpan string terformat sebagai nilai.** Lihat §2.
8. **Setiap metrik baru wajib punya flag** untuk setiap cabang penolakan, supaya
   "nol" dan "tidak ada" tidak pernah tercampur.

---

## 10. Checklist verifikasi

Setiap langkah dianggap selesai hanya bila:

- [x] `python -m unittest discover -s tests -t .` lulus seluruhnya (**438**; baseline 383)
- [x] `py_compile` lulus untuk setiap file Python yang diubah
- [x] `npx tsc --noEmit` lulus di `frontend/` (exit 0)
- [x] `npx eslint src/` tidak menambah error baru (0 error, 10 warning yang sudah ada)
- [x] `npm run build` lulus
- [x] Tiga harness `Testing/evidence_check/{check,valuation_check,render_check}.js` lulus
- [x] Nilai metrik lama **bit-identik** sebelum vs sesudah — fingerprint 2.272 baris `4c726ce2e1f9911ab7f7316e572ff97a` identik (16 metrik growth; lihat catatan di bawah)
- [x] Tidak ada duplikat di RPC: `rows == distinct_pairs` untuk 20 ticker (1.278 = 1.278)
- [x] Verifikasi numerik terhadap ticker uji (ERAA untuk rasio, GEMA untuk dividen, AUTO untuk parity workbook)
- [x] Verifikasi terhadap **5 workbook asli**: 70/70 sel EPS/BVPS cocok (`tests/test_workbook_share_basis.py`)
- [x] Verifikasi **UI yang dirender** vs 5 workbook asli: **70/70** cocok (`Testing/evidence_check/ui_vs_workbook_check.js`)
- [x] Dokumentasi diperbarui: `SUPABASE_MANUAL_RUNBOOK.md` (§1.6.1, §1.6.2, §1.8), `FRONTEND_SAMPLE_VS_CURRENT_AUDIT.md` (addendum), dokumen ini (§7.1, §8, §10)
- [x] `supabase/get_advisors` diperiksa setelah perubahan DDL (temuan RLS turun 13 → 12; tidak ada temuan baru)

**Sisa pekerjaan yang dicatat, bukan diklaim selesai:**

- `lib/analysis/*.ts` belum dipensiunkan (lihat Langkah 4). Isinya masih dipakai
  untuk main-rule, label status kartu, ringkasan Growth tab, dan tab Backtest.
- Aturan win-rate backtest (`≥3 metode`, `MoS ≥30%`) masih hidup di
  `lib/analysis/backtest.ts`, belum pindah ke SQL. Karena S4 memutuskan backtest
  tetap di RPC-nya sendiri, ini tidak menghalangi UI maupun n8n hari ini; ia
  menjadi relevan bila n8n mulai butuh agregat backtest.


**Bukti Langkah 1–2 (2026-10-02):**

| Pemeriksaan | Hasil |
|---|---|
| Metrik per snapshot | 18 growth + 9 ratio = **27** (S1 menyimpan `TOTAL_ASSETS_DERIVED`) |
| `calc_annual_ratios` | 1.278 baris, 20 instrumen, 142 baris per metric code |
| 16 metrik growth bit-identik | ya — fingerprint sama |
| Sel EPS/BVPS vs 5 workbook | **70/70** cocok |
| `mos` terisi | 102 dari 120 baris; 8 IV null, 8 IV = 0, 2 IV < 0 |
| AUTO DDM | `gap_ratio −0,5739` vs `mos −1,3467` — dua angka berbeda, keduanya tersimpan |
| GEMA Peter Lynch (IV −22) | `mos` NULL + `MOS_NOT_APPLICABLE` (bukan `+522%`) |
| Rekonsiliasi aset | 3 baris terdeteksi: ARII/INKP/ITMG 2019, selisih tepat 1 IDR |
| ITMG EPS 2021 | `6010,73` — sama dengan workbook (sebelum perbaikan: `6139,41`) |
| ERAA | Revenue 32,94→76,61 · EPS 18,50→74,98 · ROE 5,9%→11,8% · GM 8,6%→10,9% · BVPS 312→638 |

**Catatan penting soal "bit-identik".** Klaim itu berlaku untuk **16 metrik
growth** (`calc_annual_growth_quality`), dan itu sudah dibuktikan. Metrik
**ratio** (`calc_annual_ratios`) adalah tabel baru, jadi tidak punya nilai
"sebelum" untuk dibandingkan. Namun di dalamnya, EPS dan BVPS **sengaja berubah**
dari implementasi pertama: aturan sahamnya salah (lihat §6 Langkah 1), dan
perbaikannya mengubah 153 nilai. Angka yang benar sekarang adalah yang cocok
dengan workbook (70/70), bukan yang cocok dengan implementasi pertama.

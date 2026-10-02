# Panduan manual: ticker baru dan update data

Panduan ini untuk menjalankan alur data StockLens secara **manual** dari Windows PowerShell. Contoh perintah dijalankan dari root repository `D:\Stock Analyzer`. Ganti `AUTO` dengan ticker yang sedang dikerjakan.

## Jawaban singkat: metrik dan proyeksi sudah jalan?

- **Semua 19 ticker sudah lengkap:** AMRT, ARII, AUTO, BIRD, DSSA, ERAA, GEMA, GOLD, INDF, INDS, INKP, IPOL, ITMG, JSMR, MIDI, PTBA, SIDO, WIFI. Masing-masing punya periode finansial, harga harian, growth/quality, skenario proyeksi aktif, tipe saham tersimpan, dan 5–15 metode valuasi.
- **Satu perintah per ticker:** `python run_pipeline.py TICKER` menjalankan seluruh alur (upload raw, ingest, load canonical, growth, proyeksi, klasifikasi, valuasi).
- **Proyeksi:** skenario diturunkan dari actuals oleh `supabase/derive_projection_scenario.py` (rumus `DataInputProyeksi`), jadi setiap ticker yang actualnya sudah dimuat bisa punya skenario sendiri.
- **Klasifikasi tipe saham:** sudah otomatis. `supabase/derive_classifier_inputs.py` menurunkan input classifier dari data canonical, `supabase/populate_metrics_classification.py` menyimpan hasilnya ke `calc_metrics_classification`, dan `calculate_valuation.py` membacanya sehingga `--stock-type` tidak lagi wajib.
- **Belum berarti semua analisis lengkap atau otomatis:** workflow belum berjalan otomatis/scheduled. `report_date` dan `available_date` periode finansial juga masih kosong, sehingga hasil tidak boleh dianggap point-in-time/backtest-safe. Backtest belum dijalankan.
- Data yang dimuat sudah lolos validasi skema/checksum dan perbandingan skenario historis yang dikerjakan. Ini bukan jaminan independen bahwa seluruh nilai sumber benar; tetap cocokkan raw/API dengan laporan emiten bila angka dipakai untuk keputusan.

## 1. Prasyarat sekali per sesi terminal

Buka PowerShell di `D:\Stock Analyzer`:

```powershell
Set-Location 'D:\Stock Analyzer'
$env:SECTORS_API_KEY = 'API_KEY_SECTORS_APP'
$env:SUPABASE_URL = 'https://PROJECT_REF.supabase.co'
$env:SUPABASE_SERVICE_ROLE_KEY = 'SERVICE_ROLE_KEY'
```

Ambil credential dari sumber rahasia yang benar. Jangan masukkan key ke Git, file dokumentasi, frontend, atau screenshot/log yang dibagikan. Karena key `service_role` memberi akses server-side yang luas, tutup terminal setelah selesai. Script collector membutuhkan `SECTORS_API_KEY`; script Supabase membutuhkan dua variabel Supabase.

Pastikan Python dan dependency `requests` tersedia:

```powershell
python --version
python -c "import requests; print('requests OK')"
```

## 1.5 Cara cepat: satu perintah untuk seluruh alur ticker

Seluruh langkah di bagian 3 dan 4 sudah dibungkus menjadi satu perintah. Jalankan dari root repository:

```powershell
python run_pipeline.py TICKER
```

Untuk ticker yang belum pernah diunduh sama sekali, perintah yang sama juga bekerja (langkah raw otomatis mengambil dari API):

```powershell
python run_pipeline.py AADI
```

Orchestrator menjalankan langkah-langkah berikut secara berurutan, memakai script yang sama seperti jalur manual:

| # | Step | Perintah yang dijalankan |
|---|---|---|
| 1 | `upload-raw` | `supabase/upload_raw_storage_only.py TICKER --yes` |
| 2 | `ingest-raw` | `supabase/ingest_raw_history.py --symbol TICKER --apply` |
| 3 | `load-identity` | `supabase/load_identity_to_supabase.py TICKER --ingestion-run-id ...` |
| 4 | `load-annual` | `supabase/load_annual_financials_to_supabase.py TICKER` |
| 5 | `load-quarterly` | `supabase/load_quarterly_financials_to_supabase.py TICKER` |
| 6 | `load-dividend` | `supabase/load_dividend_to_supabase.py TICKER` |
| 7 | `load-prices` | `supabase/load_daily_prices_to_supabase.py TICKER` |
| 8 | `growth-quality` | `supabase/populate_growth_quality.py --ticker TICKER --apply` |
| 9 | `projection` | `supabase/derive_projection_scenario.py TICKER --apply` |
| 10 | `classification` | `supabase/populate_metrics_classification.py --ticker TICKER --apply` |
| 11 | `valuation` | `supabase/calculate_valuation.py --ticker TICKER --risk-free-from-reference --apply` |
| 12 | `backtest` | `supabase/run_backtest.py --ticker TICKER --apply` |

Langkah 12 adalah backtest historis: daftar kasus, metrik harga murni
(`Ret 3M`…`Ret 12M`, `Harga Peak`/`trough`, `Bln Peak`, `Ret Peak`/`Ret Down`),
valuasi per kasus, konsensus, dan MoS dari lima metode workbook, lalu
**verdict** (`Verdict by Method`) dan `verdict_mos` (`Verdict MoS`) dengan
rumus workbook apa adanya (`docs/BACKTEST_ARCHITECTURE.md` bagian 5.4.1).

Yang **belum** dikerjakan: tidak ada. Fase 4 (RPC + UI) selesai lewat
`supabase/migrations/0026_stock_research_backtest_rpc.sql`.

**Fase 4 — RPC dan UI.** `get_stock_backtest(p_ticker)` mengembalikan hasil
tersimpan untuk satu ticker: run `SUCCEEDED` terbaru, seluruh kasus dengan lima
IV, konsensus, MoS, verdict, dan `context` (Revenue YoY, Net Income YoY, EPS /
Revenue momentum). Tabel `calc_backtest_*` tetap privat - RPC adalah satu-satunya
permukaan yang diekspos, dan `anon`/`authenticated` tidak punya grant SELECT ke
tabelnya (dijaga blok `$verify$` di migration).

`context` **tidak** disimpan di `calc_backtest_cases` (skema bagian 4.1 tidak
punya kolomnya). Nilainya diturunkan PIT di dalam RPC:

- Revenue YoY / Net Income YoY = kuartal vs kuartal yang sama setahun sebelumnya,
  dari `financial_facts`. Hanya periode dengan `period_end <= analysis_date` yang
  dibaca. Dicocokkan ke workbook untuk 18 kasus AUTO: sama persis sampai 12
  desimal (2022-Q1 revenue `0.266892321647`, earnings `0.374660655568`).
- EPS / Revenue momentum = metrik annual `QUALITY_*_MOMENTUM` pada **base year**
  kasus itu (`1` = Accelerating, `0` = Slowing). Juga dicocokkan 18/18.

Tiga kolom context sengaja `null` karena belum ada aturannya di repo ini:
`ROE Trend`, `Yield (%)`, dan `OCF / NI Ratio`. Mengarang aturan untuk ketiganya
akan menghasilkan angka palsu, jadi UI menampilkannya sebagai "Belum Tersedia".

Dua kolom baru ikut ditambahkan sepanjang Fase 4:

- `trough_month` (`Bln Trough`). Pasangan `peak_month`. Ini **wajib disimpan**:
  workbook memakai `DATEDIF` (bulan penuh) sedangkan `monthsBetween` di frontend
  menghitung batas bulan, sehingga kasus ber-tanggal-akhir-bulan berbeda satu
  bulan. 75 dari 367 kasus bernilai `0` dan akan salah tampil kalau dihitung ulang
  di browser.
- `return_magnitude` / `return_magnitude_down` (ambang ±10%, dari perilaku
  frontend, bukan dari workbook).

**Versi 1.3.0 - penyempurnaan aturan (4 perubahan).** Hasil lama tetap utuh;
`1.3.0` adalah versi baru, bukan timpaan.

1. **`IV = 0` keluar dari penyebut konsensus.** Workbook menandainya
   `IF(B25=0, "⚪ N/A (Skip)", ...)`, jadi saham tanpa dividen menghasilkan `3|4`,
   bukan `3|5`. Ini yang membuat penyebutnya benar-benar bervariasi (`/3`, `/4`,
   `/5`) dan bukan selalu 5. Bukti: dari 72 baris ber-IV lengkap, aturan "IV=0
   di-skip" cocok 72/72 sedangkan "IV=0 valid" gagal di INDF 2024-Q4 dan 2025-Q2.
   `IV` negatif tetap valid (D5).
2. **Satu ambang harga untuk kedua klasifikasi: `×1.20` naik, `×0.85` turun.**
   Sebelumnya `OVERVALUED` memakai `×1.15`/`×0.9`.
3. **`OBSERVE` tidak dipakai lagi** (cabang "tidak menyentuh apa pun" jadi `FLAT`),
   dan **hari yang sama** jatuh ke `WIN`/`REPRICE` karena cabang terakhir memakai
   `<`. `RECOVERED` sekarang hanya untuk yang benar-benar turun dulu lalu naik.
   Konsensus tetap **dua kelas** - `MIXED` tidak pernah dihasilkan.
4. **Kasus yang belum berumur 4 bulan dibuang.** Laporan kuartalan IDX baru terbit
   sekitar 3-4 bulan setelah akhir periode. Kuartal terbaru (mis. `2026-Q2` per
   30 September) tidak ditampilkan; DSSA yang kuartal terakhirnya `2026-Q1` tetap
   ada karena sudah 6 bulan.

Hasil `1.3.0`: 348 kasus (dari 367), 0 `OBSERVE`, penyebut `/3` 23 kasus, `/4` 74
kasus, `/5` 225 kasus.

**Versi 1.4.0 - tipe saham per kasus (D7 ditutup).** Hasil lama tetap utuh;
`1.4.0` adalah versi baru, bukan timpaan.

Sebelumnya `calc_backtest_cases.stock_type` berisi **satu snapshot terbaru** yang
disalin ke semua kasus, ditandai flag `STOCK_TYPE_LATEST_SNAPSHOT`. Workbook
menghitung ulang `MetricsClassification` tiap kasus, jadi itu salah secara
material: tipe memilih bobot referensi (CYCLICAL → PBV-heavy, TURN AROUND →
aset, dst.), sehingga tipe yang salah menggeser Peter Lynch IV, konsensus, MoS
Main, `mos_method_code`, verdict, dan kedua Win Rate di UI.

`1.4.0` menghitung ulang tipe **pada tanggal setiap kasus**, dengan potongan
point-in-time yang sama dengan valuasi kasus itu (lihat
`docs/BACKTEST_ARCHITECTURE.md` D7). Konsekuensinya:

- flag `STOCK_TYPE_LATEST_SNAPSHOT` **tidak lagi ditulis** (baris lama tetap
  memuatnya di `flags`-nya sendiri);
- bobot/ambang tipe dipilih per tipe kasus, bukan per tipe hari ini;
- `details.stock_type_raw`, `details.base_quarter`, `details.stock_type_fingerprint`,
  dan `details.stock_type_source` (`RECOMPUTED` / `CACHE` / `GIVEN`) menyimpan
  provenance tipe per baris.

Cache tipe: kuncinya `(instrument_id, case_quarter)`, dipakai ulang hanya bila
**sidik input** (`details.stock_type_fingerprint`) masih sama. Revisi laporan,
perubahan ambang classifier, atau harga/dividen baru pada/sebelum tanggal kasus
mengubah sidiknya dan memaksa perhitungan ulang; run lama tanpa sidik
menghasilkan cache kosong.

Hasil perbandingan dengan workbook `Backtest_Historical (New)` kolom `Jenis
Saham` (277 kasus): 180 (65,0%) cocok sebelum, 201 (72,6%) sesudah; batas atas
classifier per kasus 215 (77,6%). Sisa 62 mismatch adalah batas metodologi
(19 GOLD, 11 WIFI, 7 INDF, 6 `BASE_QUARTER_FACT_MISSING`), bukan bug.

Jalankan `python Testing/stock_type_pit_check.py ALL` untuk memeriksa ulang, dan
`python Testing/stock_type_audit.py` untuk laju mismatch terhadap workbook.
**Versi growth/quality (bukan backtest) - rasio dividen DPR & Yield.** Hasil
lama tetap utuh; run baru, bukan timpaan.

Dua metrik annual baru masuk ke `calc_annual_growth_quality`, sehingga baris
DPR dan Yield pada kartu Dividend Consistency (dan sumbu Yield di chart Dividend
Trend pada tab Growth) akhirnya terisi:

| Kode | Rumus | Sumber Excel |
|---|---|---|
| `DIVIDEND_PAYOUT_RATIO` | `DPS / EPS` | `DataInput!B28` = `B26/B30` |
| `DIVIDEND_YIELD` | `DPS / harga close akhir tahun fiskal` | `DataInput!B29` = `B26/B25` |

Poin penting:

- **Basis harga Yield adalah point-in-time akhir tahun**, bukan harga terbaru
  (blueprint §5.8 menandai ini *critical*). Itu sebabnya nilainya **disimpan**
  sebagai hasil kalkulasi, bukan dihitung di browser: RPC hanya mengirim 260
  baris harga terakhir, yang untuk GEMA baru mulai Agustus 2025 - tidak ada
  close 31 Desember 2022-2025 di payload sama sekali.
- **`dividend_facts.yield_ratio` tetap tidak dipakai** (NULL di semua baris).
  Kolom provider itu memakai basis TTM/harga yang berbeda dari template.
- Kedua baris **selalu ada** walau nilainya tidak bisa dihitung, dengan flag
  `DIVIDEND_PER_SHARE_MISSING` (tidak ada DPS tahun itu) atau `PRICE_MISSING`
  (tidak ada close di tahun fiskal itu). DPS nol yang tercatat adalah nilai
  sah (`VALID`), bukan dianggap hilang.
- **Deviasi sadar dari workbook: EPS negatif menolak DPR.** Workbook AUTO 2020
  menghasilkan DPR `-19846%` (disebut sendiri oleh blueprint §5.7 sebagai
  outlier yang diserap `TRIMMEAN`). Di sini `_divide_optional` mengembalikan
  `NULL` + `NEGATIVE_DENOMINATOR`, mengikuti konvensi `ratio_result` yang
  dipakai semua rasio lain di modul ini. Efeknya hanya pada **tampilan**:
  sel 2020 berisi "Not available", bukan angka negatif raksasa. Proyeksi tidak
  terpengaruh, karena `derive_projection_scenario.annual_dpr_series` memakai
  seri DPS/EPS-nya sendiri, bukan metrik ini.
- Verifikasi terhadap workbook GEMA: 2024 DPR `43,6%` (workbook `43,6%`),
  2025 `22,6%` (`22,6%`), 2020 `632,9%` (`634,6%` - selisih dari
  `OUTSTANDING_SHARES` provider yang dibulatkan). Yield 2024/2025 `3,09%`
  (workbook `3,1%`), 2020 `1,45%` (`1,4%`).

Dua perubahan pendukung yang menyertainya:

1. `populate_growth_quality.py` kini membaca `dividend_facts` dan `prices_daily`
   dan memasukkannya ke `input_snapshot` run, sehingga dividen yang berubah atau
   harga yang direvisi membuat run baru - bukan meninggalkan rasio lama yang basi.
2. `supabase/migrations/0028_stock_research_latest_growth_run.sql` memaku bacaan
   `calc_annual_growth_quality` dan `calc_quarterly_quality` di RPC ke run
   `QUARTERLY_GROWTH_QUALITY` **terbaru**. Tanpa itu, menambah input ke snapshot
   membuat run kedua dan RPC - yang join-nya hanya lewat `instrument_id` - akan
   mengembalikan setiap metrik annual dua kali. Ini cacat yang sama dengan yang
   diperbaiki `0021` untuk valuasi dan `0026` untuk backtest.



UI: `get_stock_backtest` dibaca di `app/market/[ticker]/page.tsx` bersama
`get_stock_research_data` (dua-duanya paralel), lalu diadaptasi oleh
`frontend/src/lib/backtest-adapter.ts`. Verdict **ditampilkan apa adanya** dari
DB; `calculateSimulatedVerdict` tidak dipakai lagi, supaya tidak menghidupkan
kembali drift D4. Badge "Demo Data" hilang sendiri karena `isDemoData` tidak lagi
diisi saat hasil tersimpan ada; dataset sampel hanya jadi fallback untuk AUTO.

Dua kolom verdict tetap NULL bila memang tidak bisa dihitung, dan itu disengaja:
kasus yang konsensusnya `N/A` (metode valid < 3) atau yang `MoS Main`-nya NULL
tidak punya `K`, jadi rumusnya tidak menghasilkan verdict. Mengisinya dengan
`FLAT` akan menciptakan klaim yang tidak bisa dibedakan dari verdict asli.
Flag `VERDICT_NO_CONSENSUS` / `VERDICT_MOS_UNDEFINED` / `VERDICT_NO_PRICE_WINDOW`
di `flags` menandai alasannya.

Setiap kali aturan verdict ikut berubah, `formula_text`/`parameter_spec` di
`backtest_engine.py` berubah, sehingga hash-nya berubah. Naikkan `METHOD_VERSION`
- jangan pernah menimpa baris registry yang sudah ada. Versi lama sengaja
dibiarkan hidup supaya hasil lama tetap bisa direproduksi; `run_backtest.py`
akan menolak jalan (`BACKTEST_METHODOLOGY_REGISTRY_DRIFT`) kalau hash di registry
tidak lagi cocok dengan kode, dan itu memang sinyal untuk menaikkan versi.

Jalankan tanpa `--apply` untuk melihat angkanya lebih dulu. Ticker yang
classifier-nya tidak menemukan aturan yang cocok **pada tanggal kasus** (GOLD,
JSMR, INDF) tetap tersimpan metrik harganya, dengan valuasi bertanda
`VALUATION_UNAVAILABLE` dan alasan `STOCK_TYPE_UNRESOLVED` di
`details.methods[].details.reason`. Tipe mentah classifier tersimpan di
`details.stock_type_raw` supaya bisa dibandingkan dengan workbook.

Yang **tidak** lagi perlu dikerjakan manual:

- **Mencari `ingestion_run_id`.** Orchestrator membacanya dari `ingestion_runs` + `ingestion_files` (run sukses terbaru yang punya file family `info`). Tidak perlu copy-paste dari output terminal.
- **Mengunggah raw dari disk.** Langkah 1 melakukannya, sehingga ticker dengan raw lokal tidak memerlukan API.
- **Mengisi `--stock-type`.** Langkah 10 menyimpan hasil classifier, dan langkah 11 membacanya. `calculate_valuation.py` menolak berjalan bila hasil klasifikasi belum ada, sehingga tipe tidak pernah ditebak.

Opsi berguna:

```powershell
python run_pipeline.py TICKER --dry-run                      # cetak perintah saja
python run_pipeline.py TICKER --offline                      # lewati kedua langkah raw
python run_pipeline.py TICKER --from-step classification     # lanjut setelah gagal
python run_pipeline.py TICKER --only valuation               # satu langkah saja
```

Bila satu langkah gagal, orchestrator berhenti dan mencetak perintah `--from-step` untuk melanjutkan dari titik itu.

### 1.5.1 Dua sumber data: lokal vs API

Perbedaan terpenting yang perlu diketahui: `ingest_raw_history.py` **tidak** mengunggah file dari disk lokal. Ia hanya merekonsiliasi Storage dengan database:

| Keadaan | Yang dilakukan `ingest_raw_history.py` | Panggilan API? |
|---|---|---|
| File ada di Storage, provenance ada | `SKIP_ALREADY_INGESTED` | Tidak |
| File ada di Storage, provenance belum ada | `REPAIRED_FROM_EXISTING_STORAGE` (baca byte dari Storage) | Tidak |
| File **tidak** ada di Storage (baik file lokal ada maupun tidak) | ambil dari API, simpan raw, unggah, lalu catat provenance | **Ya** |

Baris ketiga adalah yang mudah disalahpahami: kalau raw belum ada di Storage, script **tidak** memakai file lokal — ia memanggil API. Karena itu `run_pipeline.py` menjalankan `upload_raw_storage_only.py` lebih dulu, yang mengunggah byte lokal apa adanya ke Storage tanpa menyentuh API. Dengan begitu `ingest_raw_history.py` menemukan byte di Storage dan hanya meregistrasi provenance (tanpa API).

**Perilaku otomatis berdasarkan ketersediaan raw lokal:**

| Raw lokal | Yang dilakukan `run_pipeline.py` |
|---|---|
| Ada | Jalankan `upload-raw`, lalu `ingest-raw`. Hasil: `API_CALLS=0`, tidak perlu `SECTORS_API_KEY`. |
| Tidak ada | Lewati `upload-raw` secara otomatis (tidak ada yang bisa diunggah), lalu `ingest-raw` mengambil dari API. Perlu `SECTORS_API_KEY`. |

Orchestrator mencetak jalur mana yang dipakai sebelum menjalankan langkah apa pun, jadi tidak ada tebakan.

**Yang diambil saat ticker benar-benar baru** (`ingest-raw` tanpa raw lokal maupun Storage): info, annual, dividend, 26 statement quarter, dan 28 window harga harian. Dua hal ini dulu membuat ticker baru gagal dan sekarang sudah diperbaiki:

| Masalah lama | Perbaikan |
|---|---|
| `quarterly` direncanakan sebelum `quarterly-dates` di-fetch, sehingga 0 target quarter | Keluarga direncanakan dan direkonsiliasi **satu per satu sesuai urutan**, bukan semua di muka. `quarterly` sekarang melihat tanggal yang baru diambil. |
| `daily` punya 0 window karena tidak ada raw lokal maupun Storage | Fallback ke rentang default collector (`2020-01-01` sampai hari ini, window 90 hari) saat belum ada window sama sekali. |
| `manifest` di-fetch dari API padahal `endpoint=None` → 404 dan `FAILED=1` | `manifest` bertanda `local_only`, jadi dilaporkan sebagai skip, bukan kegagalan fetch. |

**Untuk ticker yang raw-nya sudah ada di `Data\Raw\{TICKER}`** — cukup satu perintah, tanpa `SECTORS_API_KEY`:

```powershell
python run_pipeline.py ERAA
```

**Untuk ticker yang belum pernah diunduh** (misalnya AADI):

```powershell
python run_pipeline.py AADI          # ambil dari API
```

Atau unduh dulu ke lokal, lalu jalankan:

```powershell
python .\scripts\data_pipeline\01_download_sectors.py AADI --task all
python run_pipeline.py AADI
```

`--task all` mencakup identity, annual, dividend, date index, quarterly statements, dan harga harian. Untuk update quarter baru pada ticker yang sudah ada, lihat bagian 4.

Bila raw sudah ada di Storage dan Anda ingin melewati kedua langkah raw:

```powershell
python run_pipeline.py ERAA --offline     # sama dengan --skip-raw
```

### 1.5.3 Status 19 ticker (per verifikasi terakhir)

| Ticker | Sektor | Tipe saham | Confidence | Metode valuasi |
|---|---|---|---:|---:|
| AMRT | Consumer Non-Cyclicals | STALWART | 0.95 | 10 |
| ARII | Energy | CYCLICAL | 0.95 | 5 |
| AUTO | Consumer Cyclicals | CYCLICAL | 0.70 | 15 |
| BIRD | Transportation & Logistic | CYCLICAL | 0.95 | 5 |
| DSSA | Energy | CYCLICAL | 0.70 | 5 |
| ERAA | Consumer Cyclicals | CYCLICAL | 0.70 | 5 |
| GEMA | Consumer Cyclicals | TURN AROUND | 0.40 | 5 |
| GOLD | Infrastructures | UNCLASSIFIED → ASSET PLAY saat valuasi | 0.00 | 5 |
| INDF | Consumer Non-Cyclicals | UNCLASSIFIED (tidak ada rule cocok) | 0.00 | 5 |
| INDS | Consumer Cyclicals | CYCLICAL | 0.70 | 5 |
| INKP | Basic Materials | CYCLICAL | 0.70 | 5 |
| IPOL | Basic Materials | CYCLICAL | 0.70 | 5 |
| ITMG | Energy | CYCLICAL | 0.95 | 5 |
| JSMR | Infrastructures | UNCLASSIFIED → ASSET PLAY saat valuasi | 0.00 | 5 |
| MIDI | Consumer Non-Cyclicals | STALWART | 0.95 | 10 |
| PTBA | Energy | CYCLICAL | 0.70 | 5 |
| SIDO | Healthcare | SLOW GROWER | 0.95 | 5 |
| TLKM | Infrastructures | SLOW GROWER | 0.70 | 5 |
| WIFI | Technology | FAST GROWER | 0.95 | 5 |

Catatan: jumlah metode bervariasi (5, 10, atau 15) karena hasil valuasi menumpuk per run; 5 adalah jumlah metode unik terkini. AMRT/AUTO/MIDI punya lebih banyak baris karena dimuat beberapa kali sebelum classifier ada.

`GOLD` dan `JSMR` sengaja disimpan sebagai `UNCLASSIFIED` (hasil workbook apa adanya) dan baru dipetakan ke `ASSET PLAY` pada saat valuasi. `INDF` tidak punya rule yang cocok, jadi valuasinya perlu `--stock-type` eksplisit.

### 1.5.4 Jalankan manual (tanpa orchestrator)

Setiap langkah tetap bisa dijalankan sendiri. Yang perlu diperhatikan:

**Set credential dulu** — loader (`load_*.py`) dan `ingest_raw_history.py` membaca `os.environ` langsung dan **tidak** memuat `.env` otomatis, berbeda dengan script kalkulasi (`calculate_*.py`, `populate_*.py`) yang memuat `.env` sendiri. Dari PowerShell:

```powershell
Set-Location 'D:\Stock Analyzer'
Get-Content '.env' | ForEach-Object {
  if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
    $v = $matches[2].Trim()
    if ($v.Length -ge 2 -and ($v[0] -eq '"' -or $v[0] -eq "'")) { $v = $v.Substring(1,$v.Length-2) }
    [Environment]::SetEnvironmentVariable($matches[1], $v, 'Process')
  }
}
```

**Urutan manual untuk ticker dari data lokal:**

```powershell
# 1. Upload byte lokal ke Storage (tanpa API). Preview dulu tanpa --yes.
python .\supabase\upload_raw_storage_only.py BIRD --dry-run
python .\supabase\upload_raw_storage_only.py BIRD --yes

# 2. Daftarkan provenance. Semua target jadi SKIP_ALREADY_INGESTED.
python .\supabase\ingest_raw_history.py --symbol BIRD --apply

# 3. Ambil ingestion_run_id family "info" (bukan copy-paste: query DB)
python -c "import sys;sys.path.insert(0,'supabase');from calculation_v1_common import SupabaseRest;import os;from derive_classifier_inputs import load_env_file;load_env_file(__import__('pathlib').Path('.env'));db=SupabaseRest(os.getenv('SUPABASE_URL'),os.getenv('SUPABASE_SERVICE_ROLE_KEY'));r=db.get_all('ingestion_runs',{'symbol':'eq.BIRD','status':'eq.SUCCESS','select':'id','order':'started_at.desc'});f=db.get_all('ingestion_files',{'ingestion_run_id':'eq.'+r[0]['id'],'source_file_type':'eq.info','select':'id'});print(r[0]['id'] if f else 'check other runs')"

# 4. Load canonical
python .\supabase\load_identity_to_supabase.py BIRD --ingestion-run-id <RUN_ID>
python .\supabase\load_annual_financials_to_supabase.py BIRD
python .\supabase\load_quarterly_financials_to_supabase.py BIRD --dry-run
python .\supabase\load_quarterly_financials_to_supabase.py BIRD
python .\supabase\load_dividend_to_supabase.py BIRD
python .\supabase\load_daily_prices_to_supabase.py BIRD

# 5. Kalkulasi (script ini memuat .env sendiri)
python .\supabase\populate_growth_quality.py --ticker BIRD --apply
python .\supabase\derive_projection_scenario.py BIRD --apply
python .\supabase\populate_metrics_classification.py --ticker BIRD --apply
python .\supabase\calculate_valuation.py --ticker BIRD --risk-free-from-reference --apply
```

Catatan penting:

- `--source local` pada loader **bukan** pengganti Storage. Loader tetap memverifikasi checksum dan provenance dari Storage, jadi `PROVENANCE_NOT_FOUND` akan muncul bila langkah 1–2 belum dijalankan. Opsi itu hanya mengubah sumber pembacaan payload, bukan menghilangkan kebutuhan provenance.
- `load_quarterly_financials_to_supabase.py` punya `--dry-run`; `load_annual_financials_to_supabase.py` **tidak** punya dan langsung menulis.
- Loader berhenti pada konflik nilai, tidak menimpa fakta existing.

### 1.6 Klasifikasi tipe saham (stock type)

Tipe saham dihitung dari data canonical oleh `classify_metrics_classification()` (aturan `MetricsClassification!B80`, lengkap dengan score ladder dan override Energy). Inputnya diturunkan oleh `supabase/derive_classifier_inputs.py`, lalu disimpan oleh `supabase/populate_metrics_classification.py` ke tabel `calc_metrics_classification`.

```powershell
python .\supabase\derive_classifier_inputs.py --ticker TICKER
python .\supabase\populate_metrics_classification.py --ticker TICKER
python .\supabase\populate_metrics_classification.py --ticker TICKER --apply
```

Perintah terakhir menyimpan 9 baris: enam flag aturan, `SYSTEM_RECOMMENDATION`, `FINAL_TYPE`, dan `CONFIDENCE`.

Dua catatan penting yang sudah terverifikasi terhadap workbook AUTO Q2 2026:

1. `Metric_PE_Fwd` dan `Metric_PBV_Fwd` adalah **multiple** (harga ÷ nilai per saham forward). Kolom `PE_PROJECTED`/`PBV_PROJECTED` di `calc_valuation_inputs` bernilai **harga**, jadi keduanya tidak bisa dipakai bergantian.
2. `CLASSIFICATION_CONFIDENCE` disimpan dengan flag `REGISTRY_VERSION_UPDATE_REQUIRED` karena entri registry `classifier_confidence_level` masih `UNRESOLVED_DEFINITION` (blueprint Q17), walaupun rumusnya sudah diimplementasikan dan cocok dengan workbook.

Override manual (setara `B81`) didukung lewat `--manual-override "STALWART"`. Hasil aturan tetap disimpan, sehingga hasil aturan dan override bisa dibedakan.

### 1.7 Perbedaan yang diketahui terhadap workbook

Perbedaan berikut **diharapkan** dan terdokumentasi, bukan bug:

| Metrik | Workbook | Canonical | Penyebab |
|---|---|---|---|
| `CLASSIFICATION_CYCLICAL` (SIDO) | `True` | `False` | Artefak `G-2019-COGS`: COGS 2019 kosong di Excel sehingga Gross Margin 2019 = 100% dan `GPM Range` membengkak ke 44.87 ppt (> 0.2). Canonical punya `GROSS_PROFIT` 2019 sehingga range hanya 3.9%. |
| `Payout Ratio Avg` (SIDO) | 0.871867 | 0.876597 | `G-2019-DPS`: Excel punya baris 2019 dengan DPS 0; `dividend_facts` mulai dari 2020. |
| `CLASSIFICATION_ASSET_PLAY` (BIRD) | `True` | `False` | Tanggal harga. Workbook memakai harga `1485` → PBV `0.5965`, di bawah minimum historis `0.626` → percentile `0`. Canonical memakai close terbaru `1625` (2026-09-09) → PBV `0.6527`, berada di dalam rentang `0.626`–`0.7953` → percentile `0.25` (ambang `0.2`). |
| `eps_long` (BIRD) | 0.124447 | `UNAVAILABLE` | `OUTSTANDING_SHARES` tahun 2025 bertanda `MISSING` pada data sumber API, sehingga `GROWTH_EPS_CAGR_LONG` tidak bisa dihitung. Klasifikasi tetap benar karena CYCLICAL tidak memakai input ini. |

`FINAL TYPE` dan `CONFIDENCE` tetap identik dengan workbook pada kedua ticker:

- SIDO: SLOW GROWER / 0.95 — `system_cyclical` hanya memakai `RevCoV > 0.35` (0.0956), tidak memakai cabang GPM.
- BIRD: CYCLICAL / 0.95 — score ladder memilih CYCLICAL (60) di atas ASSET PLAY (10).

Perbedaan nilai akibat tanggal harga adalah hal yang wajar: workbook adalah snapshot pada tanggal penyusunannya, sedangkan pipeline selalu memakai close terbaru. Untuk mereproduksi angka workbook persis, pakai `--valuation-date` dan bandingkan pada tanggal yang sama.

### 1.8 Kuirk data sumber dan cara penanganannya

Beberapa ticker punya data sumber yang tidak lengkap. Ini ditangani secara eksplisit, bukan dianggap error:

| Kuirk | Ticker terdampak | Penanganan |
|---|---|---|
| `historical_dividends` bernilai `null` | ARII, DSSA, GOLD | `load_dividend_to_supabase.py` menormalkannya menjadi kosong dan memuat **nol** baris dividen. Perusahaan tanpa dividen adalah keadaan sah, bukan input rusak. Sebelumnya ini menghentikan seluruh pipeline. |
| `OUTSTANDING_SHARES` tahun terakhir `null` | BIRD (2025) | EPS/BVPS memakai jumlah saham dari tahun terakhir yang melaporkannya. Backend (`annual_share_count`) dan frontend (`buildValuationMetrics`) sama-sama mundur ke tahun sebelumnya. Di UI, catatan kartu menampilkan `(shares from 2024; latest year not reported)` supaya aproksimasi ini terlihat. |
| Annual source punya tahun ekstra (2018) | GOLD, WIFI | Loader annual menerima **superset** selama rentang wajib 2019–2025 tercakup; tahun ekstra ikut dimuat sebagai histori tambahan. Sebelumnya jumlah baris dikunci tepat 7 sehingga kedua ticker ini ditolak. |
| Field deskriptif berisi objek, bukan angka | ITMG 2025 (`industry_breakdown` = cadangan batu bara) | Validasi hanya memeriksa field yang benar-benar dipetakan ke metrik canonical (`ANNUAL_FIELDS` + `outstanding_shares`). Field deskriptif yang tidak punya padanan metrik tidak lagi menolak seluruh file. |
| `interest_expense_non_operating` `null` di semua quarter | GOLD (26/26) | Metrik yang tidak pernah disediakan provider dianggap **tidak tersedia secara struktural**: dikeluarkan dari syarat `resolve_base_quarter` dan dihilangkan dari output proyeksi, bukan diisi nol. Mengisi nol akan salah menyatakan run-rate. |
| Hanya `ASSET PLAY` yang cocok (score 10) | GOLD | Score ladder workbook tidak punya cabang untuk score 10, sehingga hasilnya `UNCLASSIFIED`. Karena engine valuasi dan reference table memodelkan kondisi ini sebagai `ASSET PLAY`, tipe tersebut dipetakan ke `ASSET PLAY` saat valuasi. Hasil classifier yang tersimpan tetap `UNCLASSIFIED` apa adanya. |
| Tidak ada rule yang cocok sama sekali | INDF | Semua enam rule `False`, jadi `UNCLASSIFIED` tanpa dasar tipe apa pun. Ini **tidak** dipetakan ke `ASSET PLAY` — valuasi akan memakai metodologi berbasis aset yang tidak pernah dipilih classifier. `calculate_valuation.py` menolak dengan `CLASSIFICATION_UNCLASSIFIED_NO_RULE_MATCHED` dan menyarankan `--stock-type` eksplisit bila valuasi memang diinginkan. |
| COGS 2019 kosong di workbook | AUTO (dan pola serupa di ticker lain) | Canonical memakai `GROSS_PROFIT` sebenarnya, sehingga `GPM Range` tidak membengkak. Efeknya `CLASSIFICATION_CYCLICAL` bisa berbeda dari workbook (lihat 1.7), tapi `FINAL TYPE` tidak terpengaruh. |

`eps_long` yang `UNAVAILABLE` adalah konsekuensi langsung dari kuirk kedua. Klasifikasi tetap dapat dijalankan selama tipe akhirnya tidak memerlukan input tersebut; rule yang tidak bisa dievaluasi menghasilkan `None` dan dilaporkan lewat flag `CLASSIFIER_INPUT_MISSING`.

**Prinsip yang dipakai:** data yang tidak ada tidak pernah diganti dengan nol atau tebakan. Kalau sebuah metrik tidak tersedia untuk seluruh histori, ia dihilangkan dari output dan disebutkan di flag/catatan; kalau sebuah tipe saham tidak bisa dipastikan, hasilnya dibiarkan eksplisit (`UNCLASSIFIED`) dan hanya dipetakan pada titik konsumsi yang memang punya padanan resmi.

## 2. Gambaran urutan kerja


```text
Sectors API
  -> scripts/data_pipeline/01_download_sectors.py
  -> Data/Raw/{TICKER} (respons JSON asli)
  -> supabase/ingest_raw_history.py --apply
  -> bucket Storage stocklens_raw + ingestion_files provenance
  -> supabase/load_*.py
  -> instruments / financial_periods / financial_facts / tabel terkait
  -> supabase/populate_growth_quality.py --apply
  -> calculation_runs + calc_annual_growth_quality + calc_quarterly_*
```

Collector dan uploader **tidak** menulis financial facts. Loader yang membaca Storage menulis actual ke tabel canonical. Perhitungan dijalankan terpisah sesudah data canonical siap. File Python tidak berjalan sendiri.

## 3. Ticker baru

### 3.1 Ambil raw dari API

Jalankan collector. `all` mengerjakan identity, annual, dividend, quarterly date index, quarterly statements, lalu harga harian:

```powershell
python .\scripts\data_pipeline\01_download_sectors.py TICKER_BARU --task all
```

Untuk alur tanpa harga harian (lebih cepat bila tujuan hanya financial metrics), jalankan:

```powershell
python .\scripts\data_pipeline\01_download_sectors.py TICKER_BARU --task info
python .\scripts\data_pipeline\01_download_sectors.py TICKER_BARU --task annual
python .\scripts\data_pipeline\01_download_sectors.py TICKER_BARU --task quarterly-dates
python .\scripts\data_pipeline\01_download_sectors.py TICKER_BARU --task quarterly
python .\scripts\data_pipeline\01_download_sectors.py TICKER_BARU --task dividend
```

`quarterly-dates` wajib dilakukan sebelum `quarterly`. Jangan tambah quarter/tanggal secara manual; loader memvalidasi tanggal yang dikembalikan provider.

### 3.2 Dry-run rencana raw ingestion, lalu simpan raw dan audit

Preview dulu—ini read-only. Pastikan simbol dan jumlah berkas masuk akal:

```powershell
python .\supabase\ingest_raw_history.py --symbol TICKER_BARU
```

Jika cocok, tambahkan `--apply`:

```powershell
python .\supabase\ingest_raw_history.py --symbol TICKER_BARU --apply
```

Tahap ini merekonsiliasi target dengan Storage. Untuk target yang belum tersimpan, script dapat memanggil Sectors API lagi, menulis respons mentah lokal, mengunggahnya ke bucket privat `stocklens_raw`, dan membuat `ingestion_runs`/`ingestion_files`; ini **bukan** data actual kanonis. Simpan output terminal untuk audit. Uploader menolak overwrite; bila file/path sudah ada, jangan hapus/ubah object untuk memaksa jalan.

### 3.3 Load company identity dahulu

Identity loader memerlukan satu `ingestion_run_id` sukses yang punya provenance berkas info. Ambil ID dari bagian output `ingest_raw_history.py` pada family `info`, lalu set variabel PowerShell berikut:

```powershell
$INFO_RUN_ID = 'PASTE_INGESTION_RUN_ID_DARI_OUTPUT_INFO'
python .\supabase\load_identity_to_supabase.py TICKER_BARU --ingestion-run-id $INFO_RUN_ID
```

Pastikan output menyebut `instrument_id=...`. Loaders annual/quarterly berikutnya mensyaratkan baris ticker ini sudah ada di `instruments`.

### 3.4 Load actual financials dari Storage

```powershell
python .\supabase\load_quarterly_financials_to_supabase.py TICKER_BARU --dry-run
python .\supabase\load_annual_financials_to_supabase.py TICKER_BARU
python .\supabase\load_quarterly_financials_to_supabase.py TICKER_BARU
```

Kedua loader default-nya membaca bucket Storage dan mengecek checksum/provenance. Jalankan quarter dulu sebagai dry-run; loader quarterly menyediakan `--dry-run`, sedangkan annual loader **langsung menulis** dan tidak punya mode dry-run. Setelah preview quarter bersih, annual loader menulis periode/facts annual dan loader quarterly (tanpa `--dry-run`) menulis quarter. Loader akan menolak konflik nilai existing daripada diam-diam menimpa actual. Annual source saat ini mengharapkan periode 2019–2025; ticker/source yang tidak sesuai harus ditinjau di mapping sebelum menjalankan.

Opsional, bila ingin memuat dividen:

```powershell
python .\supabase\load_dividend_to_supabase.py TICKER_BARU
```

Opsional, bila sudah menjalankan task `daily` dan memang perlu data harga:

```powershell
python .\supabase\load_daily_prices_to_supabase.py TICKER_BARU
```

### 3.5 Hitung dan simpan Growth & Quality

Preview dahulu; perintah tanpa `--apply` tidak menulis hasil kalkulasi:

```powershell
python .\supabase\populate_growth_quality.py --ticker TICKER_BARU
```

Periksa ticker, banyak periode, dan jumlah output. Bila sesuai, simpan:

```powershell
python .\supabase\populate_growth_quality.py --ticker TICKER_BARU --apply
```

Output sukses harus menyebut `Persisted and verified` dan status run `SUCCEEDED`. Perhitungan memakai semua periode aktual yang tersedia (annual dibatasi 7 tahun secara default), menyimpan run beserta hasil ke tiga tabel `calc_*`. Script ini **tidak** menulis MetricsClassification final; itu dikerjakan langkah terpisah (`populate_metrics_classification.py`, lihat bagian 1.6) yang membaca hasil annual di sini.

## 4. Update ketika ada quarter baru

Contoh: ticker sudah ada dan provider menerbitkan quarter baru. Jalankan perintah berikut satu per satu dari root repository.

### 4.1 Refresh daftar tanggal resmi dan ambil quarter baru

```powershell
python .\scripts\data_pipeline\01_download_sectors.py TICKER --task quarterly-dates --force
python .\scripts\data_pipeline\01_download_sectors.py TICKER --task quarterly
```

Collector menyimpan respons baru di `Data/Raw/TICKER`. `quarterly` memeriksa tanggal resmi dan melewati file lokal yang sudah ada. Pastikan output menunjukkan quarter baru yang diharapkan.

### 4.2 Simpan raw baru ke Storage/provenance

Jalankan preview, periksa ticker dan target quarter baru, lalu apply:

```powershell
python .\supabase\ingest_raw_history.py --symbol TICKER --request quarterly
python .\supabase\ingest_raw_history.py --symbol TICKER --request quarterly --apply
```

`--request quarterly` hanya merekonsiliasi file statements quarter, bukan tanggal index. Index tanggal yang lama di Storage **tidak ditimpa**; kita sengaja memakai date index API terbaru yang lokal pada langkah loader di bawah. Artinya jangan menghilangkan `--date-index-source local` untuk update ini. Setiap statement quarter tetap harus ada di Storage agar provenance/checksum-nya terverifikasi.

### 4.3 Load quarter baru ke actuals

```powershell
python .\supabase\load_quarterly_financials_to_supabase.py TICKER --date-index-source local --dry-run
python .\supabase\load_quarterly_financials_to_supabase.py TICKER --date-index-source local
```

Opsi tersebut menggunakan date index baru `Data/Raw/TICKER/quarterly_financial_dates.json`, tetapi mengambil statement quarterly dari Storage dan memverifikasi checksum/provenance-nya. Loader memeriksa coverage tanggal/file, membandingkan record yang ada, menambah periode/facts yang baru, dan berhenti bila menemukan konflik actual. AUTO kini menerima tambahan quarter resmi, tidak lagi dikunci pada tepat 26 periode.

Pastikan dry run menampilkan `conflict_count=0`, `new_period_count` sesuai jumlah quarter baru, dan quarter terakhir yang benar sebelum menjalankan perintah kedua (yang menulis ke database).

### 4.4 Hitung ulang metrik

```powershell
python .\supabase\populate_growth_quality.py --ticker TICKER
python .\supabase\populate_growth_quality.py --ticker TICKER --apply
```

Perintah pertama preview; periksa sumber/periode/output sebelum menjalankan kedua. Hasil yang disimpan membuat calculation run baru (atau no-op bila input run yang sama sudah berhasil). Metrik ini membaca ulang seluruh histori yang tersedia, bukan hanya quarter baru.

## 5. Update kategori lain

Collector biasanya melewati file lokal yang sudah ada. Untuk mengunduh ulang satu kategori gunakan `--force`, tetapi jangan lanjutkan ke upload jika storage path sudah ada: uploader tidak menimpa object lama.

Daily incremental dari collector memakai tanggal setelah latest lokal, tetapi key object Storage berbasis window berubah setiap dijalankan. Periksa dry-run agar hanya window baru yang direkonsiliasi.

Contoh refresh harga harian:

```powershell
python .\scripts\data_pipeline\01_download_sectors.py TICKER --task daily
python .\supabase\ingest_raw_history.py --symbol TICKER --request daily
python .\supabase\ingest_raw_history.py --symbol TICKER --request daily --apply
python .\supabase\load_daily_prices_to_supabase.py TICKER
```

Harga daily incremental hanya mengambil data setelah tanggal terbaru lokal. Update annual, identity, dividen, atau revisi terhadap tanggal quarter yang telah ada perlu prosedur revisi khusus; loader canonical sengaja berhenti pada konflik dan tidak memperbarui fakta existing.

## 6. Verifikasi hasil di Supabase SQL Editor

Ganti `TICKER` dengan ticker target:

```sql
select i.ticker,
       count(distinct p.id) filter (where p.period_type = 'ANNUAL') as annual_periods,
       count(distinct p.id) filter (where p.period_type = 'QUARTER') as quarterly_periods,
       count(distinct f.id) as financial_facts
from public.instruments i
left join public.financial_periods p on p.instrument_id = i.id
left join public.financial_facts f on f.financial_period_id = p.id
where i.ticker = 'TICKER'
group by i.ticker;
```

Periksa quarter terbaru:

```sql
select p.period_label, p.period_end, count(f.id) as fact_rows
from public.instruments i
join public.financial_periods p on p.instrument_id = i.id
left join public.financial_facts f on f.financial_period_id = p.id
where i.ticker = 'TICKER' and p.period_type = 'QUARTER'
group by p.period_label, p.period_end
order by p.period_end desc
limit 5;
```

Periksa calculation run:

```sql
select cr.id, cr.status, cr.calculation_type, cr.created_at
from public.calculation_runs cr
join public.instruments i on cr.scope_id = i.id::text
where i.ticker = 'TICKER'
order by cr.created_at desc;
```

Untuk run terbaru berstatus `SUCCEEDED`, hitung rows per tabel hasil (query ini sengaja memilih satu run agar tidak menjumlahkan hasil dari beberapa run):

```sql
with latest_run as (
  select cr.id
  from public.calculation_runs cr
  join public.instruments i on cr.scope_id = i.id::text
  where i.ticker = 'TICKER'
    and cr.status = 'SUCCEEDED'
    and cr.calculation_type = 'QUARTERLY_GROWTH_QUALITY'
  order by cr.created_at desc
  limit 1
)
select 'annual_growth' as result, count(*)
from public.calc_annual_growth_quality r
join latest_run lr on lr.id = r.calculation_run_id
union all
select 'quarterly_growth', count(*)
from public.calc_quarterly_growth r
join latest_run lr on lr.id = r.calculation_run_id
union all
select 'quarterly_quality', count(*)
from public.calc_quarterly_quality r
join latest_run lr on lr.id = r.calculation_run_id;
```

Tabel hasil menyimpan banyak metrik per periode. Jumlah rows yang diharapkan ditampilkan oleh script kalkulasi; jangan mengharapkan jumlah row sama dengan jumlah periode.

## 7. Proyeksi (jalur terpisah, opsional)

Proyeksi bukan quarter actual dan tidak dijalankan oleh kalkulasi Growth & Quality. Skrip menulis hasilnya ke `projection_scenarios` + `projection_values` di Supabase, bukan ke `financial_facts`.

Ada dua jalur, dan keduanya **tidak** memerlukan file JSON saat menyimpan:

| Jalur | Kapan dipakai | Sumber skenario |
|---|---|---|
| Turunan otomatis | Ticker yang actual-nya sudah dimuat (semua 19 ticker saat ini) | Dihitung dari tabel canonical |
| File skenario manual | Skenario yang diisi tangan dari workbook, atau file yang ingin dipakai ulang | File JSON di disk |

### 7.1 Menurunkan skenario otomatis dari actual kanonis

```powershell
python .\supabase\derive_projection_scenario.py TICKER_BARU          # preview
python .\supabase\derive_projection_scenario.py TICKER_BARU --apply  # simpan
```

Alurnya `Supabase → Python → Supabase`. Tanpa `--apply` skenario ditulis ke file JSON agar bisa diperiksa; dengan `--apply` file itu **tidak** dibuat karena datanya sudah tersimpan di database.

Aturan turunan (sudah diverifikasi cocok dengan skenario workbook AUTO yang tersimpan):

| Bagian | Rumus |
|---|---|
| Item arus (revenue, COGS, interest, earnings, OCF) | `sum(Q1..Q_asof) × 4 / jumlah_quarter` |
| Item neraca (aset lancar, liabilitas lancar/total, ekuitas) | nilai pada `Q_asof` |
| Avg DPR | `TRIMMEAN(seri DPS/EPS annual sepanjang Years_Avail, 0.4)` |
| Potential DPS | `EPS forward × Avg DPR` |

### 7.2 Menyimpan file skenario manual

Untuk skenario yang diisi tangan dari workbook:

```powershell
python .\supabase\store_projection_scenario.py --scenario .\supabase\projection_auto_2026_q2.json
python .\supabase\store_projection_scenario.py --scenario .\supabase\projection_auto_2026_q2.json --apply
```

Siapkan file dengan schema yang sama dan actual historis yang cocok. Script memvalidasi actual terhadap `financial_facts` dan menulis forecast ke `projection_scenarios`/`projection_values`.

Catatan penting:

- Tahun tanpa dividen tetap masuk seri dengan DPR 0 dan tahun merugi masuk negatif; keduanya **tidak** di-skip, karena `TRIMMEAN` yang membuang outlier — bukan penyaringan input. Men-skip akan mengubah DPR dan DPS.
- COGS disimpan negatif mengikuti penyajian workbook (raw kanonis positif).
- Script **menolak** menulis bila ticker sudah punya scenario ACTIVE, karena `calculate_valuation.py` mensyaratkan tepat satu. Untuk versi baru, naikkan `--scenario-version` setelah menonaktifkan yang lama secara sadar.
- Tanpa riwayat dividen, DPR = 0 (sesuai `IFERROR(TRIMMEAN(...), 0)` di workbook), sehingga DDM menjadi tidak berlaku — bukan error.


## 8. Jika gagal: aturan aman

- `INSTRUMENT_NOT_FOUND`: jalankan identity loader lebih dahulu dan pastikan raw info tersedia/provenance-nya benar.
- `PROVENANCE_NOT_FOUND` atau checksum conflict: cocokkan Storage object dan ingestion metadata; **jangan** mengakali dengan `--source local` untuk live write.
- `CONFLICT`: loader tidak mengubah fakta kanonis yang konflik. Hentikan proses dan tinjau revisi sumber; jangan hapus record atau Storage object untuk memaksa import.
- `DATE_INDEX_*` / `QUARTERLY_FILE_COVERAGE_CONFLICT`: pastikan date index resmi terbaru dan setiap tanggalnya punya statement JSON di Storage.
- Jangan jalankan migration lama sebagai bagian dari ingestion.
- Script pengumpulan, ingest, load, dan kalkulasi adalah tahap manual yang terpisah. Tidak ada scheduler end-to-end aktif.

## 9. Valuasi current (preview dahulu)

Migration `0014_valuation_reference_and_results.sql` dan `0015_valuation_methodology_alignment.sql` sudah diterapkan pada Supabase yang terhubung. Tabel acuan berisi 12 sektor, 6 tipe saham, dan 6 threshold DER/CR/ICR; hasil aktual disimpan terpisah dari input projection. Preview AUTO Q2 2026:

```powershell
python .\supabase\calculate_valuation.py --ticker AUTO
```

`--stock-type` sekarang **opsional**: tanpa argumen itu, script membaca `CLASSIFICATION_FINAL_TYPE` yang tersimpan (lihat bagian 1.6) dan mencetak `Stock type resolved from classifier: ...`. Argumen `--stock-type` tetap tersedia sebagai override untuk investigasi, misalnya `--stock-type CYCLICAL`.

Script memilih satu projection scenario ACTIVE; bila ada lebih dari satu, sebut `--scenario-code`. `Years Available` default dari scenario; `Comparison Period` memakai ladder workbook (>=7: 5 tahun, >=5: 3, >=3: 2, selain itu 0), atau dapat diatur lewat `--years-available`/`--years-compare`. Annual window dibatasi pada tahun sampai as-of quarter.

Harga menggunakan close terakhir pada/before `--valuation-date` (default harga daily terakhir). Projection harus ber-as-of tidak lebih baru dari valuation date.

Risk-free rate kini punya tabel acuan sendiri: `public.risk_free_rate_reference` (migration `0020_risk_free_rate_reference.sql`, sudah diterapkan). Tabel ini **versioned dan bertanggal**, berisi:

| Kolom | Arti |
|---|---|
| `reference_version` / `rate_code` | Versi acuan dan kode rate; saat ini `1.0.0` / `SBN_10Y_YIELD` |
| `observation_date` | Tanggal observasi yield; `NULL` hanya untuk baris konstanta workbook |
| `rate` | Nilai desimal, mis. `0.0633` |
| `source_kind` | `WORKBOOK_CONSTANT` (literal workbook) atau `MARKET_OBSERVATION` (observasi bertanggal) |
| `source_name` / `source_reference` | Sumber dan rujukan tepatnya, wajib diisi |
| `is_default` | Satu baris default per versi; dipakai bila belum ada observasi bertanggal |

Baris yang di-seed sekarang adalah konstanta workbook `DataInput!B11` = **6,33% (Yield SBN 10Y)**, dengan catatan eksplisit bahwa workbook **tidak** mencatat tanggal observasi maupun nama sumber pasar. Jadi DDM dan Discounted Earnings bisa dihitung, tetapi provenance-nya jujur tertulis sebagai konstanta workbook — bukan observasi pasar.

Untuk memakai rate dari tabel (tanpa mengetik ulang angkanya):

```powershell
python .\supabase\calculate_valuation.py --ticker AMRT --stock-type STALWART --risk-free-from-reference
python .\supabase\calculate_valuation.py --ticker AMRT --stock-type STALWART --risk-free-from-reference --apply
```

Resolver memilih **observasi `MARKET_OBSERVATION` terbaru** bila ada; kalau tidak ada, baris `is_default` (konstanta workbook) yang dipakai. `--risk-free-from-reference` tidak boleh digabung dengan `--risk-free-rate`/`--risk-free-source`.

Menambah observasi pasar yang sebenarnya (supaya menggantikan konstanta workbook) — jalankan di SQL Editor:

```sql
insert into public.risk_free_rate_reference
  (reference_version, rate_code, observation_date, rate, currency_code, tenor_years,
   source_kind, source_name, source_reference, is_default)
values
  ('1.0.0', 'SBN_10Y_YIELD', '2026-09-25', 0.0588, 'IDR', 10,
   'MARKET_OBSERVATION', '<nama sumber resmi>', '<URL/tanggal rujukan>', false);
```

Setelah baris bertanggal masuk, resolver otomatis memakainya. Jangan mengubah nilai `0.0633` pada baris workbook; nilai itu harus tetap sama persis dengan `DataInput!B11`. Tabel hanya dapat dibaca `service_role` (bukan `anon`/`authenticated`), dan migration memverifikasi RLS, default tunggal, serta nilai workbook sebelum commit.

Migration `0021_stock_research_latest_valuation_run.sql` juga sudah diterapkan: RPC `get_stock_research_data` sekarang mengambil **snapshot terbaru per `method_code`** pada `valuation_date` terakhir. Ini penting karena menjalankan ulang valuasi dengan asumsi baru (mis. menambahkan risk-free rate) membuat calculation run baru di tanggal yang sama; tanpa dedup, frontend akan menerima setiap metode dua kali.

Mean Reversion PBV diberi status `APPROXIMATED`: quarterly shares belum tersedia, sehingga angka annual terakhir yang tersedia dipakai dan flag dicatat. Financial `available_date` juga masih kosong, sehingga output belum point-in-time/backtest-safe. Setelah memeriksa preview, penyimpanan dilakukan eksplisit dengan menambah `--apply`; hasil masuk ke `calc_valuation_inputs`/`calc_valuation_methods`, bukan ke actual financial facts.

## 10. Frontend: status data per grafik

Halaman `/market/[ticker]` membaca data lewat RPC `get_stock_research_data` (hanya `anon`/`authenticated` boleh EXECUTE; tabel mentah tetap privat). Adapter `frontend/src/lib/stock-detail-adapter.ts` mengubah payload itu menjadi bentuk UI.

Prinsip yang dipakai sekarang:

- **Grafik selalu dirender.** Kalau seri datanya kosong, kerangka grafik tetap muncul dengan label `No data yet` (`frontend/src/components/ui/chart-empty-state.tsx`), bukan menghilang. Jadi bagian yang belum ada datanya terlihat jelas dan bisa diisi bertahap.
- **Tidak ada angka palsu.** Tahun yang datanya belum ada menghasilkan `null` di seri, dan `null` digambar sebagai **gap**, bukan `0`. Ini penting untuk EPS, growth rate, dan dividen: tahun tanpa dividen tidak boleh tampil sebagai payout 0.
- **Data yang sudah nyata** (per ticker, dari `financial_facts`): Revenue, Net Income, Operating Cash Flow, EPS (earnings / outstanding shares), Revenue & EPS YoY, tabel tahunan/kuartalan, kartu metrik tahunan/kuartalan, kartu forensic growth, dan kartu EPS/BVPS/P-E/P-BV.

Daftar grafik yang **masih kosong** dan perlu diisi satu per satu:

| Grafik | Sumber data yang dibutuhkan |
|---|---|
| Price Chart (Overview) | `prices_daily.close_price` untuk ticker tersebut (sudah ada untuk AMRT/AUTO/MIDI; ticker lain belum di-ingest) |
| Dividend Trend (Growth) | `dividend_facts` untuk DPS, dan `DIVIDEND_YIELD` dari `calc_annual_growth_quality` untuk sumbu yield. `dividend_facts.yield_ratio` sendiri **masih NULL** dan tidak dipakai (basis TTM/harga berbeda dari template) |
| Backtest & Historical Evidence | Belum ada tabel backtest; untuk ticker selain AUTO memang kosong, untuk AUTO masih data contoh (`DemoDataBadge`) |
| DDM & Discounted Earnings (Valuation) | Sudah terisi setelah `--risk-free-from-reference` dijalankan; ticker yang belum di-run ulang masih `UNAVAILABLE` |

Cara memverifikasi cepat setelah mengisi data:

```powershell
python .\supabase\calculate_valuation.py --ticker <TICKER> --stock-type <TYPE> --risk-free-from-reference
```

lalu cek jumlah metode yang dikembalikan RPC (harus 5, tanpa duplikasi):

```sql
select jsonb_array_length(public.get_stock_research_data('AMRT') -> 'valuation_methods');
```

### 10.1 Ukuran halaman Market Overview (8 / 12 / 16 / 20)

Halaman `/market` menampilkan kartu saham per halaman. Jumlahnya bisa dipilih dari dropdown di toolbar: **8 (default), 12, 16, 20**.

- Angkanya berasal dari parameter `p_page_size` di RPC `get_market_overview_page(p_page, p_page_size)` (migration `0027_market_overview_page_size.sql`). Sebelumnya nilai ini **hardcode 5** di dua tempat (`limit 5` dan `offset ... * 5`), jadi halaman market tidak pernah bisa menampilkan lebih dari 5 kartu.
- Pilihan dikirim lewat query string `?page=<n>&size=<n>`, jadi ukuran halaman ikut ter-bookmark dan bertahan saat pindah halaman.
- Nilai di luar daftar (mis. `?size=99`) **jatuh ke 8**, bukan error, supaya klien lama tetap tampil.
- Daftar ukuran ada di satu tempat: `frontend/src/lib/market-page-size.ts` (`MARKET_PAGE_SIZE_OPTIONS`). File itu terpisah dari `lib/stock-data.ts` karena halaman market adalah Client Component, sedangkan `stock-data.ts` bertanda `server-only`. Daftar ini **harus sama** dengan whitelist `array[8, 12, 16, 20]` di dalam RPC.
- Ganti ukuran halaman akan **reset ke halaman 1**, karena halaman terakhir pada ukuran lama bisa tidak ada di ukuran baru.
- Batas atas tetap dijaga: maksimum 20 baris per panggilan, jadi RPC tetap mengembalikan potongan terbatas, bukan seluruh tabel.

Verifikasi cepat:

```sql
select
  jsonb_array_length(public.get_market_overview_page(1, 8)  -> 'stocks') as size_8,
  jsonb_array_length(public.get_market_overview_page(1, 12) -> 'stocks') as size_12,
  jsonb_array_length(public.get_market_overview_page(1, 20) -> 'stocks') as size_20,
  jsonb_array_length(public.get_market_overview_page(1, 7)  -> 'stocks') as size_7_falls_back_to_8;
```

Catatan: migration `0027` **menghapus** signature lama `get_market_overview_page(integer)` sebelum membuat `(integer, integer)`. Kalau signature lama dibiarkan, PostgREST tidak bisa memilih kandidat saat pemanggil hanya mengirim `p_page`, dan gagal dengan `Could not choose the best candidate function`.

### 10.2 Hasil audit: tabel vs yang tampil di UI

Audit membandingkan isi tabel Postgres dengan yang benar-benar dirender. Dua jenis masalah ditemukan dan sudah diperbaiki.

**(a) Ada di tabel, tapi tidak pernah sampai ke UI (sudah diperbaiki)**

| Metrik | Baris valid di tabel | Masalah | Perbaikan |
|---|---|---|---|
| `INTEREST_EXPENSE_NON_OPERATING` (QUARTER) | 49 | Tidak ada di whitelist RPC, jadi baris "Interest Expense" selalu `Belum Tersedia` walau datanya ada | Migration `0022` menambahkannya ke whitelist; adapter kini mengisi baris itu |
| `CURRENT_ASSETS` (ANNUAL) | 18 | Tidak ada di whitelist RPC, jadi current assets tahunan tidak bisa dibaca | Migration `0022` menambahkannya (kode kuartal tetap `TOTAL_CURRENT_ASSET`) |

**(b) Skala satuan salah baca (sudah diperbaiki)**

Kolom berlabel `M Rp` di workbook sebenarnya berisi **miliar** IDR, bukan juta (lihat `docs/reference/EXCEL_POSTGRES_VALIDATION.md` §"Unit reality check": `1 template unit = 1,000,000,000 IDR`). Konversi awal memakai `÷1e6` sehingga nilainya 1000× terlalu besar. Sekarang `÷1e9` dan label UI diganti menjadi `Interest Expense (Rp Bn)` agar tidak menyesatkan.

Verifikasi terhadap angka workbook: AUTO 2026-Q2 = `9.224.000.000` IDR → tampil **9,22**; 2026-Q1 → **9,06**. Ini persis cocok dengan tabel validasi Excel (`Interest Exp | 2026-Q2 | 9.224`).

**(c) Masih kosong di DB (bukan bug UI, memang datanya belum ada)**

| Metrik | Status di tabel | Dampak |
|---|---|---|
| `dividend_facts.yield_ratio` | **NULL di seluruh baris** | Tidak dipakai; sumbu Yield pada chart Dividend Trend kini membaca `DIVIDEND_YIELD` yang dihitung (lihat bagian 1.5) |
| `dividend_facts.event_date` | **NULL di seluruh 21 baris** | Tidak ada tanggal pembayaran dividen |
| `financial_periods.report_date` / `available_date` | **NULL di seluruh 99 periode** | Output belum point-in-time; backtest belum aman secara as-of |
| `COST_OF_REVENUE` (ANNUAL) | 3 baris `MISSING` (2019 di ketiga ticker) | Baris 2019 kosong; tahun lain lengkap |
| `CURRENT_ASSETS` (ANNUAL) | 3 baris `MISSING` (2019) | Sama seperti di atas |
| `INTEREST_EXPENSE_NON_OPERATING` (QUARTER) | 29 baris `MISSING` (AUTO 12, MIDI 12, AMRT 5 — mayoritas 2020–2022) | Kuartal lama tampil `Belum Tersedia` |
| `COST_OF_REVENUE` (QUARTER) | 1 baris `MISSING` (AUTO 2023-Q4) | Satu kuartal kosong |

Catatan: baris `MISSING` **sengaja disimpan** sebagai baris dengan `value_numeric` NULL, bukan dihapus. Jadi gap-nya terlihat dan bisa diisi nanti; UI menampilkannya sebagai `Belum Tersedia`, bukan `0`.

### 10.3 Kartu "Workbook Sample vs Tabel" — **dihapus dari UI**

Kartu **Workbook Sample vs Tabel** dulu ada di tab Overview untuk memverifikasi bahwa isi tabel sudah setara dengan sampel workbook. Kartu itu sudah **tidak dirender lagi** (dihapus dari `frontend/src/components/stock-research/overview-tab-content.tsx`), karena fungsinya hanya audit sementara saat migrasi data dan tidak berguna bagi pembaca laporan.

Yang masih ada di repo, tetapi tidak dipakai oleh halaman mana pun:

| Berkas | Isi |
|---|---|
| `frontend/src/data/workbook-sample-auto.ts` | Transkrip angka sampel workbook AUTO |
| `frontend/src/lib/sample-comparison.ts` | Logika pembanding sampel vs database |
| `frontend/src/components/stock-research/sample-comparison-card.tsx` | Komponen kartunya |

Kalau audit itu perlu dijalankan lagi, panggil `buildSampleComparison(data)` dari `frontend/src/lib/sample-comparison.ts` dan render lewat `SampleComparisonCard`. Status yang dulu dipakai:

| Status | Arti |
|---|---|
| **COCOK** | Selisih ada di dalam toleransi metrik tersebut |
| **BEDA** | Ada selisih di luar toleransi — perlu ditinjau |
| **TABEL KOSONG** | Database belum punya nilainya |
| **ADA, TIDAK DIEKSPOS** | Nilainya ada di tabel, tetapi hanya bisa dibaca `service_role` (mis. `risk_free_rate_reference`) |

Sumber angka sampel (bukan dikarang): `docs/reference/Template_Sample_data.md` dan `docs/reference/EXCEL_POSTGRES_VALIDATION.md` §9.

Hasil verifikasi terakhir saat kartu masih tampil di halaman AUTO: **41 COCOK, 1 BEDA, 0 TABEL KOSONG, 1 ADA TETAPI TIDAK DIEKSPOS**.

- **BEDA — Dividend Discount Model**: sampel workbook Rp1.418 vs tabel Rp1.423,29 (selisih 0,37%). Penyebabnya detail pembulatan/metodologi di workbook, bukan kesalahan data: formula workbook yang tertulis (`DPS / (WACC − g)`) tidak mereproduksi angka cache-nya sendiri, sedangkan engine kita memakai `DPS × (1+g) / (WACC − g)` dengan `g` dibatasi 4% dan WACC = risk-free 6,33% + 6%. Perbedaan sekecil ini sengaja **ditampilkan apa adanya** alih-alih disembunyikan.
- **ADA, TIDAK DIEKSPOS — Risk Free Rate (SBN 10Y)**: nilainya **ada** di `risk_free_rate_reference`, tetapi tabel itu hanya bisa dibaca `service_role` sehingga browser tidak dapat membandingkannya. Statusnya sengaja dibedakan dari "tabel kosong" supaya tidak salah lapor: datanya ada, hanya belum diekspos ke UI.

Audit yang sama juga jadi tempat mengecek unit: kolom yang di workbook dilabeli `M Rp` sebenarnya **miliar** IDR. Perbandingannya dilakukan dalam satuan yang sama, sehingga salah skala akan langsung terlihat sebagai `BEDA` (seperti yang sempat terjadi pada Interest Expense sebelum diperbaiki).


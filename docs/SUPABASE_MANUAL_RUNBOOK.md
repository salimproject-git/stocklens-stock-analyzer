# Panduan manual: ticker baru dan update data

Panduan ini untuk menjalankan alur data StockLens secara **manual** dari Windows PowerShell. Contoh perintah dijalankan dari root repository `D:\Stock Analyzer`. Ganti `AUTO` dengan ticker yang sedang dikerjakan.

## Jawaban singkat: metrik dan proyeksi sudah jalan?

- **Metrik Growth & Quality:** kalkulasi dan penyimpanan ke Supabase sudah berjalan untuk AUTO dan MIDI (`SUCCEEDED`). Data historis masing-masing saat ini berisi 7 periode annual dan 26 periode quarterly.
- **Proyeksi:** yang sudah tersimpan adalah satu skenario **AUTO Q2 2026**, 10 nilai proyeksi. Proyeksi merupakan input workbook terpisah dari actual financial facts, bukan hasil kalkulasi otomatis untuk semua ticker.
- **Belum berarti semua analisis lengkap atau otomatis:** `MetricsClassification` akhir belum ditulis; workflow tidak berjalan otomatis/scheduled. `report_date` dan `available_date` periode finansial juga masih kosong, sehingga hasil tidak boleh dianggap point-in-time/backtest-safe.
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

Output sukses harus menyebut `Persisted and verified` dan status run `SUCCEEDED`. Perhitungan memakai semua periode aktual yang tersedia (annual dibatasi 7 tahun secara default), menyimpan run beserta hasil ke tiga tabel `calc_*`. Ini **tidak** menghitung/menyimpan MetricsClassification final.

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

## 7. Proyeksi workbook (jalur terpisah, opsional)

Proyeksi bukan quarter actual dan tidak dijalankan oleh kalkulasi Growth & Quality. File skenario JSON yang sudah divalidasi bisa di-preview lalu disimpan terpisah:

```powershell
python .\supabase\store_projection_scenario.py --scenario .\supabase\projection_auto_2026_q2.json
python .\supabase\store_projection_scenario.py --scenario .\supabase\projection_auto_2026_q2.json --apply
```

Untuk ticker/periode lain siapkan file skenario baru dengan schema yang sama dan actual historis yang cocok. Jangan salin forecast ke `financial_facts`; script memvalidasi actual dan menulis forecast ke `projection_scenarios`/`projection_values`.

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
python .\supabase\calculate_valuation.py --ticker AUTO --stock-type CYCLICAL
```

`stock-type` wajib dipilih eksplisit karena hasil classifier belum menjadi input persisted yang siap dipakai. Script memilih satu projection scenario ACTIVE; bila ada lebih dari satu, sebut `--scenario-code`. `Years Available` default dari scenario; `Comparison Period` memakai ladder workbook (>=7: 5 tahun, >=5: 3, >=3: 2, selain itu 0), atau dapat diatur lewat `--years-available`/`--years-compare`. Annual window dibatasi pada tahun sampai as-of quarter.

Harga menggunakan close terakhir pada/before `--valuation-date` (default harga daily terakhir). Projection harus ber-as-of tidak lebih baru dari valuation date. Risk-free rate belum bersumber; karena itu DDM dan Discounted Earnings akan `UNAVAILABLE` kecuali rate serta referensinya diberikan eksplisit, contoh `--risk-free-rate 0.0633 --risk-free-source "10Y SBN, source and observation date"`. Jangan gunakan angka contoh tanpa verifikasi sumber aktual.

Mean Reversion PBV diberi status `APPROXIMATED`: quarterly shares belum tersedia, sehingga angka annual terakhir yang tersedia dipakai dan flag dicatat. Financial `available_date` juga masih kosong, sehingga output belum point-in-time/backtest-safe. Setelah memeriksa preview, penyimpanan dilakukan eksplisit dengan menambah `--apply`; hasil masuk ke `calc_valuation_inputs`/`calc_valuation_methods`, bukan ke actual financial facts.
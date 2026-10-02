# Prompt untuk chat baru: backend sebagai satu-satunya sumber data

Salin seluruh isi di bawah ini ke chat baru.

---

## Konteks

Repo: `D:\Stock Analyzer` (StockLens — analisis saham IDX dengan Supabase +
Next.js + Python).

Aku sudah menyelesaikan **desain** untuk memindahkan seluruh perhitungan bisnis
dari frontend ke database, dan menyimpannya di
**`docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md`**.

**Baca dokumen itu lebih dulu, seluruhnya.** Semua keputusan, daftar fungsi,
rumus, dan bukti numerik ada di sana. Prompt ini hanya ringkasan agar kamu tahu
apa yang harus dikerjakan dan apa yang tidak boleh dilakukan.

## Latar belakang singkat

Saat ini angka yang tampil di UI berasal dari **dua tempat**: tabel hasil
kalkulasi Supabase, dan perhitungan ulang di browser
(`frontend/src/lib/stock-detail-adapter.ts` + `frontend/src/lib/analysis/*.ts`).

Masalahnya: ada workflow **n8n** yang akan mengambil data dari Supabase, melakukan
AI summary, lalu menggabungkannya dengan berita terbaru, dan menampilkan hasilnya
di popup. Kalau angkanya hidup di dua tempat, n8n tidak bisa melihat separuhnya,
dan dua implementasi rumus bisa berbeda hasil.

**Sasaran:** setiap angka **bisnis** punya satu rumah di database. Frontend dan
n8n sama-sama membacanya, lalu masing-masing memformat sesuai kebutuhannya.

## Aturan paling penting — jangan dilanggar

**Angka di backend, tampilan di UI.** Jangan pernah menyimpan string terformat
sebagai nilai. Alasannya ada di §2 dokumen, tapi ringkasnya:

- `"19,91"` sebagai `text` → n8n tidak bisa menghitung apa pun dari string
- `"Rp Trillion"` sebagai nilai → n8n tidak tahu itu triliun atau miliar, risiko
  salah **1.000×**
- `"Not available"` sebagai nilai → perbedaan "nol" vs "tidak ada" hilang, AI
  akan mengarang
- locale `id-ID` (koma) di database → ganti bahasa UI jadi migrasi data

Yang **tetap di frontend**: pembulatan, locale, satuan tampilan, tanda & warna,
placeholder, layout, ikon, geometri chart. Daftar lengkapnya ada di §3.3.

## Tugasmu

Kerjakan **Langkah 1 dan Langkah 2** dari §6 dokumen. **Jangan** kerjakan
Langkah 3 dan 4 dulu.

### Langkah 1 — Metrik annual yang hilang

Tambah 8 metrik ke `calc_annual_growth_quality`:
`EPS`, `BVPS`, `ROE`, `GROSS_MARGIN`, `NET_MARGIN`, `TOTAL_ASSETS`,
`REVENUE_CAGR_WINDOW`, `EARNINGS_CAGR_WINDOW`.

Rumus dan enam aturan wajibnya ada di §6 Langkah 1. Baca aturan itu — beberapa
di antaranya adalah bug yang **sudah pernah terjadi** di repo ini (mis.
`EPS_DERIVED_FROM_EARNINGS` pernah salah dianggap missing-input dan membuat semua
DPR kosong).

### Langkah 2 — MoS tersimpan

Tambah kolom `mos` di `calc_valuation_methods` dengan aturan D6
(`(IV − harga) / IV`, ditolak bila `IV <= 0`). Detail di §6 Langkah 2.

## Keputusan yang harus kamu tanyakan dulu — JANGAN pilih sendiri

Lima pertanyaan di §7 **belum dijawab**. Tanyakan sebelum mulai, karena
jawabannya mengubah pekerjaan:

- **S1** `TOTAL_ASSETS`: diturunkan dari `liabilities + equity`, atau dimuat dari
  raw JSON? (identitasnya sudah terbukti benar di 142/142 baris, tapi memuat dari
  raw butuh re-ingest 20 ticker)
- **S2** `OPERATING_PNL`: dimuat atau tidak?
- **S3** Metrik baru: masuk tabel yang ada, atau tabel `calc_annual_ratios` baru?
- **S4** Satu RPC untuk UI+AI, atau dua?
- **S5** Hasil AI disimpan di tabel `ai_company_summaries` atau tidak?

## Fakta yang sudah diverifikasi — JANGAN dihitung ulang

Semuanya ada di §8, dan ini yang paling sering bikin salah:

1. **Unit.** `1 template unit = 1.000.000.000 IDR` — **bukan 1 juta**.
2. **Duplikasi run.** `calc_annual_growth_quality` punya **40 run untuk 20
   instrumen**. Query mentah `where instrument_id = X` mengembalikan **2×** baris
   (backtest **5×**). RPC aman karena sudah memaku ke run terbaru; tabel mentah
   tidak. **Jangan query tabel mentah tanpa join ke run terbaru.**
3. **`gap_ratio` ≠ MoS.** `gap_ratio` = `(IV − harga) / harga`; MoS (aturan D6) =
   `(IV − harga) / IV`. AUTO DDM: `−0,5739` vs `−1,3467`. Dua angka berbeda.
4. **Fakta kanonik hanya 12 metric code.** `total_assets` dan `operating_pnl`
   **tidak ada** di `financial_facts`, meski ada di raw JSON, karena
   `ANNUAL_FIELDS` sengaja memuat 10 field dan ada test yang mengunci daftar itu.
5. **`OUTSTANDING_SHARES` kosong di tahun terakhir BIRD 2025.** Pakai
   `annual_share_count` di `derive_projection_scenario.py` yang sudah mundur ke
   tahun sebelumnya — jangan tulis logika baru.
6. **Guard yang aktif itu benar, bukan bug.** ARII/GOLD CAGR `Not available`
   (EPS awal negatif), ARII/DSSA/GOLD tanpa dividen, AUTO 2020 DPR `NULL`.

## Cara kerja yang diharapkan

Ikuti pola yang sudah ada di repo — **jangan bikin pola baru**:

- **Rumus baru** masuk ke `supabase/calculate_quarterly_growth_quality.py`,
  memakai helper yang sudah ada (`_emit`, `_divide_optional`, `_indexed_value`,
  `fact_value`). Setiap metrik baru wajib masuk `ANNUAL_GROWTH_METRICS`.
- **Flag** ditambahkan di `supabase/calculation_v1_common.py` mengikuti penamaan
  `FLAG_*` yang ada.
- **Loader** di `supabase/populate_growth_quality.py` — perhatikan bahwa
  `_prepare_outputs` sudah membuat satu snapshot per tahun annual.
- **Migrasi** ditulis di `supabase/migrations/` dengan nomor berikutnya (`0029`),
  mengikuti gaya `0025`/`0026`/`0028` (transaksional, read-only bila hanya RPC,
  ada blok `do $verify$`).
- **Test** ditambahkan ke `tests/` mengikuti pola yang ada (offline, tanpa
  database).
- **Dokumentasi** diperbarui: `SUPABASE_MANUAL_RUNBOOK.md` (versi + cara jalan)
  dan `FRONTEND_SAMPLE_VS_CURRENT_AUDIT.md` (addendum).

## Definition of done

Checklist lengkap ada di §10. Yang paling penting:

1. `python -m unittest discover -s tests -t .` → **semua test lama tetap OK**
   (baseline saat ini: **383**).
2. `py_compile` lulus untuk setiap file Python yang diubah.
3. Dry-run `python supabase/populate_growth_quality.py --ticker GEMA` melaporkan
   `18 → 26` metrik per snapshot.
4. **18 metrik lama bit-identik** sebelum vs sesudah (buktikan dengan query
   pembanding dua run, seperti yang sudah dilakukan untuk DPR/Yield).
5. Verifikasi numerik terhadap ERAA: Revenue `32,94 … 76,61`, EPS `18 … 75`,
   ROE `5,9% … 11,8%`, Gross Margin `8,6% … 10,9%`, BVPS `312 … 638`.
6. Tidak ada duplikat di RPC: `rows == distinct_pairs` untuk 20 ticker.

## Referensi untuk Langkah 3 dan 4 (jangan dikerjakan, tapi jangan dilanggar)

**Langkah 3** (RPC untuk AI) harus memakai pola `latest_run` yang sudah ada di
migrasi `0026` dan `0028`, dan **wajib menyertakan `unit_code`, `status`, dan
`flags`** untuk setiap nilai. Tanpa `unit_code`, AI akan salah 1.000× antara
miliar dan triliun.

**Langkah 4** (rampingkan adapter) harus **tidak mengubah perilaku UI**. Uji
regresi: nilai yang tampil sebelum dan sesudah refactor identik untuk 20 ticker.

Kalau di tengah jalan kamu menemukan aturan yang bertentangan dengan dokumen,
**berhenti dan tanyakan** — jangan pilih sendiri. Aturan-aturan itu sudah
diverifikasi terhadap data nyata.


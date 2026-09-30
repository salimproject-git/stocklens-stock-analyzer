# Prompt untuk chat baru: implementasi Backtest Historis

Salin seluruh isi di bawah ini ke chat baru.

---

## Konteks

Repo: `D:\Stock Analyzer` (StockLens — analisis saham IDX dengan Supabase + Next.js).
Aku sudah menyelesaikan **desain** backtest historis dan menyimpannya di
**`docs/BACKTEST_ARCHITECTURE.md`**.

**Baca dokumen itu lebih dulu, seluruhnya.** Semua aturan, keputusan, dan bukti numerik ada di
sana. Prompt ini hanya ringkasan agar kamu tahu apa yang harus dikerjakan.

## Tugasmu

Implementasikan **Fase 1** saja: daftar kasus + metrik harga. **Jangan** kerjakan fase 2/3/4 dulu.

Fase 1 = untuk setiap ticker, bangun daftar kasus backtest dan hitung metrik harga murni dari
`prices_daily`:

- `case_quarter` (mis. `2022-Q1`), `base_year`, `analysis_date`, `analysis_price`
- `high_3m/low_3m`, `high_6m/low_6m`, `high_9m/low_9m`, `high_12m/low_12m`
- `peak_price`, `trough_price`, `peak_month`, `return_peak`, `return_down`

Belum ada valuasi, belum ada verdict, belum ada UI.

## Fakta yang sudah diverifikasi — JANGAN dihitung ulang

Semua ini sudah dicek ke workbook asli dan ke database. Pakai apa adanya.

**Pemilihan kasus (makro `BuildHistoricalSnapshot`):**

- `Helper!C2#` = semua tahun annual **kecuali dua tahun terkecil**.
- Kasus = semua kuartal pada tahun `base_year + 1` untuk setiap `base_year` valid.
- AUTO (annual 2019–2025) → base year 2021–2025 → kuartal 2022–2026 → **18 kasus**.
- Jumlah kasus per ticker: sebagian besar 18; DSSA 17; GOLD 22; WIFI 22.

**Harga analisis:** close PIT (terakhir dengan `trading_date <= analysis_date`).
Sudah diverifikasi cocok: 2022-03-31→1125, 2023-06-30→2480, 2026-06-30→2350 untuk AUTO.

**Window harga — perhatikan bedanya, ini sumber bug paling mudah:**

| Metrik | Window | Batas awal |
|---|---|---|
| `Ret 3M` | `[T0, EDATE(T0,+3)]` | **inklusif** |
| `Ret 6M` | `(EDATE(T0,+3), EDATE(T0,+6)]` | **eksklusif** |
| `Ret 9M` | `(EDATE(T0,+6), EDATE(T0,+9)]` | **eksklusif** |
| `Ret 12M` | `(EDATE(T0,+9), EDATE(T0,+12)]` | **eksklusif** |
| `Harga Peak` / `trough` | `[T0, EDATE(T0,+12)]` | **inklusif** |

**Aturan High/Low nol (WAJIB, bukan opsional):** `High = 0 ? Close : High`, `Low = 0 ? Close : Low`.
Ada **865 baris** dengan `high_price = 0` dan `low_price = 0` di `prices_daily`: DSSA 539
(33.5%), GEMA 195 (12.1%), ARII 52, INDS 38, GOLD 34, IPOL 4, WIFI 3. AUTO punya **0**, jadi
menguji hanya dengan AUTO **tidak akan menangkap bug ini**.

**`Bln Peak`** = `"M+" & DATEDIF(T0, MIN(trading_date) saat High = peak_price, "m")`.

**Bukti parity AUTO 2022 Q1** (sudah dicocokkan persis, pakai sebagai fixture uji):

| Metrik | Workbook | Hitung dari DB |
|---|---|---|
| `Ret 3M` up/down | 1285 / 1080 | 1285 / 1080 |
| `Ret 6M` up/down | 1375 / 1085 | 1375 / 1085 |
| `Ret 9M` up/down | 1590 / 1155 | 1590 / 1155 |
| `Ret 12M` up/down | 1855 / 1335 | 1855 / 1335 |
| `Harga trough` / `Peak` | 1080 / 1855 | 1080 / 1855 |
| `Bln Peak` | M+11 | 2023-03-03 → M+11 |

`analysis_price` = 1125, `peak_price` = 1855, `trough_price` = 1080.

## Konvensi repo yang WAJIB diikuti

Baca dulu file-file ini supaya gayamu konsisten (jangan menebak polanya):

- `supabase/valuation_engine.py` — mesin rumus murni, **tanpa I/O**. Tiru gaya ini.
- `supabase/calculate_valuation.py` — orkestrator DB → engine → persist.
- `supabase/migrations/0024_metrics_classification_results.sql` — gaya migration hasil kalkulasi.
- `supabase/calculation_v1_common.py` — `CalculationError`, `SupabaseRest`, `calculation_contract`.
- `tests/test_valuation_engine.py` — gaya uji.
- `run_pipeline.py` — pola step orkestrator.

Aturan gaya:

1. Python 3, `from __future__ import annotations`, type hints, `Decimal` untuk angka (bukan
   float), docstring yang menjelaskan **alasan** keputusan, bukan mengulang kode.
2. Komentar/dokumen berbahasa Indonesia, kode berbahasa Inggris.
3. `backtest_engine.py` **tanpa** import `SupabaseRest`/`requests` — supaya bisa diuji offline dan
   tidak ada jalan membaca data di luar cutoff.
4. Angka yang tidak bisa dihitung → baris dengan `calculation_status` + `flags`, **jangan** nol
   dan jangan dihilangkan.
5. Jangan menyentuh `calc_valuation_*`. Backtest punya tabelnya sendiri.

## Yang harus dibuat di Fase 1

1. `supabase/backtest_engine.py` — fungsi murni:
   - `select_backtest_cases(annual_periods, quarter_periods)` → daftar kasus (aturan Helper).
   - `analysis_date_for(case)` — **satu tempat** untuk D1, supaya pindah ke `available_date`
     nanti cuma satu baris.
   - `as_of_price(prices, date)` — reuse/ikuti `pit_primitives.as_of_price`.
   - `price_windows(prices, analysis_date)` → semua `high_nm`/`low_nm`/peak/trough/peak_month.
   - `edate(date, months)` — reuse `pit_primitives.edate`.
2. `supabase/run_backtest.py` — orkestrator: baca DB, panggil engine, tulis hasil, verifikasi
   jumlah baris.
3. `supabase/migrations/0025_backtest_results.sql` — tabel `calc_backtest_cases` (+
   `calc_backtest_methods` kalau mau sekalian, tapi kolom valuasi boleh NULL di fase 1).
   Ikuti bentuk di `docs/BACKTEST_ARCHITECTURE.md` bagian 4. RLS aktif, tanpa grant ke
   `anon`/`authenticated`, grant ke `service_role`.
4. `tests/test_backtest_engine.py` — uji murni offline:
   - fixture AUTO 2022 Q1 dengan angka parity di atas;
   - fixture **DSSA atau GEMA** yang punya baris `High=0`/`Low=0` (wajib);
   - kasus 2026 Q2 (12M belum lengkap) → harus `WINDOW_PARTIAL`, bukan error;
   - jumlah kasus per ticker sesuai tabel di atas.
5. Tambah step `backtest` di `run_pipeline.py` setelah `valuation`.

## Yang JANGAN dikerjakan di fase 1

- Valuasi per kasus (`calculate_valuation_snapshot`) — itu fase 2.
- Verdict / konsensus / MoS — fase 3.
- RPC, adapter frontend, komponen UI — fase 4.
- Mengubah `backtest_generation_rule` di registry. **Parameter baru ditambahkan, yang lama tidak
  diubah**, karena `tests/test_phase_4_1_registry_and_pit.py:189` menguncinya sebagai unresolved
  dan `Testing/test_calculation_v1.py:227` mengunci "tepat 9 seed row".

## Definition of done Fase 1

1. `python -m unittest discover -s tests -t .` → **semua test lama tetap OK** (baseline: 199).
2. Test baru lolos, termasuk fixture `High=0`.
3. Untuk AUTO, 18 kasus dengan angka yang cocok dengan tabel parity di atas.
4. `python run_pipeline.py AUTO --only backtest` berjalan (boleh `--dry-run` dulu).
5. Laporkan: jumlah kasus per ticker, dan hasil verifikasi terhadap tabel parity.

## Referensi untuk fase berikutnya (jangan dikerjakan sekarang, tapi jangan dilanggar)

Fase 3 nanti memakai rumus `Verdict by Method` yang sudah disetujui pemilik produk. Rumus
lengkapnya ada di `docs/BACKTEST_ARCHITECTURE.md` bagian 5.4.1 — **salin apa adanya**. Empat
sifatnya yang mudah salah:

1. `K` pada rumus itu adalah **`[@Konsensus]`** (`2|5`), bukan `Verdict by Method`.
2. Rantai perbandingan ketat: hanya `>`; hari yang sama → `RECOVERED` / `OBSERVE`.
3. Window verdict 12 bulan (`> StartDate`), sedangkan `Ret 3M` 3 bulan (`>= StartDate`).
4. `K` tak dikenal → `FLAT`, bukan error.

Tiga cabang yang berbeda dari `frontend/src/lib/analysis/backtest.ts` sekarang (jangan ikut
frontend): UNDERVALUED hanya downside → `RISK`; OVERVALUED hanya upside → `REPRICE`; OVERVALUED
keduanya → tergantung urutan (`DownDate < UpDate` → `CONFIRMED`, selain itu `REPRICE`).

Threshold: undervalued `×1.2` / `×0.8`; overvalued/mixed `×1.15` / `×0.9`.
MoS = `(IV − price) / IV` (denominator IV). Konsensus = `Under|Valid`, `Valid = 5 − N/A − error`,
dan **IV negatif tetap valid**.

Kalau di tengah jalan kamu menemukan aturan yang bertentangan dengan dokumen arsitektur,
**berhenti dan tanyakan** — jangan pilih sendiri. Aturan-aturan itu sudah diverifikasi terhadap
18 baris workbook nyata.

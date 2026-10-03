# Prompt untuk chat baru: Consensus simpan-vs-hitung

Salin seluruh isi di bawah ini ke chat baru.

---

## Konteks

Repo: `D:\Stock Analyzer` (StockLens — analisis saham IDX dengan Supabase + Next.js).

Aku sudah menyelesaikan **desain** untuk pertanyaan "consensus disimpan di database
atau dihitung di frontend", dan menyimpannya di
**`docs/CONSENSUS_ARCHITECTURE.md`**.

**Baca dokumen itu lebih dulu, seluruhnya.** Semua aturan, keputusan, dan bukti
numerik ada di sana. Prompt ini hanya ringkasan agar kamu tahu apa yang harus
dikerjakan.

Dokumen pendukung yang wajib dibaca:

- `docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md` — framework "angka di backend, tampilan
  di UI". Prinsipnya: yang disimpan adalah "apa nilainya", yang dihitung adalah
  "bagaimana menampilkannya".
- `docs/BACKTEST_ARCHITECTURE.md` — aturan backtest (khususnya D5 denominator
  konsensus, dan §5.4.1 rumus verdict).
- `docs/DATA_RULES.md` — aturan data.

## Ringkasan desainnya

Satu aturan, dua perlakuan: **simpan yang beku, hitung yang bergerak.**

| Data | Harga | Perlakuan |
|---|---|---|
| Consensus backtest (`3\|5`) | `analysis_price` masa lalu, **beku** | **Baca nilai tersimpan** |
| Consensus valuasi terkini | harga sekarang, **bergerak** | **Hitung di SQL saat dibaca** |

Alasannya ada di dokumen: backtest beku karena `analysis_price` tidak pernah
berubah; valuasi terkini bergerak 76× dalam 1.619 hari bursa (AUTO), dan IV-nya
tetap 5 angka, jadi menyimpannya = menulis baris basi setiap hari untuk angka yang
bisa diturunkan dalam 5 perbandingan.

## Tugasmu: Langkah A dulu

Kerjakan **Langkah A saja** dari §4 dokumen. **Jangan** sentuh Langkah B/C dulu.

Langkah A = tab Backtest berhenti menghitung consensus, dan membaca nilai yang
sudah tersimpan.

**Tanpa migrasi.** Semua data sudah ada di `calc_backtest_cases` dan sudah dikirim
`get_stock_backtest`.

1. `frontend/src/lib/backtest-adapter.ts` — teruskan `consensus`,
   `consensusUndervalued`, `consensusValid` dari `BacktestCaseData` ke
   `BacktestCase` di `buildBacktestCase` (sekitar baris 103). Sekarang field itu
   **dibuang** — adapter punya 0 referensi `consensus`.
2. `frontend/src/components/stock-research/backtest-tab-content.tsx` — ganti
   `consensusByMethod` (baris 65) dan `consensusByMos` (baris 69) supaya membaca
   nilai tersimpan, bukan menghitung. Untuk "Consensus by MoS", `mosMain === null`
   harus jadi **`N/A`**, bukan `OVERVALUED` (lihat §2.4 dokumen: 41 kasus).
3. `frontend/src/lib/analysis/backtest.ts` — **jangan hapus** apa pun dulu.
   `countMethodsAboveAnalysisPrice` masih dipakai kolom "Undervalued Methods" dan
   `classifyMosMain` masih dipakai. Lihat keputusan C5 di dokumen.
4. `tests/test_backtest_no_browser_recomputation.py` — tambah guard supaya test
   gagal bila `consensusByMethod`/`consensusByMos` kembali muncul sebagai
   perhitungan.

## Fakta yang sudah diverifikasi — JANGAN dihitung ulang

Semua ini sudah dicek ke database produksi. Pakai apa adanya.

**Aturan resmi consensus** (`supabase/backtest_engine.py`, `resolve_consensus`
baris 1161; konstanta baris 272-320):

- `valid` = jumlah metode dengan `intrinsic_value is not null`.
- **`IV = 0` keluar dari penyebut** → `3|4`, bukan `3|5`.
- **`IV < 0` tetap valid.**
- `valid < 3` → `consensus = 'N/A'`, `consensus_undervalued = NULL`.
- Selain itu → `'{undervalued}|{valid}'`.

**Database selalu benar.** Uji 348 kasus yang RPC kirim ke UI:

| Uji | Hasil |
|---|---|
| `consensus_valid` DB vs hitung-ulang | **348/348 sama** |
| `consensus_undervalued` DB vs hitung-ulang | **347/348 sama** |

**Satu selisih angka = bug UI, dan itu bug yang kamu perbaiki.** GEMA 2022-Q4: harga
300, dua metode valid, keduanya `IV = 0`. DB bilang `N/A` (karena 2 < 3); UI bilang
`OVERVALUED` karena `backtest.ts:26` hanya punya dua cabang. Frontend tidak bisa
mereproduksi aturan DB karena tidak tahu ambang minimum 3 metode valid.

**Dampaknya lebih besar dari satu kasus: 44 kasus dari 348 menampilkan badge yang
salah.** Semuanya punya `consensus_valid < 3` (DB menulis `N/A`, browser memaksa
`UNDERVALUED`/`OVERVALUED`):

| Ticker | Kasus |
|---|---|
| GOLD | 19 |
| JSMR | 11 |
| BIRD | 4 |
| INDF | 4 |
| WIFI | 3 |
| ARII | 1 |
| DSSA | 1 |
| GEMA | 1 |

Sebagian besar adalah kasus `0|0` — **tidak ada satu pun metode valid** — tapi
browser tetap menampilkan `OVERVALUED`. `N/A` adalah jawaban yang jujur.

**"Consensus by MoS"** tidak butuh data baru: `mos_main` sudah tersimpan, dan
aturannya cuma `>= 0.3` (`classifyMosMain`). Jadi turunkan dari `mosMain`, bukan
dari `pricePath`.

## Konvensi repo yang WAJIB diikuti

Baca dulu file-file ini supaya gayamu konsisten (jangan menebak polanya):

- `frontend/src/lib/backtest-adapter.ts` — perhatikan gaya mapping yang sudah ada.
- `frontend/src/lib/stock-data.ts:564-600` — `BacktestCaseData` sudah punya
  `consensus`, `consensusUndervalued`, `consensusValid` (baris 578-580).
- `frontend/src/components/stock-research/backtest-tab-content.tsx` — komponennya
  adalah JSX yang sangat padat satu baris; **jangan reformat**, cukup ubah yang
  perlu.
- `tests/test_backtest_no_browser_recomputation.py` — gaya guard test yang sudah
  ada (6 test).
- `docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md` §2 — prinsip angka vs tampilan.

## Batasan

1. **Jangan ubah backend.** Langkah A murni frontend + test.
2. **Jangan buat migrasi.** Kalau kamu merasa perlu, berhenti dan tanya.
3. **Jangan ubah tampilan.** Angka yang tampil boleh berubah **hanya** untuk kasus
   yang sebelumnya salah (44 kasus `consensus_valid < 3` → jadi `N/A`). Warna,
   urutan kolom, tooltip tetap.
4. **Jangan hapus `lib/analysis/backtest.ts`.** Lihat C5.
5. Kalau kamu menemukan aturan yang bertentangan dengan
   `docs/CONSENSUS_ARCHITECTURE.md`, **berhenti dan tanyakan** — jangan pilih
   sendiri.

## Definition of done

1. `npx tsc --noEmit` → **0 error**.
2. `npm run lint` → **0 error** (baseline: 0 error, 4 warning).
3. `npm run build` → OK.
4. **44 kasus menampilkan `N/A`**, bukan `UNDERVALUED`/`OVERVALUED` (GOLD 19,
   JSMR 11, BIRD 4, INDF 4, WIFI 3, ARII 1, DSSA 1, GEMA 1).
5. 304 kasus sisanya **tidak berubah**.
6. `python -m unittest discover -s tests -t .` → **semua lulus** (baseline **444**).
7. Guard test baru gagal bila `consensusByMethod` muncul lagi.
8. Laporkan: berapa kasus yang berubah nilainya, dan konfirmasi semuanya punya
   `consensus_valid < 3` (harapan: **44 kasus** di GOLD, JSMR, BIRD, INDF, WIFI,
   ARII, DSSA, GEMA).

## Setelah selesai

Laporkan hasilnya, lalu **berhenti**. Jangan lanjut ke Langkah B/C tanpa
persetujuan — keduanya butuh keputusan C1-C5 dulu (lihat §5 dokumen).

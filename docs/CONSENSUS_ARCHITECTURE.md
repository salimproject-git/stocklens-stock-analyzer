# Arsitektur Consensus: simpan vs hitung

Dokumen ini adalah **desain**, bukan implementasi. Belum ada kode, tabel, atau data
Supabase yang diubah karena dokumen ini.

Rujukan: `docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md` (framework umum),
`docs/BACKTEST_ARCHITECTURE.md` (aturan backtest), `docs/DATA_RULES.md` (aturan data).

---

## 1. Pertanyaan yang dijawab

`Consensus` (angka `3|5` di UI) muncul di **dua tempat** yang berbeda sifatnya:

1. **Tab Backtest** — "Consensus by Method" dan "Consensus by MoS" per kasus historis.
2. **Tab Valuation** — berapa dari lima metode yang menilai harga sekarang murah.

Pertanyaan pemilik repo: **mana yang disimpan di database, mana yang dihitung?**

Jawaban singkat: **yang harganya beku disimpan; yang harganya bergerak dihitung.**
Backtest memakai `analysis_price` yang tidak pernah berubah, jadi consensus-nya
disimpan. Valuasi terkini memakai harga yang berubah setiap hari, jadi consensus-nya
dihitung saat dibaca.

---

## 2. Fakta yang sudah diverifikasi — jangan dihitung ulang

Semua angka di bawah dicek langsung ke database produksi pada 2026-10-02.

### 2.1 Backtest memang beku

Harga analisis **identik antar run** untuk kasus yang sama:

| Ticker | Kuartal | Harga run-1 | Harga run-2 | Berubah? |
|---|---|---|---|---|
| GEMA | 2022-Q4 | 300 | 300 | tidak |
| GOLD | 2021-Q1 | 274 | 274 | tidak |
| GOLD | 2022-Q2 | 332 | 332 | tidak |
| GEMA | 2023-Q1 | 174 | 174 | tidak |

`analysis_price` = close PIT pada `analysis_date`. Tanggalnya di masa lalu, jadi
nilainya tetap. Inilah alasan consensus backtest **boleh** disimpan.

### 2.2 Nilai consensus yang tersimpan sudah benar

Uji: bandingkan `consensus_valid` / `consensus_undervalued` tersimpan dengan
rekomputasi dari `intrinsic_value` vs `analysis_price`, untuk **348 kasus** yang
RPC benar-benar kirim ke UI.

| Uji | Hasil |
|---|---|
| `consensus_valid` DB vs hitung-ulang | **348 / 348 sama** |
| `consensus_undervalued` DB vs hitung-ulang | **347 / 348 sama** |
| Sisa 1 selisih | GEMA 2022-Q4 (DB `0`, UI `1`; tapi DB menulis `consensus = 'N/A'`, jadi tidak ditampilkan) |

Database **tidak** punya bug consensus. Yang berbeda adalah **badge yang tampil**,
dijelaskan di §2.3 dan §2.4.

### 2.3 44 kasus menampilkan badge yang salah

Angka `x/y`-nya cocok, tapi **kesimpulan** yang tampil tidak. Uji: bandingkan
`consensus` tersimpan dengan apa yang `consensusByMethod` hasilkan di browser.

| Uji | Hasil |
|---|---|
| Badge cocok | 304 / 348 |
| **Badge berbeda** | **44** |

Ke-44 kasus itu semuanya punya `consensus_valid < 3`, dan DB menulis `N/A`
sedangkan browser memaksa `UNDERVALUED`/`OVERVALUED`:

| Ticker | Kasus | Contoh | UI hitung | DB |
|---|---|---|---|---|
| GOLD | 19 | 2021-Q1 … 2025-Q4 | `0\|0` | `N/A` |
| JSMR | 11 | 2022-Q1 … 2025-Q4 | `0\|0` | `N/A` |
| BIRD | 4 | 2023-Q2, 2023-Q3, 2023-Q4, 2025-Q4 | `0\|0` | `N/A` |
| INDF | 4 | 2024-Q3, 2024-Q4, 2025-Q2, 2025-Q4 | `0\|0` | `N/A` |
| WIFI | 3 | 2021-Q1, 2021-Q2, 2021-Q3 | `0\|1`, `0\|2` | `N/A` |
| ARII | 1 | 2022-Q4 | `0\|0` | `N/A` |
| DSSA | 1 | 2022-Q4 | `0\|0` | `N/A` |
| GEMA | 1 | 2022-Q4 | `1\|2` | `N/A` |

Contoh paling tajam, GEMA 2022-Q4: harga 300, dua metode valid, keduanya `IV = 0`.

| Sumber | Badge | Alasan |
|---|---|---|
| Database (`resolve_consensus`) | **`N/A`** | metode valid (2) < `CONSENSUS_MIN_VALID_METHODS` (3) |
| UI (`consensusByMethod`) | **`OVERVALUED`** | `backtest.ts:26` hanya punya dua cabang |

Database punya **tiga** keadaan (`UNDERVALUED`, `OVERVALUED`, `N/A`); frontend
hanya punya **dua**. Frontend tidak bisa mereproduksi aturan DB karena tidak
mengetahui ambang minimum 3 metode valid.

Kasus `0|0` (GOLD, JSMR, dll.) lebih ekstrem lagi: **tidak ada satu pun metode
valid**, tapi browser tetap menampilkan `OVERVALUED` — seolah ada dasar untuk
menyimpulkan. `N/A` adalah jawaban yang jujur.

### 2.4 Badge "Consensus by MoS" juga salah di 41 kasus

Aturan yang sama berlaku untuk MoS. `mos_main` **NULL** di **41 kasus** — dan itu
persis kasus yang tidak punya cukup metode valid:

| Ticker | `mos_main` NULL |
|---|---|
| GOLD | 19 |
| JSMR | 11 |
| BIRD | 4 |
| INDF | 4 |
| ARII | 1 |
| DSSA | 1 |
| GEMA | 1 |

`classifyMosMain(null)` mengembalikan `OVERVALUED` (`backtest.ts:47-51`), padahal
tidak ada MoS yang bisa dihitung. `N/A` yang benar.

Catatan: `verdict_mos` yang tersimpan **bukan** consensus-by-MoS — isinya
`CONFIRMED`/`REPRICE`/`WIN`/`RISK`/`FLAT`/`RECOVERED`, yaitu verdict hasil, bukan
badge `UNDERVALUED`/`OVERVALUED`. Jadi badge MoS tetap **turunan** dari `mos_main`
(dengan aturan `NULL → N/A`), bukan dibaca dari `verdict_mos`.



### 2.5 Valuasi terkini memang hidup

AUTO, 1.619 hari bursa (2020-01-02 → 2026-09-24):

| Metrik | Nilai |
|---|---|
| Consensus berubah | **76×** (rata-rata tiap 21 hari bursa) |
| Nilai berbeda yang pernah muncul | **5** (`1\|5`, `2\|5`, `3\|5`, `4\|5`, `5\|5`) |
| Harga rata-rata bergerak per perubahan | 3,23% (maks 10,47%) |
| Jumlah IV berbeda | **5** (lima angka tetap) |

**Penyebabnya harga, bukan IV.** IV-nya lima angka konstan; yang bergerak cuma
harga. Karena itu menyimpan consensus valuasi = menulis baris baru setiap hari
untuk setiap ticker, dan setiap baris langsung basi keesokan harinya. Menghitungnya
hanya butuh **lima perbandingan** (`IV > harga`). Menyimpan lebih mahal daripada
menghitung.

### 2.6 Consensus valuasi belum ada di database sama sekali

| Tempat | Ada consensus? |
|---|---|
| Tabel `calc_valuation_methods` | **Tidak** — tidak punya kolom `consensus*` |
| RPC `get_stock_research_data` | **Tidak** — payload tidak memuat `consensus` |
| Tabel `calc_backtest_cases` | **Ya** — `consensus`, `consensus_undervalued`, `consensus_valid` |
| `frontend/src/lib/stock-data.ts:578-580` | Memetakan `consensus` dari baris backtest |
| `frontend/src/lib/backtest-adapter.ts` | **0 referensi** — consensus dibuang saat mapping |
| `backtest-tab-content.tsx:65-71` | **Menghitung ulang** lewat `consensusByMethod` / `consensusByMos` |

Jadi rantainya: DB menyimpan consensus → adapter membuangnya → tab menghitung
ulang. Dua implementasi rumus yang sama, dan yang di browser tidak lengkap
(§2.3).

### 2.7 Aturan resmi consensus (dari `backtest_engine.py`)

Sumber kebenaran: `supabase/backtest_engine.py`, fungsi `resolve_consensus`
(baris 1161) dan konstanta baris 272-320.

| Konstanta | Nilai |
|---|---|
| `CONSENSUS_NOT_AVAILABLE` | `'N/A'` |
| `CONSENSUS_MIN_VALID_METHODS` | `3` |
| `CONSENSUS_UNDERVALUED_CLASSES` | `('3\|3','3\|4','4\|4','3\|5','4\|5','5\|5')` |

Aturan:

1. `valid` = jumlah metode dengan `intrinsic_value is not null`.
2. **`IV = 0` keluar dari penyebut** (DDM untuk perusahaan tanpa dividen) →
   `3|4`, bukan `3|5`.
3. **`IV < 0` tetap valid** — model tetap menyatakan sesuatu.
4. Kalau `valid < 3` → `consensus = 'N/A'`, `consensus_undervalued = NULL`.
5. Selain itu → `consensus = '{undervalued}|{valid}'`.

Frontend `analysis/backtest.ts:22-33` mengimplementasikan aturan 1-3 dengan benar
(termasuk `IV = 0` skip), tapi **tidak punya aturan 4**.

### 2.8 Peta tiga zona umur kasus

Berdasarkan `CASE_MIN_AGE_MONTHS = 4` (`backtest_engine.py:371`) dan jendela
observasi 12 bulan:

| Zona | Definisi | Kasus | Porsi | Tampil di UI? | Verdict final? |
|---|---|---|---|---|---|
| 1 | umur < 4 bulan | 57 | 3% | **Tidak** (dibuang) | belum bisa dinilai |
| 2 | jendela **BUKA** (4–12 bulan) | 200 | 11% | Ya | **belum** |
| 3 | jendela **TUTUP** (> 12 bulan) | 1.540 | 86% | Ya | **ya** |

Yang tampil di UI sekarang: kasus terbaru = **2026-Q1**. Kuartal 2026-Q2 (57 kasus)
sudah ada di DB tapi dibuang aturan 4 bulan.

**Basis valuasi terkini = 2026-Q2** untuk semua ticker yang diperiksa. Artinya
"kuartal yang masih berjalan" dan "basis valuasi terkini" adalah **wilayah yang
sama**, dilihat dari dua pintu.

### 2.9 Backtest tidak sepenuhnya beku — 47 kasus berubah

Ini temuan yang perlu keputusan terpisah. Bandingkan run terakhir vs sebelumnya,
per (instrument, basis), hanya kasus berjendela **TUTUP**:

| Uji | Hasil |
|---|---|
| Pasangan dibandingkan | 308 |
| Verdict berubah | **47** (15%) |
| Verdict MoS berubah | 59 |
| Consensus berubah | 59 |

Harganya **identik** (§2.1). Penyebabnya `methodology_version_id` berbeda di setiap
run — AMRT 2022-Q2 punya **5 versi metodologi berbeda** dalam 3 hari. Jadi:

> Backtest beku **hanya jika dipin ke satu run + satu versi metodologi.**
> Re-run dengan kode baru mengubah "sejarah".

RPC sekarang mengambil run `SUCCEEDED` terbaru, jadi setiap re-run menggeser apa
yang dilihat user. Keputusan ini **terpisah** dari consensus, tapi harus dicatat.

### 2.10 Struktur run: satu run = satu ticker

Bukan satu batch. 100 run untuk 20 ticker × 5 iterasi. Setiap run berisi 17–21
kasus (satu ticker). Ini penting saat membandingkan "run terakhir": harus
di-partisi per `scope_id`, bukan global.

---

## 3. Aturan yang diusulkan

### 3.1 Tabel keputusan

| Data | Harga yang dipakai | Beku? | Perlakuan | Alasan |
|---|---|---|---|---|
| Consensus backtest | `analysis_price` (masa lalu) | **Ya** | **Simpan** (sudah tersimpan) | Satu kali hitung, tidak akan berubah |
| Consensus valuasi terkini | harga sekarang | **Tidak** | **Hitung saat dibaca** | 5 perbandingan; menyimpan = menulis baris basi tiap hari |
| Verdict backtest (zona 3) | `analysis_price` | **Ya** | **Simpan** (sudah tersimpan) | Final |
| Verdict backtest (zona 2) | `analysis_price` | Belum | Tandai `WINDOW_OPEN` | Masih berkembang |
| Verdict valuasi terkini | harga sekarang | **Tidak** | **Hitung saat dibaca** | Berubah harian |

### 3.2 Prinsip

> **Simpan apa yang beku. Hitung apa yang bergerak.**

Konsekuensinya:

- Backtest (zona 3) → **satu kali hitung, disimpan, diaudit**. Nilainya tidak
  bergerak, jadi menyimpan tidak menimbulkan risiko basi.
- Valuasi terkini → **tidak disimpan**, karena menyimpannya berarti menciptakan
  baris yang sudah salah begitu harga bergerak. Yang disimpan cukup **inputnya**
  (lima `intrinsic_value`), dan verdict diturunkan di SQL.

Ini selaras dengan §2 `docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md`: yang disimpan
adalah "apa nilainya" (IV), yang dihitung adalah "apa artinya bagi harga hari ini".

### 3.3 Konsekuensi pada frontend

Frontend **berhenti menghitung consensus**. Ia membaca:

- Backtest → `consensus` tersimpan (sudah dikirim `get_stock_backtest`).
- Valuasi → `consensus` baru dari `get_stock_research_data` (§4 Langkah B).

Yang **tetap** di frontend: warna badge, urutan kolom, tooltip, format `x/y`.

### 3.4 Mengapa bukan "simpan semua"

Kalau consensus valuasi ikut disimpan:

| Akibat | Penjelasan |
|---|---|
| Baris tumbuh tanpa batas | 20 ticker × 250 hari bursa/tahun = 5.000 baris/tahun untuk satu angka turunan |
| Selalu ada baris basi | Baris hari ini salah begitu harga besok masuk, sebelum job berikutnya jalan |
| Dua sumber kebenaran | Konsumen harus tahu baris mana yang "hari ini", persis masalah §4 di `BACKEND_SINGLE_SOURCE_OF_TRUTH.md` |
| Tidak menambah informasi | IV sudah tersimpan; consensus = fungsi deterministik dari (IV, harga) |

### 3.5 Mengapa bukan "hitung semua di browser"

Kalau consensus backtest tetap dihitung di browser:

| Akibat | Penjelasan |
|---|---|
| Rumus bercabang | Browser tidak punya aturan `N/A` (§2.3) → **44 kasus salah** |
| n8n tidak melihat | AI menerima angka berbeda dari yang dilihat manusia |
| Tidak diaudit | Tidak ada `calculation_run_id` untuk angka yang tampil |

---

## 4. Rencana pengerjaan

Tiga langkah, dari yang paling murah. Setiap langkah berdiri sendiri.

### Langkah A — Backtest membaca consensus tersimpan

**Tanpa migrasi.** Semua data sudah ada.

1. `backtest-adapter.ts` — teruskan `consensus`, `consensusUndervalued`,
   `consensusValid` dari `BacktestCaseData` ke `BacktestCase`
   (`buildBacktestCase`, sekitar baris 103).
2. `backtest-tab-content.tsx` — ganti `consensusByMethod` (baris 65) dan
   `consensusByMos` (baris 69) supaya membaca nilai tersimpan. Untuk "Consensus by
   MoS", nilai turunan = `classifyMosMain(testCase.mosMain)`; `mosMain` sudah
   tersimpan, jadi tidak ada rumus baru — **tapi `mosMain === null` harus jadi
   `N/A`, bukan `OVERVALUED`** (§2.4 dokumen: 41 kasus).
3. `analysis/backtest.ts` — `classifyMethodsAbovePrice` dan
   `countMethodsAboveAnalysisPrice` **tetap ada** selama masih dipakai kolom
   "Undervalued Methods"; jangan hapus sebelum kolom itu juga pindah. Catatan:
   `backtestMethodology.classification.methodUndervaluedMinimum` (baris 7) dan
   aturan tiga cabang (baris 26) **tetap dipakai** oleh kolom itu.
4. Perbarui guard test `tests/test_backtest_no_browser_recomputation.py` supaya
   gagal bila `consensusByMethod`/`consensusByMos` kembali muncul.

**Verifikasi:** 44 kasus yang sebelumnya salah harus menampilkan `N/A`
(GOLD 19, JSMR 11, BIRD 4, INDF 4, WIFI 3, ARII 1, DSSA 1, GEMA 1). 304 kasus
sisanya tidak boleh berubah.

### Langkah B — Consensus valuasi dihitung di SQL

**Migrasi kecil.** Hanya mengisi ulang fungsi; tidak ada tabel baru.

Sisipkan ke `get_stock_research_data`, memakai `latest_valuation_rows` yang sudah
ada (migrasi `0031`, sekitar baris 140-178):

```sql
stock_valuation_consensus as (
  select
    count(*) filter (where v.intrinsic_value is not null) as valid,
    count(*) filter (
      where v.intrinsic_value is not null
        and v.intrinsic_value <> 0
        and v.intrinsic_value > v.current_price
    ) as undervalued
  from latest_valuation_rows as v
),
valuation_consensus as (
  select case
    when c.valid < 3 then 'N/A'
    else c.undervalued || '|' || c.valid
  end as consensus,
  case when c.valid < 3 then null else c.undervalued end as consensus_undervalued,
  c.valid as consensus_valid
  from stock_valuation_consensus as c
)
```

Lalu tambahkan ke `jsonb_build_object` di level atas (sekitar baris 400):

```sql
'valuation_consensus', jsonb_build_object(
  'consensus', (select consensus from valuation_consensus),
  'consensus_undervalued', (select consensus_undervalued from valuation_consensus),
  'consensus_valid', (select consensus_valid from valuation_consensus)
),
```

**Catatan penting:** ambang `3` harus diambil dari satu tempat. Lihat §5 Keputusan
C2 — kalau ambang dipindah ke tabel parameter, pakai nilai itu, bukan literal `3`.

Tambahkan `$verify$` guard di akhir migrasi (pola yang sudah dipakai `0031:418`):

```sql
do $verify$
begin
  if definition not like '%valuation_consensus%' then
    raise exception 'STOCKLENS_VALUATION_CONSENSUS_MISSING';
  end if;
end
$verify$;
```

### Langkah C — Tandai zona 2 (jendela buka)

**Migrasi kecil.** Menambah flag, bukan mengubah nilai.

Untuk kasus backtest dengan `analysis_date + 12 months > current_date`, tambahkan
flag `WINDOW_OPEN` pada `flags`, dan kirim `window_open` boolean di payload.
Frontend menampilkan badge "masih berkembang" dan tidak menyajikan verdict sebagai
final.

**Jangan** ubah `verdict` tersimpan — itu tetap hasil hitung pada saat run, dan
berguna sebagai jejak.

---

## 5. Keputusan yang masih terbuka

Chat yang mengerjakan implementasi harus **bertanya dulu**, bukan memilih sendiri.

| # | Pertanyaan | Pilihan | Catatan |
|---|---|---|---|
| C1 | Zona 2: hitung saat dibaca atau simpan + tanda provisional? | (a) hitung saat dibaca, (b) simpan + flag | (a) selalu akurat, RPC lebih berat (200 kasus × 5 metode). (b) lebih ringan, tapi butuh refresh berkala. Rekomendasi: **(a)** |
| C2 | Ambang `3` metode valid: pindah ke tabel parameter? | (a) pindah, (b) tetap di kode | Sekarang ada di **dua** tempat: `backtest_engine.py:275` dan `analysis/backtest.ts:7`. (b) berarti SQL Langkah B memakai literal `3` |
| C3 | Re-run mengubah sejarah (§2.9): pin ke versi metodologi? | (a) RPC pin ke run tertentu, (b) tetap run terbaru | (b) perilaku sekarang. (a) perlu kolom "run kanonik" per instrumen |
| C4 | Consensus by MoS di backtest: tersimpan atau turunan? | (a) turunan dari `mos_main` tersimpan, (b) kolom baru | `mos_main` sudah tersimpan, dan aturannya cuma `>= 0.3`. Rekomendasi: **(a)** |
| C5 | Kolom "Undervalued Methods" (`x/y`) di tab Backtest: ikut pindah? | (a) pakai `consensus` tersimpan, (b) biarkan menghitung | Kalau (a), `countMethodsAboveAnalysisPrice` bisa dihapus sekalian |

---

## 6. Definisi selesai

**Langkah A:**

1. `npx tsc --noEmit` → 0 error.
2. `npm run lint` → 0 error.
3. 44 kasus yang salah menampilkan `N/A` (bukan `UNDERVALUED`/`OVERVALUED`).
4. 304 kasus sisanya tidak berubah.
5. `python -m unittest discover -s tests -t .` → semua lulus (baseline 444).
6. Guard test gagal bila `consensusByMethod` muncul lagi.

**Langkah B:**

1. `get_stock_research_data('AUTO')` memuat `valuation_consensus`.
2. Untuk AUTO: `consensus_valid = 5` (lima metode, tidak ada yang nol).
3. Nilai cocok dengan hitung manual dari `intrinsic_value` vs `current_price`.
4. Guard `STOCKLENS_VALUATION_CONSENSUS_MISSING` aktif.
5. Tidak ada tabel baru; tidak ada baris baru.

**Langkah C:**

1. 200 kasus zona 2 membawa flag `WINDOW_OPEN`.
2. 1.540 kasus zona 3 tidak membawa flag itu.
3. UI menampilkan penanda untuk zona 2.

---

## 7. Yang sengaja TIDAK dikerjakan

1. **Menghapus `lib/analysis/backtest.ts`.** Masih dipakai kolom "Undervalued
   Methods" dan `classifyMosMain`. Lihat C5.
2. **Menyimpan consensus valuasi.** Bertentangan dengan §3.4.
3. **Menyeragamkan ambang di dua tempat.** Itu C2, keputusan terpisah.
4. **Backfill `report_date`/`available_date`.** 658 periode, butuh data eksternal.
   Ditunda.
5. **Menghapus 20 baris duplikat `calc_valuation_methods`.** RPC sudah tahan
   (memakai `distinct on (method_code)` + `created_at desc`). Tidak mendesak.

---

## 8. Ringkasan satu paragraf

Backtest memakai harga masa lalu yang tidak berubah, jadi consensus-nya disimpan di
database dan frontend cukup membacanya — ini juga memperbaiki **44 kasus** (GOLD,
JSMR, BIRD, INDF, WIFI, ARII, DSSA, GEMA) yang salah karena browser tidak tahu
aturan "minimal 3 metode valid". Valuasi
terkini memakai harga yang bergerak setiap hari, jadi consensus-nya dihitung di SQL
dari lima IV yang sudah tersimpan; menyimpannya berarti menulis 5.000 baris basi per
tahun untuk angka yang bisa diturunkan dalam lima perbandingan. Satu aturan, dua
perlakuan: **simpan yang beku, hitung yang bergerak.**

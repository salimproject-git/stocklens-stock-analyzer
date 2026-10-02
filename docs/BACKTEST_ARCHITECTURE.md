# Arsitektur Backtest Historis — ide sebelum implementasi

Dokumen ini adalah **desain**, bukan implementasi. Belum ada kode, tabel, atau data Supabase
yang diubah hanya karena dokumen ini. Tujuannya menyepakati aturan, bentuk penyimpanan, dan
urutan pengerjaan sebelum satu baris kode backtest ditulis.

Rujukan aturan: `Template/Stock Analyzer [Dev].xlsm` (sheet `Helper`, `Backtest_Result`,
`DB_ANALYSIS`, `SUMMARY`), makro `BuildHistoricalSnapshot`, dan rumus kolom `Backtest_Result`.

---

## 1. Apa yang sebenarnya dikerjakan workbook (terverifikasi)

Prosesnya **dua tahap** dan keduanya berbeda sifat.

### Tahap A — pembentukan daftar kasus (makro `BuildHistoricalSnapshot`)

1. `Helper!C2#` menghasilkan daftar *base year* valid:

   ```excel
   LET(Years, SORT(UNIQUE(FILTER(tblStockDatabase_DB[Year], tblStockDatabase_DB[Ticker]=Stock_Ticker)),1,-1),
       IF(ROWS(Years)<=2, "", FILTER(Years, Years > SMALL(Years,2))))
   ```

   Artinya: **semua tahun annual ticker itu kecuali dua tahun terkecil**. Untuk AUTO
   (2019–2025) hasilnya 2021, 2022, 2023, 2024, 2025.

2. Loop seluruh baris `Stock_Database_Quarter` milik ticker. Untuk tiap baris
   `baseYear = dbYear - 1`. Baris diproses hanya bila `baseYear` ada di daftar valid.
3. Untuk tiap kuartal yang lolos: set `SUMMARY!E4 = baseYear`, `SUMMARY!E5 = "Q" & dbQuarter`,
   `Application.Calculate`, lalu **verifikasi** `DB_ANALYSIS!D2 == "YYYY Qn"` sebelum menyalin
   `DB_ANALYSIS!A2:AA2` ke `Backtest_Result`.
4. Di akhir, seleksi ticker/tahun/kuartal asli dikembalikan.

Konsekuensinya **kasus bukan "semua kuartal"**, melainkan *semua kuartal pada tahun setelah
setiap base year valid*. Untuk AUTO: kuartal tahun 2022–2026 → **18 kasus** (2022Q1…2026Q2).
Angka ini cocok persis dengan 18 baris `Backtest_Result` dan `totalCases: 18` di data sampel
frontend.

Dua tahun terkecil dibuang supaya setiap kasus punya riwayat tahun yang sebanding — meniru
posisi analis saat itu, yang juga belum punya dua tahun pertama.

### Tahap B — metrik hasil (rumus kolom `Backtest_Result`)

| Kolom | Aturan |
|---|---|
| `Tgl_Analisis` | `MAXIFS(Data Available Date)` untuk (Ticker, Year, Quarter) kasus itu |
| `Harga Analisis` | harga manual bila diisi; kalau tidak, close PIT pada `Tgl_Analisis` |
| `Ret 3M` | max/min `High`/`Low` pada `[Tgl_Analisis, EDATE(+3)]` — **kedua ujung inklusif** |
| `Ret 6M` | pada `(EDATE(+3), EDATE(+6)]` — ujung awal **eksklusif** |
| `Ret 9M` | pada `(EDATE(+6), EDATE(+9)]` |
| `Ret 12M` | pada `(EDATE(+9), EDATE(+12)]` |
| `Price nM` | harga max/min yang sama, ditampilkan sebagai nominal |
| `Harga trough` | `MIN(Low)` pada `[Tgl_Analisis, EDATE(+12)]` inklusif |
| `Harga Peak` | `MAX(High)` pada `[Tgl_Analisis, EDATE(+12)]` inklusif |
| `Bln Peak` | `"M+" & DATEDIF(Tgl0, MIN(Date) saat High = Harga Peak, "m")` |
| `Ret Peak` / `Ret Down` | `Harga Peak/BasePrice − 1` dan `Harga trough/BasePrice − 1` |
| `Konsensus` | `Under_Count & "|" & Valid_Count`; `"N/A"` bila `Valid_Count < 3` |
| `Verdict by Method` | dari `Konsensus`; UNDERVALUED bila ∈ {3\|3, 3\|4, 4\|4, 3\|5, 4\|5, 5\|5} |
| `Verdict MoS` | `K = IF(MoS Main >= 30%, "UNDERVALUED", "OVERVALUED")` |

`High = 0 ? Close : High` dan `Low = 0 ? Close : Low` — aturan workbook, dipakai apa adanya.

**Aturan ini material, bukan kosmetik.** Di `prices_daily` kita ada **865 baris dengan
`high_price = 0` dan `low_price = 0`**, terdistribusi:

| Ticker | Baris `High=0` | Porsi |
|---|---|---|
| DSSA | 539 | 33.5% |
| GEMA | 195 | 12.1% |
| ARII | 52 | 3.2% |
| INDS | 38 | 2.4% |
| GOLD | 34 | 2.1% |
| IPOL | 4 | 0.2% |
| WIFI | 3 | 0.2% |

Kalau aturan ini dilewatkan, `MAX(High)` akan mengembalikan 0 untuk ticker-ticker itu dan
seluruh `Ret nM` / `Harga Peak` jadi salah. AUTO kebetulan 0 baris, jadi menguji hanya dengan
AUTO **tidak akan menangkap bug ini** — fixture uji wajib menyertakan DSSA atau GEMA.

Aturan verdict (dari rumus terbaru yang dipasang):

```
UNDERVALUED : up kosong & down kosong -> FLAT
              up ada   & down kosong -> WIN
              up kosong & down ada   -> RISK
              DownDate < UpDate      -> RECOVERED
              selain itu             -> WIN        (termasuk hari yang sama)
OVERVALUED  : up kosong & down kosong -> FLAT
              up ada   & down kosong -> REPRICE
              up kosong & down ada   -> CONFIRMED
              DownDate < UpDate      -> CONFIRMED
              selain itu             -> REPRICE    (termasuk hari yang sama)
selain di atas : FLAT
```

**Target harga: `× 1.20` naik dan `× 0.85` turun, sama untuk kedua klasifikasi.**
Klasifikasi hanya memilih **nama** verdict, bukan ambangnya. (Rumus sebelumnya memakai
`1.2`/`0.8` untuk UNDERVALUED dan `1.15`/`0.9` untuk lainnya.)

Dua konsekuensi yang penting:

1. **`OBSERVE` tidak dipakai lagi.** Cabang "tidak menyentuh apa pun" pada sisi overvalued
   menjadi `FLAT`, sama seperti sisi undervalued. Nilai `OBSERVE` masih ada di check
   constraint 0025 demi baris lama, tapi aturan sekarang tidak pernah menghasilkannya.
2. **Hari yang sama bukan lagi kasus khusus.** Cabang terakhir memakai `<`, jadi
   `UpDate == DownDate` jatuh ke `WIN`/`REPRICE`. `RECOVERED` sekarang **hanya** untuk kasus
   yang benar-benar turun dulu lalu naik.

Catatan penting soal `Verdict by Method`: kolom `K` pada rumus itu adalah
**`[@Konsensus]`**, yang di workbook berisi literal `"UNDERVALUED"`/`"OVERVALUED"`.
Nilai itu berasal dari kolom `IV` (`"2|5"`) lewat:

```excel
=IF(OR(J2="3|3", J2="3|4", J2="4|4", J2="3|5", J2="4|5", J2="5|5"),
    "UNDERVALUED", "OVERVALUED")
```

**Hanya dua kelas - tidak ada `MIXED`.** Rumus rasio (`Ratio >= 0.6` → UNDERVALUED,
`>= 0.4` → MIXED) yang dipakai sheet valuasi sengaja **tidak** diikuti di backtest, karena
rumus kolom `AY` hanya mengenal dua nilai itu dan sisanya jatuh ke `FLAT`.

Rantainya: **lima IV → `Konsensus` (`2|5`) → `Verdict by Method` → `Verdict MoS`
(hitungan terpisah dari `MoS Main`)**.

### Penyebut konsensus bervariasi - dan `IV = 0` keluar dari penyebut

Konsensus **bukan** selalu `/5`. Formula workbook:

```excel
Skip_Count,COUNTIF(E13:E17,"⚪ N/A (Skip)")
Valid_Count,5-Invalid_Count
```

dan status per metode:

```excel
=IF(B25=0, "⚪ N/A (Skip)", IF(price < B25, "UNDERVALUED", "OVERVALUED"))
```

Jadi **`IV = 0` adalah "N/A (Skip)"** dan dikeluarkan dari penyebut: saham tanpa dividen
tidak punya DDM, sehingga konsensusnya `3|4`, bukan `3|5`. `IV` **negatif tetap valid**
(D5) - hanya nol yang di-skip.

Bukti ke workbook: dari 72 baris dengan lima IV lengkap, aturan "IV=0 di-skip" cocok
**72/72**, sedangkan "IV=0 dihitung valid" gagal tepat di INDF 2024-Q4 dan 2025-Q2
(workbook menulis `1|3`, bukan `1|5`).

### Kasus yang belum berumur 4 bulan dibuang

Laporan kuartalan IDX baru terbit sekitar 3-4 bulan setelah akhir periode, jadi kuartal
terbaru belum punya riwayat harga yang layak dinilai dan **tidak ditampilkan**. Contoh:
Q2 berakhir 30 Juni dan baru terbit Agustus, jadi pada 30 September umurnya baru 3 bulan;
DSSA yang kuartal terakhirnya Q1 (31 Maret) sudah 6 bulan sehingga tetap muncul.

Anchor-nya `analysis_date` (`available_date` bila terisi), sehingga begitu backfill
tanggal rilis selesai batasnya otomatis bergeser.

### Bukti numerik yang sudah dicek ke database

Untuk AUTO 2022 Q1 (`analysisPrice = 1125`, `MoS Main = 0.5509426016`):

| Metrik | Workbook | Hitung ulang dari `prices_daily` | Cocok |
|---|---|---|---|
| `Ret 3M` up/down | 1285 / 1080 | 1285 / 1080 | ya |
| `Ret 6M` up/down | 1375 / 1085 | 1375 / 1085 | ya |
| `Ret 9M` up/down | 1590 / 1155 | 1590 / 1155 | ya |
| `Ret 12M` up/down | 1855 / 1335 | 1855 / 1335 | ya |
| `Harga trough` / `Peak` | 1080 / 1855 | 1080 / 1855 | ya |
| `Bln Peak` | M+11 | 2023-03-03 → M+11 | ya |

Harga analisis juga cocok di tiga kasus uji: 2022-03-31 → 1125, 2023-06-30 → 2480,
2026-06-30 → 2350 — persis nilai `analysisPrice` di data sampel frontend.

---

## 2. Keputusan yang harus diambil sebelum menulis kode

### D1. `Tgl_Analisis` — gap terbesar

Workbook memakai `Data Available Date` dari daftar tanggal resmi quarter. Kita **tidak punya**
itu: `financial_periods.available_date` dan `report_date` masih `NULL` untuk semua ticker.
Dua pilihan:

- **(a) pakai `period_end`** kuartal kasus, dengan flag `POINT_IN_TIME_UNAVAILABLE_DATE`.
  Ini yang sudah dipakai data sampel frontend (`2022 Q1` → `2022-03-31`), jadi konsisten
  dengan yang sudah dilihat pengguna.
- **(b) isi `available_date` dulu**, baru backtest.

Catatan: `period_end` **lebih awal** daripada `Data Available Date` (laporan Q1 IDX baru
tersedia sekitar akhir Mei). Memakai `period_end` berarti mengklaim tahu lebih cepat daripada
kenyataan, jadi flag wajib, bukan opsional.

**Rekomendasi: (a) sekarang + flag; (b) nanti.** Tanggal dibuat satu fungsi yang bisa ditukar
(`analysis_date_for(case)`) supaya pindah ke (b) hanya satu baris.

### D2. `years_available` per kasus

Workbook memakai `Years_Avail = 7` (konstanta) untuk semua kasus, sedangkan engine kita menolak
bila `years_available > jumlah periode annual` (`YEARS_AVAILABLE_EXCEEDS_HISTORY`). Kasus
2022Q1 hanya punya 3 tahun annual (2019–2021), jadi 7 tidak mungkin.

**Rekomendasi:** `years_available = min(registry Years_Avail, jumlah annual ≤ period_end
kasus)`, dengan flag `YEARS_AVAILABLE_TRUNCATED`. Ini perbaikan PIT yang disengaja; akibatnya
IV pada kasus paling awal bisa berbeda sedikit dari workbook. Perbedaan itu dilaporkan, bukan
disembunyikan.

### D3. Threshold undervalued — **SUDAH DIPUTUSKAN**

Dua angka beredar:

| Sumber | upside | downside |
|---|---|---|
| Rumus workbook yang baru dipasang | +20% | **−20%** |
| `frontend/src/lib/analysis/backtest.ts` | +20% | **−15%** |

Parameter `backtest_thresholds_undervalued` di registry sekarang berisi `{upside 0.2, downside
-0.15}` — versi frontend, bukan versi workbook terbaru.

**KEPUTUSAN (pengguna): pakai rumus workbook.** Undervalued = `×1.2` / `×0.8`; overvalued/mixed =
`×1.15` / `×0.9`. Angka frontend disimpan sebagai parameter **terpisah**
(`backtest_thresholds_undervalued_legacy_frontend`) hanya sebagai jejak, tidak dipakai.

### D4. Cabang verdict yang berbeda — **SUDAH DIPUTUSKAN**

Aku sudah bandingkan rumus workbook yang disetujui (5.4.1) dengan
`calculateSimulatedVerdict` di `frontend/src/lib/analysis/backtest.ts` baris per baris. Hasilnya
**tiga** cabang berbeda, bukan dua:

| Keadaan | Workbook (disetujui) | Frontend sekarang | |
|---|---|---|---|
| UNDERVALUED, tidak sentuh apa pun | `FLAT` | `FLAT` | sama |
| UNDERVALUED, hanya upside | `WIN` | `WIN` | sama |
| UNDERVALUED, hanya downside | `RISK` | `RECOVERED` | **beda** |
| UNDERVALUED, keduanya | `UpDate < DownDate ? WIN : RECOVERED` | idem | sama |
| OVERVALUED, tidak sentuh apa pun | `OBSERVE` | `OBSERVE` | sama |
| OVERVALUED, hanya upside | `REPRICE` | `OBSERVE` | **beda** |
| OVERVALUED, hanya downside | `CONFIRMED` | `CONFIRMED` | sama |
| OVERVALUED, keduanya | `DownDate < UpDate ? CONFIRMED : REPRICE` | selalu `CONFIRMED` | **beda** |

Yang ketiga mudah terlewat: frontend mengembalikan `CONFIRMED` tanpa melihat mana yang lebih
dulu, sedangkan workbook memakai urutan kejadian (`DownDate < UpDate` → `CONFIRMED`, selain itu
`REPRICE`).

**KEPUTUSAN (pengguna): rumus workbook jadi satu-satunya sumber kebenaran.** Dihitung di backend
dan disimpan. Frontend berhenti menghitung verdict dan hanya menampilkan yang tersimpan. Ini
menghapus seluruh kelas drift antara dua implementasi rumus yang sama.

**Perubahan perilaku yang harus terlihat di UI:** verdict `RISK` akan **muncul** (sebelumnya
kasus itu dilabeli `RECOVERED`, jadi jumlah `RECOVERED` akan turun dan `RISK` naik dari nol),
dan sebagian kasus overvalued berubah dari `OBSERVE`/`CONFIRMED` menjadi `REPRICE`. Jumlah `WIN`
tidak berubah dari sisi aturan ini. Semua ini tanpa ada data yang berubah — konsekuensi yang
disengaja, bukan regresi.

### D5. Denominator konsensus

Workbook: `Under|Valid` dengan `Valid = 5 − (N/A (Skip) + error)`, dan **IV negatif tetap
dihitung valid** (DDM −100228 pada 2022Q1 adalah metode valid yang OVERVALUED). Frontend
sekarang memakai `values.length` (selalu 5) dan memperlakukan `null` sebagai tidak valid.

**Rekomendasi:** pakai aturan workbook. Parameter `iv_consensus_denominator_mode` sudah ada di
registry dan saat ini `RESOLUTION_UNRESOLVED`; backtest membacanya lewat `registry_parameter`
dan mencatat statusnya di `flags`, tanpa mengklaim sudah resolved.

### D6. MoS Main vs MoS Weight

`MoS = (IV − Price)/IV` (denominator IV, bukan harga).

- `MoS Main` = MoS metode **main**. `SUMMARY!B69`: stalwart / fast grower → weighted IV, selain
  itu → Peter Lynch.
- `MoS Weight` = MoS metode type & sector weighted.

**Verdict MoS** memakai ambang 30% (`mos_entry_threshold_frontend`, juga unresolved). Ambang
35% (`mos_entry_threshold_workbook`) dipakai untuk status entry di SUMMARY — dua angka berbeda
untuk dua keperluan berbeda, jangan disatukan.

### D7. Tipe saham per kasus — **SUDAH DIPUTUSKAN DAN DIKERJAKAN**

Workbook menghitung ulang `MetricsClassification` tiap kasus, jadi tipe saham kasus bisa berbeda
dari tipe hari ini. Versi pertama backtest hanya menyimpan classifier sebagai snapshot terbaru
dan menyalinnya ke semua kasus, dengan flag `STOCK_TYPE_LATEST_SNAPSHOT` sebagai penanda
kejujuran. Itu **salah secara material**, bukan kosmetik: `valuation_engine.py` memetakan tipe ke
bobot referensi (TURN AROUND → LIQUIDATION_VALUE, CYCLICAL → CYCLICAL_PBV, dst.), sehingga tipe
yang salah menggeser Peter Lynch IV, lalu konsensus, MoS Main, `mos_method_code`, verdict, dan
kedua Win Rate di UI.

**KEPUTUSAN: tipe dihitung ulang pada tanggal kasus, dengan resep point-in-time yang sama dengan
valuasi kasus itu.** `run_backtest.stock_type_for_case` menjalankan ulang classifier
(`classify_metrics_classification`) di atas potongan kasus:

1. `financial_periods` dipotong pada `period_end <= analysis_date`;
2. `prices_daily` dipotong pada `trading_date <= analysis_date`;
3. `years_available` dari kuartal dasar (D2), sama seperti valuasi;
4. baris Class-B (pertumbuhan/kualitas) **dihitung ulang** dengan
   `calculate_annual_growth_outputs` untuk jendela kasus. Ini wajib:
   `calc_annual_growth_quality` hanya punya satu run per instrumen (dipatok ke snapshot hari ini),
   jadi `GROWTH_REVENUE_CAGR_LONG`, `GROWTH_REVENUE_COV`, `QUALITY_REVENUE_MOMENTUM`, dan
   `GROWTH_EPS_CAGR_LONG` tidak boleh dibaca dari run tersimpan;
5. skenario proyeksi memakai skenario kasus sendiri, dan
   `scenario['projected_shares_outstanding']` **wajib** diteruskan ke `derive_classifier_inputs`.
   Bila dibiarkan `None`, `projected_pbv` menjadi `None` dan ASSET PLAY salah menyala;
6. hasilnya dinormalkan lewat `normalise_classifier_type(raw, asset_play_matched)`.

Karena tipe kini per kasus, bobot/ambang tipe juga harus per kasus: `fetch_reference_inputs`
membaca seluruh baris `valuation_type_weights` / `valuation_type_thresholds` sekali, lalu
`_reference_for_type` memilih baris tipe kasus itu. Potongan point-in-time dibentuk **sekali** di
`_case_cut` dan dipakai bersama oleh classifier dan valuasi, sehingga tipe dan valuasi tidak
mungkin memakai kuartal dasar atau `years_available` yang berbeda.

Flag `STOCK_TYPE_LATEST_SNAPSHOT` **dihapus**: tidak ada lagi provenance yang perlu ditandai.
Baris lama tetap memuat flag itu di `flags`-nya sendiri, dan versi metodologi lamanya tetap hidup
supaya bisa direproduksi.

**Bukti numerik (diverifikasi read-only sebelum implementasi).** Ground truth: sheet
`Backtest_Historical (New)` kolom `Jenis Saham`, 15 ticker, 277 kasus. Hasil perbandingan:

| | kasus | cocok dengan workbook |
|---|---|---|
| DB dengan snapshot terbaru (sebelum D7) | 277 | 180 (65,0%) |
| DB dengan tipe per kasus (sesudah D7) | 277 | 201 (72,6%) |
| classifier dijalankan per kasus (batas atas) | 277 | 215 (77,6%) |

Perbaikan +21 kasus. Sisa 62 mismatch adalah **batas metodologi classifier, bukan bug
implementasi**: 19 kasus GOLD (sektor `Infrastructures` tidak ada di `classifier_cyclical_sectors`,
workbook bilang CYCLICAL), 11 WIFI (CYCLICAL vs FAST GROWER), 7 INDF (ASSET PLAY vs STALWART), dan
`BASE_QUARTER_FACT_MISSING` pada 6 kasus. Keputusan atas tiga ticker itu (tambah sektor / override
manual) adalah keputusan metodologi owner, bukan perubahan kode backtest.

**Konsekuensi yang terlihat di UI.** Tipe bergerak untuk GOLD, WIFI, GEMA, INDF, JSMR, SIDO, INDS,
UNTR, INKP. GOLD dan JSMR adalah kasus khusus: classifier-nya `UNCLASSIFIED` tanpa aturan yang
cocok, sehingga `normalise_classifier_type` gagal dan valuasi kasus itu `UNAVAILABLE` (metrik
harga tetap tersimpan). GOLD 2025-Q2/2026-Q1 `UNCLASSIFIED` dengan `asset_play=1` (score-10
fall-through) sehingga dipetakan ke `ASSET PLAY` - perubahan tipe, bukan kegagalan.

#### Cache tipe per kasus

Classifier per kasus dijalankan untuk setiap kasus pada setiap run. Untuk menghindari menghitung
ulang kasus yang inputnya tidak berubah, `run_backtest._stock_type_cache` membaca hasil run
SUCCEEDED terbaru dan memakainya ulang **hanya bila sidik inputnya sama**.

- **Kunci cache:** `(instrument_id, case_quarter)`.
- **Sidik:** `_stock_type_fingerprint` = SHA-256 dari versi skema sidik, identitas kasus,
  `analysis_date`, `years_available`, kuartal dasar, **parameter classifier** (ambang, tangga skor,
  override Energy, daftar sektor), daftar periode terpotong, **seluruh fakta terpotong termasuk
  `revision_key` dan nilainya**, harga terpotong, dan dividen. Urutan baris dinormalkan, sehingga
  urutan respons PostgREST tidak mengubah sidik.
- **Disimpan** di `calc_backtest_cases.details.stock_type_fingerprint` (dan
  `details.stock_type_source` = `RECOMPUTED` / `CACHE` / `GIVEN`), jadi bisa diaudit per baris.

Bila input berubah, sidiknya berubah dan tipe dihitung ulang:

| Perubahan | Efek |
|---|---|
| Revisi laporan (nilai fakta atau `revision_key` berubah pada periode yang sama) | sidik berubah -> dihitung ulang |
| Ambang/tangga skor/daftar sektor classifier di registry berubah | sidik berubah -> dihitung ulang |
| Harga atau dividen baru yang jatuh pada/sebelum tanggal kasus | sidik berubah -> dihitung ulang |
| Kuartal dasar atau `years_available` bergeser | sidik berubah -> dihitung ulang |
| Kasus baru (kuartal belum ada di run sebelumnya) | tidak ada entri cache -> selalu dihitung |
| Run lama tanpa `details.stock_type_fingerprint` (versi sebelum D7) | cache kosong -> seluruh tipe dihitung ulang |

Sidiknya **selalu** dihitung, jadi cache hanya menghemat perhitungan, bukan melewatkan verifikasi.
`input_snapshot` run juga memuat `stock_type_rule`, `classifier_parameters`, dan
`stock_type_fingerprint_version`, sehingga perubahan aturan tipe menghasilkan kunci idempotensi
baru alih-alih memakai ulang run lama.

---

## 3. Arsitektur yang diusulkan

### 3.1 Prinsip

1. **Aturan hidup di satu tempat.** Semua rumus Tahap B ada di satu modul Python
   (`backtest_engine.py`) dan disimpan ke database. Frontend tidak menghitung ulang.
2. **Tidak ada angka yang diciptakan.** Metrik yang tidak bisa dihitung disimpan sebagai baris
   dengan `calculation_status = 'UNAVAILABLE'` + `flags`, bukan dihilangkan dan bukan diisi nol.
3. **Mengikuti pola modul yang sudah ada.** Bentuk `run` + `result` + `flags` + `calculation_run_id`
   sama seperti `calc_valuation_methods` dan `calc_metrics_classification`.
4. **Point-in-time dipisah dari akurasi.** Yang belum PIT diberi flag, bukan dilarang.

### 3.2 Modul baru (mengikuti konvensi yang sudah ada)

| File | Peran | Analogi yang sudah ada |
|---|---|---|
| `supabase/backtest_engine.py` | Rumus murni: window harga, verdict, konsensus, MoS. Tanpa I/O. | `valuation_engine.py` |
| `supabase/run_backtest.py` | Orkestrator: baca DB → engine → tulis `calc_backtest_cases` + `calc_backtest_runs`. | `calculate_valuation.py` |
| `supabase/migrations/0025_backtest_results.sql` | Dua tabel hasil + grant + RLS. | `0024_metrics_classification_results.sql` |
| `supabase/calculation_methodology_registry.py` | Satu definisi metodologi `BACKTEST_HISTORICAL`. | entri `VALUATION_CURRENT` |
| `supabase/calculation_parameter_catalogue.py` | Parameter backtest yang sudah ada + koreksi D3. | `PARAMETERS_BACKTEST` |
| `tests/test_backtest_engine.py` | Uji rumus murni, termasuk 18 kasus AUTO sebagai fixture. | `tests/test_valuation_engine.py` |
| `run_pipeline.py` | Step `backtest` setelah `valuation`. | step `valuation` |

`backtest_engine.py` sengaja **tanpa** I/O dan tanpa `SupabaseRest`, supaya bisa diuji penuh
secara offline dan supaya tidak ada jalan untuk membaca data di luar cutoff kasus.

### 3.3 Alur data

```
prices_daily ─┐
financial_periods ─┼─> run_backtest.py ──> backtest_engine.py ──> calc_backtest_cases
financial_facts ─┤        (cutoff per kasus)        (rumus)              │
projection_scenarios ─┘                                                 │
calc_metrics_classification ────────────────────────────────────────────┘
                                                                        │
                                                              RPC baru / existing
                                                                        │
                                                              stock-detail-adapter
                                                                        │
                                                          backtest-tab-content.tsx
```

Langkah `run_backtest.py` per kasus:

1. Susun daftar kasus dari `financial_periods` + aturan `Helper!C2#` (Tahap A).
2. Untuk setiap kasus, potong data pada `analysis_date` kasus: hanya periode dan fakta dengan
   `period_end <= analysis_date`, hanya harga dengan `trading_date <= EDATE(analysis_date, 12)`.
3. Bentuk skenario point-in-time untuk kasus itu (reuse `derive_projection_scenario.build_scenario`).
4. Panggil `calculate_valuation_snapshot` (sudah ada) dengan `valuation_date = analysis_date`.
5. Hitung metrik Tahap B dengan `backtest_engine.py`.
6. Tulis satu baris hasil + flag; verifikasi jumlah baris seperti loader lain.

### 3.4 Kenapa me-reuse `calculate_valuation_snapshot` dan bukan menyalinnya

Menyalin lima metode valuasi ke dalam backtest akan membuat dua implementasi rumus yang sama —
persis penyebab drift yang ditemukan di D3/D4. Fungsi itu sudah menerima semua input sebagai
argumen (tanpa I/O), jadi satu-satunya yang perlu ditambahkan adalah pembentukan skenario
point-in-time per kasus.

---

## 4. Skema penyimpanan (bertahap, additive)

Dua tabel, mengikuti gaya `0024`: `calculation_run_id` + `methodology_version_id` NOT NULL,
`calculation_status` dengan check constraint, `flags jsonb`, dan RLS aktif tanpa grant ke
`anon`/`authenticated`.

### 4.1 `calc_backtest_cases` — satu baris per kasus

```sql
create table public.calc_backtest_cases (
  id uuid primary key default gen_random_uuid(),
  calculation_run_id uuid not null references public.calculation_runs(id),
  methodology_version_id uuid not null references public.methodology_versions(id),
  instrument_id uuid not null references public.instruments(id),
  as_of_financial_period_id uuid not null references public.financial_periods(id),

  -- Identitas kasus
  case_quarter text not null,          -- '2022-Q1'
  base_year integer not null,          -- 2021  (Helper!C2#)
  analysis_date date not null,         -- period_end (lihat D1)
  analysis_price numeric,
  analysis_price_source text not null check (analysis_price_source in ('CLOSE_PIT','MANUAL')),
  stock_type text,                     -- tipe pada tanggal kasus (lihat D7); NULL bila classifier tidak punya aturan
  sector_name text,

  -- Konteks valuasi kasus
  years_available integer,
  years_compare integer,
  mos_main numeric,
  mos_peter numeric,
  mos_weight numeric,
  mos_method_code text,                -- metode main yang dipakai
  consensus text,                      -- '2|5' atau 'N/A'
  consensus_undervalued integer,
  consensus_valid integer,
  verdict text not null check (verdict in
    ('WIN','RISK','RECOVERED','FLAT','CONFIRMED','REPRICE','OBSERVE')),
  verdict_mos text not null check (verdict_mos in
    ('WIN','RISK','RECOVERED','FLAT','CONFIRMED','REPRICE','OBSERVE')),

  -- Metrik Tahap B (semua nullable: NULL berarti tidak bisa dihitung)
  high_3m numeric, low_3m numeric, high_6m numeric, low_6m numeric,
  high_9m numeric, low_9m numeric, high_12m numeric, low_12m numeric,
  peak_price numeric, trough_price numeric, peak_month integer,
  return_peak numeric, return_down numeric,

  calculation_status text not null check
    (calculation_status in ('VALID','APPROXIMATED','NOT_CALCULABLE','UNAVAILABLE')),
  flags jsonb not null default '[]'::jsonb,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (calculation_run_id, instrument_id, as_of_financial_period_id)
);
```

Catatan bentuk:

- **Harga disimpan sebagai nominal, bukan string `"▲ 1285. || ▼ 1080."`.** Format panah adalah
  presentasi; UI yang merangkainya dari `high_3m`/`low_3m` + `analysis_price`.
- **`verdict` dan `verdict_mos` NOT NULL** karena rumusnya selalu menghasilkan salah satu dari
  tujuh nilai; kalau tidak bisa dihitung, itu bukan verdict melainkan `calculation_status`.
- `base_year` disimpan agar aturan `Helper!C2#` bisa diaudit ulang tanpa membuka workbook.

### 4.2 `calc_backtest_methods` — lima baris per kasus

```sql
create table public.calc_backtest_methods (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null references public.calc_backtest_cases(id) on delete cascade,
  method_code text not null,           -- PETER_LYNCH, TYPE_SECTOR_WEIGHTED, ...
  method_name text not null,
  intrinsic_value numeric,
  current_price numeric,
  gap_ratio numeric,
  mos numeric,                         -- (IV - price)/IV  <-- denominator IV
  verdict text not null check (verdict in ('UNDERVALUED','OVERVALUED','NOT_APPLICABLE')),
  calculation_status text not null,
  flags jsonb not null default '[]'::jsonb,
  details jsonb not null default '{}'::jsonb,
  unique (case_id, method_code)
);
```

Ini yang mengisi kolom `IV Peter Lynch` … `IV Discounted Earnings` dan `IV` (konsensus) pada
tabel di UI, dan menyimpan lima IV yang membuat `2|5` bisa diverifikasi.

### 4.3 Rencana bertahap

| Fase | Isi | Yang dibutuhkan |
|---|---|---|
| 1 | Daftar kasus + metrik harga (`Ret nM`, peak/trough, `Bln Peak`, `Ret Peak/Down`) | `prices_daily`, `financial_periods` |
| 2 | Snapshot valuasi per kasus (`calc_backtest_methods`) + konsensus + MoS | skenario PIT per kasus |
| 3 | Verdict + `verdict_mos` | hasil fase 2 + parameter D3/D4 |
| 4 | RPC + adapter + UI mengganti data sampel | fase 3 |

**Fase 1 sengaja bisa berdiri sendiri.** Ia hanya butuh harga dan tanggal, jadi hasilnya bisa
langsung dibandingkan dengan 18 baris workbook untuk memvalidasi aturan window harga sebelum
menyentuh mesin valuasi. Kalau fase 1 tidak persis, fase 2 tidak akan pernah persis.

**Status implementasi.** Fase 1-4 sudah dikerjakan. Fase 4 memakai RPC
`get_stock_backtest` (`supabase/migrations/0026_stock_research_backtest_rpc.sql`) dan
adapter `frontend/src/lib/backtest-adapter.ts`; catatan operasionalnya ada di
`docs/SUPABASE_MANUAL_RUNBOOK.md`.

Dua penyesuaian terhadap rencana di atas, keduanya karena data yang tersimpan
tidak cukup untuk menghitung ulang di browser:

- **Kolom context diturunkan di RPC, bukan disimpan.** `Revenue YoY`,
  `Net Income YoY`, dan momentum EPS/Revenue dihitung point-in-time di dalam RPC
  dari `financial_facts`/`calc_annual_growth_quality`. `ROE Trend`, `Yield (%)`,
  dan `OCF / NI Ratio` dikembalikan `null` karena belum ada aturannya di repo ini.
- **UI membaca kolom tersimpan, bukan menghitung ulang dari `pricePath`.**
  Tabel hanya menyimpan *extremes* per window, dan extremes tidak bisa
  merekonstruksi window per-horizon (peak di bulan ke-6 bisa jatuh di luar window
  6M pada aritmetika `DATEDIF`). Menghitung ulang menghasilkan 18 sel salah dari
  18 kasus AUTO. `trough_month` ditambahkan ke tabel untuk alasan yang sama.

---

## 5. Registry, penyajian, dan batas kejujuran

### 5.1 Registry (tanpa memaksa status resolved)

`calculation_parameter_catalogue.py` sudah punya `PARAMETERS_BACKTEST` dengan
`backtest_horizons_months`, `backtest_observation_months`, `backtest_thresholds_undervalued`,
`backtest_thresholds_overvalued_or_mixed`, dan `backtest_generation_rule` (unresolved).

Perubahan yang diusulkan:

1. Tambah `backtest_thresholds_undervalued_workbook` = `{upside 0.2, downside -0.2}` dan
   `backtest_thresholds_overvalued_or_mixed_workbook` = `{upside 0.15, downside -0.1}`, keduanya
   `RESOLUTION_RESOLVED` dengan sumber "rumus kolom `Backtest_Result` (Verdict by Method)".
   Parameter lama `backtest_thresholds_undervalued` (versi frontend, downside −0.15) **tidak
   diubah** dan hanya jadi jejak audit.
2. Tambah `backtest_verdict_rule` dengan `RESOLUTION_RESOLVED`, sumber rumus 7 cabang (5.4.1),
   supaya verdict bisa direproduksi dari registry tanpa membuka workbook.
3. **Jangan** ubah `backtest_generation_rule` menjadi resolved. Sekarang isinya benar: sheet
   `Backtest_Result` memang 0 formula. Yang berubah adalah rumus **kolom**-nya kini tersedia,
   jadi tambahkan parameter baru `backtest_case_selection_rule` dan
   `backtest_price_window_rule` dengan `RESOLUTION_RESOLVED` dan sumbernya makro + rumus kolom.
4. `test_phase_4_1_registry_and_pit.py:189` mengunci `backtest_generation_rule` sebagai
   unresolved. Karena itu parameter baru ditambahkan, bukan yang lama diubah, supaya 199 test
   tetap hijau tanpa melemahkan kontraknya.
5. Metodologi `BACKTEST_HISTORICAL` didaftarkan sebagai **supplemental seed** (pola
   `supplemental_methodology_seeds()`), bukan menambah `methodology_seeds()`, supaya kontrak
   "tepat 9 seed row" di `Testing/test_calculation_v1.py:227` tidak berubah.

### 5.2 Penyajian di UI

`backtest-tab-content.tsx` sekarang sudah menerima `BacktestCase` dengan bentuk yang hampir
sama. Yang berubah hanya sumber datanya:

- `pickDemoBacktestData()` di `stock-detail-adapter.ts` diganti pembacaan hasil tersimpan;
  `isDemoData: true` hilang dengan sendirinya, sehingga badge "Demo Data" hilang.
- `analysisPrice` tetap bisa diedit manual (fitur yang sudah ada). Edit itu disimpan sebagai
  `analysis_price_source = 'MANUAL'` dan **tidak** menimpa `analysis_price_source = 'CLOSE_PIT'`
  hasil hitungan, supaya angka asli tetap bisa dipulihkan.
- Kolom `Ret 3M`…`Price 12M` dirakit dari `high_nm`/`low_nm`, jadi tidak ada string
  terformat yang perlu di-parse.
- `aggregateBacktestOverview` dan `buildHistoricalBacktestReadout` tetap dipakai untuk ringkasan;
  keduanya bekerja di atas `BacktestCase[]` dan tidak peduli asal datanya.

### 5.3 Batas kejujuran yang harus terlihat

Backtest ini **bukan** point-in-time penuh. Dua hal yang harus tampil sebagai peringatan,
bukan disembunyikan:

1. `available_date` NULL → tanggal analisis memakai akhir periode, bukan tanggal publikasi
   (`POINT_IN_TIME_UNAVAILABLE_DATE`).
2. `years_available` dipotong ke riwayat yang tersedia (`YEARS_AVAILABLE_TRUNCATED`).

Tipe saham **tidak lagi** termasuk daftar ini: sejak D7 ditutup, tipe dihitung ulang pada tanggal
kasus, jadi flag `STOCK_TYPE_LATEST_SNAPSHOT` sudah dihapus. Baris lama tetap memuat flag itu di
`flags`-nya sendiri, jadi riwayatnya tidak hilang.

Satu batas tambahan yang tidak lagi berupa flag, melainkan hasil: bila classifier tidak menemukan
aturan yang cocok pada tanggal kasus (`UNCLASSIFIED` tanpa `asset_play`), `stock_type` NULL dan
valuasinya `UNAVAILABLE` + `STOCK_TYPE_UNRESOLVED` di `details.methods[].details.reason`. Metrik
harga tetap tersimpan. Ini yang terjadi pada GOLD dan JSMR.

Karena itu setiap baris menyimpan `flags jsonb`, dan UI menampilkan badge "bukan point-in-time"
selama salah satu flag di atas ada. Ini pola yang sama dengan `POINT_IN_TIME_UNVERIFIED` yang
sudah dipakai `valuation_engine.py`.

Flag lain yang perlu ada: `WINDOW_PARTIAL` (tidak ada harga setelah tanggal tertentu, mis.
kasus 2026Q2 yang 12M-nya belum lengkap), `METHOD_UNAVAILABLE` (metode tidak bisa dihitung pada
kasus itu), dan `CONSENSUS_BELOW_THREE_METHODS` (menghasilkan `"N/A"`).

### 5.4 Kriteria selesai

Fase 1 dianggap benar bila, untuk AUTO, 18 baris hasilnya sama dengan kolom `Tgl_Analisis`,
`Harga Analisis`, `Ret 3M`…`Ret 12M`, `Price 3M`…`Price 12M`, `Ret Peak`, `Ret Down`,
`Harga trough`, `Harga Peak`, dan `Bln Peak` pada workbook. Enam dari dua belas kolom itu sudah
dicocokkan manual untuk 2022Q1 (bagian 1) dan cocok persis.

Fase 3 dianggap benar bila `Verdict by Method` dan `Verdict MoS` sama untuk 18 kasus, dengan
`MoS Main` sama pada presisi 1e-9.

### 5.4.1 Rumus verbatim yang disetujui sebagai sumber kebenaran

Pengguna sudah memasang rumus `Verdict by Method` di workbook dan menyatakannya sebagai formula
yang harus dipakai. Rumus itu **diadopsi apa adanya** dan menjadi satu-satunya sumber kebenaran
(menutup D3 dan D4). Disalin utuh di sini supaya implementasi tidak perlu membuka workbook:

```excel
=LET(
    K,[@Konsensus],
    Tkr,[@Ticker],
    BasePrice, IF([@[Harga Manual]]<>"", [@[Harga Manual]], [@[Harga Analisis]]),
    StartDate,[@[Tgl_Analisis]],
    EndDate,EDATE(StartDate,12),

    UpTarget,   IF(K="UNDERVALUED", BasePrice*1.2,
                IF(OR(K="OVERVALUED",K="MIXED"), BasePrice*1.15, "")),
    DownTarget, IF(K="UNDERVALUED", BasePrice*0.8,
                IF(OR(K="OVERVALUED",K="MIXED"), BasePrice*0.9, "")),

    UpDate, IFERROR(MIN(FILTER(tblPriceHistory_DB[Date],
        (tblPriceHistory_DB[Ticker]=Tkr)*(tblPriceHistory_DB[Date]>StartDate)*
        (tblPriceHistory_DB[Date]<=EndDate)*
        (IF(tblPriceHistory_DB[High]=0,tblPriceHistory_DB[Close],tblPriceHistory_DB[High])>=UpTarget))), ""),

    DownDate, IFERROR(MIN(FILTER(tblPriceHistory_DB[Date],
        (tblPriceHistory_DB[Ticker]=Tkr)*(tblPriceHistory_DB[Date]>StartDate)*
        (tblPriceHistory_DB[Date]<=EndDate)*
        (IF(tblPriceHistory_DB[Low]=0,tblPriceHistory_DB[Close],tblPriceHistory_DB[Low])<=DownTarget))), ""),

    IF(K="UNDERVALUED",
        IF(AND(UpDate="",DownDate=""), "FLAT",
        IF(AND(UpDate<>"",DownDate=""), "WIN",
        IF(AND(UpDate="",DownDate<>""), "RISK",
        IF(UpDate<DownDate, "WIN",
        IF(DownDate<UpDate, "RECOVERED", "RECOVERED"))))),
    IF(OR(K="OVERVALUED",K="MIXED"),
        IF(AND(UpDate="",DownDate=""), "OBSERVE",
        IF(AND(UpDate<>"",DownDate=""), "REPRICE",
        IF(AND(UpDate="",DownDate<>""), "CONFIRMED",
        IF(DownDate<UpDate, "CONFIRMED",
        IF(UpDate<DownDate, "REPRICE", "OBSERVE"))))),
    "FLAT"))
```

Empat sifat yang harus dipatuhi implementasi Python:

1. **Rantai perbandingan ketat.** Hanya `>` untuk `UpDate`/`DownDate`; hari yang sama persis
   (`UpDate = DownDate`) jatuh ke `RECOVERED` (undervalued) atau `OBSERVE` (overvalued).
2. **`K` yang tidak dikenal → `FLAT`.** Bila `K` bukan UNDERVALUED/OVERVALUED/MIXED, hasilnya
   `FLAT`, bukan error.
3. **Window verdict = 12 bulan penuh**, sedangkan window `Ret 3M` = 3 bulan. Keduanya memakai
   batas awal yang berbeda: verdict `> StartDate`, tapi `Ret 3M` `>= StartDate`. **Jangan
   disatukan.**
4. **`High`/`Low` nol → `Close`** di dalam filter, bukan sebelum filter.

### 5.5 Yang sengaja TIDAK dikerjakan

- **Market mood** (`market_adj_price`, `quality_adj_target`, `mos_final`) — tidak ada sumber
  data; tetap di luar cakupan seperti sekarang.
- **Backfill `available_date`** — pekerjaan data tersendiri (D1b), bukan bagian backtest.
- **Mengubah `calc_valuation_*`** — backtest punya tabelnya sendiri (4.3).
- **Mengubah aturan classifier** — D7 menjalankan aturan yang sudah ada apa adanya. Tiga
  pertanyaan metodologi tetap terbuka dan **tidak** dijawab di sini: (a) GOLD sektor
  `Infrastructures` tidak ada di `classifier_cyclical_sectors` padahal workbook bilang CYCLICAL;
  (b) WIFI bolak-balik CYCLICAL ↔ FAST GROWER; (c) INDF `UNCLASSIFIED` sehingga valuasinya
  kosong. Menjawabnya berarti menambah sektor atau override manual - keputusan owner, bukan
  perubahan kode backtest.

---

## 6. Ringkasan keputusan

| # | Keputusan | Status |
|---|---|---|
| D1 | Tanggal analisis | `period_end` + flag sekarang; `available_date` nanti |
| D2 | `years_available` | `min(7, riwayat tersedia)` + flag |
| D3 | Threshold undervalued | **DIPUTUSKAN: rumus workbook (×1.2 / ×0.8, ×1.15 / ×0.9)** |
| D4 | Cabang verdict | **DIPUTUSKAN: rumus workbook, 3 dari 8 cabang berbeda dari frontend** |
| D5 | Denominator konsensus | ikuti workbook (`5 − N/A − error`) |
| D6 | MoS | `(IV−price)/IV`; main = B69; verdict 30%, entry 35% |
| D7 | Tipe saham kasus | **DIPUTUSKAN: classifier dihitung ulang per kasus** (bukan snapshot + flag) |

Urutan kerja: **fase 1 → uji terhadap 18 baris workbook → fase 2 → fase 3 → RPC/UI**. Fase 1
tidak menulis ke tabel valuasi mana pun, jadi aman dijalankan lebih dulu.

Jumlah kasus yang diharapkan per ticker (sudah dihitung dari data yang ada, berguna sebagai
assertion uji):

| Ticker | Base year valid | Kasus |
|---|---|---|
| Sebagian besar ticker | 2021–2025 | 18 |
| DSSA | 2021–2025 | 17 (Q3 2020 tidak ada) |
| GOLD | 2020–2025 | 22 |
| WIFI | 2020–2025 | 22 |

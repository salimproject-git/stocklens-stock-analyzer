# Aturan Data StockLens — Keputusan Konsep Raw

Dokumen ini mencatat keputusan konsep tentang data raw sebelum implementasi. Fokusnya adalah
menyimpan dan memahami data sumber Sectors; tidak berusaha menyelesaikan semua formula Excel
atau anomali satu per satu. Dokumen ini **bukan** spesifikasi tabel atau migration final. Belum
ada kode atau data Supabase yang diubah hanya dengan menyunting dokumen ini.

## 1. Aturan yang sudah terlihat di project

| Topik | Yang sekarang dilakukan/disimpan | Status |
|---|---|---|
| Nilai keuangan | `financial_facts.value_numeric` memakai Rupiah penuh (`IDR`). Tampilan Excel mengubahnya menjadi `M Rp`. | Sudah terverifikasi |
| Saham | `OUTSTANDING_SHARES` memakai hitungan saham penuh, satuan `SHARES`. Konversi ke juta saham hanya untuk tampilan. | Sudah terverifikasi |
| Harga | `prices_daily` memakai Rupiah per saham (`IDR`) dan menyimpan tanggal perdagangan. | Sudah terverifikasi |
| Volume | `prices_daily.volume` adalah jumlah saham yang diperdagangkan, bukan rata-rata atau nilai Rupiah. | Sudah terverifikasi |
| Nilai kosong | Loader mempertahankan nilai sumber yang kosong sebagai `NULL` dan memberi status `MISSING`; `NULL` tidak sama dengan angka nol. | Sudah terverifikasi |
| COGS/HPP | Pada raw JSON lokal yang diaudit, semua nilai `cost_of_revenue` yang tersedia positif; nilai kosong tetap kosong. Loader canonical mempertahankan tanda raw. Converter CSV mengubah angka menjadi negatif hanya untuk bentuk Excel. | Sudah diaudit pada 16 file annual dan 412 file quarterly lokal |
| Tanggal laporan keuangan | Ada 33 periode AUTO, tetapi `report_date` dan `available_date` masih kosong pada semuanya. | Sudah terverifikasi |
| Harga point-in-time | Harga untuk tanggal acuan adalah `Close` terakhir dengan tanggal perdagangan tidak lebih besar dari tanggal acuan. Harga terbaru tidak boleh menggantikan harga tanggal historis. | Sudah diterapkan dan diuji |
| Rata-rata volume 3 bulan | Fungsi yang ada memakai rata-rata `volume` di antara `EDATE(tanggal_acuan, -3)` dan tanggal acuan, kedua ujung termasuk. Hari tanpa baris tidak diisi atau ditebak. | Sudah diterapkan dan diuji |

## 2. Aturan yang disetujui

### 2.1 Nilai uang dan penyajian

**Aturan disetujui (26 September 2026):** simpan nilai uang dalam Rupiah penuh di database. Ubah ke `M Rp` hanya ketika menampilkan data, dengan pembagian `1.000.000.000`.

Contoh: `3.842.000.000.000 IDR` dapat ditampilkan sebagai `3.842 M Rp`.
Angka tampilan yang sudah dibagi jangan diimpor kembali seolah-olah masih Rupiah penuh.

**Status:** DISETUJUI. Ini aturan penyimpanan dan tampilan; jangan mengubah angka sumber menjadi satuan tampilan saat ingest.

### 2.2 Nilai kosong dan nol

**Aturan disetujui (26 September 2026):** pertahankan nilai yang tidak tersedia sebagai `NULL`. Gunakan angka `0` hanya jika sumber memang menyatakan nilainya nol.

Contoh: tanda `-` pada file Excel belum tentu berarti nol; perlu diketahui dulu apakah itu berarti tidak ada data, tidak berlaku, atau benar-benar nol.

**Status:** DISETUJUI. Tanda kosong atau `-` perlu dimaknai sesuai sumber; jangan otomatis mengubahnya menjadi nol.

### 2.3 Tanda COGS/HPP

Audit raw lokal lintas ticker menemukan **96 nilai annual dan 409 nilai quarterly positif**, **18 nilai annual dan 3 nilai quarterly kosong**, serta **tidak menemukan nilai negatif atau nol**. Nilai Supabase AUTO yang diperiksa juga positif. Loader annual dan quarterly mengambil nilai sumber langsung tanpa membalik tanda. Converter CSV memakai konversi tersendiri untuk mencocokkan tampilan Excel. Sampel Stockbit yang kamu kirim menampilkan COGS negatif, tetapi nominal absolutnya sama dengan nilai API.

Contoh Q2 2026:

| Tempat | Revenue | COGS / Cost of Revenue | Gross Profit |
|---|---:|---:|---:|
| Raw JSON Sectors | `5.595.855.000.000` | `+4.749.754.000.000` | `846.101.000.000` |
| Stockbit sample | `5.595.855.000.000` | `-4.749.754.000.000` | `846.101.000.000` |

Gross profit mengonfirmasi hubungan angkanya: `Revenue - COGS positif = Gross Profit`, atau jika COGS direpresentasikan negatif: `Revenue + COGS negatif = Gross Profit`. Tanda negatif pada tampilan Stockbit menyatakan bahwa COGS adalah beban yang mengurangi revenue; **bukan** berarti operasi perusahaan mengalami kerugian. Net income/laba rugi adalah metrik terpisah.

**Keputusan disetujui (26 September 2026):** simpan COGS/HPP *as-is* sesuai tanda pada raw JSON Sectors. Pada data yang diaudit nilainya positif; jangan mengubahnya dengan `abs()` atau memaksanya selalu positif saat ingest. Jika sumber suatu saat mengirim tanda berbeda, simpan tanda dari sumber dan tinjau kasus tersebut; jangan menormalkan diam-diam. Jika tampilan produk perlu mengikuti Stockbit/Excel, perubahan tanda dilakukan hanya pada lapisan tampilan.

**Status:** DISETUJUI untuk mengikuti tanda raw Sectors. Audit lokal mencakup ticker-ticker yang memiliki file raw saat ini; cek ulang jika cakupan sumber berubah atau API mengirim nilai bertanda negatif.

Pemeriksaan silang pada data audit menemukan **lima baris** dengan `gross_profit` raw yang tidak sama dengan `revenue - cost_of_revenue` (satu annual dan empat quarterly). Ini tidak mengubah aturan tanda dan bukan alasan untuk menimpa salah satu field. Simpan fakta sesuai sumber; teliti perbedaan metrik/periode secara terpisah sebelum memakai keduanya bersama dalam formula.

Audit terperinci:

| Ticker / periode | Revenue − COGS raw | `gross_profit` raw | Catatan |
|---|---:|---:|---|
| ITMG annual 2023 | 36.776.589.576.427 | 11.464.105.938.000 | Nilai COGS raw 1.631.773.000 jauh lebih kecil daripada revenue; perlu penjelasan sumber/semantik. |
| GOLD quarterly 2024-Q3 | 8.060.619.300 | -15.623.672.000 | Rumus sederhana tidak cocok. |
| GOLD quarterly 2024-Q4 | 8.349.996.000 | 32.033.939.000 | Rumus sederhana tidak cocok. |
| ITMG quarterly 2024-Q2 | 9.158.000.477.133 | 2.547.880.721.708 | Nilai COGS raw hanya 404.418.000; perlu penjelasan sumber/semantik. |
| ITMG quarterly 2024-Q3 | 9.213.014.397.651 | 3.097.188.352.947 | Nilai COGS raw hanya 403.380.000; perlu penjelasan sumber/semantik. |

Sebaliknya, pada AUTO, semua 31 periode annual/quarterly yang memiliki Revenue, COGS, dan Gross Profit terisi cocok dengan `revenue - cost_of_revenue`. Ini membuktikan bahwa AUTO konsisten pada periode yang diperiksa, bukan bahwa rumus tersebut pasti benar untuk semua ticker.

### 2.4 Gross Profit: raw dan hasil hitung (D-04)

**Keputusan disetujui (26 September 2026):** `gross_profit` yang diberikan Sectors adalah nilai raw dan tidak ditimpa. Untuk pemeriksaan, bandingkan dengan nilai kedua yang dihitung dari `revenue - cost_of_revenue`, memakai tanda raw tanpa normalisasi. Jika berbeda, biarkan berbeda dan tinjau nanti.

Secara konsep, tampilkan/hasilkan dua nilai dengan nama jelas: **Gross Profit raw dari Sectors** dan **Gross Profit hasil hitung (Revenue − COGS)**. Keduanya jangan disatukan atau dianggap salah satunya otomatis menggantikan yang lain. Apakah nanti disimpan di dua tabel, disajikan lewat view, atau dihitung saat dibaca adalah keputusan implementasi; tidak harus membuat duplikasi fisik.

Untuk sekarang, Gross Margin dan pemilihan angka Gross Profit utama ditunda. Lima selisih yang ditemukan cukup dicatat untuk diperiksa nanti; kita tidak perlu menyelesaikan penyebab masing-masing ticker sebelum melanjutkan konsep raw lainnya.

**Status:** DISETUJUI UNTUK KONSEP. Belum ada keputusan skema implementasi.

## 3. Keputusan raw yang dibuat sederhana

### D-01 — Shares pada periode quarterly

**Fakta saat ini:** AUTO mempunyai 7 nilai `OUTSTANDING_SHARES` di periode annual dan tidak mempunyai nilai itu di periode quarterly. Artinya, database belum menyimpan jumlah saham per kuartal.

**Keputusan disetujui (26 September 2026):** shares quarterly kita **skip dulu** karena bukan prioritas saat ini. Jangan menyalin atau memperkirakan shares dari data annual ke baris quarterly. Nilai shares annual tetap disimpan untuk analisis annual. Jika suatu metrik quarterly membutuhkan shares, tandai metrik itu belum tersedia; jangan menghitungnya dengan fallback annual.

Nilai shares annual tetap disimpan dan digunakan untuk periode annual yang sesuai. Keputusan ini tidak menghapus atau mengubah nilai annual.

**Status:** DISETUJUI UNTUK SEKARANG. Contoh raw quarterly AUTO yang diperiksa tidak memiliki field shares, jadi shares quarterly AUTO belum tersedia. Keputusan ini bisa dibuka lagi nanti jika kebutuhan produk berubah atau sumber menyediakan shares quarterly.

### D-02 — Tanggal `Data Available Date` quarterly

**Fakta saat ini:** file `quarterly_financial_dates.json` berisi tanggal seperti `2026-06-30`, dan file financial quarterly bernama/tanggalnya sama. Itu adalah tanggal periode yang dilaporkan, bukan bukti tanggal laporan dipublikasikan. Loader menyimpannya sebagai `period_end`; `report_date` dan `available_date` dibiarkan kosong.

**Keputusan disetujui (26 September 2026):** sebelum angka quarterly digunakan untuk analisis historis point-in-time atau backtest, harus ada tanggal publikasi laporan yang asli dan dapat ditelusuri ke sumber tepercaya. Jika tanggal itu belum diketahui, tandai data/hasil yang membutuhkannya sebagai belum tersedia; jangan membuat tanggal perkiraan.

Tanggal akhir kuartal tetap dipakai sebagai `period_end` untuk mengidentifikasi periode laporan. `period_end` tidak boleh disalin ke `available_date`, dan waktu impor tidak boleh dipakai sebagai tanggal laporan tersedia. Harga/volume yang dihitung sampai akhir kuartal juga tidak membuktikan bahwa angka fundamentalnya sudah diketahui investor pada tanggal itu.

**Status:** DISETUJUI. Nilai `available_date` yang sudah kosong tidak diisi hanya berdasarkan keputusan ini; tanggal resmi harus ditemukan dan dicatat dengan sumbernya terlebih dahulu.

### D-03 — Rata-rata volume 3 bulan untuk annual

**Fakta saat ini:** rumus Excel annual yang diperiksa mengambil `Close` untuk kolom berlabel `Avg Vol (3M)`, sedangkan converter menghitung rata-rata seluruh volume harian setahun sebagai placeholder. Rumus quarterly yang sudah diuji menggunakan simple mean volume selama tiga bulan kalender.

**Keputusan disetujui (26 September 2026):** Avg Vol annual **diskip dulu** karena belum prioritas. Untuk annual, kolom `Avg Vol (3M)` dibiarkan kosong/tidak tersedia. Jangan mengisinya dengan rumus Excel yang mengambil `Close` dan jangan memakai rata-rata volume sepanjang tahun sebagai pengganti. Harga annual tetap dihitung terpisah sebagai `Close` terakhir pada atau sebelum 31 Desember. Data volume harian tetap disimpan dan definisi ini bisa dibuka lagi nanti.

**Status:** DISETUJUI UNTUK SEKARANG. Ini keputusan target; converter/kode belum diubah.

### D-05 — Arti angka financial quarterly

**Keputusan disetujui:** untuk metric flow (contoh: Revenue, COGS, Net Income, OCF), perlakukan record endpoint quarterly sebagai angka untuk kuartal tersebut, bukan angka YTD. Annual adalah record terpisah dari endpoint annual. Simpan kedua jenis record sesuai nilainya; jika annual berbeda dari jumlah quarterly, biarkan berbeda. Jangan menjumlahkan, menyelaraskan, atau mengubah nilai agar cocok. Jika ada selisih, catat sebagai perbedaan sumber untuk ditinjau bila dibutuhkan.

**Catatan istilah:** keputusan `STANDALONE` di sini berarti quarter-only, bukan YTD. Ini tidak menjawab apakah laporan mencakup entitas induk saja atau konsolidasi; `statement_scope` tetap tidak diketahui kecuali sumber membuktikannya. Audit lokal memperlihatkan annual-versus-quarterly cocok pada sebagian ticker dan berbeda pada sebagian lain. Perbedaan tersebut dibiarkan; kita tidak akan menyelidiki semua discrepancy sekarang.

**Status:** DISETUJUI untuk konsep raw. Provider statement scope belum diketahui.

### D-06 — Batas field raw yang dibuat terstruktur

**Keputusan disetujui:** file JSON raw Sectors disimpan utuh sebagai arsip. Untuk tabel canonical yang mudah dipakai aplikasi, petakan hanya field yang diperlukan Excel/fitur produk saat ini. Field lain tetap dapat ditemukan di arsip raw dan boleh ditambahkan ke tabel canonical di kemudian hari jika ada kebutuhan yang jelas.

Artinya, raw archive menjaga respons sumber lengkap, sedangkan canonical tables hanya menyimpan pilihan nilai terstruktur untuk query dan fitur produk. Tidak semua key JSON harus menjadi kolom/metric canonical. Field yang sudah ada di loader lama tetapi tidak diperlukan fitur awal perlu ditandai untuk ditinjau, bukan otomatis dianggap wajib.

**Status:** DISETUJUI sebagai prinsip pemilihan field. Daftar persis field minimum per fitur ditentukan pada D-07 dan `RAW_DATA_MAP.md`. JSON raw lengkap tetap di Supabase Storage; `raw_ingestion_payloads` bukan salinan arsip kedua.

### D-07 — Cakupan field canonical tahap awal

**Keputusan disetujui:** gunakan kolom Excel yang pengguna sudah berikan untuk Company Information, annual financials, quarterly financials, daily pricing, dan data dividen yang dipakai Excel sebagai cakupan peta field awal. Field Sectors lain tetap disimpan di raw archive; jangan masukkan otomatis ke canonical hanya karena tersedia.

Untuk batas cakupan ini:

- **Company Information:** ticker, company name, sector, subsector.
- **Annual:** Year, Revenue, HPP/COGS, Interest Expenses, Net Income, OCF, DPS, Current Assets, Current Liabilities, Total Liabilities, Total Equity, Shares. Stock Price merupakan nilai turunan dari daily close. Annual Avg Vol diskip.
- **Quarterly:** period end/Year/Quarter, Revenue, HPP/COGS, Interest Expenses, Net Income, OCF, Current Assets, Current Liabilities, Total Liabilities, Total Equity. Shares quarterly diskip. Quarterly Stock Price dan Avg Vol adalah nilai turunan dari daily prices; penggunaan harga historis menunggu keputusan tanggal publikasi laporan.
- **Daily Pricing:** Date, Open, High, Low, Close, Volume, Market Cap.
- **Dividends:** historical annual total dividend dipakai sebagai DPS annual. Dividend yield dan payout ratio untuk Excel dihitung dari input sesuai definisi Excel; angka provider lain tidak otomatis menggantikan hasil hitung tersebut. Field dividend provider lainnya tetap di raw archive sampai ada kebutuhan yang disetujui.

Ini adalah batas **field bisnis** untuk pemetaan awal, bukan keputusan membuat satu tabel lebar, banyak tabel, atau bentuk fisik tertentu. Annual dan quarterly tetap observasi/periode terpisah sesuai D-05.

**Status:** DISETUJUI sebagai cakupan peta raw→canonical. Implementasi saat ini memakai tabel canonical yang sudah ada; tidak membentuk schema fisik baru.

### D-08 — Penyederhanaan Company Information

**Kondisi saat ini:** Company Information tersebar di empat tabel: `companies`, `instruments`, `sectors`, dan `instrument_sector_classifications`. Database yang diperiksa baru memiliki satu baris AUTO pada masing-masing tabel tersebut.

**Keputusan konsep disetujui:** sederhanakan Company Information menjadi satu baris master per saham/listing yang sekurangnya berisi ticker, nama perusahaan, sektor, dan subsektor. Untuk katalog yang dituju (sekitar ratusan ticker, kira-kira 600), kita tidak perlu memisahkan sektor menjadi tabel lookup tersendiri pada tahap ini.

Dalam schema saat ini, `instruments` adalah master row target karena `financial_periods` dan `prices_daily` sudah terhubung dengannya memakai `instrument_id`. Migration schema-only `0010` dan backfill plan read-only terpisah telah disiapkan lokal untuk review; keduanya belum dijalankan pada Supabase live.

Penyederhanaan ini berlaku untuk identitas saham yang dicatat produk. Jika suatu saat StockLens perlu mengelola satu badan usaha dengan beberapa ticker/listing atau riwayat perubahan sektor, modelnya dapat dikembangkan lagi.

**Status:** TARGET DISETUJUI. `0010` hanya menambah kolom nullable pada `instruments`. Backfill plan read-only terpisah menampilkan nilai terverifikasi dari relasi lama; UPDATE template di dalamnya belum aktif. Legacy FK/tabel dipertahankan pada tahap awal; cleanup memerlukan audit consumer, migration terpisah, dan persetujuan.

## 4. Status pekerjaan

Dokumen ini mencatat keputusan produk/data; perubahan aturan tidak otomatis mengubah data Supabase yang sudah terlanjur dimuat. Penyelarasan awal AUTO telah dilakukan secara terarah setelah dampak penghapusan fakta di luar scope ditinjau.

Untuk saat ini:

- AUTO canonical saat ini: 33 financial periods, 337 financial facts dalam cakupan, 1.619 daily price records, dan 7 annual DPS facts.
- Metadata Storage AUTO: 60 file; JSON raw lengkap tetap di Storage. `raw_ingestion_payloads` kosong dan tidak diisi sebagai arsip duplikat.
- AUTO: fakta annual/quarterly di luar cakupan awal serta yield/TTM/payout provider di `dividend_facts` telah dikeluarkan dari canonical; raw sumbernya tetap diarsipkan.
- Migration schema-only dan backfill D-08 belum dijalankan pada Supabase live. Penyelarasan canonical AUTO terdahulu adalah perubahan data terpisah.
- Shares quarterly dan Avg Vol annual sengaja diskip untuk sekarang.
- Keputusan COGS *as-is* berlaku untuk proses ingest berikutnya. Data canonical AUTO yang sudah ada masih berisi COGS positif, sesuai tanda raw Sectors.
- Gross Profit raw dipertahankan, dan hitungan `Revenue - COGS` menjadi nilai pembanding terpisah. Bentuk teknis penyajian belum diputuskan.
- Annual dan quarterly disimpan sebagai periode terpisah; jika berbeda, nilainya tetap berbeda.
- Gross Margin dan pemilihan nilai Gross Profit utama ditunda.
- Arsip raw tetap lengkap; hanya field yang diperlukan Excel/fitur saat ini yang dipetakan ke canonical tables.
- Cakupan pemetaan awal mengikuti lima kelompok Excel: Company Information, Annual, Quarterly, Daily Pricing, dan DPS annual.
- Target Company Information: satu baris master per saham/listing pada `instruments`, dengan ticker, company name, sector, subsector.
- Migration schema-only `0010` dan backfill review plan read-only sudah disiapkan lokal; penerapan migration, backfill aktif, dan cleanup legacy masih memerlukan persetujuan.
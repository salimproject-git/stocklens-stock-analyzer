# Jadwal dan Prosedur Operasional Pipeline

**Tujuan:** panduan kapan dan bagaimana menjalankan update harga harian, update fundamental/kuartalan, backup, rebuild, dan backtest Stock Analyzer.

**Repo:** `D:\Stock Analyzer`
**Sumber raw kanonik:** Supabase Storage `stocklens_raw`
**Contoh ticker:** `AUTO`; ganti dengan ticker target yang valid.

> Dokumen ini membedakan jadwal yang direkomendasikan dari hal yang otomatis dijalankan kode. Mode pipeline tidak otomatis menjadwalkan pekerjaan. Gunakan scheduler hanya setelah sumber data tersedia dan prosedur backup/alert sudah disiapkan.

## Jadwal ringkas

| Pekerjaan | Kapan dilakukan | Mode/perintah |
|---|---|---|
| Harga harian | Setelah raw daily terbaru masuk ke Storage dan hari perdagangan selesai; umumnya sekali per hari perdagangan | `--mode daily` |
| Fundamental/kuartalan | Event-driven: setelah laporan kuartal/tahunan baru tersedia dan provenance Storage terverifikasi | Saat ini gunakan `--mode rebuild` dengan preflight dan backup; lihat catatan mode fundamental di bawah |
| Backup dan manifest | Sebelum setiap rebuild/perubahan methodology; ditambah backup terjadwal sesuai kebijakan recovery | Prosedur backup §5 |
| Rebuild menyeluruh | Hanya saat pemulihan/perbaikan dependency, perubahan pipeline/methodology, atau refresh terkontrol; bukan setiap hari/minggu | `--mode rebuild` (berakhir dengan backtest) |
| Backtest | Otomatis sebagai langkah terakhir `--mode rebuild`/`--mode fundamental`; mode mandiri hanya bila backtest perlu dihitung ulang tanpa menyentuh data lain | `--mode backtest` |

Tidak ada dasar untuk menjalankan fundamental “setiap tanggal tertentu” bila tidak ada input baru. Jadwalkan berdasarkan **ketersediaan data**, bukan sekadar tanggal kalender.

## 1. Update harga harian

### Prasyarat

1. File raw harga untuk ticker dan tanggal yang dituju telah tersedia di `stocklens_raw`.
2. Provenance pada `ingestion_files` terdaftar dan checksum cocok.
3. Jangan memakai sumber lokal/sample sebagai pengganti raw Storage.
4. Jika file belum ada di Storage, hentikan dan ikuti prosedur ingest resmi yang disetujui. Jangan memanggil Sectors API untuk objek yang sudah ada.

### Jalankan

```powershell
Set-Location 'D:\Stock Analyzer'
python .\run_pipeline.py AUTO --mode daily --dry-run
python .\run_pipeline.py AUTO --mode daily
```

Ganti `AUTO` dengan ticker yang ingin diperbarui. `--dry-run` orchestrator hanya mencetak command yang akan dipanggil; ia **tidak** menguji perubahan loader ke database. Daily mode menjalankan `load_daily_prices_to_supabase.py` dari Storage dan `calculate_daily_valuation.py`; ia tidak menjalankan intrinsic engine, growth, projection, classification, atau backtest.

### Validasi setelah run

- Loader menyatakan jumlah file/tanggal baru, skip, konflik, dan harga terbaru.
- Harus tidak ada konflik. Jika 0 tanggal baru karena tidak ada perubahan, itu kondisi no-op yang valid.
- Daily status terbaru harus merujuk ke fundamental snapshot yang diharapkan.
- Pastikan harga/tanggal, per-method gap/MoS/verdict, consensus, Based Method, dan Based MoS tersedia melalui RPC read-only.
- Pastikan `calculation_runs` tidak memiliki duplicate `idempotency_key` dan run daily berakhir `SUCCEEDED`.

## 2. Update laporan kuartalan/tahunan (fundamental)

### Kapan

Setelah laporan kuartalan/tahunan yang baru telah diarsipkan ke Storage, provenance/checksum terdaftar, dan loader preflight menunjukkan data aman. Keterlambatan publikasi berarti ticker diproses ketika data benar-benar tersedia; jangan memaksakan jadwal fixed yang menghitung ulang tanpa input baru.

### Dry-run yang tersedia

Quarterly loader menyediakan dry-run nyata terhadap Storage dan canonical DB:

```powershell
Set-Location 'D:\Stock Analyzer'
python .\supabase\load_quarterly_financials_to_supabase.py AUTO --dry-run
```

Periksa periode/fakta baru, skip, konflik, checksum, dan date index. **Annual, dividend, daily, identity, growth, classification, dan valuation tidak semuanya memiliki flag dry-run.** Jangan menganggap `run_pipeline.py ... --dry-run` sebagai preflight data; ia hanya mencetak urutan command. Untuk perubahan fundamental yang hendak ditulis, siapkan backup terlebih dahulu dan jalankan satu ticker pada satu waktu.

### Jalur aman yang sudah diverifikasi

Untuk ticker yang sudah memiliki active projection, `rebuild` memuat source keluarga inti, menghitung kandidat projection lalu memakai ulang projection aktif hanya bila nilai projection, metadata penting, dan base period cocok persis. Mismatch menghentikan proses; **jangan** otomatis menaikkan scenario version.

```powershell
python .\run_pipeline.py AUTO --mode rebuild --offline --dry-run
```

Command di atas hanya memperlihatkan urutan dan tidak menguji semua loader. Setelah Storage/provenance, dry-run quarterly, baseline, dan backup diperiksa, jalankan:

```powershell
python .\run_pipeline.py AUTO --mode rebuild --offline
```

`--offline` berarti orchestration tidak mengambil jalur upload/ingest raw. Ia **bukan** cara melewati pemeriksaan data hilang. Rebuild harus gagal tertutup bila object wajib tidak tersedia. Jalankan per ticker, lalu rekonsiliasi sebelum meneruskan ticker selanjutnya.

### Catatan tentang `--mode fundamental`

Mode `fundamental` saat ini menjalankan `derive_projection_scenario.py --apply` pada jalur biasa. Bila ada projection aktif, proses dapat menolak membuat active scenario kedua. Untuk ticker dalam keadaan itu, **jangan jadwalkan mode fundamental sebagai job otomatis** sampai jalur projection reuse yang setara ditambahkan dan dites untuk mode tersebut. Gunakan rebuild yang sudah memiliki `projection-reuse` guard atau hentikan dan investigasi mismatch.

Quarterly update memang dapat membuat intrinsic snapshot baru karena fundamental/projection/classification berubah. Itu berbeda dari daily price update yang seharusnya hanya membuat daily status baru.

## 3. Rebuild: makna dan frekuensi

Rebuild menjalankan urutan lengkap per ticker:

```text
Storage canonical loaders
-> growth/quality
-> projection (strict reuse bila existing projection setara)
-> classification
-> fundamental intrinsic snapshot
-> daily price status
-> backtest
```

Rebuild tidak menghapus/truncate tabel legacy dan tidak menjalankan upload/ingest raw API. Sejak backtest digabungkan ke akhir urutan, satu perintah `--mode rebuild` mengisi **semua tab dan kartu market**. Backtest diletakkan paling akhir karena ia membaca `financial_periods` dan `prices_daily` yang baru saja dimuat langkah sebelumnya, dan hanya menulis ke `calc_backtest_cases` / `calc_backtest_methods` — tidak pernah menyentuh `calc_valuation_*`, jadi hasil kalkulasi valuasi tidak berubah. Gunakan rebuild hanya untuk:

- perbaikan/recovery setelah masalah pipeline atau canonical data;
- perubahan code/methodology/parameter yang memang mengubah dependency hasil;
- refresh menyeluruh yang disetujui dengan backup dan rekonsiliasi;
- validasi operasional terkontrol setelah migration.

**Frekuensi rekomendasi:** tidak berulang secara harian atau mingguan. Jalankan saat ada alasan perubahan/recovery yang spesifik. Daily quotes memakai `daily`; fundamental baru memakai proses event-driven setelah data tersedia.

## 4. Backtest

Backtest adalah bagian akhir dari `--mode rebuild` dan `--mode fundamental`, jadi satu perintah operator sudah menghasilkan backtest terbaru. Ia tetap dapat dijalankan sendiri tanpa memuat ulang raw apa pun:

```powershell
Set-Location 'D:\Stock Analyzer'
python .\run_pipeline.py AUTO --mode backtest --dry-run
python .\run_pipeline.py AUTO --mode backtest
```

Jalankan mode mandiri ini hanya jika backtest perlu dihitung ulang tanpa menyentuh data lain, misalnya horizon kasus baru atau perubahan metodologi backtest. Page view dan `--mode daily` **tidak boleh** memanggilnya: `daily` sengaja tetap hanya `load-prices` + `daily-status`. Pertahankan `calculation_runs`, methodology version, input snapshot/hash, provenance, dan idempotency.

## 5. Backup, manifest, dan retensi

### Backup sebelum rebuild atau perubahan berisiko

Sebelum write:

1. Catat `git rev-parse HEAD`, migration list, row counts tabel canonical/calculation, jumlah `calculation_runs`, status runs, dan duplicate idempotency keys.
2. Export RPC read-only penuh bagi ticker yang akan diproses: research, summary lama, frequency baru, dan backtest. Jangan berhenti pada method IV; sertakan growth, annual ratios, projection, classification, dan seluruh backtest cases.
3. Simpan export tabel yang diperlukan, manifest SHA-256, Storage object manifest/checksum, provenance, dan rencana write dry-run.
4. Verifikasi setiap file: JSON dapat dibaca, row count sesuai manifest, checksum cocok, dan ticker/family lengkap.
5. Simpan backup di lokasi terpisah dengan akses terbatas/terenkripsi sesuai kebijakan organisasi. Jangan commit ekspor database/Storage ke Git secara default.

Contoh bukti run yang tersimpan dari rebuild ini:

```text
D:\Stock Analyzer\backups\valuation_frequency_20261003\
```

Direktori itu adalah artefak lokal; pastikan disalin ke backup operasional yang tahan kehilangan disk. Buat direktori baru bertanggal untuk run berikutnya; jangan menimpa satu-satunya baseline lama.

### Frekuensi backup yang disarankan

- Backup database terkelola mengikuti kebijakan RPO/RTO proyek (misalnya harian) dan diuji pemulihannya berkala.
- Snapshot/export aplikasi + manifest sebelum **setiap** rebuild, migration data, penggantian projection, atau perubahan methodology.
- Storage raw dipertahankan sebagai arsip sumber; manifest/checksum ambil sebelum tindakan yang berisiko terhadap file atau provenance.
- Jangan menganggap backup lokal run sebelumnya sebagai backup otomatis yang terus diperbarui.

Jadwal retensi tepat harus ditetapkan pemilik layanan sesuai kebutuhan pemulihan, biaya, dan sensitivitas data; jangan menghapus backup sampai restore/retensi disetujui.

## 6. Rekonsiliasi dan kondisi berhenti

Bandingkan sebelum/sesudah per ticker:

- intrinsic value/status tiap method;
- daily price/date, gap, MoS, verdict, consensus, Based Method, Based MoS;
- growth, annual ratios, quarterly quality, classification, projection;
- backtest cases/results;
- `input_hash`, `idempotency_key`, methodology version, run status, provenance.

Hentikan sebelum melanjutkan ticker lain apabila ada missing Storage object/checksum, loader conflict, projection mismatch, status run `PARTIAL`/gagal, duplicate idempotency key, RPC kosong/tidak cocok, atau perbedaan yang belum dijelaskan. Jangan truncate/hapus legacy output untuk “membersihkan” mismatch.

## 7. Jadwal operasional satu halaman

1. **Hari perdagangan selesai + daily raw tersedia:** update `--mode daily` untuk ticker yang berubah.
2. **Laporan kuartalan/tahunan baru ada + provenance valid:** backup, quarterly/loader preflight, lalu jalankan rebuild terkontrol untuk ticker itu; rekonsiliasi sebelum lanjut.
3. **Methodology/code berubah atau recovery dibutuhkan:** backup penuh, migration additive yang direview, rebuild terkontrol, rekonsiliasi semua ticker terdampak.
4. **Backtest:** sudah otomatis sebagai langkah terakhir `--mode rebuild`/`--mode fundamental`. Mode mandiri `--mode backtest` hanya untuk menghitung ulang backtest tanpa menyentuh data lain.
5. **Frontend dibuka:** tidak memicu kalkulasi; hanya membaca hasil melalui RPC.

## 8. Catatan hasil rollout 2026-10-03

Rebuild Storage telah dijalankan untuk 18 ticker yang lulus preflight dan rekonsiliasi. DSSA memakai kuartal terakhir yang tersedia, Q1 2026. INDF dan GOLD sengaja tidak memperoleh snapshot valuation baru karena classifier menghasilkan `UNCLASSIFIED`; jangan menganggap tabel baru berisi valuation untuk semua ticker atau memberi stock type manual tanpa keputusan produk. Detail, backup, dan laporan per ticker: `D:\Stock Analyzer\docs\VALUATION_FREQUENCY_AUDIT.md` dan `D:\Stock Analyzer\backups\valuation_frequency_20261003\`.

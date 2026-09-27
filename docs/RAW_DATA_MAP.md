# Peta Data Raw — Sectors ke Supabase

Peta ringkas ini menunjukkan apa saja file raw AUTO, tujuan datanya, dan tabel Supabase yang sudah dipakai loader. Ini peta konsep berdasarkan project saat ini, **bukan instruksi menjalankan loader** dan bukan keputusan migration baru.

## Alur sederhana

```text
Sectors API
  → file JSON asli di Data/Raw/{TICKER}
  → salinan JSON di Supabase Storage (arsip raw)
  → loader memetakan field ke tabel PostgreSQL
```

CSV di `Data/Converted/{TICKER}` adalah bentuk bantu untuk dibaca/dibandingkan dengan Excel. CSV bukan sumber utama API dan converter tidak menulis ke Supabase.

## Peta keluarga data

| Keluarga raw | Isi penting di JSON | Tujuan canonical Supabase saat ini | Catatan sederhana |
|---|---|---|---|
| Info perusahaan | Raw mencakup `symbol`, `company_name`, dan banyak field `overview` | **Target D-08:** `instruments.ticker`, `company_name`, `sector_name`, `subsector_name`; tabel legacy tetap sementara karena FK | Website, alamat, listing date, dan field overview lain tetap di raw archive. Migration schema-only belum dijalankan pada Supabase live. |
| Annual | `financials.historical_financials[]`, tiap record punya `year` dan banyak metric | `financial_periods` dengan `period_type=ANNUAL`; hanya metric cakupan Excel masuk ke `financial_facts` | Field lain, termasuk `historical_eps`, tetap di raw archive. Shares annual menggunakan `OUTSTANDING_SHARES` dengan unit `SHARES`. |
| Quarterly | `quarterly_financial_dates.json` memberi label/tanggal periode; file `quarterly/{YYYY-MM-DD}.json` berisi satu record financial | `financial_periods` dengan `period_type=QUARTER`; nilai metric masuk ke `financial_facts` | Tanggal indeks dipakai sebagai `period_end`, bukan tanggal laporan diumumkan. Raw quarterly AUTO tidak memiliki field shares. |
| Daily price | Record per hari: `date`, `open`, `high`, `low`, `close`, `volume`, `market_cap` | `prices_daily`, satu record per instrument dan trading date | Field tetap sesuai raw; `market_cap` boleh kosong. Rata-rata volume bukan nilai dari record harga harian; itu kalkulasi dari beberapa record. |
| Dividend | `dividend.historical_dividends[year].total_dividend` untuk DPS annual; field provider lain dan breakdown bertanggal tetap di raw | `dividend_facts` (`ANNUAL_TOTAL`) | Yield/DPR Excel dihitung sesuai definisi Excel; aggregate/yield provider tidak otomatis dipetakan. Tanggal breakdown tidak otomatis berarti tanggal pembayaran. |
| Manifest / proses ingest | Manifest lokal berisi status file; metadata ingest punya checksum dan Storage path | `ingestion_runs`, `ingestion_files`, private Supabase Storage | Ini untuk melacak file dan proses. `raw_ingestion_payloads` adalah tabel lain dan saat audit tercatat kosong; arsip file berada di Storage. |

## Cakupan field awal yang disetujui (mengikuti Excel)

Daftar berikut menjawab **field bisnis mana** yang masuk peta awal. Ini belum menetapkan tabel fisik baru: model sekarang menyimpan data annual/quarterly di `financial_periods` + `financial_facts`, harga harian di `prices_daily`, dan dividen di `dividend_facts`.

| Keluarga | Field Excel dalam cakupan awal | Raw source Sectors | Tujuan/data Supabase sekarang | Aturan/catatan |
|---|---|---|---|---|
| Company Information | Ticker, Company Name, Sector, Subsector | `symbol`, `company_name`, `overview.sector`, `overview.sub_sector` | `companies`, `instruments`, `sectors`, `instrument_sector_classifications` | `symbol` provider seperti `AUTO.JK`; ticker IDX untuk produk seperti `AUTO`. |
| Annual financials | Year, Revenue, HPP/COGS, Interest Expenses, Net Income, OCF, Current Assets, Current Liabilities, Total Liabilities, Total Equity, Shares | `financials.historical_financials[]` | `financial_periods` (`ANNUAL`) + `financial_facts` | IDR penuh; COGS tanda raw; shares unit `SHARES`. |
| Annual DPS | Year, DPS (Rp) | `dividend.historical_dividends[year].total_dividend` | `dividend_facts` (`ANNUAL_TOTAL.amount_per_share`) | Raw annual total dividend digunakan sebagai DPS. Yield/DPR Excel dihitung dengan definisi Excel, bukan diganti nilai yield/payout provider. |
| Annual price | Stock Price (Rp) | daily `date`, `close` | `prices_daily.close_price` → hasil turunan/query | Close terakhir pada/sebelum 31 Desember; bukan financial fact dari annual report. |
| Annual Avg Vol | Tidak dipakai sekarang | Daily `date`, `volume` tetap diarsipkan | Tidak dihitung untuk annual sekarang | Kolom annual dibiarkan kosong sesuai keputusan D-03. |
| Quarterly financials | Period end/Year/Quarter, Revenue, HPP/COGS, Interest Expenses, Net Income, OCF, Current Assets, Current Liabilities, Total Liabilities, Total Equity | `quarterly_financial_dates.json` + `quarterly/{period_end}.json` | `financial_periods` (`QUARTER`) + `financial_facts` | Quarter adalah periode observasi terpisah dari annual; jika jumlah tahunan berbeda, biarkan berbeda. Shares quarterly tidak dipakai. |
| Quarterly price/liquidity inputs | Stock Price (Rp), Avg Vol (3M) | Daily `date`, `close`, `volume` | `prices_daily` → hasil turunan/query | Harga dan volume dirujuk ke tanggal acuan yang benar. Tanpa tanggal publikasi laporan nyata, jangan menyebut fundamental quarterly result point-in-time valid. |
| Daily Pricing | Date, Open, High, Low, Close, Volume, Market Cap | Tiap daily row: `date`, `open`, `high`, `low`, `close`, `volume`, `market_cap` | `prices_daily` | Pertahankan `NULL` saat field tidak tersedia. |

## Company Information: target sederhana

| Ticker | Company Name | Sector | Subsector |
|---|---|---|---|
| AUTO | Astra Otoparts Tbk | Consumer Cyclicals | Automobiles & Components |

Konsepnya: satu row master per saham/listing agar aplikasi mudah membaca Company Information. Target `instruments` membawa ticker, company name, sector, subsector karena harga dan financial periods sudah merujuk ke `instrument_id`.

Schema live masih memecah data ke `companies`, `instruments`, `sectors`, dan `instrument_sector_classifications`. Migration schema-only lokal `0010_instrument_company_information.sql` dan backfill preview/update-template read-only `supabase/backfills/0010_instrument_company_information_backfill.sql` telah disiapkan, tetapi belum diterapkan. Tabel/kolom lama, foreign key, RLS, dan grants tetap dipertahankan sampai cleanup terpisah disetujui.

## Contoh field ke canonical metric

| Field Sectors | Canonical metric / tujuan | Unit yang disimpan |
|---|---|---|
| `revenue` | `REVENUE` | `IDR` penuh |
| `cost_of_revenue` | `COST_OF_REVENUE` | `IDR` penuh; tanda raw dipertahankan |
| `gross_profit` | `GROSS_PROFIT` (raw Sectors) | `IDR` penuh; pembanding hasil `revenue - cost_of_revenue` dihitung terpisah dan tidak menimpa nilai raw |
| `earnings` | `EARNINGS` | `IDR` penuh |
| `operating_cash_flow` | `OPERATING_CASH_FLOW` | `IDR` penuh |
| `current_assets` (annual) / `total_current_asset` (quarterly) | `CURRENT_ASSETS` / `TOTAL_CURRENT_ASSET` | `IDR` penuh; nama source berbeda |
| `current_liabilities` | `CURRENT_LIABILITIES` | `IDR` penuh |
| `total_liabilities` | `TOTAL_LIABILITIES` | `IDR` penuh |
| `total_equity` | `TOTAL_EQUITY` | `IDR` penuh |
| `outstanding_shares` (annual only in this feed) | `OUTSTANDING_SHARES` | `SHARES` penuh |
| daily `close`, `volume`, `market_cap` | `prices_daily.close_price`, `.volume`, `.market_cap` | IDR/share, jumlah saham, IDR |

Nama tampilan Excel seperti `Revenue (M Rp)` atau `Shares (Juta)` bukan satuan penyimpanan canonical. `M Rp` dan `Juta` adalah format tampilan.

Daftar contoh di atas tunduk pada batas cakupan D-07 dan keputusan gross-profit D-04. Import awal memetakan field pada tabel cakupan Excel serta `gross_profit` raw sebagai field pembanding yang disetujui D-04. Hasil `revenue - cost_of_revenue` adalah pembanding terpisah, bukan pengganti/penimpaan fakta raw. Field raw lainnya tetap utuh di arsip JSON; fakta legacy di Supabase tidak dihapus atau diubah.

## AUTO: kondisi yang sudah dicek

- Local raw AUTO: 7 annual records, 26 quarterly records, 1.610 daily rows di snapshot CSV terdahulu; raw files sekarang juga mencakup incremental daily windows sesudah snapshot tersebut.
- Supabase setelah penyelarasan scope: 1 instrument AUTO, 33 financial periods (7 annual + 26 quarterly), 337 financial facts (77 annual + 260 quarterly sesuai peta, termasuk Gross Profit raw), 1.619 daily price rows, 7 annual DPS facts, dan 60 file metadata Storage.
- JSON raw lengkap tetap di private Storage. `raw_ingestion_payloads` adalah tabel terpisah yang saat ini kosong; tidak dibuat salinan kedua dari arsip Storage.
- `report_date` dan `available_date` masih kosong pada semua 33 periode financial AUTO.
- Annual dan quarterly adalah record berbeda. Sesuai aturan konsep, perbedaan antar-keduanya tidak dipaksa hilang.
- Shares quarterly dan Avg Vol annual sementara tidak dipakai.
- Fakta canonical AUTO di luar scope awal sudah dikeluarkan; nilai sumber lengkap tetap dapat ditelusuri pada arsip Storage. Tidak ada backfill nilai atau transformasi raw yang dilakukan.
- Cakupan field canonical awal mengikuti Company Information, Annual, Quarterly, Daily Pricing, dan DPS annual pada template Excel.
- Lima contoh raw GOLD/ITMG memiliki `gross_profit` berbeda dari `revenue - cost_of_revenue`. Nilai raw dan hasil hitung akan dibandingkan terpisah; penyebab dan angka utama ditunda untuk pemeriksaan berikutnya.

## Pertanyaan yang sengaja ditunda

- Apakah laporan mencakup entitas konsolidasi atau entitas induk saja (`statement_scope`).
- Tanggal publikasi laporan financial yang sebenarnya (`report_date` / `available_date`). Tanpa itu jangan mengklaim fundamental point-in-time/backtest tersedia.
- Arti setiap komponen dividend `breakdown` dan tanggal event-nya.
- Bentuk teknis penyimpanan/penyajian Gross Profit raw versus hasil hitung.

Tidak ada kode, tabel, atau data Supabase yang diubah saat peta konsep ini dibuat.
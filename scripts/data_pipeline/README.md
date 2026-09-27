# Data scripts (beginner guide)

This folder contains the two scripts for preparing Sectors.app source data:

1. `01_download_sectors.py` downloads and caches original API responses as JSON in `Data/Raw/{TICKER}/`.
2. `02_convert_sectors_raw.py` reads that JSON and creates CSV files in `Data/Converted/{TICKER}/` for review and comparison with the Excel template.

**The converter does not write to Supabase.** Supabase upload and database loaders are separate scripts in `supabase/`.

## Before running

From the project root (`D:\Stock Analyzer`):

```powershell
$env:SECTORS_API_KEY = 'YOUR_SECTORS_API_KEY'
```

Use your real API key only in your local terminal. Do not paste it into a script, document, or Git commit.

## Download data

Download all supported data for one ticker:

```powershell
python .\scripts\data_pipeline\01_download_sectors.py AUTO --task all
```

Or download one category at a time:

```powershell
python .\scripts\data_pipeline\01_download_sectors.py AUTO --task info
python .\scripts\data_pipeline\01_download_sectors.py AUTO --task annual
python .\scripts\data_pipeline\01_download_sectors.py AUTO --task quarterly-dates
python .\scripts\data_pipeline\01_download_sectors.py AUTO --task quarterly
python .\scripts\data_pipeline\01_download_sectors.py AUTO --task dividend
python .\scripts\data_pipeline\01_download_sectors.py AUTO --task daily
```

Daily data starts at 2020-01-01 by default. The collector keeps local JSON files and can continue fetching from the latest saved date. To choose another raw folder, pass `--data-root PATH`.

## Convert saved JSON to CSV

Convert one ticker:

```powershell
python .\scripts\data_pipeline\02_convert_sectors_raw.py AUTO
```

Convert several tickers, or all tickers under `Data/Raw`:

```powershell
python .\scripts\data_pipeline\02_convert_sectors_raw.py AUTO ARII
python .\scripts\data_pipeline\02_convert_sectors_raw.py
```

CSV output is written to `Data/Converted/{TICKER}/`. Optional `--raw-root PATH` and `--output-root PATH` arguments select different folders.

## Safety reminder

These commands call the external Sectors API or create local CSV files. They do not change Supabase. Before running any `supabase/` importer, read its instructions and confirm which ticker and project it will write to.
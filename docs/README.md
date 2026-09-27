# Project notes

This folder is split into three simple groups:

- [`PRODUCT_CONTEXT.md`](PRODUCT_CONTEXT.md): what StockLens is meant to do.
- [`DATA_RULES.md`](DATA_RULES.md): agreed data rules and remaining implementation questions.
- [`RAW_DATA_MAP.md`](RAW_DATA_MAP.md): simple map from Sectors JSON families to the canonical Supabase tables.
- [`SUPABASE_MANUAL_RUNBOOK.md`](SUPABASE_MANUAL_RUNBOOK.md): step-by-step PowerShell workflow for ingesting a new ticker or updating a newly published quarter, loading actuals, recalculating metrics, and verifying results.
- The runbook also documents valuation preview/persistence and its remaining input limitations.
- [`reference/`](reference/): useful historical analysis and Excel/template examples. These help answer questions but are not instructions to run the current system.
- [`archive/`](archive/): older plans and runbooks kept so previous work is not lost. Some descriptions are outdated; check the code and live database before following them.

## What is implemented today

- The Sectors collector and CSV converter are in `scripts/data_pipeline/`.
- Local source JSON and generated CSVs live under `Data/` and are not tracked by Git.
- Supabase migrations, data loaders, and calculation modules live under `supabase/`.
- The Next.js frontend lives under `frontend/` and still uses mock data.
- The passing Phase 4.1 offline regression test lives under `tests/`. Older experiments remain under the ignored `Testing/` folder.

Use the root [`README.md`](../README.md) as the entry point and `scripts/data_pipeline/README.md` for data-script commands.
# Supabase folder guide

This folder contains code and SQL migrations used to work with the existing StockLens Supabase project.

## Current state

- The live project already has Supabase tables and AUTO data.
- The original migrations (`0001`–`0003`) and later calculation migrations (`0008`–`0009`) are kept here as project history.
- `migrations/0010_instrument_company_information.sql` is an unapplied, additive schema proposal. Its companion `backfills/0010_instrument_company_information_backfill.sql` is read-only as written; the UPDATE exists only as a commented review template. Neither has been run against Supabase live.
- Some calculation modules and migrations are still being developed. The frontend is not yet connected to Supabase.
- The old setup notes are kept at [`docs/archive/SUPABASE_RUNBOOK_OLD.md`](../docs/archive/SUPABASE_RUNBOOK_OLD.md). They describe earlier project stages, not a fresh setup for today's database.

## What the file groups do

- `migrations/`: changes to database structure. A migration already applied to the live project is history; do not rerun it as a cleanup step or edit it to change live tables. Future changes should be new migrations.
- Company Information D-08 rollout keeps legacy tables/FKs during the first stage. Do not apply the backfill or remove `companies`, `sectors`, or `instrument_sector_classifications` until separately reviewed and approved.
- `upload_raw_to_supabase_storage.py` and `upload_raw_storage_only.py`: copy local raw JSON files to the private Storage bucket and record upload metadata.
- `load_*_to_supabase.py`: import company, annual, quarterly, dividend, or daily-price data into canonical database tables.
- `raw_storage_source.py`: shared helper for reading the raw files stored in Supabase Storage.
- `calculation_*.py`, `calculate_*.py`, `run_calculation_*.py`: calculation rules and orchestration. Treat these as work in progress until their matching tests pass.
- `projection_scenarios` / `projection_values`: user/workbook forecasts, kept separate from actuals in `financial_periods` + `financial_facts`. Migration `0013_projection_scenarios.sql` is applied to the connected live project. Tables are RLS-protected and accessible only through trusted server-side `service_role` code; never use that key in the frontend.
- `store_projection_scenario.py`: validates workbook historical inputs against canonical actuals, then dry-runs by default. Run `python supabase/store_projection_scenario.py --apply` to save the supplied AUTO Q2 2026 forecast, or use `--scenario <path.json>` for another input JSON. Amount display values in M Rp are stored as full IDR (`display × 1,000,000,000`); DPS uses IDR per share. Historical values are validated/referenced, not copied into forecast tables.
- `migrations/0014_valuation_reference_and_results.sql` and `0015_valuation_methodology_alignment.sql` add versioned reference weights/thresholds, current-valuation result tables, and a matching methodology registry entry. The first reference seed has 12 sectors, 6 stock types and 6 DER/CR/ICR threshold rows. `calculate_valuation.py` previews by default and stores a current valuation snapshot only with `--apply`. It requires an explicit stock type and one active projection scenario. DDM and discounted earnings remain unavailable unless a risk-free rate and its source are supplied. Mean-reversion PBV currently uses annual shares as a flagged quarterly proxy because quarterly shares and available dates are not in canonical facts.
- Other one-off files such as `clean_raw_storage.py` can delete remote Storage objects. Read the entire script before use; never run a cleanup script just to tidy local files.

## Beginner safety checklist

1. Start with the root [`README.md`](../README.md) and the data pipeline guide in `scripts/data_pipeline/README.md`.
2. Do not run a Supabase loader until you know which project, ticker, and rows it will write.
3. Never expose `SUPABASE_SERVICE_ROLE_KEY` to the frontend or commit it to Git.
4. Do not rerun old migrations on the populated project. Do not delete Storage objects or database rows as part of repository cleanup.
5. Run offline checks from the project root with `python -m unittest tests.test_phase_4_1_registry_and_pit -v`.

This guide intentionally does not prescribe a complete import workflow yet. Choose and document that workflow separately before automating writes to the live database.
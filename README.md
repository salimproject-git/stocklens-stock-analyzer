# StockLens

StockLens is a stock research project. This repository contains a Next.js frontend, Python data scripts, and a Supabase database setup.

## Start here

- **New to the project?** Read [`docs/README.md`](docs/README.md) for a short guide to the folders and project status.
- **Data rules?** Review [`docs/DATA_RULES.md`](docs/DATA_RULES.md); recommendations there are drafts until approved.
- **Raw field map?** See [`docs/RAW_DATA_MAP.md`](docs/RAW_DATA_MAP.md) for the agreed first-pass Excel field scope.
- **Get Sectors data and convert it for review?** Follow [`scripts/data_pipeline/README.md`](scripts/data_pipeline/README.md).
- **Database code and migrations?** Read [`supabase/README.md`](supabase/README.md). It explains the current folder and warns which old steps not to repeat.
- **Frontend?** See [`frontend/README.md`](frontend/README.md).

## Repository map

```text
README.md                    Start here
docs/                        Current short guides and archived references
scripts/data_pipeline/       Sectors API collector and JSON-to-CSV converter
supabase/                    Database loaders, calculation code, and migrations
tests/                       Current offline regression tests and small fixtures
frontend/                    Next.js application
Data/                         Local raw JSON and converted CSV; ignored by Git
Phyton/ and Testing/          Legacy experiments retained for now; ignored by Git
```

## Important safety notes

- Local data under `Data/` is deliberately not committed to Git.
- Never put a Supabase service-role key in the frontend or commit it to Git. Keep credentials in your local `.env` or PowerShell session.
- Do not delete or rewrite migrations that have already been applied to Supabase. Add a new migration for future database changes.
- The database has real AUTO data. A script that writes to Supabase is not a harmless cleanup command; inspect it before running.

## Current limitations

- The frontend still uses sample/mock data; it is not yet connected to Supabase.
- The collector and converter are in `scripts/data_pipeline/`; Supabase importers remain under `supabase/` because they use the database schema and each other.
- The full calculation test suite is unfinished. The Phase 4.1 offline tests are the currently passing baseline; check the current code before relying on other suites.
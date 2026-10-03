-- 0029_annual_ratios.sql
-- ============================================================================
-- Annual ratio results: one row per (annual period, ratio metric).
--
-- Why a separate table
-- --------------------
-- `calc_annual_growth_quality` holds growth, forensic and dividend-series
-- metrics. The eight ratios added here (EPS, BVPS, ROE, GROSS_MARGIN,
-- NET_MARGIN, TOTAL_ASSETS, REVENUE_CAGR_WINDOW, EARNINGS_CAGR_WINDOW) are
-- *levels* rather than growth series, and each is produced once per annual
-- snapshot so the UI's per-year table and the AI payload can read a year's own
-- value instead of recomputing it in the browser
-- (docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md, decision S3 = option b).
--
-- Storing them in `calc_annual_growth_quality` would have been cheaper, but the
-- table name would then claim that `TOTAL_ASSETS` is a growth metric. A separate
-- table keeps the name honest, which matters because the AI payload labels each
-- metric group.
--
-- Shape
-- -----
-- Same as the other Phase 4.2 result tables (migration 0009): same columns,
-- same status vocabulary, same `nulls not distinct` idempotency key, same
-- provenance requirements. `value_numeric` is nullable on purpose - a row exists
-- for every metric evaluated, including the ones a guard refused, so "zero" and
-- "not available" never collapse into each other.
--
-- `unit_code` is carried **per row**, following `calc_valuation_inputs`. The
-- design doc requires an unambiguous unit label to be stored rather than
-- formatted into the value, because the single largest risk in the AI payload is
-- reading a ratio as an amount (docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md section 2
-- and Langkah 3 rule 2). Storing it beside the value means the read layer cannot
-- get it wrong by omission. Values used here: `IDR_PER_SHARE` (EPS, BVPS), `IDR`
-- (TOTAL_ASSETS, TOTAL_ASSETS_DERIVED), `RATIO` (ROE, GROSS_MARGIN, NET_MARGIN,
-- both CAGR windows).
--
-- Metric codes written by `calculate_quarterly_growth_quality.py`:
--   EPS, BVPS, ROE, GROSS_MARGIN, NET_MARGIN,
--   TOTAL_ASSETS, TOTAL_ASSETS_DERIVED,
--   REVENUE_CAGR_WINDOW, EARNINGS_CAGR_WINDOW
--
-- `TOTAL_ASSETS` is the *reported* provider figure (decision S1). The
-- balance-sheet reconstruction `liabilities + equity` is kept beside it as
-- `TOTAL_ASSETS_DERIVED` so the two can be compared; the reported value is the
-- official one and a disagreement is flagged, not hidden.
--
-- Purely additive: no existing table, row or function is modified.
-- ============================================================================

begin;

create table if not exists public.calc_annual_ratios (
  id uuid primary key default gen_random_uuid(),
  calculation_run_id uuid not null
    references public.calculation_runs(id),
  methodology_version_id uuid not null
    references public.methodology_versions(id),
  instrument_id uuid not null
    references public.instruments(id),
  financial_period_id uuid
    references public.financial_periods(id),
  metric_code text not null,
  observation_date date,
  value_numeric numeric,
  unit_code text not null
    check (unit_code in ('IDR_PER_SHARE', 'IDR', 'RATIO', 'PERCENT', 'SHARES', 'YEARS')),
  calculation_status text not null
    check (calculation_status in ('VALID', 'NOT_CALCULABLE', 'UNAVAILABLE')),
  availability_status text not null default 'READY',
  flags jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  constraint calc_annual_ratios_unique
    unique nulls not distinct
    (calculation_run_id, instrument_id, financial_period_id, metric_code)
);

create index if not exists idx_calc_annual_ratios_run
  on public.calc_annual_ratios(calculation_run_id);

create index if not exists idx_calc_annual_ratios_period
  on public.calc_annual_ratios(instrument_id, observation_date);

create index if not exists idx_calc_annual_ratios_status
  on public.calc_annual_ratios(calculation_status);

-- ============================================================================
-- Row level security and grants
-- ============================================================================
-- Same rule as every other result table: the browser roles get no table grant,
-- only the narrow `stocklens_market_reader` role does, and only on the columns a
-- read RPC needs. The RPC that exposes these rows to the UI and to n8n is
-- Langkah 3 of docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md and is NOT part of this
-- migration; the grant is created now so the table is fully configured.

alter table public.calc_annual_ratios enable row level security;

revoke all on table public.calc_annual_ratios from public, anon, authenticated;
grant select, insert, update on table public.calc_annual_ratios to service_role;

revoke all on table public.calc_annual_ratios from stocklens_market_reader;
grant select (instrument_id, financial_period_id, metric_code, value_numeric, unit_code, calculation_status, availability_status)
  on table public.calc_annual_ratios to stocklens_market_reader;

drop policy if exists stocklens_market_reader_select on public.calc_annual_ratios;
create policy stocklens_market_reader_select on public.calc_annual_ratios
  for select to stocklens_market_reader using (true);

do $verify$
declare
  missing integer;
begin
  -- The table and its idempotency key must exist, or a re-run duplicates rows.
  if not exists (
    select 1
    from information_schema.tables t
    where t.table_schema = 'public' and t.table_name = 'calc_annual_ratios'
  ) then
    raise exception 'ANNUAL_RATIOS_TABLE_MISSING';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_constraint c
    join pg_catalog.pg_class r on r.oid = c.conrelid
    join pg_catalog.pg_namespace n on n.oid = r.relnamespace
    where n.nspname = 'public'
      and r.relname = 'calc_annual_ratios'
      and c.conname = 'calc_annual_ratios_unique'
      and c.contype = 'u'
  ) then
    raise exception 'ANNUAL_RATIOS_UNIQUE_KEY_MISSING';
  end if;

  -- Provenance columns must be NOT NULL so no ratio is stored without the run
  -- and the methodology version that produced it.
  select count(*) into missing
  from (values
    ('calculation_run_id'),
    ('methodology_version_id'),
    ('instrument_id'),
    ('metric_code'),
    ('unit_code'),
    ('calculation_status'),
    ('availability_status')
  ) as expected(column_name)
  where not exists (
    select 1
    from information_schema.columns c
    where c.table_schema = 'public'
      and c.table_name = 'calc_annual_ratios'
      and c.column_name = expected.column_name
      and c.is_nullable = 'NO'
  );

  if missing > 0 then
    raise exception 'ANNUAL_RATIOS_PROVENANCE_NOT_NULL_VIOLATED: %', missing;
  end if;

  -- A value column that cannot be NULL would force a refused ratio to be
  -- written as a zero, which is exactly the conflation the design forbids.
  if not exists (
    select 1
    from information_schema.columns c
    where c.table_schema = 'public'
      and c.table_name = 'calc_annual_ratios'
      and c.column_name = 'value_numeric'
      and c.is_nullable = 'YES'
  ) then
    raise exception 'ANNUAL_RATIOS_VALUE_MUST_BE_NULLABLE';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_class c
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relname = 'calc_annual_ratios'
      and c.relrowsecurity
  ) then
    raise exception 'ANNUAL_RATIOS_RLS_DISABLED';
  end if;

  -- The browser roles must stay unable to read the raw table directly; only the
  -- RPC may expose these values.
  if has_table_privilege('anon', 'public.calc_annual_ratios', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_annual_ratios', 'SELECT') then
    raise exception 'ANNUAL_RATIOS_RAW_GRANTS_MUST_REMAIN_PRIVATE';
  end if;

  -- The reader role gets *column-level* grants, not a table-level one, matching
  -- 0017/0018. `has_table_privilege` reports false for a column grant, so the
  -- check has to be per column - otherwise this block would always fail.
  select count(*) into missing
  from (values
    ('instrument_id'), ('financial_period_id'), ('metric_code'),
    ('value_numeric'), ('unit_code'), ('calculation_status'), ('availability_status')
  ) as expected(column_name)
  where not has_column_privilege(
    'stocklens_market_reader', 'public.calc_annual_ratios',
    expected.column_name, 'SELECT'
  );

  if missing > 0 then
    raise exception 'ANNUAL_RATIOS_READER_GRANT_MISSING: %', missing;
  end if;
  if not exists (
    select 1
    from pg_catalog.pg_policy p
    join pg_catalog.pg_class c on c.oid = p.polrelid
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relname = 'calc_annual_ratios'
      and p.polname = 'stocklens_market_reader_select'
  ) then
    raise exception 'ANNUAL_RATIOS_READER_POLICY_MISSING';
  end if;
end
$verify$;

commit;

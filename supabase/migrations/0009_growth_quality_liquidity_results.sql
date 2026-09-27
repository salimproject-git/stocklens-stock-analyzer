-- 0009_growth_quality_liquidity_results.sql
-- ============================================================================
-- StockLens Phase 4.2 - Growth, quality and balance-sheet liquidity results
-- ============================================================================
--
-- Scope
-- -----
-- This migration is **purely additive**. It creates the four result tables that
-- the Phase 4.2 calculation layer writes, and nothing else. It does NOT:
--
--   * alter, drop or rename anything created by migrations 0001-0008;
--   * create any valuation result table (`calc_valuation`,
--     `calc_valuation_inputs`, `calc_valuation_methods`). Valuation is blocked
--     by the unresolved 5-to-11 method mapping and the unsourced risk-free
--     rate, so its tables are deliberately absent;
--   * write to `financial_facts`, `financial_periods`, `prices_daily`,
--     `dividend_facts`, `ingestion_runs` or `ingestion_files`;
--   * touch Supabase Storage.
--
-- The canonical baseline (0001 + 0002 + 0003) and the Phase 4.1 registry
-- (0008) are preserved exactly. No row in any pre-existing table is updated.
--
-- Why these table names
-- ---------------------
-- `Testing/test_run_calculation_v1.py` (line 178) names the growth/quality and
-- liquidity result tables:
--
--     calc_quarterly_growth, calc_quarterly_quality,
--     calc_liquidity_periodic, calc_liquidity_daily, calc_valuation_inputs
--
-- The three quarterly/liquidity names are created here verbatim so the
-- contract is satisfied. `calc_liquidity_daily` (Phase 4.2 has no daily
-- liquidity layer) and the `calc_valuation*` tables are NOT created.
--
-- `calc_annual_growth_quality` is a Phase 4.2 addition, not a contract name.
-- The annual Class-B growth/quality/forensic metrics (Excel
-- `MetricsClassification` B7-B20 and `FinancialHealth` B16-B17) are annual
-- series metrics, and storing them in `calc_quarterly_*` would mislabel their
-- period type. It is created so those results have an honest home.
--
-- Provenance
-- ----------
-- Every result row carries `calculation_run_id` and `methodology_version_id`,
-- both NOT NULL, so a value can always be traced back to the run and the
-- versioned methodology/parameter registry that produced it (Phase 4.1,
-- migration 0008). `flags` records the explicit edge-case semantics
-- (DENOMINATOR_ZERO, NEGATIVE_BASE, QUARTERLY_COMPARISON_MISSING,
-- STATEMENT_SCOPE_UNKNOWN, INVENTORY_MISSING, NEGATIVE_DENOMINATOR, ...) so a
-- refused or unavailable value stays queryable instead of being silently
-- absent.
--
-- `value_numeric` is nullable on purpose: a row exists for every metric the
-- layer evaluated, including the ones it could not compute. A NULL value with
-- `calculation_status = 'UNAVAILABLE'` means an input was missing; a NULL value
-- with `calculation_status = 'NOT_CALCULABLE'` means a documented guard refused
-- the division. Neither is ever substituted with a guess.
-- ============================================================================


-- ============================================================================
-- Shared shape
-- ============================================================================
-- All four tables share one column layout and one idempotency rule so a reader
-- only has to learn the contract once.
--
-- Idempotency: the unique key is
--   (calculation_run_id, instrument_id, financial_period_id, metric_code)
-- and the run itself is already deduplicated by `calculation_runs.idempotency_key`
-- (migration 0008), so re-running an identical calculation cannot duplicate a
-- result row. `financial_period_id` is nullable because an annual
-- series-level metric (for example a full-history revenue CAGR) is anchored to
-- the instrument rather than to a single period; NULLS NOT DISTINCT is
-- therefore required so the key still rejects a duplicate instrument-level row.


-- ============================================================================
-- 1. Quarterly growth results
-- ============================================================================
-- One row per (quarter, growth metric). Phase 4.2 writes the five `*_QOQ` rows
-- per quarter: REVENUE_QOQ, EARNINGS_QOQ, EBITDA_QOQ,
-- OPERATING_CASH_FLOW_QOQ, FREE_CASH_FLOW_QOQ.

create table if not exists public.calc_quarterly_growth (
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
  calculation_status text not null
    check (calculation_status in ('VALID', 'NOT_CALCULABLE', 'UNAVAILABLE')),
  availability_status text not null default 'READY',
  flags jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  constraint calc_quarterly_growth_unique
    unique nulls not distinct
    (calculation_run_id, instrument_id, financial_period_id, metric_code)
);

create index if not exists idx_calc_quarterly_growth_run
  on public.calc_quarterly_growth(calculation_run_id);

create index if not exists idx_calc_quarterly_growth_period
  on public.calc_quarterly_growth(instrument_id, observation_date);

create index if not exists idx_calc_quarterly_growth_status
  on public.calc_quarterly_growth(calculation_status);


-- ============================================================================
-- 2. Quarterly quality results
-- ============================================================================
-- One row per (quarter, quality ratio): QUALITY_GROSS_MARGIN,
-- QUALITY_NET_MARGIN, QUALITY_OCF_TO_NET_INCOME, QUALITY_ROE.

create table if not exists public.calc_quarterly_quality (
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
  calculation_status text not null
    check (calculation_status in ('VALID', 'NOT_CALCULABLE', 'UNAVAILABLE')),
  availability_status text not null default 'READY',
  flags jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  constraint calc_quarterly_quality_unique
    unique nulls not distinct
    (calculation_run_id, instrument_id, financial_period_id, metric_code)
);

create index if not exists idx_calc_quarterly_quality_run
  on public.calc_quarterly_quality(calculation_run_id);

create index if not exists idx_calc_quarterly_quality_period
  on public.calc_quarterly_quality(instrument_id, observation_date);

create index if not exists idx_calc_quarterly_quality_status
  on public.calc_quarterly_quality(calculation_status);


-- ============================================================================
-- 3. Periodic balance-sheet liquidity results
-- ============================================================================
-- One row per (period, ratio). Phase 4.2 writes LIQUIDITY_CURRENT_RATIO,
-- LIQUIDITY_QUICK_RATIO, LIQUIDITY_DER_ACTUAL and
-- LIQUIDITY_INTEREST_COVERAGE for both ANNUAL and QUARTER periods, because the
-- balance sheet is a point-in-time statement and is meaningful at both
-- frequencies. This is the contract's `calc_liquidity_periodic`.

create table if not exists public.calc_liquidity_periodic (
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
  calculation_status text not null
    check (calculation_status in ('VALID', 'NOT_CALCULABLE', 'UNAVAILABLE')),
  availability_status text not null default 'READY',
  flags jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  constraint calc_liquidity_periodic_unique
    unique nulls not distinct
    (calculation_run_id, instrument_id, financial_period_id, metric_code)
);

create index if not exists idx_calc_liquidity_periodic_run
  on public.calc_liquidity_periodic(calculation_run_id);

create index if not exists idx_calc_liquidity_periodic_period
  on public.calc_liquidity_periodic(instrument_id, observation_date);

create index if not exists idx_calc_liquidity_periodic_status
  on public.calc_liquidity_periodic(calculation_status);


-- ============================================================================
-- 4. Annual growth / quality / forensic results
-- ============================================================================
-- One row per (annual period, metric) for the annual Class-B series metrics that
-- have no quarterly counterpart:
--
--   GROWTH_REVENUE_CAGR_LONG, GROWTH_REVENUE_CAGR_SHORT, GROWTH_REVENUE_YOY,
--   GROWTH_REVENUE_COV, GROWTH_EPS_CAGR_LONG, GROWTH_EPS_CAGR_SHORT,
--   GROWTH_CURRENT_ASSET_YOY, GROWTH_ASSET_GROWTH_GAP,
--   QUALITY_NWC_TO_REVENUE, QUALITY_NWC_INTENSITY_CHANGE,
--   QUALITY_REVENUE_MOMENTUM, FORENSIC_DEBT_GROWTH_GAP, FORENSIC_MARGIN_SPIKE
--
-- These are series metrics over the annual history, so mixing them into
-- `calc_quarterly_growth` would mislabel their period type. This table is a
-- Phase 4.2 addition, not a forward-contract name.

create table if not exists public.calc_annual_growth_quality (
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
  calculation_status text not null
    check (calculation_status in ('VALID', 'NOT_CALCULABLE', 'UNAVAILABLE')),
  availability_status text not null default 'READY',
  flags jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  constraint calc_annual_growth_quality_unique
    unique nulls not distinct
    (calculation_run_id, instrument_id, financial_period_id, metric_code)
);

create index if not exists idx_calc_annual_growth_quality_run
  on public.calc_annual_growth_quality(calculation_run_id);

create index if not exists idx_calc_annual_growth_quality_period
  on public.calc_annual_growth_quality(instrument_id, observation_date);

create index if not exists idx_calc_annual_growth_quality_status
  on public.calc_annual_growth_quality(calculation_status);


-- ============================================================================
-- 5. Row level security and grants
-- ============================================================================
-- Mirrors migration 0008: RLS is enabled and only `service_role` may read or
-- write. The browser-facing anon key gets no grant, so a client cannot read
-- calculation results directly from these tables; results are served through
-- the application layer, which is where unit normalisation happens
-- (blueprint rule U-2).

alter table public.calc_quarterly_growth enable row level security;
alter table public.calc_quarterly_quality enable row level security;
alter table public.calc_liquidity_periodic enable row level security;
alter table public.calc_annual_growth_quality enable row level security;

grant select, insert, update on table public.calc_quarterly_growth to service_role;
grant select, insert, update on table public.calc_quarterly_quality to service_role;
grant select, insert, update on table public.calc_liquidity_periodic to service_role;
grant select, insert, update on table public.calc_annual_growth_quality to service_role;


-- ============================================================================
-- 6. Post-create verification
-- ============================================================================
-- Fails the migration if a result table did not end up with the exact shared
-- shape, so a partial create cannot pass silently. It also asserts that no
-- valuation result table exists, because Phase 4.2 must not create one.

do $$
declare
  missing integer;
  valuation_tables integer;
begin
  select count(*) into missing
  from (values
    ('calc_quarterly_growth'),
    ('calc_quarterly_quality'),
    ('calc_liquidity_periodic'),
    ('calc_annual_growth_quality')
  ) as expected(name)
  where not exists (
    select 1
    from information_schema.tables t
    where t.table_schema = 'public' and t.table_name = expected.name
  );

  if missing > 0 then
    raise exception 'CALC_RESULT_TABLE_MISSING: %', missing;
  end if;

  -- Every result table must carry the calculation_status vocabulary check and
  -- the provenance columns, so a value can never be stored without a run and a
  -- methodology version.
  select count(*) into missing
  from (values
    ('calc_quarterly_growth'),
    ('calc_quarterly_quality'),
    ('calc_liquidity_periodic'),
    ('calc_annual_growth_quality')
  ) as expected(name)
  where not exists (
    select 1
    from information_schema.columns c
    where c.table_schema = 'public'
      and c.table_name = expected.name
      and c.column_name = 'calculation_status'
      and c.is_nullable = 'NO'
  )
  or not exists (
    select 1
    from information_schema.columns c
    where c.table_schema = 'public'
      and c.table_name = expected.name
      and c.column_name = 'methodology_version_id'
      and c.is_nullable = 'NO'
  );

  if missing > 0 then
    raise exception 'CALC_RESULT_TABLE_SHAPE_INVALID: %', missing;
  end if;

  select count(*) into valuation_tables
  from information_schema.tables
  where table_schema = 'public'
    and table_name in (
      'calc_valuation', 'calc_valuation_inputs', 'calc_valuation_methods'
    );

  if valuation_tables > 0 then
    raise exception 'VALUATION_TABLE_MUST_NOT_EXIST_IN_PHASE_4_2: %', valuation_tables;
  end if;
end
$$;




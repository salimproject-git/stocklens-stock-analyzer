-- 0013_projection_scenarios.sql
-- ============================================================================
-- Store user/workbook forecasts separately from canonical actual financial data.
--
-- Historical values remain in financial_periods + financial_facts. A projection
-- scenario links to its as-of quarter and stores only assumptions and forecast
-- values, so it cannot overwrite actual observations.
-- ============================================================================

create table public.projection_scenarios (
  id uuid primary key default gen_random_uuid(),
  instrument_id uuid not null references public.instruments(id),
  as_of_financial_period_id uuid not null references public.financial_periods(id),
  scenario_code text not null,
  scenario_version integer not null default 1 check (scenario_version > 0),
  projection_year integer not null check (projection_year between 1900 and 2200),
  as_of_quarter smallint not null check (as_of_quarter between 1 and 4),
  years_available integer not null check (years_available > 0),
  average_dpr_ratio numeric not null check (average_dpr_ratio >= 0),
  manual_dpr_ratio numeric check (manual_dpr_ratio is null or manual_dpr_ratio >= 0),
  projected_shares_outstanding numeric not null check (projected_shares_outstanding > 0),
  status text not null default 'DRAFT'
    check (status in ('DRAFT', 'ACTIVE', 'FAILED')),
  source_name text not null,
  source_reference text not null default '',
  input_hash text not null check (input_hash ~ '^[0-9a-f]{64}$'),
  historical_validation jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (instrument_id, scenario_code, scenario_version)
);

create table public.projection_values (
  id uuid primary key default gen_random_uuid(),
  scenario_id uuid not null references public.projection_scenarios(id),
  metric_code text not null check (metric_code in (
    'REVENUE',
    'COST_OF_REVENUE',
    'INTEREST_EXPENSE_NON_OPERATING',
    'EARNINGS',
    'OPERATING_CASH_FLOW',
    'POTENTIAL_DPS',
    'TOTAL_CURRENT_ASSET',
    'CURRENT_LIABILITIES',
    'TOTAL_LIABILITIES',
    'TOTAL_EQUITY'
  )),
  projection_year integer not null check (projection_year between 1900 and 2200),
  period_label text not null,
  value_numeric numeric not null,
  unit_code text not null check (unit_code in ('IDR', 'IDR_PER_SHARE')),
  source_kind text not null default 'WORKBOOK_INPUT'
    check (source_kind in ('WORKBOOK_INPUT', 'WORKBOOK_FORMULA_OUTPUT')),
  source_display_value text not null,
  source_note text not null default '',
  created_at timestamptz not null default now(),
  unique (scenario_id, metric_code)
);

create index idx_projection_scenarios_instrument_year
  on public.projection_scenarios(instrument_id, projection_year, as_of_quarter);

create index idx_projection_values_scenario_period
  on public.projection_values(scenario_id, projection_year, metric_code);

alter table public.projection_scenarios enable row level security;
alter table public.projection_values enable row level security;

-- Forecast scenarios are currently managed server-side only. Do not make them
-- directly readable/writable by browser roles until application policies exist.
revoke all on table public.projection_scenarios from public, anon, authenticated;
revoke all on table public.projection_values from public, anon, authenticated;
grant select, insert, update on table public.projection_scenarios to service_role;
grant select, insert on table public.projection_values to service_role;

do $$
begin
  if not exists (
    select 1 from information_schema.tables
    where table_schema = 'public' and table_name = 'projection_scenarios'
  ) or not exists (
    select 1 from information_schema.tables
    where table_schema = 'public' and table_name = 'projection_values'
  ) then
    raise exception 'PROJECTION_TABLE_CREATION_FAILED';
  end if;

  if not (
    select c.relrowsecurity
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relname = 'projection_scenarios'
  ) or not (
    select c.relrowsecurity
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relname = 'projection_values'
  ) then
    raise exception 'PROJECTION_RLS_NOT_ENABLED';
  end if;
end
$$;
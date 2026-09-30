-- 0024_metrics_classification_results.sql
-- ============================================================================
-- Persist the MetricsClassification (stock-type classifier) output.
--
-- Why this table exists
-- ---------------------
-- `classify_metrics_classification()` (calculate_quarterly_growth_quality.py)
-- already implements the six workbook rules, the score ladder and the Energy
-- override, and its thresholds are seeded in `calculation_parameters`. What was
-- missing was somewhere to store the result, so `populate_growth_quality.py`
-- had to report "Classification final: not written". Without a stored type,
-- `calculate_valuation.py --stock-type` stays a manual input.
--
-- Shape notes
-- -----------
-- * No `financial_period_id`: the classifier is an as-of snapshot over the
--   trailing annual history, not a per-period series. That matches the existing
--   "series vs snapshot" split documented in 0009.
-- * `classification_code` holds the text enum for
--   CLASSIFICATION_SYSTEM_RECOMMENDATION / CLASSIFICATION_FINAL_TYPE; the six
--   rule rows and CLASSIFICATION_CONFIDENCE keep using `value_numeric`.
-- * `manual_override` records the workbook's `B81` input when supplied, so a
--   reviewer can always tell a rule-derived type from an overridden one.
--
-- Nothing here touches existing tables or data.
-- ============================================================================

begin;

create table if not exists public.calc_metrics_classification (
  id uuid primary key default gen_random_uuid(),
  calculation_run_id uuid not null
    references public.calculation_runs(id),
  methodology_version_id uuid not null
    references public.methodology_versions(id),
  instrument_id uuid not null
    references public.instruments(id),
  metric_code text not null,
  observation_date date,
  value_numeric numeric,
  classification_code text,
  manual_override text,
  calculation_status text not null
    check (calculation_status in ('VALID', 'NOT_CALCULABLE', 'UNAVAILABLE')),
  availability_status text not null default 'READY',
  flags jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  constraint calc_metrics_classification_unique
    unique nulls not distinct
    (calculation_run_id, instrument_id, metric_code)
);

create index if not exists idx_calc_metrics_classification_run
  on public.calc_metrics_classification(calculation_run_id);

create index if not exists idx_calc_metrics_classification_instrument
  on public.calc_metrics_classification(instrument_id, observation_date);

create index if not exists idx_calc_metrics_classification_type
  on public.calc_metrics_classification(classification_code);

-- ============================================================================
-- Row level security and grants
-- ============================================================================
-- Mirrors 0008/0009: only `service_role` may read or write. The browser never
-- reads this table directly; the research RPC is the only exposed surface.

alter table public.calc_metrics_classification enable row level security;

grant select, insert, update on table public.calc_metrics_classification to service_role;

comment on table public.calc_metrics_classification is
  'MetricsClassification snapshot per calculation run: six stock-type rule flags, SYSTEM_RECOMMENDATION, FINAL_TYPE, and CONFIDENCE. Final type is rule-derived unless manual_override is recorded.';

-- ============================================================================
-- Post-create verification
-- ============================================================================

do $$
declare
  missing integer;
begin
  select count(*) into missing
  from (values ('calc_metrics_classification')) as expected(name)
  where not exists (
    select 1
    from information_schema.tables t
    where t.table_schema = 'public' and t.table_name = expected.name
  );

  if missing > 0 then
    raise exception 'CALC_RESULT_TABLE_MISSING: %', missing;
  end if;

  -- Provenance columns must be NOT NULL so a classification can never be stored
  -- without the run and methodology version that produced it.
  select count(*) into missing
  from (values
    ('calculation_status'),
    ('methodology_version_id'),
    ('calculation_run_id'),
    ('instrument_id')
  ) as expected(column_name)
  where not exists (
    select 1
    from information_schema.columns c
    where c.table_schema = 'public'
      and c.table_name = 'calc_metrics_classification'
      and c.column_name = expected.column_name
      and c.is_nullable = 'NO'
  );

  if missing > 0 then
    raise exception 'CALC_RESULT_TABLE_SHAPE_INVALID: %', missing;
  end if;

  -- The two text-enum rows and the override need their own columns.
  select count(*) into missing
  from (values ('classification_code'), ('manual_override')) as expected(column_name)
  where not exists (
    select 1
    from information_schema.columns c
    where c.table_schema = 'public'
      and c.table_name = 'calc_metrics_classification'
      and c.column_name = expected.column_name
  );

  if missing > 0 then
    raise exception 'CALC_CLASSIFICATION_COLUMN_MISSING: %', missing;
  end if;

  -- RLS must be on, and the browser roles must not hold any grant.
  if not exists (
    select 1
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relname = 'calc_metrics_classification'
      and c.relrowsecurity
  ) then
    raise exception 'CALC_CLASSIFICATION_RLS_DISABLED';
  end if;

  if has_table_privilege('anon', 'public.calc_metrics_classification', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_metrics_classification', 'SELECT') then
    raise exception 'CALC_CLASSIFICATION_RAW_GRANTS_MUST_REMAIN_PRIVATE';
  end if;
end
$$;

commit;

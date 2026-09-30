-- 0020_risk_free_rate_reference.sql
-- ============================================================================
-- Reference table for the risk-free rate used by the DDM and Discounted
-- Earnings methods (workbook `DataInput!B11`, "Risk Free Rate (Yield SBN 10Y)").
--
-- Why a table instead of a constant
-- ---------------------------------
-- `calculation_parameter_catalogue.risk_free_rate` records the workbook literal
-- `0.0633` and is deliberately flagged `UNRESOLVED_SOURCE`, because the workbook
-- does not say where the yield came from or on which date it was observed. The
-- valuation engine therefore refuses to run DDM / Discounted Earnings unless a
-- rate *and* its source are supplied explicitly.
--
-- This table is the explicit, auditable home for that rate. It is versioned and
-- dated, so:
--   * the workbook constant is preserved verbatim with its exact provenance;
--   * a real, dated market observation can be added later without deleting the
--     workbook row, and the resolver prefers the newest dated observation.
--
-- No canonical or Sectors raw source exists for the 10Y SBN yield, so every row
-- must carry a `source_reference`. Nothing here is inferred or interpolated.
-- ============================================================================

begin;

create table public.risk_free_rate_reference (
  id uuid primary key default gen_random_uuid(),
  reference_version text not null,
  rate_code text not null,
  -- NULL means "the source did not record an observation date" (true for the
  -- workbook constant). A dated MARKET_OBSERVATION row always sets it.
  observation_date date,
  rate numeric not null check (rate > -1 and rate < 1),
  currency_code text not null default 'IDR',
  tenor_years integer check (tenor_years is null or tenor_years > 0),
  source_kind text not null check (source_kind in ('WORKBOOK_CONSTANT', 'MARKET_OBSERVATION')),
  source_name text not null,
  source_reference text not null,
  -- At most one default per (reference_version, rate_code); enforced by the
  -- partial unique index below.
  is_default boolean not null default false,
  notes text not null default '',
  created_at timestamptz not null default now(),
  -- PostgreSQL 15+ `nulls not distinct` keeps the workbook constant unique even
  -- though its observation_date is NULL.
  unique nulls not distinct (reference_version, rate_code, observation_date)
);

create unique index uq_risk_free_rate_reference_default
  on public.risk_free_rate_reference(reference_version, rate_code)
  where is_default;

create index idx_risk_free_rate_reference_lookup
  on public.risk_free_rate_reference(reference_version, rate_code, observation_date desc nulls last);

comment on table public.risk_free_rate_reference is
  'Versioned, dated risk-free rate observations for DDM and Discounted Earnings. Workbook constant (6,33% SBN 10Y) is seeded with explicit provenance; add dated MARKET_OBSERVATION rows to supersede it.';
comment on column public.risk_free_rate_reference.observation_date is
  'Yield observation date. NULL only for a WORKBOOK_CONSTANT row whose source never recorded a date.';
comment on column public.risk_free_rate_reference.source_kind is
  'WORKBOOK_CONSTANT = literal copied from the workbook; MARKET_OBSERVATION = dated observation from a named market source.';

-- The workbook constant, preserved exactly. `is_default` lets the valuation
-- script resolve a rate without the operator retyping it, while the note makes
-- clear that it is not a dated market observation.
insert into public.risk_free_rate_reference
  (reference_version, rate_code, observation_date, rate, currency_code, tenor_years,
   source_kind, source_name, source_reference, is_default, notes)
values
  ('1.0.0', 'SBN_10Y_YIELD', null, 0.0633, 'IDR', 10,
   'WORKBOOK_CONSTANT', 'Excel workbook DataInput!B11',
   'DataInput!B11 - "Risk Free Rate (Yield SBN 10Y)" = 6,33%',
   true,
   'Workbook literal 0.0633, used by ValuationCurrent!B28 (WACC = RiskFree + 6%) and B29 (Disc_Rate = RiskFree + 4%). The workbook records no observation date and names no market source, so this row is explicitly NOT a dated observation. Insert a MARKET_OBSERVATION row with a real date and source to supersede it.');

alter table public.risk_free_rate_reference enable row level security;

-- Valuation assumptions stay server-side, like the other reference tables.
revoke all on table public.risk_free_rate_reference from public, anon, authenticated;
grant select, insert, update on table public.risk_free_rate_reference to service_role;

do $verify$
begin
  if not exists (
    select 1 from information_schema.tables
    where table_schema = 'public' and table_name = 'risk_free_rate_reference'
  ) then
    raise exception 'RISK_FREE_RATE_REFERENCE_TABLE_MISSING';
  end if;

  if not (
    select c.relrowsecurity
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relname = 'risk_free_rate_reference'
  ) then
    raise exception 'RISK_FREE_RATE_REFERENCE_RLS_NOT_ENABLED';
  end if;

  if has_table_privilege('anon', 'public.risk_free_rate_reference', 'SELECT')
    or has_table_privilege('authenticated', 'public.risk_free_rate_reference', 'SELECT') then
    raise exception 'RISK_FREE_RATE_REFERENCE_MUST_STAY_PRIVATE';
  end if;

  if not has_table_privilege('service_role', 'public.risk_free_rate_reference', 'SELECT') then
    raise exception 'RISK_FREE_RATE_REFERENCE_SERVICE_ROLE_SELECT_MISSING';
  end if;

  -- Exactly one default row must exist for the active reference version, so the
  -- valuation script can always resolve a rate without guessing.
  if (select count(*) from public.risk_free_rate_reference
      where reference_version = '1.0.0' and rate_code = 'SBN_10Y_YIELD' and is_default) <> 1 then
    raise exception 'RISK_FREE_RATE_REFERENCE_DEFAULT_ROW_INVALID';
  end if;

  -- The workbook literal must be stored exactly as the workbook shows it.
  if (select rate from public.risk_free_rate_reference
      where reference_version = '1.0.0' and rate_code = 'SBN_10Y_YIELD' and is_default) <> 0.0633 then
    raise exception 'RISK_FREE_RATE_REFERENCE_WORKBOOK_VALUE_DRIFT';
  end if;
end
$verify$;

commit;

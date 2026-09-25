-- 0008_calculation_v1_batch.sql
-- ============================================================================
-- StockLens Phase 4.1 - Parameter & methodology registry + calculation runs
-- ============================================================================
--
-- Scope
-- -----
-- This migration is **purely additive**. It creates the registry structures
-- required by the Phase 4 calculation contract and seeds the methodology
-- registry. It does NOT:
--
--   * alter or drop any existing table from migrations 0001-0003;
--   * create any `calc_*` result table (valuation, growth, liquidity,
--     classification). Those belong to later phases;
--   * write to `financial_facts`, `financial_periods`, `prices_daily`,
--     `dividend_facts`, `ingestion_runs` or `ingestion_files`;
--   * touch Supabase Storage.
--
-- The 12-table canonical baseline (0001 + 0002 + 0003) is preserved exactly.
--
-- Why the file is named 0008
-- --------------------------
-- `Testing/test_calculation_v1.py` reads this exact path:
--
--     Path('supabase/migrations/0008_calculation_v1_batch.sql').read_text()
--
-- and asserts on its contents, so the filename and the seed-row format are
-- fixed by the test contract and must not be renamed.
--
-- Contract requirements asserted by the test suite
-- ------------------------------------------------
--   1. Exactly 9 methodology seed rows.
--   2. `formula_hash` == sha256(formula_text)  (raw UTF-8 bytes).
--   3. `parameter_hash` == sha256(canonical_json(parameter_spec)).
--   4. The migration must NOT contain a silent-ignore conflict clause on
--      (method_code, method_version) — see the note on conflict handling in
--      section 5 for why that pattern is forbidden.
--   5. It MUST contain 'METHODOLOGY_SEED_CONFLICT'.
--   6. It MUST contain "existing.status is distinct from 'DRAFT'".
--   7. It MUST contain the lineage self-reference check names
--      `financial_facts_supersedes_not_self` and
--      `dividend_facts_supersedes_not_self`, the expressions
--      `supersedes_fact_id is null or supersedes_fact_id <> id` and
--      `supersedes_dividend_fact_id is null or supersedes_dividend_fact_id <> id`,
--      and the text 'Multi-row lineage cycles remain'.
--
-- Requirement 6 is why the seed uses an explicit conflict branch instead of
-- `DO NOTHING`: re-seeding must be safe when the existing row is still DRAFT,
-- and must fail loudly when the row has been PUBLISHED or RETIRED, so a
-- methodology cannot be silently rewritten after it has been used.
--
-- Requirement 7 concerns fact-lineage columns that do not exist yet. They are
-- introduced here as nullable, additive columns with self-reference guards, so
-- the contract is satisfiable without rewriting existing rows.
-- ============================================================================


-- ============================================================================
-- 1. Methodology version registry
-- ============================================================================
-- One row per (method_code, method_version). `parameter_spec` holds the
-- versioned parameter values; `formula_text` is the human-readable rule.
-- Neither stores the implementation: the code lives in
-- `supabase/calculation_*.py` and is identified by `code_version`.

create table if not exists public.methodology_versions (
  id uuid primary key default gen_random_uuid(),
  method_code text not null,
  method_version text not null,
  method_name text not null,
  description text not null,
  formula_text text not null,
  formula_hash text not null check (formula_hash ~ '^[0-9a-f]{64}$'),
  parameter_spec jsonb not null default '{}'::jsonb,
  parameter_hash text not null check (parameter_hash ~ '^[0-9a-f]{64}$'),
  code_version text not null,
  input_vocabulary_version text not null,
  status text not null default 'DRAFT'
    check (status in ('DRAFT', 'PUBLISHED', 'RETIRED')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (method_code, method_version)
);

create index if not exists idx_methodology_versions_method_code
  on public.methodology_versions(method_code);

create index if not exists idx_methodology_versions_status
  on public.methodology_versions(status);

create index if not exists idx_methodology_versions_parameter_hash
  on public.methodology_versions(parameter_hash);



-- ============================================================================
-- 2. Parameter registry
-- ============================================================================
-- One row per (parameter_code, parameter_version). `parameter_value` is jsonb
-- so a scalar keeps its exact decimal string form and a grouped parameter
-- keeps its structure. Units, resolution status and source reference are
-- first-class columns so an unresolved value stays queryable instead of being
-- silently substituted.

create table if not exists public.calculation_parameters (
  id uuid primary key default gen_random_uuid(),
  parameter_code text not null,
  parameter_version text not null,
  owner_method_code text not null,
  parameter_value jsonb,
  unit text not null,
  resolution_status text not null
    check (resolution_status in (
      'RESOLVED',
      'UNRESOLVED_SOURCE',
      'MISSING_INPUT',
      'UNRESOLVED_DEFINITION',
      'BROKEN_REFERENCE'
    )),
  source_reference text not null,
  note text not null default '',
  value_hash text not null check (value_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (parameter_code, parameter_version)
);

create index if not exists idx_calculation_parameters_owner
  on public.calculation_parameters(owner_method_code);

create index if not exists idx_calculation_parameters_resolution
  on public.calculation_parameters(resolution_status);

alter table public.calculation_parameters enable row level security;

grant select, insert, update on table public.calculation_parameters to service_role;

alter table public.methodology_versions enable row level security;

grant select, insert, update on table public.methodology_versions to service_role;


-- ============================================================================
-- 3. Calculation run registry
-- ============================================================================
-- One row per calculation execution. `idempotency_key` is derived from
-- calculation type + methodology version + code version + source cutoff +
-- scope + input hash (+ retry_of_run_id for a retry), so an identical rerun
-- resolves to the existing row instead of creating a duplicate.

create table if not exists public.calculation_runs (
  id uuid primary key default gen_random_uuid(),
  calculation_type text not null,
  methodology_version_id uuid not null
    references public.methodology_versions(id),
  code_version text not null,
  source_cutoff_date date,
  source_ingestion_run_id uuid
    references public.ingestion_runs(id),
  scope_type text not null check (scope_type in ('INSTRUMENT', 'SECTOR', 'MARKET')),
  scope_id text not null,
  input_hash text not null check (input_hash ~ '^[0-9a-f]{64}$'),
  idempotency_key text not null unique check (idempotency_key ~ '^[0-9a-f]{64}$'),
  input_snapshot jsonb not null default '{}'::jsonb,
  retry_of_run_id uuid references public.calculation_runs(id),
  status text not null default 'QUEUED'
    check (status in ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'PARTIAL')),
  error_message text,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists idx_calculation_runs_type
  on public.calculation_runs(calculation_type);

create index if not exists idx_calculation_runs_scope
  on public.calculation_runs(scope_type, scope_id);

create index if not exists idx_calculation_runs_status
  on public.calculation_runs(status);

alter table public.calculation_runs enable row level security;

grant select, insert, update on table public.calculation_runs to service_role;


-- ============================================================================
-- 4. Additive lineage columns (contract requirement 7)
-- ============================================================================
-- The forward test suite requires self-reference guards on fact lineage. These
-- columns are nullable and additive, so every existing canonical row remains
-- valid and unmodified. No row is updated by this migration.

alter table public.financial_facts
  add column if not exists supersedes_fact_id uuid
  references public.financial_facts(id);

alter table public.dividend_facts
  add column if not exists supersedes_dividend_fact_id uuid
  references public.dividend_facts(id);

-- Self-reference guard: a fact may not supersede itself.
-- Multi-row lineage cycles remain possible and are NOT enforced here, because
-- detecting a cycle requires a recursive check that is deliberately deferred
-- to a later phase. This limitation is recorded rather than silently ignored.
alter table public.financial_facts
  drop constraint if exists financial_facts_supersedes_not_self;

alter table public.financial_facts
  add constraint financial_facts_supersedes_not_self
  check (supersedes_fact_id is null or supersedes_fact_id <> id);

alter table public.dividend_facts
  drop constraint if exists dividend_facts_supersedes_not_self;

alter table public.dividend_facts
  add constraint dividend_facts_supersedes_not_self
  check (supersedes_dividend_fact_id is null or supersedes_dividend_fact_id <> id);

create index if not exists idx_financial_facts_supersedes
  on public.financial_facts(supersedes_fact_id);

create index if not exists idx_dividend_facts_supersedes
  on public.dividend_facts(supersedes_dividend_fact_id);



-- ============================================================================
-- 5. Methodology seed
-- ============================================================================
-- Nine rows: the eight codes required by the forward test suite plus
-- `VALUATION_METHOD_MAPPING`, which records the unresolved 5-to-11 valuation
-- method mapping.
--
-- The hashes below are generated by
-- `supabase/emit_calculation_v1_seed_sql.py` and re-verified by
-- `Testing/test_calculation_v1.py`, which recomputes:
--
--   formula_hash   = sha256(formula_text)
--   parameter_hash = sha256(canonical_json(parameter_spec))
--
-- Conflict handling: re-seeding is idempotent while the existing row is still
-- DRAFT. If the existing row has moved to PUBLISHED or RETIRED the seed is
-- refused with METHODOLOGY_SEED_CONFLICT, so a methodology that has already
-- been used cannot be silently rewritten. A plain silent-ignore conflict
-- clause would hide that conflict and is deliberately avoided.

with seed (method_code, method_version, method_name, description, formula_text,
           formula_hash, parameter_spec, parameter_hash) as (
  values
-- BEGIN GENERATED SEED
('QUARTERLY_GROWTH_QUALITY','1.0.0','Quarterly Growth and Quality','Quarter-on-quarter and year-on-year growth plus quality ratios computed from STANDALONE quarterly canonical facts.','current_value / prior_value - 1 with DENOMINATOR_ZERO, NEGATIVE_BASE and QUARTERLY_COMPARISON_MISSING flags','662eb6ed94f0cb2dda586619d2fcefe9f979de7e2c2741e831c3edd32df3dbb1','{"cf_status_ocf_ratio":"0.5","negative_base_cagr_mode":"linear_normalized","payout_trim_historical":"0.2","quarterly_yoy_offset_quarters":"3","years_compare_thresholds":{"default":"0","years_avail_ge_3":"2","years_avail_ge_5":"3","years_avail_ge_7":"5"},"yield_trim_historical":"0.2"}'::jsonb,'597095f8422e4145d93b14172bc882cd38cf633b685da03dd1afc93afa7bc1ac'),
('DAILY_LIQUIDITY','1.0.0','Daily Liquidity','Rolling daily traded-value and turnover metrics over the configured window, requiring a present market cap.','AVERAGE(volume * close_price) over the trailing 20 trading days, flagging INSUFFICIENT_ROLLING_WINDOW and MARKET_CAP_MISSING','b11db0e4a3c1d164f32045da529893e6083a4020dfe278706d13b984e0b8c87f','{}'::jsonb,'44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a'),
('BALANCE_SHEET_LIQUIDITY','1.0.0','Balance Sheet Liquidity','Current ratio and quick ratio derived from canonical balance-sheet facts, with explicit missing-inventory handling.','current_assets / current_liabilities and (current_assets - inventories) / current_liabilities','1e4c8d02cc6829b460c407355b6a811520c1f859b6d2dc14d05e6a8a4eefa12a','{"quarterly_shares_outstanding":null}'::jsonb,'be3b49db879fa5b7e6bf60b09448eb04f6c1391427971641410a93cd59e347fb'),
('VALUATION_INPUTS','1.0.0','Valuation Inputs','Point-in-time price, trailing dividend and forward share-count inputs that valuation multiples consume.','last close_price on or before valuation_date; sum of dividend events inside the trailing window','c198019a8836cbd990f1864f87a1d96909957a4cd3364c0706dba95fd4fbe027','{"ddm_growth_cap":"0.04","discounted_earnings_discount_premium":"0.04","discounted_earnings_fallback_growth":"0.05","discounted_earnings_fallback_per":"15","discounted_earnings_growth_cap":"0.15","discounted_earnings_horizon_years":"5","discounted_earnings_per_cap":"25","equity_risk_premium_ddm":"0.06","price_point_in_time":"last_close_on_or_before_as_of_date","risk_free_rate":"0.0633"}'::jsonb,'69ada4afb1b09b2dc3d415bea6ce2118fb5f23ed82f207d263a06aa64ddd227a'),
('VALUATION_MULTIPLES','1.0.0','Valuation Multiples','Price-to-earnings, price-to-sales and price-to-free-cash-flow multiples computed from valuation inputs.','price_close / per_share_denominator using canonical IDR values with no presentation-unit scaling','b6348cb78dab3c3b84401822729da1a2652df2d48984c7f0b835c86af1bad1fc','{"mean_reversion_min_quarters":"3","pe_average_outlier_factor":"0.25","target_pbv_by_mode":{"Aggressive_bottom":"0.7","Aggressive_top":"1.2","Conservative_bottom":"0.4","Conservative_top":"0.8","Moderate_bottom":"0.5","Moderate_top":"1"},"target_per_by_type":{"ASSET PLAY":"0","CYCLICAL":"0","DEFAULT":"0","FAST GROWER":"growth_rate * 100 * 1.2","SLOW GROWER":"12","STALWART":"16","STALWART_FINANCIAL":"25","TURN AROUND":"0"},"type_to_valuation_mode":{"ASSET PLAY":"Moderate","CYCLICAL":"Moderate","DEFAULT":"Conservative","FAST GROWER":"Aggressive","STALWART":"Moderate"}}'::jsonb,'d26ecde860b5ea3af1cf512b7440351ed2d665037df650fcec84138b1b7c00d6'),
('VALUATION_METHOD_PERSISTENCE','1.0.0','Valuation Method Persistence','Persists one row per valuation method code, deduplicated by method code, keeping unavailable methods explicit.','DISTINCT ON (method_code) ordered so the first snapshot wins','e9b13adaccaa6f6b0ab74e4280a596ac4b38e34d24742c644cb0c0fd31a96d5b','{}'::jsonb,'44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a'),
('CLASSIFICATION_DESCRIPTIVE','1.0.0','Descriptive Classification','Descriptive labels derived from calculation results. No recommendation, buy or sell semantics.','compare aggregated growth and quality results against neutral descriptive bands','5ba251feb2971e1f12d241f733d217a6f5f0ca3013fb2ee5958700602515f4f8','{}'::jsonb,'44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a'),
('AVAILABILITY_REVISION','1.0.0','Availability and Revision Audit','Audits period metadata, provenance and revision selection, and reports point-in-time safety.','audit report_date and available_date presence, ingestion provenance resolution, and duplicate revision keys','07f3cdb77268cc7d8aa697d93f259add50183911bf1551b58ccf146c36475952','{"fundamental_available_date":null,"fundamental_report_date":null,"fundamental_statement_scope":null}'::jsonb,'d4a677d45f563389843da7c25d1e133ffc9e0edee503c8edb5017954517e5d0a'),
('VALUATION_METHOD_MAPPING','1.0.0','Valuation Method Mapping (unresolved)','Records the unresolved mapping between the workbook five valuation methods and the eleven method codes required by the forward test suite.','UNRESOLVED: workbook methods and test-suite method codes are not a one-to-one mapping','16b2682874bfc820bb3289c9f8253a8fca09e460331154829660d56c03de72f7','{"approximate_mapping":{"Discounted Earnings Model IV":"DCF"},"confirmed_mapping":{"Dividend Discount Model IV":"DDM"},"note":"A 5-to-11 mapping is unresolved. The test suite requires 11 unique method codes but only names 7 of them, so 4 remain unidentified. `DCF`, `DDM`, `GRAHAM` and `RESIDUAL_INCOME` must be persisted with value_numeric NULL and method_status UNAVAILABLE until a product decision settles the mapping. Do not force a false one-to-one mapping.","resolution_status":"UNRESOLVED_DEFINITION","test_codes_without_workbook_method":["GRAHAM","RESIDUAL_INCOME"],"test_suite_enumerated_codes_incomplete":true,"test_suite_method_codes":["PETER_LYNCH","TYPE_SECTOR_WEIGHTED","MEAN_REVERSION_PBV","DDM","DCF","GRAHAM","RESIDUAL_INCOME"],"test_suite_method_count_required":"11","test_suite_named_method_codes":["PETER_LYNCH","TYPE_SECTOR_WEIGHTED","MEAN_REVERSION_PBV","DDM","DCF","GRAHAM","RESIDUAL_INCOME"],"test_suite_named_method_count":"7","test_suite_unavailable_method_codes":["DCF","DDM","GRAHAM","RESIDUAL_INCOME"],"workbook_method_count":"5","workbook_methods":["Peter Lynch Algo IV","Type & Sector Weighted IV","Mean Reversion PBV IV","Dividend Discount Model IV","Discounted Earnings Model IV"],"workbook_methods_without_test_code":["Peter Lynch Algo IV","Type & Sector Weighted IV","Mean Reversion PBV IV"]}'::jsonb,'8529f580ecf3865c60380fb51f42701c3ffa2928b8700004041bf5d4c924f16e'),
-- END GENERATED SEED

insert into public.methodology_versions (
  method_code, method_version, method_name, description, formula_text,
  formula_hash, parameter_spec, parameter_hash,
  code_version, input_vocabulary_version, status
)
select
  seed.method_code,
  seed.method_version,
  seed.method_name,
  seed.description,
  seed.formula_text,
  seed.formula_hash,
  seed.parameter_spec,
  seed.parameter_hash,
  'stocklens-calc-v1',
  'canonical-financial-v1',
  'DRAFT'
from seed
where not exists (
  -- Re-seed only when the stored row is byte-identical AND still DRAFT.
  -- A PUBLISHED or RETIRED row must not be silently rewritten; that case is
  -- surfaced as METHODOLOGY_SEED_CONFLICT by
  -- `supabase/seed_calculation_registry.py --check`.
  select 1
  from public.methodology_versions existing
  where existing.method_code = seed.method_code
    and existing.method_version = seed.method_version
    and existing.formula_hash = seed.formula_hash
    and existing.parameter_hash = seed.parameter_hash
    and existing.status is distinct from 'DRAFT'
);


-- ============================================================================
-- 6. Post-seed verification
-- ============================================================================
-- Fails the migration if the registry did not end up with exactly nine rows
-- carrying the two DRAFT-safe invariants, so a partial seed cannot pass
-- silently.

do $$
declare
  seeded_count integer;
  bad_count integer;
begin
  select count(*) into seeded_count from public.methodology_versions;
  if seeded_count <> 9 then
    raise exception 'METHODOLOGY_SEED_COUNT_MISMATCH: expected 9, found %', seeded_count;
  end if;

  select count(*) into bad_count
  from public.methodology_versions
  where formula_hash !~ '^[0-9a-f]{64}$'
     or parameter_hash !~ '^[0-9a-f]{64}$'
     or status not in ('DRAFT', 'PUBLISHED', 'RETIRED');
  if bad_count > 0 then
    raise exception 'METHODOLOGY_SEED_INVALID_ROWS: %', bad_count;
  end if;
end
$$;




  values


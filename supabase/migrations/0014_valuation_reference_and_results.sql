-- 0014_valuation_reference_and_results.sql
-- -----------------------------------------------------------------------------
-- Versioned workbook reference tables and persisted valuation snapshots.
-- Actual financials and projection inputs remain untouched.

create table public.valuation_sector_weights (
  reference_version text not null,
  sector_name text not null,
  w_pe numeric not null check (w_pe >= 0),
  w_pbv numeric not null check (w_pbv >= 0),
  w_ddm numeric not null check (w_ddm >= 0),
  w_graham numeric not null check (w_graham >= 0),
  w_peg numeric not null check (w_peg >= 0),
  source_reference text not null,
  created_at timestamptz not null default now(),
  primary key (reference_version, sector_name)
);

create table public.valuation_type_weights (
  reference_version text not null,
  stock_type text not null,
  w_pe numeric not null check (w_pe >= 0),
  w_pbv numeric not null check (w_pbv >= 0),
  w_ddm numeric not null check (w_ddm >= 0),
  w_graham numeric not null check (w_graham >= 0),
  w_peg numeric not null check (w_peg >= 0),
  source_reference text not null,
  created_at timestamptz not null default now(),
  primary key (reference_version, stock_type)
);

create table public.valuation_type_thresholds (
  reference_version text not null,
  stock_type text not null,
  max_der numeric not null check (max_der >= 0),
  min_cr numeric not null check (min_cr >= 0),
  min_icr numeric not null check (min_icr >= 0),
  source_reference text not null,
  created_at timestamptz not null default now(),
  primary key (reference_version, stock_type)
);

insert into public.valuation_sector_weights
  (reference_version, sector_name, w_pe, w_pbv, w_ddm, w_graham, w_peg, source_reference)
values
  ('1.0.0','Basic Materials',2,2,1,1,1,'User-provided Reference table'),
  ('1.0.0','Consumer Cyclicals',3,1,1,1,2,'User-provided Reference table'),
  ('1.0.0','Consumer Non-Cyclicals',3,2,1,1,1,'User-provided Reference table'),
  ('1.0.0','Energy',1,2,1,2,1,'User-provided Reference table'),
  ('1.0.0','Financials',1,3,2,1,0,'User-provided Reference table'),
  ('1.0.0','Healthcare',3,1,0,1,2,'User-provided Reference table'),
  ('1.0.0','Industrials',2,2,1,1,1,'User-provided Reference table'),
  ('1.0.0','Infrastructures',1,2,1,2,1,'User-provided Reference table'),
  ('1.0.0','Properties & Real Estate',1,3,0,2,0,'User-provided Reference table'),
  ('1.0.0','Technology',3,1,0,1,3,'User-provided Reference table'),
  ('1.0.0','Transportation & Logistic',2,2,1,1,1,'User-provided Reference table'),
  ('1.0.0','Utilities',1,3,3,1,0,'User-provided Reference table');

insert into public.valuation_type_weights
  (reference_version, stock_type, w_pe, w_pbv, w_ddm, w_graham, w_peg, source_reference)
values
  ('1.0.0','Asset Play',0,3,0,2,0,'User-provided Reference table'),
  ('1.0.0','Cyclical',0,10,1,2,0,'User-provided Reference table'),
  ('1.0.0','Fast Grower',3,0,1,1,3,'User-provided Reference table'),
  ('1.0.0','Slow Grower',2,3,3,1,0,'User-provided Reference table'),
  ('1.0.0','Stalwart',3,2,2,1,1,'User-provided Reference table'),
  ('1.0.0','Turn around',0,3,0,2,0,'User-provided Reference table');

insert into public.valuation_type_thresholds
  (reference_version, stock_type, max_der, min_cr, min_icr, source_reference)
values
  ('1.0.0','Slow Grower',0.5,1.5,3,'User-provided Reference table'),
  ('1.0.0','Stalwart',0.8,1.3,3,'User-provided Reference table'),
  ('1.0.0','Fast Grower',1,1.2,2.5,'User-provided Reference table'),
  ('1.0.0','Cyclical',0.3,2,5,'User-provided Reference table'),
  ('1.0.0','Turn around',0.5,1.5,2,'User-provided Reference table'),
  ('1.0.0','Asset Play',0.4,1.5,3,'User-provided Reference table');

-- Current valuation formulas and selectable history windows are versioned
-- independently from the older broad valuation registry entries.
insert into public.methodology_versions (
  method_code, method_version, method_name, description, formula_text,
  formula_text, formula_hash, parameter_spec, parameter_hash, code_version,
  input_vocabulary_version, status
) values (
  'VALUATION_CURRENT',
  '1.0.0',
  'Current Stock Valuation',
  'Five workbook current-valuation methods using a selected active projection scenario, explicit stock type, history windows and versioned reference tables.',
  'Peter Lynch adaptive PER/PBV/liquidation; blended PER/PBV sector-type weights; quarterly PBV mean minus population standard deviation; Gordon DDM; five-year discounted earnings; missing inputs fail closed.',
  '5affb4ab87f89cd7494bac7134bb5a0ae2eda97297cc8517703f61490bd05d93',
  '{"reference_version":"1.0.0","years_compare_thresholds":{"years_avail_ge_7":"5","years_avail_ge_5":"3","years_avail_ge_3":"2","default":"0"},"target_per_by_type":{"SLOW GROWER":{"bottom":"8","top":"12"},"STALWART":{"bottom":"10","top":"16"},"STALWART_FINANCIAL":{"bottom":"15","top":"25"},"FAST GROWER":{"bottom":"growth_rate * 100 * 0.8","top":"growth_rate * 100 * 1.2"},"CYCLICAL":{"bottom":"0","top":"0"},"ASSET PLAY":{"bottom":"0","top":"0"},"TURN AROUND":{"bottom":"0","top":"0"},"DEFAULT":{"bottom":"0","top":"0"}},"target_pbv_by_mode":{"Conservative_bottom":"0.4","Moderate_bottom":"0.5","Aggressive_bottom":"0.7","Conservative_top":"0.8","Moderate_top":"1","Aggressive_top":"1.2"},"type_to_valuation_mode":{"FAST GROWER":"Aggressive","CYCLICAL":"Moderate","ASSET PLAY":"Moderate","STALWART":"Moderate","DEFAULT":"Conservative"},"mean_reversion_min_quarters":"3","pe_average_outlier_factor":"0.25","ddm_growth_cap":"0.04","equity_risk_premium_ddm":"0.06","discounted_earnings_growth_cap":"0.15","discounted_earnings_per_cap":"25","discounted_earnings_horizon_years":"5","discounted_earnings_discount_premium":"0.04","quarterly_shares_policy":"latest_annual_share_count_as_approximation","risk_free_rate":"UNRESOLVED_SOURCE"}'::jsonb,
  'e513c482e00fac37b1e7fa9c9fd6cf2345f4e43c9f1286ae87b294e1861d98af',
  'stocklens-valuation-v1',
  'canonical-financial-v1',
  'DRAFT'
);

create table public.calc_valuation_inputs (
  id uuid primary key default gen_random_uuid(),
  calculation_run_id uuid not null references public.calculation_runs(id),
  methodology_version_id uuid not null references public.methodology_versions(id),
  instrument_id uuid not null references public.instruments(id),
  as_of_financial_period_id uuid not null references public.financial_periods(id),
  projection_scenario_id uuid references public.projection_scenarios(id),
  valuation_date date not null,
  metric_code text not null,
  value_numeric numeric,
  value_text text,
  unit_code text not null,
  calculation_status text not null check
    (calculation_status in ('VALID','APPROXIMATED','NOT_CALCULABLE','UNAVAILABLE')),
  flags jsonb not null default '[]'::jsonb,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (calculation_run_id, instrument_id, as_of_financial_period_id, metric_code)
);

create table public.calc_valuation_methods (
  id uuid primary key default gen_random_uuid(),
  calculation_run_id uuid not null references public.calculation_runs(id),
  methodology_version_id uuid not null references public.methodology_versions(id),
  instrument_id uuid not null references public.instruments(id),
  as_of_financial_period_id uuid not null references public.financial_periods(id),
  projection_scenario_id uuid references public.projection_scenarios(id),
  valuation_date date not null,
  method_code text not null,
  method_name text not null,
  stock_type text not null,
  years_available integer not null check (years_available > 0),
  years_compare integer not null check (years_compare >= 0),
  intrinsic_value numeric,
  current_price numeric,
  gap_ratio numeric,
  verdict text not null check
    (verdict in ('UNDERVALUED','OVERVALUED','AT_FAIR_VALUE','NOT_APPLICABLE')),
  calculation_status text not null check
    (calculation_status in ('VALID','APPROXIMATED','NOT_CALCULABLE','UNAVAILABLE')),
  flags jsonb not null default '[]'::jsonb,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (calculation_run_id, instrument_id, as_of_financial_period_id, method_code)
);

create index idx_calc_valuation_inputs_run
  on public.calc_valuation_inputs(calculation_run_id);
create index idx_calc_valuation_methods_run
  on public.calc_valuation_methods(calculation_run_id);
create index idx_calc_valuation_methods_instrument_date
  on public.calc_valuation_methods(instrument_id, valuation_date desc);

alter table public.valuation_sector_weights enable row level security;
alter table public.valuation_type_weights enable row level security;
alter table public.valuation_type_thresholds enable row level security;
alter table public.calc_valuation_inputs enable row level security;
alter table public.calc_valuation_methods enable row level security;

revoke all on table public.valuation_sector_weights from public, anon, authenticated;
revoke all on table public.valuation_type_weights from public, anon, authenticated;
revoke all on table public.valuation_type_thresholds from public, anon, authenticated;
revoke all on table public.calc_valuation_inputs from public, anon, authenticated;
revoke all on table public.calc_valuation_methods from public, anon, authenticated;

grant select on table public.valuation_sector_weights to service_role;
grant select on table public.valuation_type_weights to service_role;
grant select on table public.valuation_type_thresholds to service_role;
grant select, insert, update on table public.calc_valuation_inputs to service_role;
grant select, insert, update on table public.calc_valuation_methods to service_role;
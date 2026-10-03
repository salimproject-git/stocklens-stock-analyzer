-- Additive separation of fundamental intrinsic values from daily price status.
-- Legacy calculation tables and RPC results remain intact for reconciliation.
begin;

create table public.calc_valuation_fundamental_snapshots (
  id uuid primary key default gen_random_uuid(),
  calculation_run_id uuid not null references public.calculation_runs(id),
  methodology_version_id uuid not null references public.methodology_versions(id),
  instrument_id uuid not null references public.instruments(id),
  as_of_financial_period_id uuid not null references public.financial_periods(id),
  projection_scenario_id uuid references public.projection_scenarios(id),
  snapshot_date date not null,
  historical_price_cutoff date not null,
  stock_type text not null,
  years_available integer not null check (years_available > 0),
  years_compare integer not null check (years_compare >= 0),
  reference_version text not null,
  code_version text not null,
  input_snapshot jsonb not null,
  input_hash text not null check (input_hash ~ '^[0-9a-f]{64}$'),
  idempotency_key text not null check (idempotency_key ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  unique (calculation_run_id, instrument_id),
  unique (instrument_id, idempotency_key)
);

create index idx_calc_valuation_fundamental_latest
  on public.calc_valuation_fundamental_snapshots (instrument_id, snapshot_date desc, created_at desc);

create table public.calc_valuation_fundamental_methods (
  id uuid primary key default gen_random_uuid(),
  snapshot_id uuid not null references public.calc_valuation_fundamental_snapshots(id),
  instrument_id uuid not null references public.instruments(id),
  methodology_version_id uuid not null references public.methodology_versions(id),
  as_of_financial_period_id uuid not null references public.financial_periods(id),
  method_code text not null,
  method_name text not null,
  stock_type text not null,
  intrinsic_value numeric,
  calculation_status text not null check
    (calculation_status in ('VALID','APPROXIMATED','NOT_CALCULABLE','UNAVAILABLE')),
  flags jsonb not null default '[]'::jsonb,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (snapshot_id, method_code)
);

create index idx_calc_valuation_fundamental_methods_snapshot
  on public.calc_valuation_fundamental_methods (snapshot_id, method_code);

create table public.calc_valuation_daily_status (
  id uuid primary key default gen_random_uuid(),
  calculation_run_id uuid not null references public.calculation_runs(id),
  methodology_version_id uuid not null references public.methodology_versions(id),
  snapshot_id uuid not null references public.calc_valuation_fundamental_snapshots(id),
  instrument_id uuid not null references public.instruments(id),
  trading_date date not null,
  current_price numeric not null,
  input_snapshot jsonb not null,
  input_hash text not null check (input_hash ~ '^[0-9a-f]{64}$'),
  idempotency_key text not null check (idempotency_key ~ '^[0-9a-f]{64}$'),
  consensus_verdict text check (consensus_verdict in ('UNDERVALUED','OVERVALUED','N/A')),
  valid_method_count integer not null default 0 check (valid_method_count >= 0),
  undervalued_method_count integer not null default 0 check
    (undervalued_method_count >= 0 and undervalued_method_count <= valid_method_count),
  based_method_code text,
  based_mos numeric,
  based_mos_verdict text check (based_mos_verdict in ('UNDERVALUED','OVERVALUED','N/A')),
  created_at timestamptz not null default now(),
  unique (calculation_run_id, instrument_id),
  unique (instrument_id, idempotency_key)
);

create index idx_calc_valuation_daily_status_latest
  on public.calc_valuation_daily_status (instrument_id, trading_date desc, created_at desc);

create table public.calc_valuation_daily_methods (
  id uuid primary key default gen_random_uuid(),
  daily_status_id uuid not null references public.calc_valuation_daily_status(id),
  snapshot_id uuid not null references public.calc_valuation_fundamental_snapshots(id),
  instrument_id uuid not null references public.instruments(id),
  method_code text not null,
  intrinsic_value numeric,
  current_price numeric not null,
  gap_ratio numeric,
  mos numeric,
  verdict text not null check (verdict in ('UNDERVALUED','OVERVALUED','AT_FAIR_VALUE','NOT_APPLICABLE')),
  calculation_status text not null check
    (calculation_status in ('VALID','APPROXIMATED','NOT_CALCULABLE','UNAVAILABLE')),
  flags jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  unique (daily_status_id, method_code)
);

create index idx_calc_valuation_daily_methods_status
  on public.calc_valuation_daily_methods (daily_status_id, method_code);

alter table public.calc_valuation_fundamental_snapshots enable row level security;
alter table public.calc_valuation_fundamental_methods enable row level security;
alter table public.calc_valuation_daily_status enable row level security;
alter table public.calc_valuation_daily_methods enable row level security;

revoke all on table public.calc_valuation_fundamental_snapshots,
  public.calc_valuation_fundamental_methods,
  public.calc_valuation_daily_status,
  public.calc_valuation_daily_methods from public, anon, authenticated;
grant select, insert, update on table public.calc_valuation_fundamental_snapshots,
  public.calc_valuation_fundamental_methods,
  public.calc_valuation_daily_status,
  public.calc_valuation_daily_methods to service_role;

comment on table public.calc_valuation_fundamental_snapshots is
  'Immutable, idempotent fundamental valuation input snapshots; input_snapshot/hash retain exact dependencies including historical price window and cutoff.';
comment on table public.calc_valuation_fundamental_methods is
  'Intrinsic valuation outputs only; no current daily quote or quote-derived verdict/MoS.';
comment on table public.calc_valuation_daily_status is
  'Daily price comparison summary, tied to the exact fundamental snapshot and calculation run.';
comment on table public.calc_valuation_daily_methods is
  'Daily quote-derived gap, MoS, and verdict per method; intrinsic values reference the immutable fundamental snapshot.';

do $verify$
begin
  if has_table_privilege('anon', 'public.calc_valuation_fundamental_snapshots', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_valuation_fundamental_snapshots', 'SELECT')
    or has_table_privilege('anon', 'public.calc_valuation_fundamental_methods', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_valuation_fundamental_methods', 'SELECT')
    or has_table_privilege('anon', 'public.calc_valuation_daily_status', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_valuation_daily_status', 'SELECT')
    or has_table_privilege('anon', 'public.calc_valuation_daily_methods', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_valuation_daily_methods', 'SELECT') then
    raise exception 'VALUATION_FREQUENCY_RAW_TABLE_BROWSER_GRANT';
  end if;
end
$verify$;

commit;
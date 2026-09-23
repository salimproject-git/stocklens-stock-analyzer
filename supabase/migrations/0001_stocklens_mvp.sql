create extension if not exists pgcrypto;

create table if not exists public.data_sources (
  id uuid primary key default gen_random_uuid(),
  source_code text not null unique,
  source_name text not null,
  base_url text,
  created_at timestamptz not null default now()
);

create table if not exists public.ingestion_runs (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.data_sources(id),
  symbol text not null,
  status text not null check (status in ('RUNNING', 'SUCCESS', 'PARTIAL', 'FAILED')),
  collector_version text,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  error_message text
);

create table if not exists public.raw_ingestion_payloads (
  id uuid primary key default gen_random_uuid(),
  ingestion_run_id uuid not null references public.ingestion_runs(id) on delete cascade,
  endpoint text not null,
  request_key text not null,
  request_params jsonb not null default '{}'::jsonb,
  payload jsonb not null,
  fetched_at timestamptz not null default now(),
  unique (ingestion_run_id, request_key)
);

create table if not exists public.companies (
  id uuid primary key default gen_random_uuid(),
  provider_identity text not null unique,
  legal_name text not null,
  website text,
  headquarters text,
  listing_date date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.instruments (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references public.companies(id),
  exchange_code text not null,
  ticker text not null,
  provider_symbol text not null,
  currency_code text not null default 'IDR',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (exchange_code, ticker),
  unique (provider_symbol)
);

create table if not exists public.sectors (
  id uuid primary key default gen_random_uuid(),
  taxonomy text not null default 'SECTORS_APP',
  sector_name text not null,
  subsector_name text,
  unique (taxonomy, sector_name, subsector_name)
);

create table if not exists public.instrument_sector_classifications (
  id uuid primary key default gen_random_uuid(),
  relationship_key text not null unique,
  instrument_id uuid not null references public.instruments(id) on delete cascade,
  sector_id uuid not null references public.sectors(id),
  effective_from date,
  effective_to date,
  source_payload_id uuid references public.raw_ingestion_payloads(id),
  created_at timestamptz not null default now()
);

create table if not exists public.financial_periods (
  id uuid primary key default gen_random_uuid(),
  instrument_id uuid not null references public.instruments(id) on delete cascade,
  period_type text not null check (period_type in ('ANNUAL', 'QUARTER')),
  period_label text not null,
  period_start date,
  period_end date not null,
  report_date date,
  available_date date,
  period_basis text not null default 'UNKNOWN' check (period_basis in ('STANDALONE', 'YTD', 'UNKNOWN')),
  statement_scope text not null default 'UNKNOWN' check (statement_scope in ('CONSOLIDATED', 'STANDALONE', 'UNKNOWN')),
  source_payload_id uuid references public.raw_ingestion_payloads(id),
  unique (instrument_id, period_type, period_end, statement_scope)
);

create table if not exists public.financial_facts (
  id uuid primary key default gen_random_uuid(),
  financial_period_id uuid not null references public.financial_periods(id) on delete cascade,
  metric_code text not null,
  value_numeric numeric,
  unit_code text not null,
  currency_code text,
  source_field text not null,
  revision_key text not null default 'CURRENT',
  quality_status text not null default 'VALID' check (quality_status in ('VALID', 'MISSING', 'INVALID', 'ESTIMATED')),
  source_payload_id uuid references public.raw_ingestion_payloads(id),
  unique (financial_period_id, metric_code, revision_key)
);

create table if not exists public.prices_daily (
  id uuid primary key default gen_random_uuid(),
  instrument_id uuid not null references public.instruments(id) on delete cascade,
  trading_date date not null,
  open_price numeric,
  high_price numeric,
  low_price numeric,
  close_price numeric,
  volume numeric,
  market_cap numeric,
  currency_code text not null default 'IDR',
  source_payload_id uuid references public.raw_ingestion_payloads(id),
  unique (instrument_id, trading_date)
);

create table if not exists public.dividend_facts (
  id uuid primary key default gen_random_uuid(),
  instrument_id uuid not null references public.instruments(id) on delete cascade,
  fact_type text not null check (fact_type in ('ANNUAL_TOTAL', 'TTM', 'YIELD', 'PAYOUT_RATIO')),
  period_year integer,
  event_date date,
  amount_per_share numeric,
  yield_ratio numeric,
  currency_code text default 'IDR',
  source_label text not null default 'CURRENT',
  source_payload_id uuid references public.raw_ingestion_payloads(id),
  unique (instrument_id, fact_type, period_year, source_label)
);

create index if not exists idx_ingestion_runs_symbol on public.ingestion_runs(symbol);
create index if not exists idx_raw_payloads_run on public.raw_ingestion_payloads(ingestion_run_id);
create index if not exists idx_financial_periods_instrument_end on public.financial_periods(instrument_id, period_end desc);
create index if not exists idx_financial_facts_metric on public.financial_facts(metric_code);
create index if not exists idx_prices_daily_instrument_date on public.prices_daily(instrument_id, trading_date desc);
create index if not exists idx_dividend_facts_instrument_year on public.dividend_facts(instrument_id, period_year desc);

insert into public.data_sources (source_code, source_name, base_url)
values ('SECTORS_APP', 'Sectors.app', 'https://api.sectors.app/v2')
on conflict (source_code) do update
set source_name = excluded.source_name,
    base_url = excluded.base_url;

alter table public.data_sources enable row level security;
alter table public.ingestion_runs enable row level security;
alter table public.raw_ingestion_payloads enable row level security;
alter table public.companies enable row level security;
alter table public.instruments enable row level security;
alter table public.sectors enable row level security;
alter table public.instrument_sector_classifications enable row level security;
alter table public.financial_periods enable row level security;
alter table public.financial_facts enable row level security;
alter table public.prices_daily enable row level security;
alter table public.dividend_facts enable row level security;

-- Tidak ada policy publik pada MVP ini.
-- Worker lokal memakai service_role key yang bypasses RLS.
-- Jangan pernah menaruh service_role key di frontend atau commit ke Git.

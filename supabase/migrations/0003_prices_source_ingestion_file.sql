alter table public.prices_daily
  add column if not exists source_ingestion_file_id uuid
  references public.ingestion_files(id);

create index if not exists idx_prices_daily_source_ingestion_file
  on public.prices_daily(source_ingestion_file_id);

alter table public.prices_daily enable row level security;

grant select, insert, update on table public.prices_daily to service_role;

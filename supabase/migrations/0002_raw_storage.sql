create table if not exists public.ingestion_files (
  id uuid primary key default gen_random_uuid(),
  ingestion_run_id uuid not null references public.ingestion_runs(id) on delete cascade,
  source_file_type text not null,
  storage_bucket text not null,
  storage_path text not null,
  checksum_sha256 text not null,
  record_count integer,
  first_record_date date,
  last_record_date date,
  status text not null check (status in ('UPLOADED', 'SKIPPED', 'FAILED')),
  created_at timestamptz not null default now(),
  unique (ingestion_run_id, storage_path)
);

create index if not exists idx_ingestion_files_run
  on public.ingestion_files(ingestion_run_id);

create index if not exists idx_ingestion_files_storage_path
  on public.ingestion_files(storage_path);

create index if not exists idx_ingestion_files_checksum
  on public.ingestion_files(checksum_sha256);

alter table public.ingestion_files enable row level security;

grant select, insert, update on table public.ingestion_files to service_role;

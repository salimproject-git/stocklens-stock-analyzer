-- 0025_backtest_results.sql
-- ============================================================================
-- Fase 1 backtest historis: daftar kasus + metrik harga.
--
-- Kenapa tabel ini ada
-- --------------------
-- Sheet `Backtest_Result` di workbook berisi 18 baris nilai yang ditempel statis
-- tanpa satu pun sel formula, jadi aturan pembentukannya tidak bisa dibaca dari
-- sheet itu. Yang bisa dibaca adalah makro `BuildHistoricalSnapshot` (daftar
-- kasus) dan rumus kolom-kolomnya (metrik). Keduanya sudah diterjemahkan ke
-- `supabase/backtest_engine.py` dan diverifikasi ke 18 baris nyata.
--
-- Tanpa tabel ini hasilnya hanya hidup di terminal, sehingga tidak bisa dipakai
-- UI dan tidak bisa dibandingkan ulang setelah kode berubah.
--
-- Bentuk tabel
-- ------------
-- Mengikuti pola 0024: `calculation_run_id` + `methodology_version_id` NOT NULL,
-- `calculation_status` dengan check constraint, `flags jsonb`, RLS aktif, dan
-- grant hanya ke `service_role`. Backtest punya tabelnya sendiri dan tidak
-- menyentuh `calc_valuation_*` (docs/BACKTEST_ARCHITECTURE.md bagian 4.3).
--
-- Dua penyimpangan yang disengaja dari sketsa di dokumen arsitektur bagian 4.1:
--
--   1. `verdict` dan `verdict_mos` boleh NULL. Sketsa menulisnya NOT NULL karena
--      rumusnya selalu menghasilkan salah satu dari tujuh nilai. Itu tidak lagi
--      benar untuk kasus yang valuasinya tidak bisa dihitung (`consensus = N/A`)
--      atau yang `MoS Main`-nya NULL: rumusnya tidak punya `K`, jadi verdict-nya
--      tidak ada. Mengisinya dengan default akan menciptakan verdict palsu yang
--      tidak bisa dibedakan dari yang asli. Check constraint tetap menolak nilai
--      di luar tujuh verdict.
--   2. `analysis_price_source` tetap NOT NULL dengan default 'CLOSE_PIT'. Harga
--      analisis selalu punya sumber: hasil hitung PIT, atau isian manual (D6
--      bagian 5.2). Tidak ada keadaan ketiga.
--
-- Migration ini awalnya ditulis untuk Fase 1 (kolom valuasi/verdict NULL) dan
-- sudah diterapkan. Dua kolom `return_magnitude*` ditambahkan kemudian lewat
-- `alter table` di blok bawah, karena `create table if not exists` tidak akan
-- menambah kolom ke tabel yang sudah ada.
--
-- Metrik harga semuanya nullable: NULL berarti "tidak bisa dihitung", bukan nol.
-- Kasus yang window 12 bulannya belum selesai (2026 Q2) tetap tersimpan dengan
-- flag `WINDOW_PARTIAL`, bukan dihilangkan.
-- ============================================================================

begin;

create table if not exists public.calc_backtest_cases (
  id uuid primary key default gen_random_uuid(),
  calculation_run_id uuid not null references public.calculation_runs(id),
  methodology_version_id uuid not null references public.methodology_versions(id),
  instrument_id uuid not null references public.instruments(id),
  as_of_financial_period_id uuid not null references public.financial_periods(id),

  -- Identitas kasus
  case_quarter text not null,
  base_year integer not null,
  analysis_date date not null,
  analysis_price numeric,
  analysis_price_source text not null default 'CLOSE_PIT',
  stock_type text,
  sector_name text,

  -- Konteks valuasi kasus. NULL di fase 1; diisi fase 2 dan 3.
  years_available integer,
  years_compare integer,
  mos_main numeric,
  mos_peter numeric,
  mos_weight numeric,
  mos_method_code text,
  consensus text,
  consensus_undervalued integer,
  consensus_valid integer,
  verdict text,
  verdict_mos text,

  -- Metrik Tahap B
  high_3m numeric, low_3m numeric,
  high_6m numeric, low_6m numeric,
  high_9m numeric, low_9m numeric,
  high_12m numeric, low_12m numeric,
  peak_price numeric, trough_price numeric, peak_month integer,
  return_peak numeric, return_down numeric,

  -- Magnitude: penyaring pergerakan signifikan untuk frontend (|return| >= 10%).
  -- Bukan dari workbook; lihat komentar kolom di bawah.
  return_magnitude text,
  return_magnitude_down text,

  calculation_status text not null,
  flags jsonb not null default '[]'::jsonb,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),

  constraint calc_backtest_cases_unique
    unique (calculation_run_id, instrument_id, as_of_financial_period_id),
  constraint calc_backtest_cases_case_quarter_format
    check (case_quarter ~ '^[0-9]{4}-Q[1-4]$'),
  constraint calc_backtest_cases_analysis_price_source
    check (analysis_price_source in ('CLOSE_PIT', 'MANUAL')),
  constraint calc_backtest_cases_status
    check (calculation_status in ('VALID', 'APPROXIMATED', 'NOT_CALCULABLE', 'UNAVAILABLE')),
  constraint calc_backtest_cases_verdict
    check (verdict is null or verdict in
      ('WIN', 'RISK', 'RECOVERED', 'FLAT', 'CONFIRMED', 'REPRICE', 'OBSERVE')),
  constraint calc_backtest_cases_verdict_mos
    check (verdict_mos is null or verdict_mos in
      ('WIN', 'RISK', 'RECOVERED', 'FLAT', 'CONFIRMED', 'REPRICE', 'OBSERVE')),
  constraint calc_backtest_cases_return_magnitude
    check (return_magnitude is null or return_magnitude in ('UP', 'DOWN', 'FLAT')),
  constraint calc_backtest_cases_return_magnitude_down
    check (return_magnitude_down is null or return_magnitude_down in ('UP', 'DOWN', 'FLAT'))
);

create index if not exists idx_calc_backtest_cases_run
  on public.calc_backtest_cases(calculation_run_id);

create index if not exists idx_calc_backtest_cases_instrument
  on public.calc_backtest_cases(instrument_id, analysis_date);

create index if not exists idx_calc_backtest_cases_quarter
  on public.calc_backtest_cases(case_quarter);

-- ============================================================================
-- Kolom tambahan (additive, idempotent)
-- ============================================================================
-- `create table if not exists` tidak menambah kolom ke tabel yang sudah ada,
-- jadi kolom yang ditambahkan setelah migration ini pertama diterapkan harus
-- ditulis eksplisit di sini. Keduanya nullable: baris yang belum dihitung ulang
-- tetap sah.

alter table public.calc_backtest_cases
  add column if not exists return_magnitude text,
  add column if not exists return_magnitude_down text;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'calc_backtest_cases_return_magnitude'
  ) then
    alter table public.calc_backtest_cases
      add constraint calc_backtest_cases_return_magnitude
      check (return_magnitude is null or return_magnitude in ('UP', 'DOWN', 'FLAT'));
  end if;

  if not exists (
    select 1 from pg_constraint
    where conname = 'calc_backtest_cases_return_magnitude_down'
  ) then
    alter table public.calc_backtest_cases
      add constraint calc_backtest_cases_return_magnitude_down
      check (return_magnitude_down is null or return_magnitude_down in ('UP', 'DOWN', 'FLAT'));
  end if;
end
$$;

comment on column public.calc_backtest_cases.return_magnitude is
  'UP bila Ret Peak >= +10%, DOWN bila <= -10%, selain itu FLAT. Bukan kolom workbook: penyaring pergerakan signifikan untuk frontend, disimpan agar bisa disaring di SQL.';

comment on column public.calc_backtest_cases.return_magnitude_down is
  'Idem return_magnitude, memakai Ret Down.';

-- ============================================================================
-- calc_backtest_methods - lima baris per kasus (diisi fase 2)
-- ============================================================================
-- Tabel ini dibuat sekarang bersama tabel kasus, bukan nanti, supaya bentuk
-- penyimpanan fase 2 tidak perlu migration tambahan yang mengubah tabel yang
-- sudah berisi data. Fase 1 tidak menulis satu baris pun ke sini.
--
-- `verdict` di sini adalah klasifikasi PER METODE (UNDERVALUED / OVERVALUED /
-- NOT_APPLICABLE), bukan verdict kasus - dua hal berbeda yang mudah tertukar.
-- Karena itu check constraint-nya juga berbeda dari `calc_backtest_cases.verdict`.
--
-- `mos` memakai denominator IV, bukan harga: (IV - price) / IV. Keputusan D6.
-- IV negatif tetap valid dan tetap ikut dihitung (keputusan D5).

create table if not exists public.calc_backtest_methods (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null references public.calc_backtest_cases(id) on delete cascade,
  method_code text not null,
  method_name text not null,
  intrinsic_value numeric,
  current_price numeric,
  gap_ratio numeric,
  mos numeric,
  verdict text not null,
  calculation_status text not null,
  flags jsonb not null default '[]'::jsonb,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),

  constraint calc_backtest_methods_unique unique (case_id, method_code),
  constraint calc_backtest_methods_verdict
    check (verdict in ('UNDERVALUED', 'OVERVALUED', 'NOT_APPLICABLE')),
  constraint calc_backtest_methods_status
    check (calculation_status in ('VALID', 'APPROXIMATED', 'NOT_CALCULABLE', 'UNAVAILABLE'))
);

create index if not exists idx_calc_backtest_methods_case
  on public.calc_backtest_methods(case_id);

create index if not exists idx_calc_backtest_methods_code
  on public.calc_backtest_methods(method_code);

-- ============================================================================
-- Row level security dan grant
-- ============================================================================
-- Sama seperti 0008/0009/0024: hanya `service_role` yang boleh baca/tulis.
-- Browser tidak pernah membaca tabel ini langsung; RPC adalah satu-satunya
-- permukaan yang diekspos (fase 4).

alter table public.calc_backtest_cases enable row level security;
alter table public.calc_backtest_methods enable row level security;

grant select, insert, update on table public.calc_backtest_cases to service_role;
grant select, insert, update on table public.calc_backtest_methods to service_role;

comment on table public.calc_backtest_cases is
  'Satu baris per kasus backtest historis: kuartal kasus, base year (Helper!C2#), harga analisis point-in-time, dan metrik window harga Tahap B. Kolom valuasi/verdict diisi fase 2-3.';

comment on table public.calc_backtest_methods is
  'Lima intrinsic value per kasus backtest (fase 2). mos = (IV - price) / IV dengan denominator IV; IV negatif tetap valid.';

comment on column public.calc_backtest_cases.analysis_price_source is
  'CLOSE_PIT = hasil hitung close point-in-time; MANUAL = diisi pengguna dan tidak menimpa hasil hitung.';

comment on column public.calc_backtest_cases.peak_month is
  'Bln Peak: DATEDIF(analysis_date, tanggal perdagangan pertama yang menyentuh peak_price, "m").';

comment on column public.calc_backtest_cases.verdict is
  'Verdict by Method. NULL selama fase 3 belum dijalankan; check constraint tetap menolak nilai di luar tujuh verdict.';

-- ============================================================================
-- Verifikasi setelah create
-- ============================================================================

do $$
declare
  missing integer;
begin
  select count(*) into missing
  from (values ('calc_backtest_cases'), ('calc_backtest_methods')) as expected(name)
  where not exists (
    select 1
    from information_schema.tables t
    where t.table_schema = 'public' and t.table_name = expected.name
  );

  if missing > 0 then
    raise exception 'BACKTEST_RESULT_TABLE_MISSING: %', missing;
  end if;

  -- Kolom provenance wajib NOT NULL supaya tidak ada hasil backtest yang
  -- tersimpan tanpa run dan versi metodologi yang menghasilkannya.
  select count(*) into missing
  from (values
    ('calculation_status'),
    ('methodology_version_id'),
    ('calculation_run_id'),
    ('instrument_id'),
    ('as_of_financial_period_id'),
    ('analysis_price_source'),
    ('case_quarter'),
    ('base_year'),
    ('analysis_date')
  ) as expected(column_name)
  where not exists (
    select 1
    from information_schema.columns c
    where c.table_schema = 'public'
      and c.table_name = 'calc_backtest_cases'
      and c.column_name = expected.column_name
      and c.is_nullable = 'NO'
  );

  if missing > 0 then
    raise exception 'BACKTEST_RESULT_TABLE_SHAPE_INVALID: %', missing;
  end if;

  -- Delapan kolom window harga harus ada dan harus nullable: NULL berarti
  -- "tidak bisa dihitung", dan kolom NOT NULL akan memaksa nol.
  select count(*) into missing
  from (values
    ('high_3m'), ('low_3m'), ('high_6m'), ('low_6m'),
    ('high_9m'), ('low_9m'), ('high_12m'), ('low_12m'),
    ('peak_price'), ('trough_price'), ('peak_month'),
    ('return_peak'), ('return_down')
  ) as expected(column_name)
  where not exists (
    select 1
    from information_schema.columns c
    where c.table_schema = 'public'
      and c.table_name = 'calc_backtest_cases'
      and c.column_name = expected.column_name
      and c.is_nullable = 'YES'
  );

  if missing > 0 then
    raise exception 'BACKTEST_PRICE_METRIC_COLUMN_INVALID: %', missing;
  end if;

  -- Kolom magnitude harus ada dan nullable.
  select count(*) into missing
  from (values ('return_magnitude'), ('return_magnitude_down')) as expected(column_name)
  where not exists (
    select 1
    from information_schema.columns c
    where c.table_schema = 'public'
      and c.table_name = 'calc_backtest_cases'
      and c.column_name = expected.column_name
      and c.is_nullable = 'YES'
  );

  if missing > 0 then
    raise exception 'BACKTEST_MAGNITUDE_COLUMN_INVALID: %', missing;
  end if;

  -- RLS harus aktif di kedua tabel, dan peran browser tidak boleh punya grant.
  if not exists (
    select 1
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relname = 'calc_backtest_cases'
      and c.relrowsecurity
  ) then
    raise exception 'BACKTEST_CASES_RLS_DISABLED';
  end if;

  if not exists (
    select 1
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relname = 'calc_backtest_methods'
      and c.relrowsecurity
  ) then
    raise exception 'BACKTEST_METHODS_RLS_DISABLED';
  end if;

  if has_table_privilege('anon', 'public.calc_backtest_cases', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_backtest_cases', 'SELECT')
    or has_table_privilege('anon', 'public.calc_backtest_methods', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_backtest_methods', 'SELECT') then
    raise exception 'BACKTEST_RAW_GRANTS_MUST_REMAIN_PRIVATE';
  end if;
end
$$;

commit;

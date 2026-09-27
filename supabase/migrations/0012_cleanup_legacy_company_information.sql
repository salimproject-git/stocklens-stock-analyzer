-- 0012_cleanup_legacy_company_information.sql
-- D-08 destructive cleanup proposal. DO NOT APPLY without explicit owner
-- approval after reviewing row counts, dependencies, API effects, and backup.
--
-- This migration removes the legacy Company Information relations only.
-- It deliberately uses no CASCADE: any unreviewed dependency must make this
-- migration fail instead of being silently removed.

BEGIN;

LOCK TABLE public.instruments,
           public.companies,
           public.sectors,
           public.instrument_sector_classifications
  IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'instruments'
      AND column_name = 'company_id'
  ) THEN
    RAISE EXCEPTION 'D08_CLEANUP_EXPECTED_COMPANY_ID: instruments.company_id is missing';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.instruments'::regclass
      AND conname = 'instruments_company_id_fkey'
      AND contype = 'f'
      AND confrelid = 'public.companies'::regclass
  ) THEN
    RAISE EXCEPTION 'D08_CLEANUP_EXPECTED_COMPANY_FK: instruments.company_id FK differs from audited schema';
  END IF;

  -- Only the four audited foreign keys involving legacy relations are allowed:
  -- instruments.company_id and the three FKs owned by the classification table.
  -- Any new external or internal FK blocks cleanup.
  IF EXISTS (
    SELECT 1
    FROM pg_constraint AS constraint_row
    WHERE constraint_row.contype = 'f'
      AND (
        constraint_row.conrelid IN (
          'public.instruments'::regclass,
          'public.companies'::regclass,
          'public.sectors'::regclass,
          'public.instrument_sector_classifications'::regclass
        )
        OR constraint_row.confrelid IN (
          'public.companies'::regclass,
          'public.sectors'::regclass,
          'public.instrument_sector_classifications'::regclass
        )
      )
      AND NOT (
        constraint_row.conrelid = 'public.instruments'::regclass
        AND constraint_row.conname = 'instruments_company_id_fkey'
        AND constraint_row.confrelid = 'public.companies'::regclass
      )
      AND NOT (
        constraint_row.conrelid = 'public.instrument_sector_classifications'::regclass
        AND constraint_row.conname = 'instrument_sector_classifications_instrument_id_fkey'
        AND constraint_row.confrelid = 'public.instruments'::regclass
      )
      AND NOT (
        constraint_row.conrelid = 'public.instrument_sector_classifications'::regclass
        AND constraint_row.conname = 'instrument_sector_classifications_sector_id_fkey'
        AND constraint_row.confrelid = 'public.sectors'::regclass
      )
      AND NOT (
        constraint_row.conrelid = 'public.instrument_sector_classifications'::regclass
        AND constraint_row.conname = 'instrument_sector_classifications_source_payload_id_fkey'
        AND constraint_row.confrelid = 'public.raw_ingestion_payloads'::regclass
      )
  ) THEN
    RAISE EXCEPTION 'D08_CLEANUP_UNEXPECTED_FOREIGN_KEY: a new or changed FK involves a legacy relation';
  END IF;

  -- Refuse cleanup if a view or materialized view has acquired a dependency.
  IF EXISTS (
    SELECT 1
    FROM pg_depend AS dependency
    JOIN pg_rewrite AS rewrite_rule ON rewrite_rule.oid = dependency.objid
    JOIN pg_class AS dependent_relation ON dependent_relation.oid = rewrite_rule.ev_class
    WHERE dependency.refclassid = 'pg_class'::regclass
      AND dependency.refobjid IN (
        'public.companies'::regclass,
        'public.sectors'::regclass,
        'public.instrument_sector_classifications'::regclass
      )
      AND dependent_relation.relkind IN ('v', 'm')
  ) THEN
    RAISE EXCEPTION 'D08_CLEANUP_UNEXPECTED_VIEW: a view depends on a legacy relation';
  END IF;

  -- Refuse cleanup if a stored routine has an explicit catalog dependency.
  IF EXISTS (
    SELECT 1
    FROM pg_depend AS dependency
    JOIN pg_proc AS routine ON routine.oid = dependency.objid
    JOIN pg_namespace AS routine_schema ON routine_schema.oid = routine.pronamespace
    WHERE dependency.classid = 'pg_proc'::regclass
      AND dependency.refclassid = 'pg_class'::regclass
      AND dependency.refobjid IN (
        'public.companies'::regclass,
        'public.sectors'::regclass,
        'public.instrument_sector_classifications'::regclass
      )
      AND routine_schema.nspname NOT IN ('pg_catalog', 'information_schema')
  ) THEN
    RAISE EXCEPTION 'D08_CLEANUP_UNEXPECTED_ROUTINE: a stored routine depends on a legacy relation';
  END IF;

  -- No application triggers were present during the audit. If one is added,
  -- stop and require a fresh dependency review before dropping its table.
  IF EXISTS (
    SELECT 1
    FROM pg_trigger AS trigger_row
    WHERE trigger_row.tgrelid IN (
      'public.instruments'::regclass,
      'public.companies'::regclass,
      'public.sectors'::regclass,
      'public.instrument_sector_classifications'::regclass
    )
      AND NOT trigger_row.tgisinternal
  ) THEN
    RAISE EXCEPTION 'D08_CLEANUP_UNEXPECTED_TRIGGER: a trigger exists on a reviewed relation';
  END IF;
END;
$$;

ALTER TABLE public.instruments
  DROP CONSTRAINT instruments_company_id_fkey;

ALTER TABLE public.instruments
  DROP COLUMN company_id;

DROP TABLE public.instrument_sector_classifications;
DROP TABLE public.sectors;
DROP TABLE public.companies;

COMMIT;
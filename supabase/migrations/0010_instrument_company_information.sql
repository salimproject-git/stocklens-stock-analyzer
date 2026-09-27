-- 0010_instrument_company_information.sql
-- ============================================================================
-- D-08: add the application-facing Company Information fields to instruments.
--
-- This is the additive schema stage only. It intentionally preserves:
--   * every instruments.id (and therefore financial/price/dividend links);
--   * the existing company_id FK and the legacy companies/sectors/classification
--     tables, which remain in place for a separately reviewed cleanup stage;
--   * current RLS state, grants, and policies (no access is broadened here);
--   * the complete raw JSON archive in private Supabase Storage.
--
-- IMPORTANT: this migration contains NO data backfill and is NOT applied to
-- Supabase live. Review/run the explicit backfill plan separately.
-- ============================================================================

BEGIN;

-- Stage 1: nullable additive fields permit an independently reviewed
-- backfill. A NOT NULL constraint, if needed, belongs in a later reviewed
-- migration after the backfill has been applied and verified.
ALTER TABLE public.instruments
  ADD COLUMN IF NOT EXISTS company_name text,
  ADD COLUMN IF NOT EXISTS sector_name text,
  ADD COLUMN IF NOT EXISTS subsector_name text;

COMMENT ON COLUMN public.instruments.company_name IS
  'Application-facing company name copied from the existing companies.legal_name during D-08 backfill.';
COMMENT ON COLUMN public.instruments.sector_name IS
  'Application-facing source sector copied from the active legacy classification; NULL is preserved when unavailable.';
COMMENT ON COLUMN public.instruments.subsector_name IS
  'Application-facing source subsector copied from the active legacy classification; NULL is preserved when unavailable.';

COMMIT;
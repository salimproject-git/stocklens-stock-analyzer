-- 0011_backfill_instrument_company_information.sql
-- D-08 data migration: copy the reviewed legacy Company Information into the
-- nullable master columns added by migration 0010.
--
-- This migration is intentionally separate from the additive schema change.
-- It aborts on missing company names, ambiguous active classifications, or
-- conflicting values already present in the instrument master. It preserves
-- instruments.id, company_id, ticker, exchange/provider identity, all related
-- financial/price/dividend records, permissions, policies, and raw Storage.

BEGIN;

-- Prevent concurrent edits to the source/target identity rows while validating
-- and copying this small master dataset. SHARE locks allow ordinary SELECTs.
LOCK TABLE public.instruments,
           public.companies,
           public.sectors,
           public.instrument_sector_classifications
  IN SHARE MODE;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM public.instruments AS i
    LEFT JOIN public.companies AS c ON c.id = i.company_id
    WHERE c.id IS NULL
       OR c.legal_name IS NULL
       OR btrim(c.legal_name) = ''
  ) THEN
    RAISE EXCEPTION
      'D08_BACKFILL_COMPANY_NAME_MISSING: every instrument needs a non-empty legacy company name';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.instrument_sector_classifications AS isc
    JOIN public.sectors AS s ON s.id = isc.sector_id
    WHERE s.taxonomy = 'SECTORS_APP'
      AND (isc.effective_from IS NULL OR isc.effective_from <= CURRENT_DATE)
      AND (isc.effective_to IS NULL OR isc.effective_to > CURRENT_DATE)
    GROUP BY isc.instrument_id
    HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION
      'D08_BACKFILL_AMBIGUOUS: instrument has multiple active SECTORS_APP classifications';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.instruments AS i
    JOIN public.companies AS c ON c.id = i.company_id
    WHERE i.company_name IS NOT NULL
      AND i.company_name IS DISTINCT FROM c.legal_name
  ) THEN
    RAISE EXCEPTION
      'D08_BACKFILL_COMPANY_NAME_CONFLICT: existing master name differs from legacy company name';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.instruments AS i
    JOIN public.instrument_sector_classifications AS isc ON isc.instrument_id = i.id
    JOIN public.sectors AS s ON s.id = isc.sector_id
    WHERE s.taxonomy = 'SECTORS_APP'
      AND (isc.effective_from IS NULL OR isc.effective_from <= CURRENT_DATE)
      AND (isc.effective_to IS NULL OR isc.effective_to > CURRENT_DATE)
      AND (
        (i.sector_name IS NOT NULL AND i.sector_name IS DISTINCT FROM s.sector_name)
        OR (i.subsector_name IS NOT NULL AND i.subsector_name IS DISTINCT FROM s.subsector_name)
      )
  ) THEN
    RAISE EXCEPTION
      'D08_BACKFILL_SECTOR_CONFLICT: existing master sector differs from active legacy classification';
  END IF;
END;
$$;

CREATE TEMPORARY TABLE d08_company_information_source
ON COMMIT DROP
AS
SELECT i.id AS instrument_id,
       c.legal_name AS company_name,
       active.sector_name,
       active.subsector_name,
       active.instrument_id IS NOT NULL AS has_active_classification
FROM public.instruments AS i
JOIN public.companies AS c ON c.id = i.company_id
LEFT JOIN LATERAL (
  SELECT isc.instrument_id, s.sector_name, s.subsector_name
  FROM public.instrument_sector_classifications AS isc
  JOIN public.sectors AS s ON s.id = isc.sector_id
  WHERE isc.instrument_id = i.id
    AND s.taxonomy = 'SECTORS_APP'
    AND (isc.effective_from IS NULL OR isc.effective_from <= CURRENT_DATE)
    AND (isc.effective_to IS NULL OR isc.effective_to > CURRENT_DATE)
) AS active ON true;

DO $$
DECLARE
  expected_rows bigint;
  updated_rows bigint;
BEGIN
  SELECT count(*)
  INTO expected_rows
  FROM public.instruments AS i
  JOIN d08_company_information_source AS source
    ON source.instrument_id = i.id
  WHERE i.company_name IS DISTINCT FROM source.company_name
     OR (
       source.has_active_classification
       AND (
         i.sector_name IS DISTINCT FROM source.sector_name
         OR i.subsector_name IS DISTINCT FROM source.subsector_name
       )
     );

  UPDATE public.instruments AS target
  SET company_name = source.company_name,
      sector_name = CASE
        WHEN source.has_active_classification THEN source.sector_name
        ELSE target.sector_name
      END,
      subsector_name = CASE
        WHEN source.has_active_classification THEN source.subsector_name
        ELSE target.subsector_name
      END
  FROM d08_company_information_source AS source
  WHERE target.id = source.instrument_id
    AND (
      target.company_name IS DISTINCT FROM source.company_name
      OR (
        source.has_active_classification
        AND (
          target.sector_name IS DISTINCT FROM source.sector_name
          OR target.subsector_name IS DISTINCT FROM source.subsector_name
        )
      )
    );

  GET DIAGNOSTICS updated_rows = ROW_COUNT;
  IF updated_rows <> expected_rows THEN
    RAISE EXCEPTION
      'D08_BACKFILL_ROW_COUNT_MISMATCH: expected %, updated %', expected_rows, updated_rows;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.instruments AS i
    JOIN d08_company_information_source AS source
      ON source.instrument_id = i.id
    WHERE i.company_name IS DISTINCT FROM source.company_name
       OR (
         source.has_active_classification
         AND (
           i.sector_name IS DISTINCT FROM source.sector_name
           OR i.subsector_name IS DISTINCT FROM source.subsector_name
         )
       )
  ) THEN
    RAISE EXCEPTION 'D08_BACKFILL_VERIFICATION_FAILED: master values differ from validated legacy sources';
  END IF;

  RAISE NOTICE 'D08 backfill updated % instrument row(s)', updated_rows;
END;
$$;

COMMIT;
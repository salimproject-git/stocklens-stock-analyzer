-- REVIEW ONLY — D-08 Company Information backfill plan.
--
-- This file is READ-ONLY as written. The guarded UPDATE is included inside a
-- block comment as a review template. It has not been run against any Supabase
-- project. Do not copy/uncomment the UPDATE until the owner approves the
-- backfill and an operator reviews the preflight results. Executing this file
-- as written performs only preflight checks and a SELECT preview.
--
-- Source mapping:
--   instruments.company_name <- companies.legal_name via instruments.company_id
--   instruments.sector_name/subsector_name <- one active SECTORS_APP
--       instrument_sector_classifications -> sectors row
--
-- No guessed values: missing sector classifications leave sector fields NULL.
-- Any ambiguous active classification or conflicting pre-existing master value
-- aborts before the UPDATE. instrument.id is never changed.

DO $$
BEGIN
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
    LEFT JOIN public.companies AS c ON c.id = i.company_id
    WHERE c.id IS NULL OR c.legal_name IS NULL OR btrim(c.legal_name) = ''
  ) THEN
    RAISE EXCEPTION
      'D08_BACKFILL_COMPANY_NAME_MISSING: every instrument needs a non-empty legacy company name';
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

-- Read-only preview: source values only; does not modify instruments.
WITH active_classifications AS (
  SELECT isc.instrument_id,s.sector_name,s.subsector_name
  FROM public.instrument_sector_classifications AS isc
  JOIN public.sectors AS s ON s.id = isc.sector_id
  WHERE s.taxonomy = 'SECTORS_APP'
    AND (isc.effective_from IS NULL OR isc.effective_from <= CURRENT_DATE)
    AND (isc.effective_to IS NULL OR isc.effective_to > CURRENT_DATE)
)
SELECT i.id AS instrument_id,i.ticker,
       COALESCE(i.company_name,c.legal_name) AS target_company_name,
       COALESCE(i.sector_name,ac.sector_name) AS target_sector_name,
       COALESCE(i.subsector_name,ac.subsector_name) AS target_subsector_name,
       i.company_name AS current_company_name,
       i.sector_name AS current_sector_name,
       i.subsector_name AS current_subsector_name
FROM public.instruments AS i
JOIN public.companies AS c ON c.id = i.company_id
LEFT JOIN active_classifications AS ac ON ac.instrument_id = i.id
ORDER BY i.ticker;

/*
-- GUARDED UPDATE TEMPLATE — DO NOT RUN WITHOUT OWNER APPROVAL.
-- If separately approved, copy this statement to a controlled session, run in
-- an explicit transaction, inspect affected rows, then COMMIT or ROLLBACK.
WITH active_classifications AS (
  SELECT isc.instrument_id,s.sector_name,s.subsector_name
  FROM public.instrument_sector_classifications AS isc
  JOIN public.sectors AS s ON s.id = isc.sector_id
  WHERE s.taxonomy = 'SECTORS_APP'
    AND (isc.effective_from IS NULL OR isc.effective_from <= CURRENT_DATE)
    AND (isc.effective_to IS NULL OR isc.effective_to > CURRENT_DATE)
), master_values AS (
  SELECT i.id AS instrument_id,c.legal_name AS company_name,
         ac.sector_name,ac.subsector_name
  FROM public.instruments AS i
  JOIN public.companies AS c ON c.id = i.company_id
  LEFT JOIN active_classifications AS ac ON ac.instrument_id = i.id
)
UPDATE public.instruments AS target
SET company_name = COALESCE(target.company_name,master_values.company_name),
    sector_name = COALESCE(target.sector_name,master_values.sector_name),
    subsector_name = COALESCE(target.subsector_name,master_values.subsector_name)
FROM master_values
WHERE target.id = master_values.instrument_id
  AND (
    target.company_name IS NULL
    OR (target.sector_name IS NULL AND master_values.sector_name IS NOT NULL)
    OR (target.subsector_name IS NULL AND master_values.subsector_name IS NOT NULL)
  );
*/
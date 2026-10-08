-- 0041_market_sector_options.sql
-- ============================================================================
-- Expose the sector list the Market Overview screener can filter by.
--
-- Why this is a separate function
-- ------------------------------
-- Sector names are data, not a constant: they come from `instruments.sector_name`
-- as populated by the Sectors ingest. The screener's "All Sectors" control must
-- therefore offer exactly the values that exist, or it would show options that
-- match nothing. The stock-type list is deliberately NOT returned here — that one
-- is a whitelist enforced inside `get_market_overview_page` (0040), and
-- duplicating it in a second place is how the two drift apart.
--
-- Read-only, and bounded: the result is a short list of distinct names for one
-- exchange, not a data dump.
-- ============================================================================

begin;

create function public.get_market_sectors()
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  select coalesce(
    jsonb_agg(distinct_sector.sector_name order by distinct_sector.sector_name),
    '[]'::jsonb
  )
  from (
    select distinct i.sector_name
    from public.instruments as i
    where i.exchange_code = 'IDX'
      and i.sector_name is not null
      and btrim(i.sector_name) <> ''
  ) as distinct_sector;
$$;

revoke all on function public.get_market_sectors() from public, anon, authenticated;
grant execute on function public.get_market_sectors() to anon, authenticated;

comment on function public.get_market_sectors() is
  'Distinct IDX sector names, sorted, for the market screener filter options. Read-only and bounded.';

do $verify$
begin
  if not has_function_privilege('anon', 'public.get_market_sectors()', 'EXECUTE')
    or not has_function_privilege('authenticated', 'public.get_market_sectors()', 'EXECUTE') then
    raise exception 'STOCKLENS_MARKET_SECTOR_OPTIONS_GRANTS_MISSING';
  end if;

  -- The function must stay bounded to IDX rows; a missing predicate would turn
  -- a filter-option helper into a whole-table read.
  if position(
      'exchange_code = ''idx''' in lower(
        pg_get_functiondef('public.get_market_sectors()'::regprocedure)
      )
    ) = 0 then
    raise exception 'STOCKLENS_MARKET_SECTOR_OPTIONS_SCOPE_MISSING';
  end if;
end
$verify$;

commit;
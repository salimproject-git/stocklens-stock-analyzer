-- 0038_market_overview_stock_type.sql
-- ============================================================================
-- Add the stock type to the Market Overview card from the same stored valuation
-- source used by the stock detail page.
--
-- The existing paginated RPC is retained as a private base function. A narrow
-- public wrapper enriches only the returned stock rows with `stock_type`; this
-- avoids duplicating the 0037 market/evidence query and keeps its page bounds,
-- metrics, and row ordering unchanged.
--
-- Source precedence mirrors the current stock detail behavior:
--   1. latest immutable fundamental valuation snapshot (`stock_type`)
--   2. latest legacy valuation method (`stock_type`) for tickers not yet
--      refreshed into the snapshot model (e.g. GOLD -> ASSET PLAY)
--   3. `Not available` when neither stored valuation source exists
--
-- This deliberately does not fall back to `CLASSIFICATION_FINAL_TYPE` alone:
-- GOLD/JSMR are stored as UNCLASSIFIED by the workbook-compatible classifier,
-- while valuation explicitly maps those cases to ASSET PLAY. The detail page
-- shows ASSET PLAY, so the market card must use the valuation's resolved type.
-- ============================================================================

begin;

alter function public.get_market_overview_page(integer, integer)
  rename to get_market_overview_page_base;

-- The renamed function is an implementation detail. Browser roles must call
-- only the wrapper below, which adds the stock_type projection.
revoke all on function public.get_market_overview_page_base(integer, integer)
  from public, anon, authenticated, service_role;

create function public.get_market_overview_page(
  p_page integer default 1,
  p_page_size integer default 8
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  with base as (
    select public.get_market_overview_page_base(p_page, p_page_size) as payload
  ),
  enriched_stocks as (
    select coalesce(
      jsonb_agg(
        stock_row.stock || jsonb_build_object(
          'stock_type', coalesce(resolved.stock_type, 'Not available')
        )
        order by stock_row.ordinality
      ),
      '[]'::jsonb
    ) as rows
    from base
    cross join lateral jsonb_array_elements(
      coalesce(base.payload -> 'stocks', '[]'::jsonb)
    ) with ordinality as stock_row(stock, ordinality)
    left join public.instruments as i
      on i.ticker = stock_row.stock ->> 'ticker'
     and i.exchange_code = 'IDX'
    left join lateral (
      select coalesce(
        (
          select snapshot.stock_type
          from public.calc_valuation_fundamental_snapshots as snapshot
          where snapshot.instrument_id = i.id
          order by snapshot.snapshot_date desc, snapshot.created_at desc, snapshot.id desc
          limit 1
        ),
        (
          select legacy.stock_type
          from public.calc_valuation_methods as legacy
          where legacy.instrument_id = i.id
          order by legacy.valuation_date desc, legacy.created_at desc, legacy.id desc
          limit 1
        )
      ) as stock_type
    ) as resolved on true
  )
  select jsonb_set(
    base.payload,
    '{stocks}',
    enriched_stocks.rows,
    true
  )
  from base
  cross join enriched_stocks;
$$;

revoke all on function public.get_market_overview_page(integer, integer)
  from public, anon, authenticated;
grant execute on function public.get_market_overview_page(integer, integer)
  to anon, authenticated;

comment on function public.get_market_overview_page(integer, integer) is
  'Paginated public market overview with current quote, 1Y sparkline, valuation/evidence metrics, and the resolved valuation stock type.';

do $verify$
begin
  if not has_function_privilege(
    'anon', 'public.get_market_overview_page(integer, integer)', 'EXECUTE'
  ) or not has_function_privilege(
    'authenticated', 'public.get_market_overview_page(integer, integer)', 'EXECUTE'
  ) then
    raise exception 'STOCKLENS_MARKET_RPC_GRANTS_MISSING';
  end if;

  if has_function_privilege(
    'anon', 'public.get_market_overview_page_base(integer, integer)', 'EXECUTE'
  ) or has_function_privilege(
    'authenticated', 'public.get_market_overview_page_base(integer, integer)', 'EXECUTE'
  ) or has_function_privilege(
    'service_role', 'public.get_market_overview_page_base(integer, integer)', 'EXECUTE'
  ) then
    raise exception 'STOCKLENS_MARKET_RPC_BASE_MUST_REMAIN_PRIVATE';
  end if;

  if position(
    'stock_type' in pg_get_functiondef(
      'public.get_market_overview_page(integer, integer)'::regprocedure
    )
  ) = 0 or position(
    'calc_valuation_fundamental_snapshots' in pg_get_functiondef(
      'public.get_market_overview_page(integer, integer)'::regprocedure
    )
  ) = 0 or position(
    'calc_valuation_methods' in pg_get_functiondef(
      'public.get_market_overview_page(integer, integer)'::regprocedure
    )
  ) = 0 then
    raise exception 'STOCKLENS_MARKET_STOCK_TYPE_SOURCE_MISSING';
  end if;
end
$verify$;

commit;
-- 0039_market_overview_legacy_valuation_fallback.sql
-- ============================================================================
-- Complete Market Overview valuation fields for tickers that have legacy
-- valuation rows but no daily valuation status yet.
--
-- 0038 already enriches the payload with stock_type. The base 0037 RPC still
-- leaves Signal, MoS, and Valuation Methods empty when a ticker has no row in
-- calc_valuation_daily_status, even though the detail page can read the legacy
-- valuation summary. Merge that same summary into the public market payload.
--
-- Daily valuation fields remain authoritative when present. The legacy summary
-- is only a fallback, so GEMA keeps its daily 1/2 method result while GOLD and
-- INDF receive the legacy values that are already visible on their detail page.
-- ============================================================================

begin;

create or replace function public.get_market_overview_page(
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
        stock_row.stock
        || jsonb_build_object(
          'stock_type', coalesce(resolved.stock_type, 'Not available'),
          'signal', coalesce(stock_row.stock ->> 'signal', fallback.signal),
          'consensus_verdict', coalesce(
            stock_row.stock ->> 'consensus_verdict',
            fallback.method_verdict
          ),
          'based_mos_verdict', coalesce(
            stock_row.stock ->> 'based_mos_verdict',
            fallback.mos_verdict
          ),
          'mos_percent', coalesce(
            nullif(stock_row.stock ->> 'mos_percent', '')::numeric,
            fallback.mos_percent
          ),
          'undervalued_method_count', coalesce(
            nullif(stock_row.stock ->> 'undervalued_method_count', '')::integer,
            fallback.method_undervalued_count
          ),
          'valid_method_count', coalesce(
            nullif(stock_row.stock ->> 'valid_method_count', '')::integer,
            fallback.method_valid_count
          )
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
    left join lateral (
      select public.get_stock_valuation_summary(stock_row.stock ->> 'ticker') as summary
    ) as valuation on true
    left join lateral (
      select
        case
          when stock_row.stock ->> 'signal' is not null then stock_row.stock ->> 'signal'
          when valuation.summary ->> 'method_verdict' = 'UNDERVALUED'
            and valuation.summary ->> 'mos_verdict' = 'UNDERVALUED' then 'UNDERVALUED'
          when valuation.summary ->> 'method_verdict' = 'OVERVALUED'
            and valuation.summary ->> 'mos_verdict' = 'OVERVALUED' then 'OVERVALUED'
          when valuation.summary ->> 'method_verdict' in ('UNDERVALUED', 'OVERVALUED')
            and valuation.summary ->> 'mos_verdict' in ('UNDERVALUED', 'OVERVALUED') then 'MIXED'
          else null
        end as signal,
        valuation.summary ->> 'method_verdict' as method_verdict,
        valuation.summary ->> 'mos_verdict' as mos_verdict,
        case
          when valuation.summary ->> 'mos' is null then null
          else round((valuation.summary ->> 'mos')::numeric * 100, 1)
        end as mos_percent,
        (valuation.summary ->> 'method_undervalued_count')::integer as method_undervalued_count,
        (valuation.summary ->> 'method_valid_count')::integer as method_valid_count
    ) as fallback on true
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
  'Paginated public market overview with daily valuation metrics, legacy valuation fallback, 1Y sparkline, evidence metrics, and resolved valuation stock type.';

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
    'get_stock_valuation_summary' in pg_get_functiondef(
      'public.get_market_overview_page(integer, integer)'::regprocedure
    )
  ) = 0 or position(
    'fallback' in pg_get_functiondef(
      'public.get_market_overview_page(integer, integer)'::regprocedure
    )
  ) = 0 then
    raise exception 'STOCKLENS_MARKET_LEGACY_FALLBACK_MISSING';
  end if;
end
$verify$;

commit;
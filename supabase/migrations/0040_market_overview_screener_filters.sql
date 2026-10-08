-- 0040_market_overview_screener_filters.sql
-- ============================================================================
-- Make the Market Overview a real screener: sector, stock type and sort are
-- applied in the database, over the whole IDX instrument set.
--
-- Why this is needed
-- ------------------
-- Until now `get_market_overview_page(p_page, p_page_size)` returned one page of
-- 8/12/16/20 rows chosen by ticker. The UI offered "All Sectors", "All Stock
-- Type" and "Sort by Market Cap" as buttons, but a client-side filter over one
-- page can only ever filter the rows already on screen, and a client-side sort
-- can only rank those same rows. That is a display trick, not a screener.
--
-- What changes
-- ------------
--   * `p_sector`     — exact match on `instruments.sector_name`. NULL/'' = all.
--   * `p_stock_type` — exact match on the resolved valuation stock type, using
--                      the same precedence 0038/0039 established (newest
--                      fundamental snapshot, then newest legacy method).
--   * `p_sort`       — whitelisted: ticker, market_cap_desc, mos_desc,
--                      win_rate_desc, price_desc, price_asc.
--   * `total_count` and `current_page` are computed from the FILTERED set, so
--     pagination is correct after narrowing (previously they described the
--     unfiltered set).
--
-- Single code path
-- ----------------
-- 0038/0039 kept the 0037 function as a private `get_market_overview_page_base`
-- and wrapped it. A wrapper cannot filter: the base has already chosen its page
-- by ticker before the wrapper sees a row, so a filter could only ever remove
-- rows from an already-wrong page. The enrichment is therefore folded into one
-- function here and the base is dropped, leaving exactly one implementation to
-- read and audit. Every metric rule is carried over unchanged:
--   * Signal = agreement of the method consensus (>= 3 valid methods above
--     price) and the MoS rule (based MoS >= 30%).
--   * Historical evidence is pinned to the newest SUCCEEDED
--     BACKTEST_HISTORICAL run per instrument (the 0021/0026/0028 rule).
--   * Legacy `get_stock_valuation_summary` is a fallback only; daily valuation
--     status stays authoritative when present (the 0039 rule).
--
-- Note on 0019: its pending `alter function ... owner to stocklens_market_reader`
-- statement still names the two-argument signature. When that manual step is
-- eventually applied it must be retargeted to
-- `public.get_market_overview_page(integer, integer, text, text, text)`.
--
-- Read-only: no table, row or other function is modified beyond this function
-- and the now-unused private base.
-- ============================================================================

begin;

-- Dropped before the base so the dependency disappears with it. Both signatures
-- are gone afterwards; a caller that still sends only two arguments still
-- resolves, because every parameter after `p_page_size` has a default.
drop function if exists public.get_market_overview_page(integer, integer);
drop function if exists public.get_market_overview_page_base(integer, integer);

create function public.get_market_overview_page(
  p_page integer default 1,
  p_page_size integer default 8,
  p_sector text default null,
  p_stock_type text default null,
  p_sort text default 'ticker'
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  with requested as (
    -- A whitelist, not a free integer: the value becomes a LIMIT, and an
    -- unbounded one would let a caller request the entire table. Anything
    -- outside the list falls back to the default instead of raising, so a stale
    -- client that still sends an old value keeps rendering a page.
    select case
      when coalesce(p_page_size, 8) = any (array[8, 12, 16, 20]) then coalesce(p_page_size, 8)
      else 8
    end as page_size
  ),
  requested_sector as (
    -- Bounded and trimmed. Empty means "all sectors"; the value is only ever
    -- compared against stored sector names, so it cannot widen the result set.
    select nullif(left(btrim(coalesce(p_sector, '')), 64), '') as sector_name
  ),
  requested_stock_type as (
    -- A whitelist for the same reason as the page size: this value selects
    -- which derived classification the caller may see.
    select case
      when upper(btrim(coalesce(p_stock_type, ''))) = any (array[
        'ASSET PLAY', 'CYCLICAL', 'FAST GROWER', 'SLOW GROWER', 'STALWART', 'TURN AROUND'
      ]) then upper(btrim(coalesce(p_stock_type, '')))
      else null
    end as stock_type
  ),
  requested_sort as (
    -- A whitelist, not a free string: the value becomes an ORDER BY expression.
    select case lower(btrim(coalesce(p_sort, 'ticker')))
      when 'market_cap_desc' then 'market_cap_desc'
      when 'mos_desc' then 'mos_desc'
      when 'win_rate_desc' then 'win_rate_desc'
      when 'price_desc' then 'price_desc'
      when 'price_asc' then 'price_asc'
      else 'ticker'
    end as sort_key
  ),
  instrument_facets as (
    -- The instrument set plus its resolved valuation stock type. Resolved here
    -- (not per output row) because the facet filter has to see it before the
    -- page is chosen.
    select
      i.id,
      i.ticker,
      i.company_name,
      i.sector_name,
      i.currency_code,
      coalesce(
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
    from public.instruments as i
    where i.exchange_code = 'IDX'
  ),
  filtered_instruments as (
    select f.*
    from instrument_facets as f
    cross join requested_sector as rs
    cross join requested_stock_type as rst
    where (rs.sector_name is null or f.sector_name = rs.sector_name)
      and (rst.stock_type is null or f.stock_type = rst.stock_type)
  ),
  matched_count as (
    select count(*)::integer as total from filtered_instruments
  ),
  requested_page as (
    -- Clamped against the FILTERED count, so narrowing the screener cannot leave
    -- the caller on a page that no longer exists.
    select least(
      greatest(coalesce(p_page, 1), 1),
      greatest(
        ceil(
          (select total from matched_count)::numeric
          / (select page_size from requested)
        )::integer,
        1
      )
    ) as page_number
  ),
  stock_rows as (
    select
      i.ticker,
      i.company_name,
      i.sector_name,
      i.currency_code,
      coalesce(i.stock_type, 'Not available') as stock_type,
      latest.trading_date as latest_trading_date,
      latest.close_price as latest_close,
      latest.market_cap as market_cap,
      case
        when previous.close_price is not null then latest.close_price - previous.close_price
        else null
      end as price_change,
      case
        when previous.close_price is not null and previous.close_price <> 0
          then ((latest.close_price - previous.close_price) / previous.close_price) * 100
        else null
      end as change_percent,
      coalesce(history.sparkline, '[]'::jsonb) as sparkline,
      -- Signal: do the two "cheap" rules agree? The method consensus comes from
      -- `consensus_verdict`, the MoS rule from `based_mos_verdict`. Daily status
      -- wins; the legacy summary only fills the gaps (0039).
      coalesce(
        case
          when val.consensus_verdict = 'UNDERVALUED' and val.based_mos_verdict = 'UNDERVALUED' then 'UNDERVALUED'
          when val.consensus_verdict = 'OVERVALUED' and val.based_mos_verdict = 'OVERVALUED' then 'OVERVALUED'
          when val.consensus_verdict in ('UNDERVALUED', 'OVERVALUED')
            and val.based_mos_verdict in ('UNDERVALUED', 'OVERVALUED') then 'MIXED'
          else null
        end,
        case
          when valuation.summary ->> 'method_verdict' = 'UNDERVALUED'
            and valuation.summary ->> 'mos_verdict' = 'UNDERVALUED' then 'UNDERVALUED'
          when valuation.summary ->> 'method_verdict' = 'OVERVALUED'
            and valuation.summary ->> 'mos_verdict' = 'OVERVALUED' then 'OVERVALUED'
          when valuation.summary ->> 'method_verdict' in ('UNDERVALUED', 'OVERVALUED')
            and valuation.summary ->> 'mos_verdict' in ('UNDERVALUED', 'OVERVALUED') then 'MIXED'
          else null
        end
      ) as signal,
      coalesce(val.consensus_verdict, valuation.summary ->> 'method_verdict') as consensus_verdict,
      coalesce(val.based_mos_verdict, valuation.summary ->> 'mos_verdict') as based_mos_verdict,
      coalesce(
        case when val.based_mos is not null then round(val.based_mos * 100, 1) else null end,
        case
          when valuation.summary ->> 'mos' is null then null
          else round((valuation.summary ->> 'mos')::numeric * 100, 1)
        end
      ) as mos_percent,
      coalesce(
        val.undervalued_method_count,
        (valuation.summary ->> 'method_undervalued_count')::integer
      ) as undervalued_method_count,
      coalesce(
        val.valid_method_count,
        (valuation.summary ->> 'method_valid_count')::integer
      ) as valid_method_count,
      bt.evidence_total as evidence_total,
      bt.evidence_wins as evidence_wins,
      bt.win_rate_percent as win_rate_percent,
      bt.win_rate_cases as win_rate_cases
    from filtered_instruments as i
    left join lateral (
      select p.trading_date, p.close_price, p.market_cap
      from public.prices_daily as p
      where p.instrument_id = i.id and p.close_price is not null
      order by p.trading_date desc
      limit 1
    ) as latest on true
    left join lateral (
      select p.close_price
      from public.prices_daily as p
      where p.instrument_id = i.id and p.close_price is not null
      order by p.trading_date desc
      offset 1
      limit 1
    ) as previous on true
    left join lateral (
      select jsonb_agg(monthly.close_price order by monthly.month_start asc) as sparkline
      from (
        select distinct on (date_trunc('month', p.trading_date::timestamp))
          date_trunc('month', p.trading_date::timestamp)::date as month_start,
          p.close_price
        from public.prices_daily as p
        where p.instrument_id = i.id and p.close_price is not null
        order by date_trunc('month', p.trading_date::timestamp) desc, p.trading_date desc
        limit 12
      ) as monthly
    ) as history on true
    left join lateral (
      -- Newest daily valuation status for this instrument.
      select
        s.consensus_verdict,
        s.based_mos_verdict,
        s.based_mos,
        s.undervalued_method_count,
        s.valid_method_count
      from public.calc_valuation_daily_status as s
      where s.instrument_id = i.id
      order by s.trading_date desc, s.created_at desc, s.id
      limit 1
    ) as val on true
    left join lateral (
      -- Legacy summary, used only where the daily status above is absent.
      select public.get_stock_valuation_summary(i.ticker) as summary
    ) as valuation on true
    left join lateral (
      -- Newest SUCCEEDED backtest run for this instrument, then both historical
      -- rules' win rates so the card can show the higher one.
      with latest_run as (
        select r.id
        from public.calculation_runs as r
        where r.calculation_type = 'BACKTEST_HISTORICAL'
          and r.status = 'SUCCEEDED'
          and r.scope_type = 'INSTRUMENT'
          and r.scope_id = i.id::text
        order by r.completed_at desc nulls last, r.created_at desc, r.id
        limit 1
      ),
      case_rows as (
        select
          c.analysis_price,
          c.verdict,
          c.verdict_mos,
          c.mos_main,
          count(*) filter (
            where m.intrinsic_value is not null and m.intrinsic_value <> 0
          ) as valid_methods,
          count(*) filter (
            where m.intrinsic_value is not null and m.intrinsic_value <> 0
              and m.intrinsic_value > c.analysis_price
          ) as undervalued_methods
        from public.calc_backtest_cases as c
        join latest_run as run on run.id = c.calculation_run_id
        left join public.calc_backtest_methods as m on m.case_id = c.id
        where c.instrument_id = i.id
        group by c.id, c.analysis_price, c.verdict, c.verdict_mos, c.mos_main
      ),
      totals as (
        select
          count(*) as total_cases,
          count(*) filter (where verdict in ('WIN', 'RECOVERED')) as wins_all,
          count(*) filter (where undervalued_methods >= 3) as method_den,
          count(*) filter (where undervalued_methods >= 3 and verdict in ('WIN', 'RECOVERED')) as method_wins,
          count(*) filter (where mos_main >= 0.30) as mos_den,
          count(*) filter (where mos_main >= 0.30 and verdict_mos in ('WIN', 'RECOVERED')) as mos_wins
        from case_rows
      )
      select
        case when t.total_cases = 0 then null else t.total_cases end as evidence_total,
        case when t.total_cases = 0 then null else t.wins_all end as evidence_wins,
        case
          when t.method_den = 0 and t.mos_den = 0 then null
          when t.method_den = 0 then round((t.mos_wins::numeric / t.mos_den) * 100, 1)
          when t.mos_den = 0 then round((t.method_wins::numeric / t.method_den) * 100, 1)
          when (t.method_wins::numeric / t.method_den) >= (t.mos_wins::numeric / t.mos_den)
            then round((t.method_wins::numeric / t.method_den) * 100, 1)
          else round((t.mos_wins::numeric / t.mos_den) * 100, 1)
        end as win_rate_percent,
        case
          when t.method_den = 0 and t.mos_den = 0 then null
          when t.method_den = 0 then t.mos_den
          when t.mos_den = 0 then t.method_den
          when (t.method_wins::numeric / t.method_den) >= (t.mos_wins::numeric / t.mos_den) then t.method_den
          else t.mos_den
        end as win_rate_cases
      from totals as t
    ) as bt on true
  ),
  ranked as (
    -- One ORDER BY, expressed once. Only the branch matching the requested sort
    -- key produces a non-null value, so the other branches tie and hand over to
    -- the next one; `nulls last` keeps stocks with no stored figure at the end
    -- in both directions (an absent price is not a low price).
    select
      stock_rows.*,
      row_number() over (
        order by
          case when (select sort_key from requested_sort) = 'market_cap_desc' then stock_rows.market_cap end desc nulls last,
          case when (select sort_key from requested_sort) = 'mos_desc' then stock_rows.mos_percent end desc nulls last,
          case when (select sort_key from requested_sort) = 'win_rate_desc' then stock_rows.win_rate_percent end desc nulls last,
          case when (select sort_key from requested_sort) = 'price_desc' then stock_rows.latest_close end desc nulls last,
          case when (select sort_key from requested_sort) = 'price_asc' then stock_rows.latest_close end asc nulls last,
          stock_rows.ticker asc
      ) as sort_rank
    from stock_rows
  ),
  paged as (
    select ranked.*
    from ranked
    order by sort_rank
    limit (select page_size from requested)
    offset ((select page_number from requested_page) - 1) * (select page_size from requested)
  )
  select jsonb_build_object(
    'current_page', (select page_number from requested_page),
    'page_size', (select page_size from requested),
    'total_count', (select total from matched_count),
    'stocks', coalesce((
      select jsonb_agg(to_jsonb(paged) - 'sort_rank' order by paged.sort_rank)
      from paged
    ), '[]'::jsonb)
  );
$$;

revoke all on function public.get_market_overview_page(integer, integer, text, text, text)
  from public, anon, authenticated;
grant execute on function public.get_market_overview_page(integer, integer, text, text, text)
  to anon, authenticated;

comment on function public.get_market_overview_page(integer, integer, text, text, text) is
  'Paginated public market screener: filters by sector and resolved valuation stock type, sorts by ticker/market cap/MoS/win rate/price, and returns quote, 1Y sparkline, valuation signal/MoS/consensus and backtest evidence per row. total_count and current_page describe the filtered set. p_page_size is whitelisted to 8/12/16/20.';

do $verify$
begin
  if not has_function_privilege(
    'anon', 'public.get_market_overview_page(integer, integer, text, text, text)', 'EXECUTE'
  ) or not has_function_privilege(
    'authenticated', 'public.get_market_overview_page(integer, integer, text, text, text)', 'EXECUTE'
  ) then
    raise exception 'STOCKLENS_MARKET_RPC_GRANTS_MISSING';
  end if;

  -- The superseded signatures must not survive as an unfiltered back door.
  -- Matched on the argument count, not on the rendered signature: identity
  -- arguments include the parameter names, so comparing text here would reject
  -- the new function itself.
  if exists (
    select 1 from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname in ('get_market_overview_page', 'get_market_overview_page_base')
      and p.pronargs <> 5
  ) then
    raise exception 'STOCKLENS_MARKET_RPC_OLD_SIGNATURE_STILL_PRESENT';
  end if;

  -- The daily-status table must stay service-role only for browser roles.
  if has_table_privilege('anon', 'public.calc_valuation_daily_status', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_valuation_daily_status', 'SELECT') then
    raise exception 'STOCKLENS_MARKET_RAW_TABLE_GRANTS_MUST_REMAIN_PRIVATE';
  end if;

  if position(
      'win_rate_percent' in pg_get_functiondef(
        'public.get_market_overview_page(integer, integer, text, text, text)'::regprocedure
      )
    ) = 0
    or position(
      'signal' in pg_get_functiondef(
        'public.get_market_overview_page(integer, integer, text, text, text)'::regprocedure
      )
    ) = 0
    or position(
      'stock_type' in pg_get_functiondef(
        'public.get_market_overview_page(integer, integer, text, text, text)'::regprocedure
      )
    ) = 0 then
    raise exception 'STOCKLENS_MARKET_RPC_EVIDENCE_FIELDS_MISSING';
  end if;

  -- The facet filter and the sort whitelist must be present, otherwise the
  -- "screener" would silently degrade back into a fixed page again.
  if position(
      'requested_sector' in pg_get_functiondef(
        'public.get_market_overview_page(integer, integer, text, text, text)'::regprocedure
      )
    ) = 0
    or position(
      'requested_stock_type' in pg_get_functiondef(
        'public.get_market_overview_page(integer, integer, text, text, text)'::regprocedure
      )
    ) = 0
    or position(
      'requested_sort' in pg_get_functiondef(
        'public.get_market_overview_page(integer, integer, text, text, text)'::regprocedure
      )
    ) = 0 then
    raise exception 'STOCKLENS_MARKET_SCREENER_FACETS_MISSING';
  end if;
end
$verify$;

commit;
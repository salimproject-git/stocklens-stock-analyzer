-- 0037_market_overview_valuation_and_evidence.sql
-- ============================================================================
-- Fill the Market Overview card with the "cheap" and "history" figures it has
-- always shown as "Not available".
--
-- `get_market_overview_page` returned only identity, price and a sparkline, so
-- `lib/stock-data.ts` hardcoded `verdict: "Not available"`, `mos: null`,
-- `evidenceWins: null`, `evidenceTotal: null`. Three of the four card blocks
-- were therefore empty for every row, including tickers that have full
-- valuation and backtest data.
--
-- What is added per row
-- ---------------------
--   * `signal` — short agreement between the two "cheap" rules: the method
--     consensus (>= 3 valid methods above price) and the MoS rule (MoS main
--     >= 30%). Both say cheap -> UNDERVALUED, both say expensive -> OVERVALUED,
--     they disagree -> MIXED, and a rule with no stored verdict -> null (the UI
--     reads that as "Not available").
--   * `mos_percent` — `based_mos` as a percentage (the stored value is a ratio).
--   * `undervalued_method_count` / `valid_method_count` — the `3 / 4` consensus.
--   * `win_rate_percent` / `win_rate_cases` — the higher of the two historical
--     rules' win rates, each `(WIN + RECOVERED) / Undervalued`, with the case
--     count that rate is measured over. The two rules are the method rule and
--     the MoS rule; ties go to the larger sample.
--   * `evidence_wins` / `evidence_total` — every WIN/RECOVERED case over the
--     total cases in the newest SUCCEEDED BACKTEST_HISTORICAL run, for the list
--     view's "Historical Evidence" column.
--
-- Dedup
-- -----
-- The newest SUCCEEDED BACKTEST_HISTORICAL run per instrument wins (the rule
-- 0021/0026/0028 established), because a re-run legitimately creates a new run
-- and an unpinned read would count every case once per run. The valuation status
-- is the newest `calc_valuation_daily_status` row per instrument.
--
-- Read-only: no table, row or other function is modified. The only additions are
-- the column-level read grants and the RLS policy the reader role needs, which
-- matter once the pending owner transfer in 0019 is applied.
-- ============================================================================

begin;

-- The reader role needs the daily-status columns this RPC now reads. Without
-- them the function only works while it is still owned by `postgres` (owner
-- transfer pending in 0019).
revoke all on table public.calc_valuation_daily_status from stocklens_market_reader;
grant select (
  id, instrument_id, trading_date, created_at,
  consensus_verdict, based_mos_verdict, based_mos,
  undervalued_method_count, valid_method_count
) on table public.calc_valuation_daily_status to stocklens_market_reader;

drop policy if exists stocklens_market_reader_select on public.calc_valuation_daily_status;
create policy stocklens_market_reader_select on public.calc_valuation_daily_status
  for select to stocklens_market_reader using (true);

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
  requested_page as (
    select least(
      greatest(coalesce(p_page, 1), 1),
      greatest(
        ceil(
          (select count(*)::numeric from public.instruments where exchange_code = 'IDX')
          / (select page_size from requested)
        )::integer,
        1
      )
    ) as page_number
  ),
  instrument_page as (
    select i.id, i.ticker, i.company_name, i.sector_name, i.currency_code
    from public.instruments as i
    where i.exchange_code = 'IDX'
    order by i.ticker
    limit (select page_size from requested)
    offset ((select page_number - 1 from requested_page) * (select page_size from requested))
  ),
  stock_rows as (
    select
      i.ticker,
      i.company_name,
      i.sector_name,
      i.currency_code,
      latest.trading_date as latest_trading_date,
      latest.close_price as latest_close,
      latest.market_cap as latest_market_cap,
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
      -- `consensus_verdict`, the MoS rule from `based_mos_verdict`.
      case
        when val.consensus_verdict = 'UNDERVALUED' and val.based_mos_verdict = 'UNDERVALUED' then 'UNDERVALUED'
        when val.consensus_verdict = 'OVERVALUED' and val.based_mos_verdict = 'OVERVALUED' then 'OVERVALUED'
        when val.consensus_verdict in ('UNDERVALUED', 'OVERVALUED')
          and val.based_mos_verdict in ('UNDERVALUED', 'OVERVALUED') then 'MIXED'
        else null
      end as signal,
      val.consensus_verdict as consensus_verdict,
      val.based_mos_verdict as based_mos_verdict,
      case when val.based_mos is not null then round(val.based_mos * 100, 1) else null end as mos_percent,
      val.undervalued_method_count as undervalued_method_count,
      val.valid_method_count as valid_method_count,
      bt.evidence_total as evidence_total,
      bt.evidence_wins as evidence_wins,
      bt.win_rate_percent as win_rate_percent,
      bt.win_rate_cases as win_rate_cases
    from instrument_page as i
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
  )
  select jsonb_build_object(
    'current_page', (select page_number from requested_page),
    'page_size', (select page_size from requested),
    'total_count', (select count(*) from public.instruments where exchange_code = 'IDX'),
    'stocks', coalesce((
      select jsonb_agg(to_jsonb(stock_rows) order by stock_rows.ticker)
      from stock_rows
    ), '[]'::jsonb)
  );
$$;
comment on function public.get_market_overview_page(integer, integer) is
  'Paginated public market overview with latest daily quote, up to 12 monthly close points, the newest valuation signal/MoS/consensus, and the newest backtest win rate and evidence counts. p_page_size is whitelisted to 8/12/16/20 and defaults to 8.';

revoke all on function public.get_market_overview_page(integer, integer) from public, anon, authenticated;
grant execute on function public.get_market_overview_page(integer, integer) to anon, authenticated;

-- Same pending owner transfer as 0019/0027: this signature is owned by postgres
-- until 0019's `alter function ... owner to stocklens_market_reader` is applied
-- from the Supabase SQL editor, so the column-level grants above are
-- documentation only for the duration.

do $verify$
begin
  if not has_function_privilege('anon', 'public.get_market_overview_page(integer, integer)', 'EXECUTE')
    or not has_function_privilege('authenticated', 'public.get_market_overview_page(integer, integer)', 'EXECUTE') then
    raise exception 'STOCKLENS_MARKET_RPC_GRANTS_MISSING';
  end if;

  -- The daily-status table must stay service-role only for browser roles.
  if has_table_privilege('anon', 'public.calc_valuation_daily_status', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_valuation_daily_status', 'SELECT') then
    raise exception 'STOCKLENS_MARKET_RAW_TABLE_GRANTS_MUST_REMAIN_PRIVATE';
  end if;

  if position(
      'win_rate_percent' in pg_get_functiondef('public.get_market_overview_page(integer, integer)'::regprocedure)
    ) = 0
    or position(
      'signal' in pg_get_functiondef('public.get_market_overview_page(integer, integer)'::regprocedure)
    ) = 0 then
    raise exception 'STOCKLENS_MARKET_RPC_EVIDENCE_FIELDS_MISSING';
  end if;
end
$verify$;

commit;





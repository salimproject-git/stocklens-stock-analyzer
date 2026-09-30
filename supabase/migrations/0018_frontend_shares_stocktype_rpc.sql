-- Add OUTSTANDING_SHARES to the exposed financial fact metrics (needed for
-- EPS/BVPS/P-E/P-BV display) and expose stock_type on valuation methods
-- (needed to pick the correct primary valuation method per methodology).
-- No data is changed; this only widens the read-only RPC's SELECT list.

begin;

create or replace function public.get_stock_research_data(p_ticker text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  with selected_instrument as (
    select i.id, i.ticker, i.company_name, i.sector_name, i.subsector_name, i.currency_code
    from public.instruments as i
    where i.ticker = upper(trim(p_ticker))
      and i.exchange_code = 'IDX'
      and (select count(*) from public.instruments as matches where matches.ticker = upper(trim(p_ticker)) and matches.exchange_code = 'IDX') = 1
    order by i.ticker
    limit 1
  ),
  stock_prices as (
    select jsonb_agg(to_jsonb(recent_prices) order by recent_prices.trading_date asc) as prices
    from (
      select p.trading_date, p.close_price, p.market_cap, p.currency_code
      from selected_instrument as i
      join public.prices_daily as p on p.instrument_id = i.id
      where p.close_price is not null
      order by p.trading_date desc
      limit 260
    ) as recent_prices
  ),
  stock_financial_periods as (
    select jsonb_agg(to_jsonb(period_rows) order by period_rows.period_end asc, period_rows.period_type asc, period_rows.statement_scope asc) as financial_periods
    from (
      select
        fp.period_type,
        fp.period_label,
        fp.period_end,
        fp.period_basis,
        fp.statement_scope,
        coalesce(facts.rows, '[]'::jsonb) as facts
      from selected_instrument as i
      join public.financial_periods as fp on fp.instrument_id = i.id
      left join lateral (
        select jsonb_agg(
          jsonb_build_object(
            'metric_code', ff.metric_code,
            'value_numeric', ff.value_numeric,
            'unit_code', ff.unit_code,
            'currency_code', ff.currency_code,
            'quality_status', ff.quality_status
          ) order by ff.metric_code
        ) as rows
        from public.financial_facts as ff
        where ff.financial_period_id = fp.id
          and ff.revision_key = 'CURRENT'
          and ff.quality_status in ('VALID', 'ESTIMATED')
          and ff.metric_code in (
            'REVENUE', 'EARNINGS', 'GROSS_PROFIT', 'COST_OF_REVENUE',
            'OPERATING_CASH_FLOW', 'TOTAL_CURRENT_ASSET', 'CURRENT_LIABILITIES',
            'TOTAL_LIABILITIES', 'TOTAL_EQUITY', 'OUTSTANDING_SHARES'
          )
      ) as facts on true
      order by fp.period_end desc, fp.period_type, fp.statement_scope
      limit 40
    ) as period_rows
  ),
  latest_valuation_date as (
    select max(v.valuation_date) as valuation_date
    from selected_instrument as i
    join public.calc_valuation_methods as v on v.instrument_id = i.id
  ),
  stock_valuations as (
    select jsonb_agg(
      jsonb_build_object(
        'method_code', v.method_code,
        'method_name', v.method_name,
        'valuation_date', v.valuation_date,
        'intrinsic_value', v.intrinsic_value,
        'current_price', v.current_price,
        'gap_ratio', v.gap_ratio,
        'verdict', v.verdict,
        'calculation_status', v.calculation_status,
        'stock_type', v.stock_type
      ) order by v.method_code
    ) as valuation_methods
    from selected_instrument as i
    cross join latest_valuation_date as d
    join public.calc_valuation_methods as v
      on v.instrument_id = i.id and v.valuation_date = d.valuation_date
  ),
  stock_annual_growth as (
    select jsonb_agg(to_jsonb(growth_rows) order by growth_rows.period_end asc, growth_rows.metric_code asc) as annual_growth
    from (
      select fp.period_end, fp.period_label, g.metric_code, g.value_numeric, g.calculation_status
      from selected_instrument as i
      join public.calc_annual_growth_quality as g on g.instrument_id = i.id
      join public.financial_periods as fp on fp.id = g.financial_period_id
      where g.calculation_status = 'VALID'
      order by fp.period_end desc
      limit 200
    ) as growth_rows
  ),
  stock_quarterly_quality as (
    select jsonb_agg(to_jsonb(quality_rows) order by quality_rows.period_end asc, quality_rows.metric_code asc) as quarterly_quality
    from (
      select fp.period_end, fp.period_label, q.metric_code, q.value_numeric, q.calculation_status
      from selected_instrument as i
      join public.calc_quarterly_quality as q on q.instrument_id = i.id
      join public.financial_periods as fp on fp.id = q.financial_period_id
      where q.calculation_status = 'VALID'
      order by fp.period_end desc
      limit 100
    ) as quality_rows
  ),
  stock_dividends as (
    select jsonb_agg(to_jsonb(dividend_rows) order by dividend_rows.period_year desc) as dividends
    from (
      select d.fact_type, d.period_year, d.event_date, d.amount_per_share, d.yield_ratio, d.currency_code
      from selected_instrument as i
      join public.dividend_facts as d on d.instrument_id = i.id
      order by d.period_year desc
      limit 20
    ) as dividend_rows
  )
  select case
    when not exists (select 1 from selected_instrument) then null
    else jsonb_build_object(
      'instrument', (
        select jsonb_build_object(
          'ticker', i.ticker,
          'company_name', i.company_name,
          'sector_name', i.sector_name,
          'subsector_name', i.subsector_name,
          'currency_code', i.currency_code
        )
        from selected_instrument as i
      ),
      'prices', coalesce((select prices from stock_prices), '[]'::jsonb),
      'financial_periods', coalesce((select financial_periods from stock_financial_periods), '[]'::jsonb),
      'valuation_methods', coalesce((select valuation_methods from stock_valuations), '[]'::jsonb),
      'annual_growth', coalesce((select annual_growth from stock_annual_growth), '[]'::jsonb),
      'quarterly_quality', coalesce((select quarterly_quality from stock_quarterly_quality), '[]'::jsonb),
      'dividends', coalesce((select dividends from stock_dividends), '[]'::jsonb)
    )
  end;
$$;

revoke all on function public.get_stock_research_data(text) from public, anon, authenticated;
grant execute on function public.get_stock_research_data(text) to anon, authenticated;

grant select (stock_type) on table public.calc_valuation_methods to stocklens_market_reader;

comment on function public.get_stock_research_data(text) is
  'Read-only public stock research payload: instrument identity, recent prices, selected financial facts (incl. outstanding shares), latest valuation results with stock type, computed annual growth metrics, quarterly quality metrics, and dividend history for one ticker.';

do $verify$
begin
  if has_table_privilege('anon', 'public.financial_facts', 'SELECT')
    or has_table_privilege('authenticated', 'public.financial_facts', 'SELECT')
    or has_table_privilege('anon', 'public.calc_valuation_methods', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_valuation_methods', 'SELECT') then
    raise exception 'STOCKLENS_RAW_TABLE_GRANTS_MUST_REMAIN_PRIVATE';
  end if;

  if not has_function_privilege('anon', 'public.get_stock_research_data(text)', 'EXECUTE')
    or not has_function_privilege('authenticated', 'public.get_stock_research_data(text)', 'EXECUTE') then
    raise exception 'STOCKLENS_RPC_GRANTS_MISSING';
  end if;
end
$verify$;

commit;

-- 0028_stock_research_latest_growth_run.sql
-- ============================================================================
-- Make the public research RPC read the newest QUARTERLY_GROWTH_QUALITY run for
-- `calc_annual_growth_quality` and `calc_quarterly_quality`.
--
-- Why
-- ---
-- This is the same defect 0021 fixed for `calc_valuation_methods` and 0026 fixed
-- for the backtest, still present on the growth/quality tables.
--
-- The run idempotency key covers the calculation *input snapshot*. Adding a new
-- input to the growth layer (for example the DPS and year-end price the dividend
-- ratios need) legitimately changes that snapshot, so `populate_growth_quality.py`
-- creates a *new* run instead of upserting the previous one. Both runs then hold
-- a full set of rows for the same instrument, because the unique key is
-- `(calculation_run_id, instrument_id, financial_period_id, metric_code)`.
--
-- The previous definition joined `calc_annual_growth_quality` and
-- `calc_quarterly_quality` on `instrument_id` alone, so the frontend would have
-- received every metric once per run - `GROWTH_REVENUE_YOY` twice for the same
-- fiscal year, and so on. The `limit 200` / `limit 100` bounds would also have
-- been consumed by the duplicates, truncating the real series.
--
-- The fix pins both tables to the newest SUCCEEDED run, matching the
-- "newest snapshot wins" rule of 0021 and 0026. No data is changed; this only
-- narrows the read-only RPC's SELECT list.
-- ============================================================================

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
  -- "Newest run wins", the rule 0021 and 0026 already apply elsewhere. Both
  -- growth tables below are pinned to this run, so a re-run with a new input
  -- snapshot replaces the exposed values instead of duplicating them.
  latest_growth_run as (
    select r.id
    from selected_instrument as i
    join public.calculation_runs as r
      on r.scope_type = 'INSTRUMENT' and r.scope_id = i.id::text
    where r.calculation_type = 'QUARTERLY_GROWTH_QUALITY'
      and r.status = 'SUCCEEDED'
    order by r.completed_at desc nulls last, r.created_at desc, r.id
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
            'OPERATING_CASH_FLOW', 'TOTAL_CURRENT_ASSET', 'CURRENT_ASSETS',
            'CURRENT_LIABILITIES', 'TOTAL_LIABILITIES', 'TOTAL_EQUITY',
            'OUTSTANDING_SHARES', 'INTEREST_EXPENSE_NON_OPERATING'
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
  latest_valuation_rows as (
    select distinct on (v.method_code)
      v.method_code,
      v.method_name,
      v.valuation_date,
      v.intrinsic_value,
      v.current_price,
      v.gap_ratio,
      v.verdict,
      v.calculation_status,
      v.stock_type
    from selected_instrument as i
    cross join latest_valuation_date as d
    join public.calc_valuation_methods as v
      on v.instrument_id = i.id and v.valuation_date = d.valuation_date
    order by v.method_code, v.created_at desc, v.id
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
    from latest_valuation_rows as v
  ),
  stock_annual_growth as (
    select jsonb_agg(to_jsonb(growth_rows) order by growth_rows.period_end asc, growth_rows.metric_code asc) as annual_growth
    from (
      select fp.period_end, fp.period_label, g.metric_code, g.value_numeric, g.calculation_status
      from selected_instrument as i
      cross join latest_growth_run as run
      join public.calc_annual_growth_quality as g
        on g.instrument_id = i.id and g.calculation_run_id = run.id
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
      cross join latest_growth_run as run
      join public.calc_quarterly_quality as q
        on q.instrument_id = i.id and q.calculation_run_id = run.id
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
  ),
  active_scenario as (
    -- Exactly one ACTIVE scenario per instrument is the contract enforced by
    -- calculate_valuation.py.
    select
      s.id, s.scenario_code, s.scenario_version, s.projection_year, s.as_of_quarter,
      s.years_available, s.average_dpr_ratio, s.manual_dpr_ratio,
      s.projected_shares_outstanding, s.source_name, s.source_reference
    from selected_instrument as i
    join public.projection_scenarios as s
      on s.instrument_id = i.id and s.status = 'ACTIVE'
    order by s.scenario_version desc
    limit 1
  ),
  stock_projection as (
    select jsonb_build_object(
      'scenario_code', s.scenario_code,
      'scenario_version', s.scenario_version,
      'projection_year', s.projection_year,
      'as_of_quarter', s.as_of_quarter,
      'years_available', s.years_available,
      'average_dpr_ratio', s.average_dpr_ratio,
      'manual_dpr_ratio', s.manual_dpr_ratio,
      'projected_shares_outstanding', s.projected_shares_outstanding,
      'source_name', s.source_name,
      'source_reference', s.source_reference,
      'values', coalesce((
        select jsonb_agg(
          jsonb_build_object(
            'metric_code', v.metric_code,
            'value_numeric', v.value_numeric,
            'unit_code', v.unit_code,
            'period_label', v.period_label,
            'source_kind', v.source_kind
          ) order by v.metric_code
        )
        from (
          select pv.metric_code, pv.value_numeric, pv.unit_code, pv.period_label, pv.source_kind
          from public.projection_values as pv
          where pv.scenario_id = s.id
          order by pv.metric_code
          limit 10
        ) as v
      ), '[]'::jsonb)
    ) as projection
    from active_scenario as s
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
      'dividends', coalesce((select dividends from stock_dividends), '[]'::jsonb),
      'projection', (select projection from stock_projection)
    )
  end;
$$;

revoke all on function public.get_stock_research_data(text) from public, anon, authenticated;
grant execute on function public.get_stock_research_data(text) to anon, authenticated;

comment on function public.get_stock_research_data(text) is
  'Read-only public stock research payload: instrument identity, recent prices, selected financial facts, latest valuation results (newest snapshot per method_code), computed annual growth metrics and quarterly quality metrics (newest QUARTERLY_GROWTH_QUALITY run), dividend history, and the single ACTIVE projection scenario for one ticker.';

do $verify$
begin
  if not has_function_privilege('anon', 'public.get_stock_research_data(text)', 'EXECUTE')
    or not has_function_privilege('authenticated', 'public.get_stock_research_data(text)', 'EXECUTE') then
    raise exception 'STOCKLENS_RPC_GRANTS_MISSING';
  end if;

  -- The dedup rule must actually be present: without it a second growth run
  -- silently doubles every annual metric in the payload.
  if not exists (
    select 1
    from pg_proc as p
    join pg_namespace as n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname = 'get_stock_research_data'
      and pg_get_functiondef(p.oid) like '%latest_growth_run%'
      and pg_get_functiondef(p.oid) like '%calculation_run_id = run.id%'
  ) then
    raise exception 'STOCKLENS_GROWTH_RUN_PIN_MISSING';
  end if;

  if has_table_privilege('anon', 'public.calc_annual_growth_quality', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_annual_growth_quality', 'SELECT')
    or has_table_privilege('anon', 'public.calc_quarterly_quality', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_quarterly_quality', 'SELECT') then
    raise exception 'STOCKLENS_RAW_TABLE_GRANTS_MUST_REMAIN_PRIVATE';
  end if;
end
$verify$;

commit;

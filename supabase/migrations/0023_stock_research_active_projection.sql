-- 0023_stock_research_active_projection.sql
-- ============================================================================
-- Expose the ACTIVE projection scenario for one ticker so the research UI can
-- compare the workbook sample against what is actually stored.
--
-- Why
-- ---
-- The projection is the most assumption-heavy data in the system (it feeds DDM,
-- Discounted Earnings, PE/PBV projections). The UI could show valuation results
-- but not the projection inputs they were derived from, so a reader had no way
-- to check the chain. This adds the active scenario and its values, read-only.
--
-- Bounded on purpose:
--   * only `status = 'ACTIVE'` scenarios (the set `calculate_valuation.py`
--     requires to be exactly one);
--   * at most 10 `projection_values` rows per scenario (unique by metric_code);
--   * column-level grants, so nothing beyond these fields is readable.
-- No data is changed.
-- ============================================================================

begin;

revoke all on table public.projection_scenarios, public.projection_values from stocklens_market_reader;

grant select (
  id, instrument_id, scenario_code, scenario_version, projection_year, as_of_quarter,
  years_available, average_dpr_ratio, manual_dpr_ratio, projected_shares_outstanding,
  status, source_name, source_reference
) on table public.projection_scenarios to stocklens_market_reader;

grant select (scenario_id, metric_code, projection_year, period_label, value_numeric, unit_code, source_kind)
  on table public.projection_values to stocklens_market_reader;

drop policy if exists stocklens_market_reader_select on public.projection_scenarios;
drop policy if exists stocklens_market_reader_select on public.projection_values;

create policy stocklens_market_reader_select on public.projection_scenarios
  for select to stocklens_market_reader using (status = 'ACTIVE');
create policy stocklens_market_reader_select on public.projection_values
  for select to stocklens_market_reader using (
    exists (
      select 1 from public.projection_scenarios as s
      where s.id = projection_values.scenario_id and s.status = 'ACTIVE'
    )
  );

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
  'Read-only public stock research payload: instrument identity, recent prices, selected financial facts, latest valuation results (newest snapshot per method_code), computed annual growth metrics, quarterly quality metrics, dividend history, and the single ACTIVE projection scenario for one ticker.';

do $verify$
begin
  if not has_function_privilege('anon', 'public.get_stock_research_data(text)', 'EXECUTE')
    or not has_function_privilege('authenticated', 'public.get_stock_research_data(text)', 'EXECUTE') then
    raise exception 'STOCKLENS_RPC_GRANTS_MISSING';
  end if;

  -- Projection data must never become directly readable by browser roles.
  if has_table_privilege('anon', 'public.projection_scenarios', 'SELECT')
    or has_table_privilege('authenticated', 'public.projection_scenarios', 'SELECT')
    or has_table_privilege('anon', 'public.projection_values', 'SELECT')
    or has_table_privilege('authenticated', 'public.projection_values', 'SELECT') then
    raise exception 'STOCKLENS_PROJECTION_TABLES_MUST_STAY_PRIVATE';
  end if;

  if has_table_privilege('anon', 'public.financial_facts', 'SELECT')
    or has_table_privilege('authenticated', 'public.financial_facts', 'SELECT') then
    raise exception 'STOCKLENS_RAW_TABLE_GRANTS_MUST_REMAIN_PRIVATE';
  end if;
end
$verify$;

commit;


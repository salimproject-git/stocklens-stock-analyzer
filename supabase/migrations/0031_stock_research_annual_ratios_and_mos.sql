-- 0031_stock_research_annual_ratios_and_mos.sql
-- ============================================================================
-- Extend the public research RPC with the figures that used to be recomputed in
-- the browser, so the UI and n8n read one set of numbers.
--
-- What is added
-- -------------
-- 1. `annual_ratios` — the nine ratio metrics from `calc_annual_ratios` (EPS,
--    BVPS, ROE, GROSS_MARGIN, NET_MARGIN, TOTAL_ASSETS, TOTAL_ASSETS_DERIVED,
--    REVENUE_CAGR_WINDOW, EARNINGS_CAGR_WINDOW), each carrying its `unit_code`,
--    `calculation_status` and `flags`.
-- 2. `mos` on every valuation method row — workbook rule D6,
--    `(IV - price) / IV`. Distinct from `gap_ratio`, which divides by the price.
-- 3. `stock_classification` — the classifier's stored output, read as its own
--    section instead of being inferred from a valuation method row.
-- 4. `data_quality.warnings` — the cases a consumer must not silently average
--    over (shares carried forward, a non-positive denominator, assets whose
--    reported and reconstructed values disagree, missing point-in-time dates).
--
-- Why `unit_code` matters
-- -----------------------
-- The single largest risk in an AI payload is reading a ratio as an amount.
-- `0.1087` is a 10.9% gross margin, not 0.1087 rupiah. Every value therefore
-- travels with its unit, and `annual_ratios` carries one per row rather than
-- relying on the reader to know the metric.
--
-- Dedup
-- -----
-- `annual_ratios` is pinned to the same newest SUCCEEDED `QUARTERLY_GROWTH_QUALITY`
-- run as `annual_growth` (the rule 0021/0026/0028 established). The table holds
-- one row per (run, instrument, period, metric), and a re-run with a new input
-- snapshot creates a *new* run, so an unpinned read would return every metric
-- once per run.
--
-- Backtest stays in its own RPC
-- -----------------------------
-- `get_stock_backtest` is deliberately untouched (decision S4). The data source
-- is the same; only the delivery is separate, which is also how the n8n workflow
-- consumes it.
--
-- Read-only: no table, row or other function is modified. The only grants added
-- are the column-level read grants this function needs.
-- ============================================================================

begin;

-- `calc_metrics_classification` had no reader grant (noted in
-- docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md section 8). The classification section
-- below needs it, and only the columns the payload exposes are granted.
revoke all on table public.calc_metrics_classification from stocklens_market_reader;
grant select (instrument_id, metric_code, value_numeric, classification_code, calculation_status, availability_status)
  on table public.calc_metrics_classification to stocklens_market_reader;

drop policy if exists stocklens_market_reader_select on public.calc_metrics_classification;
create policy stocklens_market_reader_select on public.calc_metrics_classification
  for select to stocklens_market_reader using (true);

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
  -- "Newest run wins", the rule 0021 and 0026 already apply elsewhere. All three
  -- computed sections below are pinned to this run.
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
            'OUTSTANDING_SHARES', 'INTEREST_EXPENSE_NON_OPERATING',
            'TOTAL_ASSETS'
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
      v.mos,
      v.verdict,
      v.calculation_status,
      v.flags,
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
        -- Two different ratios, both kept: gap_ratio divides by the price, mos
        -- divides by the intrinsic value (workbook rule D6).
        'gap_ratio', v.gap_ratio,
        'mos', v.mos,
        'verdict', v.verdict,
        'calculation_status', v.calculation_status,
        'flags', v.flags,
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
  -- The annual ratio layer. `unit_code` travels with every row so a consumer can
  -- never read a margin as an amount, and `flags` records every refusal. Unlike
  -- `annual_growth` this does not filter to VALID: a refused ratio is information
  -- ("this year's CAGR is unavailable because the window starts in a loss"), and
  -- dropping it would make the year look absent instead of unavailable.
  stock_annual_ratios as (
    select jsonb_agg(to_jsonb(ratio_rows) order by ratio_rows.period_end asc, ratio_rows.metric_code asc) as annual_ratios
    from (
      select
        fp.period_end,
        fp.period_label,
        a.metric_code,
        a.value_numeric,
        a.unit_code,
        a.calculation_status,
        a.flags
      from selected_instrument as i
      cross join latest_growth_run as run
      join public.calc_annual_ratios as a
        on a.instrument_id = i.id and a.calculation_run_id = run.id
      join public.financial_periods as fp on fp.id = a.financial_period_id
      order by fp.period_end desc, a.metric_code
      limit 200
    ) as ratio_rows
  ),
  -- The classifier's stored output. It lives in `calc_metrics_classification` as
  -- one row per metric code (the final type is the *value* of
  -- `CLASSIFICATION_FINAL_TYPE`), so it is assembled here rather than read from a
  -- column.
  latest_classification_run as (
    select r.id
    from selected_instrument as i
    join public.calculation_runs as r
      on r.scope_type = 'INSTRUMENT' and r.scope_id = i.id::text
    where r.calculation_type = 'CLASSIFICATION_DESCRIPTIVE'
      and r.status = 'SUCCEEDED'
    order by r.completed_at desc nulls last, r.created_at desc, r.id
    limit 1
  ),
  stock_classification as (
    select jsonb_build_object(
      'final_type', (
        select c.classification_code
        from selected_instrument as i
        cross join latest_classification_run as run
        join public.calc_metrics_classification as c
          on c.instrument_id = i.id and c.calculation_run_id = run.id
        where c.metric_code = 'CLASSIFICATION_FINAL_TYPE'
        limit 1
      ),
      'system_recommendation', (
        select c.classification_code
        from selected_instrument as i
        cross join latest_classification_run as run
        join public.calc_metrics_classification as c
          on c.instrument_id = i.id and c.calculation_run_id = run.id
        where c.metric_code = 'CLASSIFICATION_SYSTEM_RECOMMENDATION'
        limit 1
      ),
      'confidence', (
        select c.value_numeric
        from selected_instrument as i
        cross join latest_classification_run as run
        join public.calc_metrics_classification as c
          on c.instrument_id = i.id and c.calculation_run_id = run.id
        where c.metric_code = 'CLASSIFICATION_CONFIDENCE'
        limit 1
      ),
      'rule_flags', coalesce((
        select jsonb_agg(c.metric_code order by c.metric_code)
        from selected_instrument as i
        cross join latest_classification_run as run
        join public.calc_metrics_classification as c
          on c.instrument_id = i.id and c.calculation_run_id = run.id
        where c.metric_code like 'CLASSIFICATION_%'
          and c.classification_code = 'true'
      ), '[]'::jsonb)
    ) as classification
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
  ),
  -- Warnings a consumer must not silently average over. Each is derived from a
  -- stored fact, never invented: the flags come from the ratio and valuation
  -- rows already assembled above, and the point-in-time warning records the
  -- documented gap that `report_date`/`available_date` are NULL for every
  -- canonical period (docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md section 8).
  data_quality as (
    select jsonb_build_object(
      'warnings', to_jsonb(
        array_remove(array[
          case when exists (
            select 1 from public.calc_annual_ratios as a
            cross join latest_growth_run as run
            where a.calculation_run_id = run.id
              and a.flags @> '["SHARES_CARRIED_FORWARD"]'::jsonb
          ) then 'SHARES_CARRIED_FORWARD: EPS/BVPS use the newest reported annual share count, not the year''s own' end,
          case when exists (
            select 1 from public.calc_annual_ratios as a
            cross join latest_growth_run as run
            where a.calculation_run_id = run.id
              and a.flags @> '["TOTAL_ASSETS_RECONCILIATION_MISMATCH"]'::jsonb
          ) then 'TOTAL_ASSETS_RECONCILIATION_MISMATCH: the reported total assets and liabilities+equity disagree' end,
          case when exists (
            select 1 from public.calc_annual_ratios as a
            cross join latest_growth_run as run
            where a.calculation_run_id = run.id
              and a.calculation_status <> 'VALID'
          ) then 'ANNUAL_RATIO_UNAVAILABLE: at least one annual ratio is unavailable or refused; read its flags' end,
          case when exists (
            select 1 from public.calc_valuation_methods as v
            join selected_instrument as i on i.id = v.instrument_id
            where v.flags @> '["MOS_NOT_APPLICABLE"]'::jsonb
          ) then 'MOS_NOT_APPLICABLE: a method has a non-positive intrinsic value, so MoS is withheld' end,
          case when exists (
            select 1
            from public.financial_periods as fp
            join selected_instrument as i on i.id = fp.instrument_id
            where fp.report_date is null or fp.available_date is null
          ) then 'POINT_IN_TIME_UNAVAILABLE_DATE: report_date/available_date are missing, so results are not point-in-time safe' end
        ], null)
      )
    ) as data_quality
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
      'annual_ratios', coalesce((select annual_ratios from stock_annual_ratios), '[]'::jsonb),
      'quarterly_quality', coalesce((select quarterly_quality from stock_quarterly_quality), '[]'::jsonb),
      'dividends', coalesce((select dividends from stock_dividends), '[]'::jsonb),
      'projection', (select projection from stock_projection),
      'stock_classification', (select classification from stock_classification),
      'data_quality', (select data_quality from data_quality)
    )
  end;
$$;

revoke all on function public.get_stock_research_data(text) from public, anon, authenticated;
grant execute on function public.get_stock_research_data(text) to anon, authenticated;

comment on function public.get_stock_research_data(text) is
  'Read-only public stock research payload: instrument identity, recent prices, selected financial facts, latest valuation results (newest snapshot per method_code, with both gap_ratio and MoS), computed annual growth metrics and annual ratios (newest QUARTERLY_GROWTH_QUALITY run, each ratio carrying its unit_code and flags), quarterly quality metrics, dividend history, the ACTIVE projection scenario, the classifier output, and data-quality warnings for one ticker.';

do $verify$
declare
  definition text;
begin
  if not has_function_privilege('anon', 'public.get_stock_research_data(text)', 'EXECUTE')
    or not has_function_privilege('authenticated', 'public.get_stock_research_data(text)', 'EXECUTE') then
    raise exception 'STOCKLENS_RPC_GRANTS_MISSING';
  end if;

  select pg_get_functiondef(p.oid) into definition
  from pg_proc as p
  join pg_namespace as n on n.oid = p.pronamespace
  where n.nspname = 'public' and p.proname = 'get_stock_research_data';

  -- Every new section must actually be present, or the payload would silently
  -- drop a figure the UI and n8n were promised.
  if definition not like '%calc_annual_ratios%' then
    raise exception 'STOCKLENS_ANNUAL_RATIOS_SECTION_MISSING';
  end if;
  if definition not like '%v.mos%' then
    raise exception 'STOCKLENS_MOS_SECTION_MISSING';
  end if;
  if definition not like '%unit_code%' then
    raise exception 'STOCKLENS_UNIT_CODE_MISSING';
  end if;
  if definition not like '%stock_classification%' then
    raise exception 'STOCKLENS_CLASSIFICATION_SECTION_MISSING';
  end if;
  -- The classifier's run type is `CLASSIFICATION_DESCRIPTIVE`; reading the wrong
  -- type yields a silently null section.
  if definition not like '%CLASSIFICATION_DESCRIPTIVE%' then
    raise exception 'STOCKLENS_CLASSIFICATION_RUN_TYPE_WRONG';
  end if;
  if definition not like '%data_quality%' then
    raise exception 'STOCKLENS_DATA_QUALITY_SECTION_MISSING';
  end if;
  -- The dedup pin must survive: without it a second growth run doubles every
  -- annual ratio in the payload.
  if definition not like '%latest_growth_run%'
    or definition not like '%calculation_run_id = run.id%' then
    raise exception 'STOCKLENS_GROWTH_RUN_PIN_MISSING';
  end if;

  -- The raw tables must stay unreadable by the browser roles; only the RPC may
  -- expose these values.
  if has_table_privilege('anon', 'public.calc_annual_ratios', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_annual_ratios', 'SELECT')
    or has_table_privilege('anon', 'public.calc_metrics_classification', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_metrics_classification', 'SELECT') then
    raise exception 'STOCKLENS_RAW_TABLE_GRANTS_MUST_REMAIN_PRIVATE';
  end if;

  if not has_column_privilege('stocklens_market_reader', 'public.calc_metrics_classification', 'metric_code', 'SELECT') then
    raise exception 'STOCKLENS_CLASSIFICATION_READER_GRANT_MISSING';
  end if;
end
$verify$;

commit;

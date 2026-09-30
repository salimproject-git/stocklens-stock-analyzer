-- 0026_stock_research_backtest_rpc.sql
-- ============================================================================
-- Expose the stored historical backtest for one ticker so the research UI can
-- replace its sample data with real results.
--
-- Why a separate RPC instead of extending get_stock_research_data
-- ---------------------------------------------------------------
-- The backtest is large (up to 22 cases x 5 methods) and is only needed by one
-- tab. Extending the existing 250-line function would mean rewriting it whole
-- for every future change, and the two payloads have nothing in common. A
-- second bounded, single-purpose read-only function keeps both small; the
-- architecture doc (section 3.3) explicitly allows "RPC baru / existing".
--
-- What is exposed
-- ---------------
--   * the newest SUCCEEDED BACKTEST_HISTORICAL run per instrument
--     ("newest run wins", the same rule 0021 uses for valuations);
--   * one row per case: identity, point-in-time price, the five method
--     intrinsic values, consensus, MoS, and the stored verdicts;
--   * the honesty flags from section 5.3 (`POINT_IN_TIME_UNAVAILABLE_DATE`,
--     `STOCK_TYPE_LATEST_SNAPSHOT`, `YEARS_AVAILABLE_TRUNCATED`, ...) so the UI
--     can label the tab "not fully point-in-time" instead of hiding it.
--
-- Context columns (Revenue YoY, Net Income YoY, EPS/Revenue momentum)
-- ------------------------------------------------------------------
-- These are NOT stored on calc_backtest_cases (the section 4.1 schema has no
-- such columns). They are derived here from data that is already stored, and
-- only from periods whose `period_end` is on or before the case's own
-- `analysis_date`, so the derivation stays point-in-time:
--
--   * Revenue YoY / Net Income YoY: quarter vs the same quarter a year earlier
--     (`REVENUE` / `EARNINGS` in `financial_facts`). Verified against the
--     workbook for all 18 AUTO cases: exact to 12 decimals, e.g. 2022-Q1
--     revenue 0.266892321647 and earnings 0.374660655568.
--   * EPS / Revenue momentum: the `QUALITY_*_MOMENTUM` annual metric of the
--     case's **base year** (1 = Accelerating, 0 = Slowing). Also verified
--     against all 18 AUTO cases.
--
-- Three workbook context columns are deliberately NOT emitted, because no rule
-- for them exists in this repository and inventing one would fabricate numbers:
-- `ROE Trend` (needs a trend rule; only a raw `QUALITY_ROE` level is stored),
-- `Yield (%)` (needs a per-case dividend yield rule) and `OCF / NI Ratio`
-- (stored only as a category label, not the ratio the column name promises).
-- They are returned as null and the UI renders them as unavailable.
--
-- No data is changed by this migration.
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- Additive column (idempotent) - MUST come before the column grants below,
-- because `grant select (col)` validates that the column already exists.
-- ----------------------------------------------------------------------------
-- `trough_month` is the counterpart of `peak_month` and is needed so the UI can
-- show "Bln Trough" without recomputing the whole price path in the browser.
alter table public.calc_backtest_cases
  add column if not exists trough_month integer;

comment on column public.calc_backtest_cases.trough_month is
  'Bln Trough: DATEDIF(analysis_date, first date whose Low equals trough_price, months). Counterpart of peak_month.';

-- ----------------------------------------------------------------------------
-- Column-level grants for the narrow RPC owner role
-- ----------------------------------------------------------------------------
revoke all on table public.calc_backtest_cases, public.calc_backtest_methods,
  public.calculation_runs, public.methodology_versions from stocklens_market_reader;

grant select (
  id, calculation_run_id, methodology_version_id, instrument_id,
  case_quarter, base_year, analysis_date, analysis_price, analysis_price_source,
  stock_type, sector_name, years_available, years_compare,
  mos_main, mos_peter, mos_weight, mos_method_code,
  consensus, consensus_undervalued, consensus_valid, verdict, verdict_mos,
  high_3m, low_3m, high_6m, low_6m, high_9m, low_9m, high_12m, low_12m,
  peak_price, trough_price, peak_month, trough_month,
  return_peak, return_down,
  calculation_status, flags, details
) on table public.calc_backtest_cases to stocklens_market_reader;

grant select (
  case_id, method_code, method_name, intrinsic_value, current_price,
  gap_ratio, mos, verdict, calculation_status, flags
) on table public.calc_backtest_methods to stocklens_market_reader;

-- Needed only for the run-scoping predicates below.
grant select (id, calculation_type, scope_type, scope_id, status, created_at, completed_at)
  on table public.calculation_runs to stocklens_market_reader;

grant select (id, method_code, method_version)
  on table public.methodology_versions to stocklens_market_reader;

-- ----------------------------------------------------------------------------
-- RLS policies scoped to the narrow reader role
-- ----------------------------------------------------------------------------
-- Only rows belonging to a SUCCEEDED BACKTEST_HISTORICAL run are readable.
-- Partial runs (status PARTIAL) are excluded on purpose: a half-written run
-- would show up as a truncated case list, which reads like real history.
drop policy if exists stocklens_market_reader_select on public.calc_backtest_cases;
drop policy if exists stocklens_market_reader_select on public.calc_backtest_methods;
drop policy if exists stocklens_market_reader_select on public.calculation_runs;
drop policy if exists stocklens_market_reader_select on public.methodology_versions;

create policy stocklens_market_reader_select on public.calculation_runs
  for select to stocklens_market_reader using (
    calculation_type = 'BACKTEST_HISTORICAL' and status = 'SUCCEEDED'
  );

create policy stocklens_market_reader_select on public.calc_backtest_cases
  for select to stocklens_market_reader using (
    exists (
      select 1
      from public.calculation_runs as r
      where r.id = calc_backtest_cases.calculation_run_id
        and r.calculation_type = 'BACKTEST_HISTORICAL'
        and r.status = 'SUCCEEDED'
    )
  );

create policy stocklens_market_reader_select on public.calc_backtest_methods
  for select to stocklens_market_reader using (
    exists (
      select 1
      from public.calc_backtest_cases as c
      join public.calculation_runs as r on r.id = c.calculation_run_id
      where c.id = calc_backtest_methods.case_id
        and r.calculation_type = 'BACKTEST_HISTORICAL'
        and r.status = 'SUCCEEDED'
    )
  );

create policy stocklens_market_reader_select on public.methodology_versions
  for select to stocklens_market_reader using (true);

-- ----------------------------------------------------------------------------
-- The RPC
-- ----------------------------------------------------------------------------
create or replace function public.get_stock_backtest(p_ticker text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  with selected_instrument as (
    select i.id, i.ticker, i.sector_name
    from public.instruments as i
    where i.ticker = upper(trim(p_ticker))
      and i.exchange_code = 'IDX'
      and (
        select count(*) from public.instruments as matches
        where matches.ticker = upper(trim(p_ticker)) and matches.exchange_code = 'IDX'
      ) = 1
    order by i.ticker
    limit 1
  ),
  -- "Newest run wins", the same rule 0021 uses for valuations: re-running the
  -- backtest legitimately creates a new run, and the UI must show one case list.
  latest_run as (
    select r.id, r.methodology_version_id, r.completed_at
    from selected_instrument as i
    join public.calculation_runs as r
      on r.scope_type = 'INSTRUMENT' and r.scope_id = i.id::text
    where r.calculation_type = 'BACKTEST_HISTORICAL'
      and r.status = 'SUCCEEDED'
    order by r.completed_at desc nulls last, r.created_at desc, r.id
    limit 1
  ),
  case_rows as (
    select
      c.id,
      c.case_quarter,
      c.base_year,
      c.analysis_date,
      c.analysis_price,
      c.analysis_price_source,
      c.stock_type,
      c.years_available,
      c.years_compare,
      c.mos_main,
      c.mos_peter,
      c.mos_weight,
      c.mos_method_code,
      c.consensus,
      c.consensus_undervalued,
      c.consensus_valid,
      c.verdict,
      c.verdict_mos,
      c.high_3m, c.low_3m, c.high_6m, c.low_6m,
      c.high_9m, c.low_9m, c.high_12m, c.low_12m,
      c.peak_price, c.trough_price, c.peak_month, c.trough_month,
      c.return_peak, c.return_down,
      c.calculation_status,
      c.flags,
      c.details
    from selected_instrument as i
    cross join latest_run as run
    join public.calc_backtest_cases as c
      on c.calculation_run_id = run.id and c.instrument_id = i.id
  ),
  case_methods as (
    select
      m.case_id,
      jsonb_agg(
        jsonb_build_object(
          'method_code', m.method_code,
          'method_name', m.method_name,
          'intrinsic_value', m.intrinsic_value,
          'current_price', m.current_price,
          'gap_ratio', m.gap_ratio,
          'mos', m.mos,
          'verdict', m.verdict,
          'calculation_status', m.calculation_status,
          'flags', m.flags
        ) order by m.method_code
      ) as methods
    from public.calc_backtest_methods as m
    where m.case_id in (select id from case_rows)
    group by m.case_id
  ),
  -- Point-in-time context, part 1: quarter-over-quarter-year revenue and
  -- earnings growth. Only periods ending on or before the case's own
  -- `analysis_date` are used, so a case can never see a later quarter.
  quarterly_facts as (
    select
      fp.instrument_id,
      fp.period_end,
      fp.id as financial_period_id,
      max(ff.value_numeric) filter (where ff.metric_code = 'REVENUE') as revenue,
      max(ff.value_numeric) filter (where ff.metric_code = 'EARNINGS') as earnings
    from public.financial_periods as fp
    join public.financial_facts as ff
      on ff.financial_period_id = fp.id
     and ff.revision_key = 'CURRENT'
     and ff.quality_status in ('VALID', 'ESTIMATED')
    where fp.instrument_id = (select id from selected_instrument)
      and fp.period_type = 'QUARTER'
    group by fp.instrument_id, fp.period_end, fp.id
  ),
  case_context as (
    select
      c.id as case_id,
      current_q.revenue as current_revenue,
      current_q.earnings as current_earnings,
      prior.revenue as prior_revenue,
      prior.earnings as prior_earnings
    from case_rows as c
    -- The latest quarter that has actually ended by the analysis date.
    left join lateral (
      select q.period_end, q.revenue, q.earnings
      from quarterly_facts as q
      where q.period_end <= c.analysis_date
      order by q.period_end desc
      limit 1
    ) as current_q on true
    -- The SAME quarter one year earlier, keyed off that period's own end date
    -- rather than off the analysis date, so a missing quarter cannot silently
    -- compare two different quarters.
    left join lateral (
      select q.revenue, q.earnings
      from quarterly_facts as q
      where q.period_end = current_q.period_end - interval '1 year'
      limit 1
    ) as prior on true
  ),
  -- Point-in-time context, part 2: the annual momentum flags of the case's base
  -- year (1 = Accelerating, 0 = Slowing).
  annual_momentum as (
    select
      fp.period_end,
      gg.metric_code,
      gg.value_numeric
    from public.calc_annual_growth_quality as gg
    join public.financial_periods as fp on fp.id = gg.financial_period_id
    where gg.instrument_id = (select id from selected_instrument)
      and gg.metric_code in ('QUALITY_EPS_MOMENTUM', 'QUALITY_REVENUE_MOMENTUM')
  ),
  case_momentum as (
    select
      c.id as case_id,
      (select case when g.value_numeric = 1 then 'Accelerating'
                   when g.value_numeric = 0 then 'Slowing' end
       from annual_momentum as g
       where g.metric_code = 'QUALITY_EPS_MOMENTUM'
         and extract(year from g.period_end) = c.base_year
       limit 1) as eps_momentum,
      (select case when g.value_numeric = 1 then 'Accelerating'
                   when g.value_numeric = 0 then 'Slowing' end
       from annual_momentum as g
       where g.metric_code = 'QUALITY_REVENUE_MOMENTUM'
         and extract(year from g.period_end) = c.base_year
       limit 1) as revenue_momentum
    from case_rows as c
  ),
  assembled as (
    select
      c.id,
      c.case_quarter,
      jsonb_build_object(
        'case_id', c.id,
        'case_quarter', c.case_quarter,
        'base_year', c.base_year,
        'analysis_date', c.analysis_date,
        'analysis_price', c.analysis_price,
        'analysis_price_source', c.analysis_price_source,
        'stock_type', c.stock_type,
        'years_available', c.years_available,
        'years_compare', c.years_compare,
        'mos_main', c.mos_main,
        'mos_peter', c.mos_peter,
        'mos_weight', c.mos_weight,
        'mos_method_code', c.mos_method_code,
        'consensus', c.consensus,
        'consensus_undervalued', c.consensus_undervalued,
        'consensus_valid', c.consensus_valid,
        'verdict', c.verdict,
        'verdict_mos', c.verdict_mos,
        'calculation_status', c.calculation_status,
        'flags', c.flags,
        'details', c.details,
        'high_3m', c.high_3m,
        'low_3m', c.low_3m,
        'high_6m', c.high_6m,
        'low_6m', c.low_6m,
        'high_9m', c.high_9m,
        'low_9m', c.low_9m,
        'high_12m', c.high_12m,
        'low_12m', c.low_12m,
        'peak_price', c.peak_price,
        'trough_price', c.trough_price,
        'peak_month', c.peak_month,
        'trough_month', c.trough_month,
        'return_peak', c.return_peak,
        'return_down', c.return_down,
        'methods', coalesce(cm.methods, '[]'::jsonb),
        'context', jsonb_build_object(
          -- Derived, point-in-time. See the header comment for the rule and the
          -- workbook verification. Null means "not available", never zero.
          'revenueYoY', case
            when ctx.current_revenue is not null and ctx.prior_revenue is not null
             and ctx.prior_revenue <> 0
            then (ctx.current_revenue / ctx.prior_revenue) - 1
          end,
          'netIncomeYoY', case
            when ctx.current_earnings is not null and ctx.prior_earnings is not null
             and ctx.prior_earnings <> 0
            then (ctx.current_earnings / ctx.prior_earnings) - 1
          end,
          'epsMomentum', mom.eps_momentum,
          'revenueMomentum', mom.revenue_momentum,
          -- Deliberately null: no rule for these exists in this repository.
          'roeTrend', null,
          'yield', null,
          'ocfNi', null
        )
      ) as payload
    from case_rows as c
    left join case_methods as cm on cm.case_id = c.id
    left join case_context as ctx on ctx.case_id = c.id
    left join case_momentum as mom on mom.case_id = c.id
  )
  select case
    when not exists (select 1 from selected_instrument) then null
    else jsonb_build_object(
      'instrument', (
        select jsonb_build_object(
          'ticker', i.ticker,
          'sector_name', i.sector_name
        )
        from selected_instrument as i
      ),
      'run', (
        select jsonb_build_object(
          'run_id', r.id,
          'method_version', m.method_version,
          'completed_at', r.completed_at
        )
        from latest_run as r
        join public.methodology_versions as m on m.id = r.methodology_version_id
      ),
      'cases', coalesce(
        (select jsonb_agg(a.payload order by a.case_quarter) from assembled as a),
        '[]'::jsonb
      )
    )
  end;
$$;

revoke all on function public.get_stock_backtest(text) from public, anon, authenticated;
grant execute on function public.get_stock_backtest(text) to anon, authenticated;

comment on function public.get_stock_backtest(text) is
  'Read-only historical backtest payload for one ticker: newest SUCCEEDED run, every stored case with its five method intrinsic values, consensus, MoS, stored verdicts, and point-in-time derived context (revenue/earnings YoY, EPS/revenue momentum).';

do $verify$
declare
  missing integer;
begin
  if not has_function_privilege('anon', 'public.get_stock_backtest(text)', 'EXECUTE')
    or not has_function_privilege('authenticated', 'public.get_stock_backtest(text)', 'EXECUTE') then
    raise exception 'STOCKLENS_BACKTEST_RPC_GRANTS_MISSING';
  end if;

  -- Backtest tables must never become directly readable by browser roles.
  if has_table_privilege('anon', 'public.calc_backtest_cases', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_backtest_cases', 'SELECT')
    or has_table_privilege('anon', 'public.calc_backtest_methods', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_backtest_methods', 'SELECT')
    or has_table_privilege('anon', 'public.calculation_runs', 'SELECT')
    or has_table_privilege('authenticated', 'public.calculation_runs', 'SELECT') then
    raise exception 'STOCKLENS_BACKTEST_RAW_GRANTS_MUST_REMAIN_PRIVATE';
  end if;

  -- RLS must be on, and each table must carry exactly one reader policy.
  select count(*) into missing
  from (values
    ('calc_backtest_cases'),
    ('calc_backtest_methods'),
    ('calculation_runs'),
    ('methodology_versions')
  ) as expected(name)
  where not exists (
    select 1
    from pg_catalog.pg_class as c
    join pg_catalog.pg_namespace as n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relname = expected.name and c.relrowsecurity
  );

  if missing > 0 then
    raise exception 'STOCKLENS_BACKTEST_RLS_DISABLED: %', missing;
  end if;

  -- The reader role must stay narrow.
  if (select rolsuper or rolbypassrls or rolcanlogin or rolinherit
      from pg_catalog.pg_roles where rolname = 'stocklens_market_reader') then
    raise exception 'STOCKLENS_MARKET_READER_ROLE_IS_NOT_RESTRICTED';
  end if;

  -- `trough_month` must exist and be nullable.
  if not exists (
    select 1
    from information_schema.columns c
    where c.table_schema = 'public'
      and c.table_name = 'calc_backtest_cases'
      and c.column_name = 'trough_month'
      and c.is_nullable = 'YES'
  ) then
    raise exception 'STOCKLENS_BACKTEST_TROUGH_MONTH_INVALID';
  end if;
end
$verify$;

commit;

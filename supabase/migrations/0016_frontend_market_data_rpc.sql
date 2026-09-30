-- Expose only the read-only stock data needed by the public Next.js UI.
-- Raw tables stay private to service_role; this migration does not change data.

begin;

-- The RPC owner must not be a superuser, table owner, or BYPASSRLS role.
-- It can read only the explicitly granted columns below; its narrow RLS
-- policies do not grant access to anon/authenticated callers.
create role stocklens_market_reader nologin noinherit nobypassrls;

grant usage on schema public to stocklens_market_reader;

do $policy_check$
begin
  if exists (
    select 1 from pg_catalog.pg_policy as p
    join pg_catalog.pg_class as c on c.oid = p.polrelid
    join pg_catalog.pg_namespace as n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relname in ('instruments', 'prices_daily', 'financial_periods', 'financial_facts', 'calc_valuation_methods')
      and p.polname = 'stocklens_market_reader_select'
  ) then
    raise exception 'STOCKLENS_MARKET_READER_POLICY_ALREADY_EXISTS';
  end if;
end
$policy_check$;

revoke all on table public.instruments, public.prices_daily,
  public.financial_periods, public.financial_facts,
  public.calc_valuation_methods from stocklens_market_reader;

grant select (id, ticker, company_name, sector_name, subsector_name, currency_code)
  on table public.instruments to stocklens_market_reader;
grant select (exchange_code) on table public.instruments to stocklens_market_reader;
grant select (instrument_id, trading_date, close_price, market_cap, currency_code)
  on table public.prices_daily to stocklens_market_reader;
grant select (id, instrument_id, period_type, period_label, period_end, period_basis, statement_scope)
  on table public.financial_periods to stocklens_market_reader;
grant select (financial_period_id, metric_code, value_numeric, unit_code, currency_code, quality_status, revision_key)
  on table public.financial_facts to stocklens_market_reader;
grant select (instrument_id, valuation_date, method_code, method_name, intrinsic_value,
  current_price, gap_ratio, verdict, calculation_status)
  on table public.calc_valuation_methods to stocklens_market_reader;

create policy stocklens_market_reader_select on public.instruments
  for select to stocklens_market_reader using (true);
create policy stocklens_market_reader_select on public.prices_daily
  for select to stocklens_market_reader using (true);
create policy stocklens_market_reader_select on public.financial_periods
  for select to stocklens_market_reader using (true);
create policy stocklens_market_reader_select on public.financial_facts
  for select to stocklens_market_reader using (true);
create policy stocklens_market_reader_select on public.calc_valuation_methods
  for select to stocklens_market_reader using (true);

create or replace function public.get_market_overview_page(p_page integer default 1)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  with requested_page as (
    select least(
      greatest(coalesce(p_page, 1), 1),
      greatest(ceil((select count(*)::numeric from public.instruments where exchange_code = 'IDX') / 5)::integer, 1)
    ) as page_number
  ),
  instrument_page as (
    select i.id, i.ticker, i.company_name, i.sector_name, i.currency_code
    from public.instruments as i
    where i.exchange_code = 'IDX'
    order by i.ticker
    limit 5
    offset ((select page_number - 1 from requested_page) * 5)
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
      coalesce(history.sparkline, '[]'::jsonb) as sparkline
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
  )
  select jsonb_build_object(
    'current_page', (select page_number from requested_page),
    'page_size', 5,
    'total_count', (select count(*) from public.instruments where exchange_code = 'IDX'),
    'stocks', coalesce((
      select jsonb_agg(to_jsonb(stock_rows) order by stock_rows.ticker)
      from stock_rows
    ), '[]'::jsonb)
  );
$$;

revoke all on function public.get_market_overview_page(integer) from public, anon, authenticated;
grant execute on function public.get_market_overview_page(integer) to anon, authenticated;
-- NOTE: owner transfer requires a role with SET ROLE on stocklens_market_reader
-- (e.g. postgres via the SQL editor). Without it the function stays owned by
-- postgres, which has BYPASSRLS, so the least-privilege grants below are not
-- actually enforced. See supabase/migrations/0019_*.sql.
-- alter function public.get_market_overview_page(integer) owner to stocklens_market_reader;

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
            'TOTAL_LIABILITIES', 'TOTAL_EQUITY'
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
        'calculation_status', v.calculation_status
      ) order by v.method_code
    ) as valuation_methods
    from selected_instrument as i
    cross join latest_valuation_date as d
    join public.calc_valuation_methods as v
      on v.instrument_id = i.id and v.valuation_date = d.valuation_date
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
      'valuation_methods', coalesce((select valuation_methods from stock_valuations), '[]'::jsonb)
    )
  end;
$$;

revoke all on function public.get_stock_research_data(text) from public, anon, authenticated;
grant execute on function public.get_stock_research_data(text) to anon, authenticated;
-- alter function public.get_stock_research_data(text) owner to stocklens_market_reader;
-- Functions in public can receive default EXECUTE privileges. Explicitly remove
-- those and grant only execution of these two bounded, read-only API functions.

comment on function public.get_market_overview_page(integer) is
  'Paginated public market overview with latest daily quote and up to 12 monthly close points.';
comment on function public.get_stock_research_data(text) is
  'Read-only public stock research payload limited to one ticker, recent prices, selected financial facts, and latest valuation results.';

-- (no schema CREATE grant is needed by the reader role)

do $verify$
begin
  if (select rolsuper or rolbypassrls or rolcanlogin or rolinherit
      from pg_catalog.pg_roles where rolname = 'stocklens_market_reader') then
    raise exception 'STOCKLENS_MARKET_READER_ROLE_IS_NOT_RESTRICTED';
  end if;

  if has_table_privilege('anon', 'public.instruments', 'SELECT')
    or has_table_privilege('authenticated', 'public.instruments', 'SELECT')
    or has_table_privilege('anon', 'public.prices_daily', 'SELECT')
    or has_table_privilege('authenticated', 'public.prices_daily', 'SELECT')
    or has_table_privilege('anon', 'public.financial_periods', 'SELECT')
    or has_table_privilege('authenticated', 'public.financial_periods', 'SELECT')
    or has_table_privilege('anon', 'public.financial_facts', 'SELECT')
    or has_table_privilege('authenticated', 'public.financial_facts', 'SELECT')
    or has_table_privilege('anon', 'public.calc_valuation_methods', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_valuation_methods', 'SELECT') then
    raise exception 'STOCKLENS_RAW_TABLE_GRANTS_MUST_REMAIN_PRIVATE';
  end if;

  if not has_function_privilege('anon', 'public.get_market_overview_page(integer)', 'EXECUTE')
    or not has_function_privilege('authenticated', 'public.get_market_overview_page(integer)', 'EXECUTE')
    or not has_function_privilege('anon', 'public.get_stock_research_data(text)', 'EXECUTE')
    or not has_function_privilege('authenticated', 'public.get_stock_research_data(text)', 'EXECUTE') then
    raise exception 'STOCKLENS_RPC_GRANTS_MISSING';
  end if;
end
$verify$;

commit;
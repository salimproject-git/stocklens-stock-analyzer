-- Bounded read-only reader for the latest immutable fundamental snapshot and
-- latest price-sensitive daily result. Raw calc tables remain service-role only.
begin;

create or replace function public.get_stock_valuation_frequency(p_ticker text)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $$
  with selected_instrument as (
    select i.id, i.ticker
    from public.instruments as i
    where i.ticker = upper(trim(p_ticker))
      and i.exchange_code = 'IDX'
      and (select count(*) from public.instruments as x
           where x.ticker = upper(trim(p_ticker)) and x.exchange_code = 'IDX') = 1
  ), latest_snapshot as (
    select s.*
    from public.calc_valuation_fundamental_snapshots as s
    join selected_instrument as i on i.id = s.instrument_id
    order by s.snapshot_date desc, s.created_at desc, s.id
    limit 1
  ), latest_daily as (
    select d.*
    from public.calc_valuation_daily_status as d
    join selected_instrument as i on i.id = d.instrument_id
    join latest_snapshot as s on s.id = d.snapshot_id
    order by d.trading_date desc, d.created_at desc, d.id
    limit 1
  ), fundamental_methods as (
    select coalesce(jsonb_agg(jsonb_build_object(
      'method_code', m.method_code,
      'method_name', m.method_name,
      'valuation_date', s.snapshot_date,
      'stock_type', m.stock_type,
      'intrinsic_value', m.intrinsic_value,
      'calculation_status', m.calculation_status,
      'flags', m.flags,
      'details', m.details
    ) order by m.method_code), '[]'::jsonb) as rows
    from latest_snapshot as s
    join public.calc_valuation_fundamental_methods as m on m.snapshot_id = s.id
  ), daily_methods as (
    select coalesce(jsonb_agg(jsonb_build_object(
      'method_code', m.method_code,
      'intrinsic_value', m.intrinsic_value,
      'valuation_date', d.trading_date,
      'stock_type', (select fs.stock_type from public.calc_valuation_fundamental_methods fs
                     where fs.snapshot_id = d.snapshot_id and fs.method_code = m.method_code),
      'current_price', m.current_price,
      'gap_ratio', m.gap_ratio,
      'mos', m.mos,
      'verdict', m.verdict,
      'calculation_status', m.calculation_status,
      'flags', m.flags
    ) order by m.method_code), '[]'::jsonb) as rows
    from latest_daily as d
    join public.calc_valuation_daily_methods as m on m.daily_status_id = d.id
  )
  select case when not exists (select 1 from selected_instrument) then null
    else jsonb_build_object(
      'instrument', (select jsonb_build_object('ticker', i.ticker) from selected_instrument as i),
      'fundamental', (select jsonb_build_object(
        'snapshot_id', s.id,
        'snapshot_date', s.snapshot_date,
        'historical_price_cutoff', s.historical_price_cutoff,
        'as_of_financial_period_id', s.as_of_financial_period_id,
        'projection_scenario_id', s.projection_scenario_id,
        'stock_type', s.stock_type,
        'years_available', s.years_available,
        'years_compare', s.years_compare,
        'input_hash', s.input_hash,
        'calculation_run_id', s.calculation_run_id,
        'methods', (select rows from fundamental_methods)
      ) from latest_snapshot as s),
      'daily', (select jsonb_build_object(
        'trading_date', d.trading_date,
        'current_price', d.current_price,
        'consensus_verdict', d.consensus_verdict,
        'valid_method_count', d.valid_method_count,
        'undervalued_method_count', d.undervalued_method_count,
        'based_method_code', d.based_method_code,
        'based_mos', d.based_mos,
        'based_mos_verdict', d.based_mos_verdict,
        'mos_threshold', coalesce((
          select (p.parameter_value #>> '{}')::numeric
          from public.calculation_parameters p
          where p.parameter_code = 'mos_entry_threshold_frontend'
          order by p.parameter_version desc limit 1
        ), 0.30::numeric),
        'input_hash', d.input_hash,
        'calculation_run_id', d.calculation_run_id,
        'snapshot_id', d.snapshot_id,
        'methods', (select rows from daily_methods)
      ) from latest_daily as d)
    )
  end;
$$;

revoke all on function public.get_stock_valuation_frequency(text) from public, anon, authenticated;
grant execute on function public.get_stock_valuation_frequency(text) to anon, authenticated;
comment on function public.get_stock_valuation_frequency(text) is
  'Bounded read-only latest fundamental intrinsic snapshot plus latest daily comparison for one unique IDX ticker.';

do $verify$
begin
  if not has_function_privilege('anon', 'public.get_stock_valuation_frequency(text)', 'EXECUTE')
    or not has_function_privilege('authenticated', 'public.get_stock_valuation_frequency(text)', 'EXECUTE') then
    raise exception 'VALUATION_FREQUENCY_RPC_GRANT_MISSING';
  end if;
  if has_table_privilege('anon', 'public.calc_valuation_fundamental_snapshots', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_valuation_fundamental_snapshots', 'SELECT')
    or has_table_privilege('anon', 'public.calc_valuation_daily_status', 'SELECT')
    or has_table_privilege('authenticated', 'public.calc_valuation_daily_status', 'SELECT') then
    raise exception 'VALUATION_FREQUENCY_RAW_TABLE_BROWSER_GRANT';
  end if;
end
$verify$;

commit;
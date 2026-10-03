-- 0032_stock_valuation_summary_rpc.sql
-- ============================================================================
-- Expose the current valuation summary used by the Overview card.
--
-- The per-method intrinsic values, verdicts and MoS already live in
-- calc_valuation_methods. This RPC owns only the aggregation that the UI used
-- to repeat: method consensus and the MoS entry classification.
-- ============================================================================

begin;

create or replace function public.get_stock_valuation_summary(p_ticker text)
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
      and (
        select count(*)
        from public.instruments as matches
        where matches.ticker = upper(trim(p_ticker))
          and matches.exchange_code = 'IDX'
      ) = 1
  ),
  latest_valuation_date as (
    select max(v.valuation_date) as valuation_date
    from selected_instrument as i
    join public.calc_valuation_methods as v on v.instrument_id = i.id
  ),
  valuation_rows as (
    select distinct on (v.method_code)
      v.method_code,
      v.stock_type,
      v.intrinsic_value,
      v.mos,
      v.verdict,
      v.calculation_status,
      v.created_at,
      v.id
    from selected_instrument as i
    cross join latest_valuation_date as d
    join public.calc_valuation_methods as v
      on v.instrument_id = i.id
     and v.valuation_date = d.valuation_date
    order by v.method_code, v.created_at desc, v.id
  ),
  parameters as (
    select
      coalesce((
        select (p.parameter_value #>> '{}')::integer
        from public.calculation_parameters as p
        where p.parameter_code = 'iv_consensus_min_methods'
          and p.resolution_status = 'RESOLVED'
        order by p.parameter_version desc
        limit 1
      ), 3) as min_methods,
      coalesce((
        select (p.parameter_value #>> '{}')::numeric
        from public.calculation_parameters as p
        where p.parameter_code = 'mos_entry_threshold_frontend'
        order by p.parameter_version desc
        limit 1
      ), 0.30::numeric) as mos_threshold
  ),
  counts as (
    select
      count(*) filter (
        where r.intrinsic_value is not null
          and r.verdict in ('UNDERVALUED', 'OVERVALUED')
          and r.calculation_status in ('VALID', 'APPROXIMATED')
      )::integer as valid_count,
      count(*) filter (
        where r.intrinsic_value is not null
          and r.verdict = 'UNDERVALUED'
          and r.calculation_status in ('VALID', 'APPROXIMATED')
      )::integer as undervalued_count
    from valuation_rows as r
  ),
  main_method as (
    select r.*
    from valuation_rows as r
    cross join lateral (
      select case
        when lower(coalesce(r.stock_type, '')) in ('stalwart', 'fast grower')
          then 'TYPE_SECTOR_WEIGHTED'
        else 'PETER_LYNCH'
      end as preferred_code
    ) as preferred
    where r.method_code = preferred.preferred_code
      and r.intrinsic_value > 0
    union all
    select r.*
    from valuation_rows as r
    cross join lateral (
      select case
        when lower(coalesce(r.stock_type, '')) in ('stalwart', 'fast grower')
          then 'PETER_LYNCH'
        else 'TYPE_SECTOR_WEIGHTED'
      end as alternative_code
    ) as alternative
    where r.method_code = alternative.alternative_code
      and r.intrinsic_value > 0
      and not exists (
        select 1
        from valuation_rows as preferred_row
        where preferred_row.method_code = case
          when lower(coalesce(r.stock_type, '')) in ('stalwart', 'fast grower')
            then 'TYPE_SECTOR_WEIGHTED'
          else 'PETER_LYNCH'
        end
          and preferred_row.intrinsic_value > 0
      )
  )
  select case
    when not exists (select 1 from selected_instrument)
      or not exists (select 1 from valuation_rows)
      then null
    else jsonb_build_object(
      'method_verdict', case
        when c.valid_count < p.min_methods then 'N/A'
        when c.undervalued_count * 2 > c.valid_count then 'UNDERVALUED'
        else 'OVERVALUED'
      end,
      'method_undervalued_count', c.undervalued_count,
      'method_valid_count', c.valid_count,
      'mos_method_code', m.method_code,
      'mos', m.mos,
      'mos_verdict', case
        when m.mos is null then 'N/A'
        when m.mos >= p.mos_threshold then 'UNDERVALUED'
        else 'OVERVALUED'
      end,
      'mos_threshold', p.mos_threshold
    )
  end
  from counts as c
  cross join parameters as p
  left join main_method as m on true;
$$;

revoke all on function public.get_stock_valuation_summary(text) from public, anon, authenticated;
grant execute on function public.get_stock_valuation_summary(text) to anon, authenticated;

comment on function public.get_stock_valuation_summary(text) is
  'Read-only current valuation summary: stored-method consensus and stored-MoS classification for one IDX ticker.';

commit;
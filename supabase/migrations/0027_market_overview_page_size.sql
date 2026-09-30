-- Make the market overview page size selectable (8 / 12 / 16 / 20).
--
-- The page size used to be hardcoded to 5 in two places (`limit 5` and
-- `offset ... * 5`), so the market page could only ever show five cards. It is
-- now a parameter with an explicit whitelist, defaulting to 8. Nothing else
-- about the payload changes: same columns, same 12-month sparkline, same
-- IDX-only scope, same read-only guarantee. No data is changed.
--
-- Bounds are unchanged in spirit: the largest allowed page is 20, so the RPC
-- still returns a bounded slice instead of the whole table.

begin;

-- The one-argument version has to be dropped rather than replaced. Adding a
-- second parameter with a DEFAULT would create a *new* overload alongside the
-- old one, and PostgREST cannot choose between `(p_page)` and
-- `(p_page, p_page_size default 8)` when a caller supplies only `p_page`; it
-- fails with "Could not choose the best candidate function".
drop function if exists public.get_market_overview_page(integer);

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
    'page_size', (select page_size from requested),
    'total_count', (select count(*) from public.instruments where exchange_code = 'IDX'),
    'stocks', coalesce((
      select jsonb_agg(to_jsonb(stock_rows) order by stock_rows.ticker)
      from stock_rows
    ), '[]'::jsonb)
  );
$$;

comment on function public.get_market_overview_page(integer, integer) is
  'Paginated public market overview with latest daily quote and up to 12 monthly close points. p_page_size is whitelisted to 8/12/16/20 and defaults to 8.';

revoke all on function public.get_market_overview_page(integer, integer) from public, anon, authenticated;
grant execute on function public.get_market_overview_page(integer, integer) to anon, authenticated;

-- Same pending owner transfer as 0019: this new function signature is owned by
-- postgres until 0019's `alter function ... owner to stocklens_market_reader`
-- is applied from the Supabase SQL editor, so the column-level grants in 0016
-- remain documentation only for the duration. See
-- supabase/migrations/0019_market_rpc_least_privilege_owner.sql.

do $verify$
begin
  if not has_function_privilege('anon', 'public.get_market_overview_page(integer, integer)', 'EXECUTE')
    or not has_function_privilege('authenticated', 'public.get_market_overview_page(integer, integer)', 'EXECUTE') then
    raise exception 'STOCKLENS_MARKET_RPC_GRANTS_MISSING';
  end if;

  -- The superseded one-argument signature must be gone, otherwise PostgREST
  -- would have two candidates for a `p_page`-only call.
  if exists (
    select 1
    from pg_catalog.pg_proc as p
    join pg_catalog.pg_namespace as n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname = 'get_market_overview_page'
      and pg_catalog.pg_get_function_identity_arguments(p.oid) = 'p_page integer'
  ) then
    raise exception 'STOCKLENS_MARKET_RPC_OLD_SIGNATURE_STILL_PRESENT';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc as p
    join pg_catalog.pg_namespace as n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname = 'get_market_overview_page'
      and pg_catalog.pg_get_function_identity_arguments(p.oid) = 'p_page integer, p_page_size integer'
  ) then
    raise exception 'STOCKLENS_MARKET_RPC_NEW_SIGNATURE_MISSING';
  end if;
end
$verify$;

commit;

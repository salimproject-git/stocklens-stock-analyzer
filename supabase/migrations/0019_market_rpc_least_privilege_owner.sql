-- Harden the public market RPCs so they run as the narrow, non-login
-- `stocklens_market_reader` role instead of `postgres` (which has BYPASSRLS).
-- This keeps the RPCs from being able to read anything beyond the explicit
-- column-level grants and RLS policies created in 0016/0017/0018. No data is
-- changed by this migration.
--
-- STATUS: NOT YET APPLIED to the remote project.
--
-- Reason: `alter function ... owner to` requires the executing role to be able
-- to SET ROLE stocklens_market_reader. The MCP migration runner is not a member
-- of that role, so it fails with:
--   ERROR 42501: must be able to SET ROLE "stocklens_market_reader"
--
-- Apply this from the Supabase SQL editor (running as `postgres`) or any role
-- that is a member of `stocklens_market_reader`.
--
-- Until this is applied, `get_market_overview_page` and
-- `get_stock_research_data` are owned by `postgres`, so the column-level grants
-- in 0016/0017 are documentation only: the functions run with postgres
-- privileges and can read every column of the five granted tables. The blast
-- radius is still limited to those tables and the bounded queries inside the
-- functions (5 / 260 / 40 rows, single ticker, IDX only), but the intended
-- least-privilege boundary is not enforced.

begin;

do $guard$
begin
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'stocklens_market_reader') then
    raise exception 'STOCKLENS_MARKET_READER_ROLE_MISSING';
  end if;

  if (select rolsuper or rolbypassrls or rolcanlogin or rolinherit
      from pg_catalog.pg_roles where rolname = 'stocklens_market_reader') then
    raise exception 'STOCKLENS_MARKET_READER_ROLE_IS_NOT_RESTRICTED';
  end if;
end
$guard$;

alter function public.get_market_overview_page(integer, integer) owner to stocklens_market_reader;
alter function public.get_stock_research_data(text) owner to stocklens_market_reader;

revoke all on function public.get_market_overview_page(integer, integer) from public, anon, authenticated;
revoke all on function public.get_stock_research_data(text) from public, anon, authenticated;
grant execute on function public.get_market_overview_page(integer, integer) to anon, authenticated;
grant execute on function public.get_stock_research_data(text) to anon, authenticated;

do $verify$
begin
  if exists (
    select 1
    from pg_catalog.pg_proc as p
    join pg_catalog.pg_namespace as n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname in ('get_market_overview_page', 'get_stock_research_data')
      and pg_catalog.pg_get_userbyid(p.proowner) <> 'stocklens_market_reader'
  ) then
    raise exception 'STOCKLENS_RPC_OWNER_NOT_LOW_PRIVILEGE';
  end if;

  if not has_function_privilege('anon', 'public.get_market_overview_page(integer, integer)', 'EXECUTE')
    or not has_function_privilege('authenticated', 'public.get_market_overview_page(integer, integer)', 'EXECUTE')
    or not has_function_privilege('anon', 'public.get_stock_research_data(text)', 'EXECUTE')
    or not has_function_privilege('authenticated', 'public.get_stock_research_data(text)', 'EXECUTE') then
    raise exception 'STOCKLENS_RPC_GRANTS_MISSING';
  end if;
end
$verify$;

commit;

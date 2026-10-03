-- Allow trusted server-side verification/consumers as well as browser readers.
begin;
grant execute on function public.get_stock_valuation_frequency(text) to service_role;
do $verify$
begin
  if not has_function_privilege('service_role','public.get_stock_valuation_frequency(text)','EXECUTE') then
    raise exception 'VALUATION_FREQUENCY_SERVICE_ROLE_GRANT_MISSING';
  end if;
end
$verify$;
commit;
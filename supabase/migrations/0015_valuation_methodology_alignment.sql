-- 0015_valuation_methodology_alignment.sql
-- -----------------------------------------------------------------------------
-- Keep the DRAFT valuation methodology parameter hash aligned with the
-- supplemental local registry (including TURN AROUND -> Conservative mode).
-- Refuse to modify a methodology that has already been published or retired.

update public.methodology_versions
set parameter_spec = jsonb_set(
      parameter_spec,
      '{type_to_valuation_mode}',
      '{"FAST GROWER":"Aggressive","CYCLICAL":"Moderate","ASSET PLAY":"Moderate","STALWART":"Moderate","TURN AROUND":"Conservative","DEFAULT":"Conservative"}'::jsonb,
      true
    ),
    parameter_hash = '14e9b5bdc77e81e0b3c0a093824aada65d7cbb0070283daff17c8fdb0eaeede4',
    updated_at = now()
where method_code = 'VALUATION_CURRENT'
  and method_version = '1.0.0'
  and status = 'DRAFT'
  and formula_hash = '5affb4ab87f89cd7494bac7134bb5a0ae2eda97297cc8517703f61490bd05d93';

do $$
begin
  if not exists (
    select 1
    from public.methodology_versions
    where method_code = 'VALUATION_CURRENT'
      and method_version = '1.0.0'
      and formula_hash = '5affb4ab87f89cd7494bac7134bb5a0ae2eda97297cc8517703f61490bd05d93'
      and parameter_hash = '14e9b5bdc77e81e0b3c0a093824aada65d7cbb0070283daff17c8fdb0eaeede4'
  ) then
    raise exception 'VALUATION_METHODOLOGY_ALIGNMENT_FAILED';
  end if;
end
$$;
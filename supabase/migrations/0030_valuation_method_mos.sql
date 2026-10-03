-- 0030_valuation_method_mos.sql
-- ============================================================================
-- Store the margin of safety on `calc_valuation_methods`.
--
-- Why
-- ---
-- Two different ratios were both being called "MoS":
--
--   gap_ratio (already stored)  = (IV - price) / price
--   MoS, workbook rule D6       = (IV - price) / IV
--
-- For AUTO's DDM row these are -0.5739 and -1.3467 from the same inputs. The
-- frontend computed the second one in the browser (`computeMos`), so the UI and
-- any other consumer could disagree, and n8n could not see the figure at all.
-- This migration gives the D6 value a home
-- (docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md, Langkah 2).
--
-- The divisor is the intrinsic value, not the price, so the ratio is only
-- defined for a positive IV:
--
--   IV > 0  ->  (IV - price) / IV, stored as a number
--   IV = 0  ->  NULL + MOS_DENOMINATOR_ZERO
--   IV < 0  ->  NULL + MOS_NOT_APPLICABLE
--
-- The negative-IV case is refused on purpose. A negative divisor flips the sign
-- of the whole ratio: GEMA's Peter Lynch IV of -22 against a price of 93 would
-- report +522%, which reads as a large discount when the model actually values
-- the company far below its price. `gap_ratio` is unaffected and keeps its own
-- semantics.
--
-- `calc_backtest_methods.mos` already existed with exactly this rule
-- (`backtest_engine.mos_for`); the two tables now agree.
--
-- Backfill
-- --------
-- Existing rows are filled from their own stored `intrinsic_value` and
-- `current_price`, so no value is invented: the inputs are already in the row.
-- Rows whose IV is NULL or non-positive are left NULL and flagged. The flags are
-- appended, never replaced, so the provenance flags a row already carries
-- survive.
-- ============================================================================

begin;

alter table public.calc_valuation_methods
  add column if not exists mos numeric;

comment on column public.calc_valuation_methods.mos is
  'Margin of safety, workbook rule D6: (intrinsic_value - current_price) / intrinsic_value. NULL when intrinsic_value <= 0; see flags MOS_DENOMINATOR_ZERO / MOS_NOT_APPLICABLE. Distinct from gap_ratio, which divides by current_price.';

-- Backfill: positive IV only. The expression is written the same way as
-- `valuation_engine.py` so the stored value and a fresh calculation agree.
update public.calc_valuation_methods
set mos = (intrinsic_value - current_price) / intrinsic_value
where mos is null
  and intrinsic_value is not null
  and intrinsic_value > 0
  and current_price is not null;

-- Zero IV: undefined. Flag it so "not computable" is never read as "no discount".
update public.calc_valuation_methods
set flags = flags || '["MOS_DENOMINATOR_ZERO"]'::jsonb
where intrinsic_value = 0
  and current_price is not null
  and not (flags @> '["MOS_DENOMINATOR_ZERO"]'::jsonb);

-- Negative IV: the divisor would flip the sign, so the ratio is not applicable.
update public.calc_valuation_methods
set flags = flags || '["MOS_NOT_APPLICABLE"]'::jsonb
where intrinsic_value < 0
  and current_price is not null
  and not (flags @> '["MOS_NOT_APPLICABLE"]'::jsonb);

do $verify$
declare
  bad integer;
begin
  if not exists (
    select 1
    from information_schema.columns c
    where c.table_schema = 'public'
      and c.table_name = 'calc_valuation_methods'
      and c.column_name = 'mos'
      and c.is_nullable = 'YES'
  ) then
    raise exception 'VALUATION_METHOD_MOS_COLUMN_MISSING_OR_NOT_NULLABLE';
  end if;

  -- Every stored value must reproduce rule D6 exactly, so a later reader cannot
  -- be handed a number that came from the gap_ratio formula.
  select count(*) into bad
  from public.calc_valuation_methods
  where mos is not null
    and mos <> (intrinsic_value - current_price) / intrinsic_value;

  if bad > 0 then
    raise exception 'VALUATION_METHOD_MOS_RULE_VIOLATED: %', bad;
  end if;

  -- No non-positive IV may carry a value: that is the sign-flip case.
  select count(*) into bad
  from public.calc_valuation_methods
  where mos is not null and intrinsic_value <= 0;

  if bad > 0 then
    raise exception 'VALUATION_METHOD_MOS_SET_FOR_NON_POSITIVE_IV: %', bad;
  end if;

  -- The two refusal branches must be flagged, not silently NULL.
  select count(*) into bad
  from public.calc_valuation_methods
  where intrinsic_value = 0
    and current_price is not null
    and not (flags @> '["MOS_DENOMINATOR_ZERO"]'::jsonb);

  if bad > 0 then
    raise exception 'VALUATION_METHOD_MOS_ZERO_IV_UNFLAGGED: %', bad;
  end if;

  select count(*) into bad
  from public.calc_valuation_methods
  where intrinsic_value < 0
    and current_price is not null
    and not (flags @> '["MOS_NOT_APPLICABLE"]'::jsonb);

  if bad > 0 then
    raise exception 'VALUATION_METHOD_MOS_NEGATIVE_IV_UNFLAGGED: %', bad;
  end if;
end
$verify$;

commit;

"""Offline contract checks for the annual-ratio and MoS migrations (0029/0030)."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase" / "migrations"


class AnnualRatiosMigrationTests(unittest.TestCase):
    """`0029_annual_ratios.sql` - the new ratio table and its access rules."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = (MIGRATIONS / "0029_annual_ratios.sql").read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()

    def test_migration_is_transactional(self) -> None:
        self.assertRegex(self.lower, r"(?m)^begin;")
        self.assertRegex(self.lower, r"(?m)^commit;")
        self.assertLess(self.lower.index("do $verify$"), self.lower.rindex("commit;"))

    def test_table_shape_matches_the_other_result_tables(self) -> None:
        # Same provenance and status vocabulary as 0009, or readers would need a
        # second contract for the same kind of row.
        self.assertIn("create table if not exists public.calc_annual_ratios", self.lower)
        for column in (
            "calculation_run_id", "methodology_version_id", "instrument_id",
            "financial_period_id", "metric_code", "observation_date",
            "value_numeric", "unit_code", "calculation_status",
            "availability_status", "flags",
        ):
            self.assertIn(column, self.lower, column)
        self.assertIn(
            "check (calculation_status in ('valid', 'not_calculable', 'unavailable'))",
            self.lower,
        )

    def test_unit_code_is_required_and_whitelisted(self) -> None:
        """A stored unit is what stops a margin being read as an amount."""
        self.assertIn("unit_code text not null", self.lower)
        self.assertRegex(self.lower, r"check \(unit_code in \(")
        for unit in ("idr_per_share", "idr", "ratio", "percent", "shares", "years"):
            self.assertIn(f"'{unit}'", self.lower, unit)

    def test_value_numeric_is_nullable_so_zero_never_means_absent(self) -> None:
        self.assertIn("value_numeric numeric,", self.lower)
        self.assertIn("annual_ratios_value_must_be_nullable", self.lower)

    def test_idempotency_key_uses_nulls_not_distinct(self) -> None:
        # An instrument-level row has a NULL period, and the key must still reject
        # a duplicate.
        self.assertIn("unique nulls not distinct", self.lower)
        self.assertIn("calc_annual_ratios_unique", self.lower)

    def test_browser_roles_get_no_table_grant(self) -> None:
        self.assertIn(
            "revoke all on table public.calc_annual_ratios from public, anon, authenticated",
            self.lower,
        )
        self.assertIn("annual_ratios_raw_grants_must_remain_private", self.lower)
        self.assertNotRegex(
            self.lower,
            r"grant\s+select\s+on\s+table\s+public\.calc_annual_ratios\s+to\s+(anon|authenticated)",
        )

    def test_reader_role_gets_column_grants_and_a_policy(self) -> None:
        self.assertIn("to stocklens_market_reader", self.lower)
        self.assertIn("grant select (", self.lower)
        self.assertIn("for select to stocklens_market_reader using (true)", self.lower)
        self.assertIn("annual_ratios_reader_policy_missing", self.lower)

    def test_reader_grant_check_is_column_level(self) -> None:
        """`has_table_privilege` is false for a column grant.

        Using it here would make the verify block fail on a correct migration, so
        the check must go through `has_column_privilege`.
        """
        self.assertIn("has_column_privilege(", self.lower)
        self.assertIn("annual_ratios_reader_grant_missing", self.lower)
        self.assertNotRegex(
            self.lower,
            r"not has_table_privilege\('stocklens_market_reader'",
        )

    def test_rls_is_enabled(self) -> None:
        self.assertIn(
            "alter table public.calc_annual_ratios enable row level security", self.lower
        )
        self.assertIn("annual_ratios_rls_disabled", self.lower)


class ValuationMethodMosMigrationTests(unittest.TestCase):
    """`0030_valuation_method_mos.sql` - workbook rule D6 on the method rows."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = (MIGRATIONS / "0030_valuation_method_mos.sql").read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()

    def test_migration_is_transactional(self) -> None:
        self.assertRegex(self.lower, r"(?m)^begin;")
        self.assertRegex(self.lower, r"(?m)^commit;")
        self.assertLess(self.lower.index("do $verify$"), self.lower.rindex("commit;"))

    def test_mos_column_is_added_and_nullable(self) -> None:
        self.assertIn(
            "alter table public.calc_valuation_methods\n  add column if not exists mos numeric",
            self.lower,
        )
        self.assertIn("valuation_method_mos_column_missing_or_not_nullable", self.lower)

    def test_backfill_divides_by_intrinsic_value_not_price(self) -> None:
        """Rule D6 divides by the IV. Dividing by the price would be `gap_ratio`."""
        self.assertIn("(intrinsic_value - current_price) / intrinsic_value", self.lower)
        self.assertNotIn("(intrinsic_value - current_price) / current_price", self.lower)

    def test_backfill_is_restricted_to_a_positive_intrinsic_value(self) -> None:
        self.assertIn("and intrinsic_value > 0", self.lower)
        self.assertIn("valuation_method_mos_set_for_non_positive_iv", self.lower)

    def test_both_refusal_branches_are_flagged(self) -> None:
        # A zero divisor is undefined; a negative one flips the sign of the ratio.
        self.assertIn("mos_denominator_zero", self.lower)
        self.assertIn("mos_not_applicable", self.lower)
        self.assertIn("valuation_method_mos_zero_iv_unflagged", self.lower)
        self.assertIn("valuation_method_mos_negative_iv_unflagged", self.lower)

    def test_flags_are_appended_never_replaced(self) -> None:
        """A row's existing provenance flags must survive the backfill."""
        self.assertIn("set flags = flags ||", self.lower)
        self.assertNotRegex(self.lower, r"set\s+flags\s*=\s*'\[")

    def test_gap_ratio_column_is_untouched(self) -> None:
        """The two ratios are different numbers and both must remain."""
        self.assertNotRegex(self.lower, r"drop\s+column.*gap_ratio")
        self.assertNotRegex(self.lower, r"set\s+gap_ratio")


if __name__ == "__main__":
    unittest.main()

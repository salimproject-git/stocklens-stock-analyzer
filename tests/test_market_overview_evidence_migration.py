"""Offline contract checks for the 0037 market-overview valuation/evidence migration.

The regression this guards: the market card's Valuation, MoS and Historical
Evidence blocks were hardcoded to "Not available" because the RPC never returned
valuation or backtest data. This migration adds those fields, so the checks below
pin the field names, the run-pinning rule and the read-only/least-privilege
guarantees.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MarketOverviewEvidenceMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = (
            ROOT / "supabase" / "migrations" / "0037_market_overview_valuation_and_evidence.sql"
        )
        cls.sql = cls.path.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()

    def test_migration_is_transactional_and_read_only(self) -> None:
        self.assertRegex(self.lower, r"(?m)^begin;")
        self.assertRegex(self.lower, r"(?m)^commit;")
        self.assertNotRegex(
            self.lower,
            r"\b(insert\s+into|update\s+public\.|delete\s+from|truncate|drop\s+table)\b",
        )

    def test_new_fields_are_exposed(self) -> None:
        for field in (
            "signal",
            "mos_percent",
            "undervalued_method_count",
            "valid_method_count",
            "win_rate_percent",
            "win_rate_cases",
            "evidence_wins",
            "evidence_total",
        ):
            self.assertIn(field, self.lower)

    def test_backtest_is_pinned_to_the_newest_succeeded_run(self) -> None:
        # The table holds one row per case per run, so an unpinned read would
        # count every case once per run.
        self.assertIn("latest_run as (", self.lower)
        self.assertIn("r.calculation_type = 'backtest_historical'", self.lower)
        self.assertIn("r.status = 'succeeded'", self.lower)
        self.assertIn("join latest_run as run on run.id = c.calculation_run_id", self.lower)

    def test_rules_match_the_frontend_thresholds(self) -> None:
        # Method rule: >= 3 valid methods above price. MoS rule: MoS main >= 30%.
        self.assertIn("undervalued_methods >= 3", self.lower)
        self.assertIn("mos_main >= 0.30", self.lower)
        # WIN + RECOVERED count as a success, matching the Backtest tab.
        self.assertIn("in ('win', 'recovered')", self.lower)

    def test_function_stays_bounded_definer_and_selectively_executable(self) -> None:
        self.assertIn("security definer", self.lower)
        self.assertIn("set search_path = ''", self.lower)
        self.assertIn("i.exchange_code = 'idx'", self.lower)
        self.assertIn("limit (select page_size from requested)", self.lower)
        self.assertIn("array[8, 12, 16, 20]", self.lower)
        self.assertIn(
            "grant execute on function public.get_market_overview_page(integer, integer) to anon, authenticated",
            self.lower,
        )
        self.assertIn("stocklens_market_rpc_grants_missing", self.lower)
        self.assertLess(self.lower.index("do $verify$"), self.lower.rindex("commit;"))

    def test_daily_status_table_stays_private_to_browser_roles(self) -> None:
        # The reader role gets column grants; anon/authenticated must not.
        self.assertIn(
            "grant select (",
            self.lower,
        )
        self.assertIn("on table public.calc_valuation_daily_status to stocklens_market_reader", self.lower)
        self.assertNotIn(
            "on table public.calc_valuation_daily_status to anon",
            self.lower,
        )
        self.assertNotIn(
            "on table public.calc_valuation_daily_status to authenticated",
            self.lower,
        )
        self.assertIn("stocklens_market_raw_table_grants_must_remain_private", self.lower)


if __name__ == "__main__":
    unittest.main()

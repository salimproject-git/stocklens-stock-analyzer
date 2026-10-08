"""Contract checks for legacy valuation fallback in Market Overview."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MarketOverviewLegacyFallbackMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = ROOT / "supabase" / "migrations" / "0039_market_overview_legacy_valuation_fallback.sql"
        cls.sql = cls.path.read_text(encoding="utf-8")
        cls.base_sql = (
            ROOT / "supabase" / "migrations" / "0038_market_overview_stock_type.sql"
        ).read_text(encoding="utf-8")
        cls.lower = f"{cls.base_sql}\n{cls.sql}".lower()

    def test_migration_is_transactional_and_read_only(self) -> None:
        self.assertRegex(self.lower, r"(?m)^begin;")
        self.assertRegex(self.lower, r"(?m)^commit;")
        self.assertNotRegex(
            self.lower,
            r"\b(insert\s+into|update\s+public\.|delete\s+from|truncate|drop\s+table)\b",
        )

    def test_legacy_summary_is_used_only_as_metric_fallback(self) -> None:
        self.assertIn("public.get_stock_valuation_summary(stock_row.stock ->> 'ticker')", self.lower)
        self.assertIn("coalesce(stock_row.stock ->> 'signal', fallback.signal)", self.lower)
        self.assertIn("coalesce(\n            nullif(stock_row.stock ->> 'mos_percent', '')::numeric,", self.lower)
        self.assertIn("coalesce(\n            nullif(stock_row.stock ->> 'valid_method_count', '')::integer,", self.lower)
        self.assertIn("valuation.summary ->> 'method_verdict'", self.lower)
        self.assertIn("valuation.summary ->> 'mos_verdict'", self.lower)

    def test_signal_mapping_preserves_mixed_and_unavailable_cases(self) -> None:
        self.assertIn("then 'mixed'", self.lower)
        self.assertIn("when valuation.summary ->> 'method_verdict' = 'undervalued'", self.lower)
        self.assertIn("and valuation.summary ->> 'mos_verdict' = 'overvalued'", self.lower)
        self.assertIn("else null", self.lower)

    def test_base_rpc_remains_private(self) -> None:
        self.assertIn(
            "revoke all on function public.get_market_overview_page_base(integer, integer)",
            self.lower,
        )
        self.assertIn("stocklens_market_rpc_base_must_remain_private", self.lower)
        self.assertIn("stocklens_market_legacy_fallback_missing", self.lower)


if __name__ == "__main__":
    unittest.main()
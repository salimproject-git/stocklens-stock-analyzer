"""Contract checks for stock type enrichment in the market overview RPC."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MarketOverviewStockTypeMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = ROOT / "supabase" / "migrations" / "0038_market_overview_stock_type.sql"
        cls.sql = cls.path.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()

    def test_migration_is_transactional_and_does_not_modify_data(self) -> None:
        self.assertRegex(self.lower, r"(?m)^begin;")
        self.assertRegex(self.lower, r"(?m)^commit;")
        self.assertNotRegex(
            self.lower,
            r"\b(insert\s+into|update\s+public\.|delete\s+from|truncate|drop\s+table)\b",
        )

    def test_public_rpc_enriches_bounded_base_payload_with_stock_type(self) -> None:
        self.assertIn("alter function public.get_market_overview_page(integer, integer)", self.lower)
        self.assertIn("rename to get_market_overview_page_base", self.lower)
        self.assertIn("public.get_market_overview_page_base(p_page, p_page_size)", self.lower)
        self.assertIn("jsonb_array_elements", self.lower)
        self.assertIn("'stock_type'", self.lower)
        self.assertIn("'not available'", self.lower)

    def test_valuation_snapshot_precedes_legacy_type_fallback(self) -> None:
        snapshot = self.lower.index("from public.calc_valuation_fundamental_snapshots as snapshot")
        legacy = self.lower.index("from public.calc_valuation_methods as legacy")
        self.assertLess(snapshot, legacy)
        self.assertIn("snapshot.snapshot_date desc, snapshot.created_at desc, snapshot.id desc", self.lower)
        self.assertIn("legacy.valuation_date desc, legacy.created_at desc, legacy.id desc", self.lower)

    def test_base_rpc_is_private_and_public_wrapper_is_selectively_executable(self) -> None:
        self.assertIn(
            "revoke all on function public.get_market_overview_page_base(integer, integer)",
            self.lower,
        )
        self.assertIn(
            "grant execute on function public.get_market_overview_page(integer, integer)\n  to anon, authenticated",
            self.lower,
        )
        self.assertIn("stocklens_market_rpc_base_must_remain_private", self.lower)
        self.assertIn("stocklens_market_stock_type_source_missing", self.lower)


if __name__ == "__main__":
    unittest.main()
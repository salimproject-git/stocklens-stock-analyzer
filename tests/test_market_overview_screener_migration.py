"""Offline contract checks for the 0040 market-overview screener migration.

The regression this guards: the market overview exposed "All Sectors",
"All Stock Type" and "Sort by Market Cap" as controls, but the RPC took only a
page number and a page size. A filter applied to one already-chosen page is not
a screener, so the facet and the sort have to be pushed into the query.

The checks below pin the new parameters, the whitelists, the filtered-count
semantics, and the removal of the superseded signatures.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MarketOverviewScreenerMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = (
            ROOT
            / "supabase"
            / "migrations"
            / "0040_market_overview_screener_filters.sql"
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

    def test_new_signature_exposes_facets_and_sort(self) -> None:
        self.assertIn(
            "create function public.get_market_overview_page(\n"
            "  p_page integer default 1,\n"
            "  p_page_size integer default 8,\n"
            "  p_sector text default null,\n"
            "  p_stock_type text default null,\n"
            "  p_sort text default 'ticker'\n"
            ")",
            self.lower,
        )

    def test_superseded_signatures_are_dropped(self) -> None:
        # The old two-argument function and the 0038 wrapper must not survive as
        # an unfiltered back door.
        self.assertIn(
            "drop function if exists public.get_market_overview_page(integer, integer);",
            self.lower,
        )
        self.assertIn(
            "drop function if exists public.get_market_overview_page_base(integer, integer);",
            self.lower,
        )
        # The guard must match on argument count: `pg_get_function_identity_arguments`
        # renders parameter names too, so a text comparison would reject the new
        # function itself.
        self.assertIn("p.pronargs <> 5", self.lower)
        self.assertNotIn("pg_get_function_identity_arguments(p.oid) <>", self.lower)
        self.assertIn("stocklens_market_rpc_old_signature_still_present", self.lower)

    def test_sort_is_a_whitelist_not_a_free_expression(self) -> None:
        for key in (
            "market_cap_desc",
            "mos_desc",
            "win_rate_desc",
            "price_desc",
            "price_asc",
        ):
            self.assertIn(f"when '{key}' then '{key}'", self.lower)
        # The ORDER BY is expressed once, over a row_number, not repeated per branch.
        self.assertEqual(self.lower.count("row_number() over ("), 1)
        self.assertIn("nulls last", self.lower)

    def test_facet_filters_are_whitelisted_and_bounded(self) -> None:
        self.assertIn("requested_sector as (", self.lower)
        self.assertIn("requested_stock_type as (", self.lower)
        # Sector names are data, so only the length and shape are constrained.
        self.assertIn("left(btrim(coalesce(p_sector, '')), 64)", self.lower)
        for stock_type in (
            "asset play",
            "cyclical",
            "fast grower",
            "slow grower",
            "stalwart",
            "turn around",
        ):
            self.assertIn(f"'{stock_type}'", self.lower)
        # A null facet means "all", and the comparison is an exact match.
        self.assertIn("rs.sector_name is null or f.sector_name = rs.sector_name", self.lower)
        self.assertIn(
            "rst.stock_type is null or f.stock_type = rst.stock_type", self.lower
        )

    def test_count_and_pagination_describe_the_filtered_set(self) -> None:
        # Before 0040 both came from the unfiltered instrument table.
        self.assertIn("matched_count as (", self.lower)
        self.assertIn("select total from matched_count", self.lower)
        self.assertNotIn(
            "(select count(*)::numeric from public.instruments where exchange_code = 'idx')",
            self.lower,
        )
        self.assertIn("'total_count', (select total from matched_count)", self.lower)

    def test_metric_rules_are_carried_over_unchanged(self) -> None:
        # Signal, MoS and evidence must survive the rewrite.
        self.assertIn("undervalued_methods >= 3", self.lower)
        self.assertIn("mos_main >= 0.30", self.lower)
        self.assertIn("in ('win', 'recovered')", self.lower)
        self.assertIn("latest_run as (", self.lower)
        self.assertIn("r.calculation_type = 'backtest_historical'", self.lower)
        self.assertIn("join latest_run as run on run.id = c.calculation_run_id", self.lower)
        # 0039: daily status stays authoritative, legacy summary is a fallback.
        self.assertIn("public.get_stock_valuation_summary(i.ticker)", self.lower)
        self.assertIn("coalesce(", self.lower)
        # 0038: stock type precedence, snapshot before legacy method.
        snapshot = self.lower.index(
            "from public.calc_valuation_fundamental_snapshots as snapshot"
        )
        legacy = self.lower.index("from public.calc_valuation_methods as legacy")
        self.assertLess(snapshot, legacy)

    def test_function_stays_bounded_definer_and_selectively_executable(self) -> None:
        self.assertIn("security definer", self.lower)
        self.assertIn("set search_path = ''", self.lower)
        self.assertIn("i.exchange_code = 'idx'", self.lower)
        self.assertIn("array[8, 12, 16, 20]", self.lower)
        self.assertIn("limit (select page_size from requested)", self.lower)
        self.assertNotIn("select *", self.lower)
        self.assertIn(
            "grant execute on function public.get_market_overview_page"
            "(integer, integer, text, text, text)\n  to anon, authenticated",
            self.lower,
        )
        self.assertIn("stocklens_market_rpc_grants_missing", self.lower)
        self.assertIn("stocklens_market_screener_facets_missing", self.lower)
        self.assertLess(self.lower.index("do $verify$"), self.lower.rindex("commit;"))

    def test_daily_status_table_stays_private_to_browser_roles(self) -> None:
        self.assertIn(
            "stocklens_market_raw_table_grants_must_remain_private", self.lower
        )
        self.assertNotIn(
            "on table public.calc_valuation_daily_status to anon", self.lower
        )
        self.assertNotIn(
            "on table public.calc_valuation_daily_status to authenticated", self.lower
        )

    def test_pending_owner_transfer_target_is_documented(self) -> None:
        # 0019 still names the two-argument signature; applying it after 0040
        # would fail, so the retarget must be written down here.
        self.assertIn(
            "public.get_market_overview_page(integer, integer, text, text, text)",
            self.lower,
        )


if __name__ == "__main__":
    unittest.main()
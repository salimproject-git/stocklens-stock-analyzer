"""Offline contract checks for the narrow market-data RPC migration."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "0016_frontend_market_data_rpc.sql"


class MarketReadRpcsMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()

    def test_migration_is_transactional_and_read_only(self) -> None:
        self.assertRegex(self.lower, r"(?m)^begin;")
        self.assertRegex(self.lower, r"(?m)^commit;")
        self.assertNotRegex(self.lower, r"\b(insert\s+into|update\s+public\.|delete\s+from|truncate|drop\s+table)\b")

    def test_reader_role_has_no_login_inheritance_or_rls_bypass(self) -> None:
        self.assertIn("create role stocklens_market_reader nologin noinherit nobypassrls", self.lower)
        self.assertIn("grant select (", self.lower)
        self.assertNotIn("grant all", self.lower)
        self.assertIn("for select to stocklens_market_reader using (true)", self.lower)

    def test_raw_table_select_is_not_granted_to_browser_roles(self) -> None:
        self.assertNotRegex(self.lower, r"grant\s+select\s+on\s+table\s+public\.(instruments|prices_daily|financial_periods|financial_facts|calc_valuation_methods)\s+to\s+(anon|authenticated)")
        self.assertIn("stocklens_raw_table_grants_must_remain_private", self.lower)

    def test_rpc_functions_are_bounded_definers_and_selectively_executable(self) -> None:
        self.assertIn("create or replace function public.get_market_overview_page(p_page integer default 1)", self.lower)
        self.assertIn("create or replace function public.get_stock_research_data(p_ticker text)", self.lower)
        self.assertEqual(self.lower.count("security definer"), 2)
        self.assertEqual(self.lower.count("set search_path = ''"), 2)
        self.assertEqual(self.lower.count("revoke all on function public.get_"), 2)
        self.assertEqual(self.lower.count("grant execute on function public.get_"), 2)

    def test_owner_transfer_is_documented_as_pending(self) -> None:
        # The owner transfer cannot run through the MCP migration runner
        # (ERROR 42501: must be able to SET ROLE stocklens_market_reader), so it
        # is commented out here and prepared in 0019 instead. The file must say
        # so explicitly rather than silently dropping the intent.
        self.assertNotRegex(
            self.lower,
            r"(?m)^alter function public\.get_(market_overview_page|stock_research_data).*owner to stocklens_market_reader;",
        )
        self.assertIn("owner transfer requires a role with set role on stocklens_market_reader", self.lower)

    def test_queries_bound_market_page_and_ticker_scope(self) -> None:
        # NOTE: the market page bound below is superseded by 0027, which makes
        # the page size a whitelisted parameter (8/12/16/20) instead of the
        # fixed 5 asserted here. This assertion documents what 0016 shipped.
        self.assertIn("limit 5", self.lower)
        self.assertIn("limit 260", self.lower)
        self.assertIn("limit 40", self.lower)
        self.assertIn("i.exchange_code = 'idx'", self.lower)
        self.assertIn("where i.ticker = upper(trim(p_ticker))", self.lower)
        self.assertIn("latest.close_price", self.lower)
        self.assertNotIn("select *", self.lower)

    def test_migration_checks_security_invariants_before_commit(self) -> None:
        self.assertIn("stocklens_market_reader_role_is_not_restricted", self.lower)
        self.assertIn("stocklens_rpc_grants_missing", self.lower)
        self.assertLess(self.lower.index("do $verify$"), self.lower.rindex("commit;"))


class GrowthDividendRpcMigrationTests(unittest.TestCase):
    """Contract checks for the 0017 growth/dividend RPC extension."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.path = ROOT / "supabase" / "migrations" / "0017_frontend_growth_dividend_rpc.sql"
        cls.sql = cls.path.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()

    def test_migration_is_transactional_and_read_only(self) -> None:
        self.assertRegex(self.lower, r"(?m)^begin;")
        self.assertRegex(self.lower, r"(?m)^commit;")
        self.assertNotRegex(self.lower, r"\b(insert\s+into|update\s+public\.|delete\s+from|truncate|drop\s+table)\b")

    def test_only_computed_tables_are_exposed_with_column_grants(self) -> None:
        for table in ("calc_annual_growth_quality", "calc_quarterly_quality", "dividend_facts"):
            self.assertIn(f"public.{table} to stocklens_market_reader", self.lower)
        self.assertIn("grant select (", self.lower)
        self.assertNotIn("grant all", self.lower)
        self.assertIn("for select to stocklens_market_reader using (true)", self.lower)

    def test_raw_table_select_still_not_granted_to_browser_roles(self) -> None:
        self.assertIn("stocklens_raw_table_grants_must_remain_private", self.lower)

    def test_rpc_grants_execute_only_to_browser_roles(self) -> None:
        self.assertIn(
            "revoke all on function public.get_stock_research_data(text) from public, anon, authenticated",
            self.lower,
        )
        self.assertIn(
            "grant execute on function public.get_stock_research_data(text) to anon, authenticated",
            self.lower,
        )


class SharesStockTypeRpcMigrationTests(unittest.TestCase):
    """Contract checks for the 0018 shares/stock_type RPC extension."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.path = ROOT / "supabase" / "migrations" / "0018_frontend_shares_stocktype_rpc.sql"
        cls.sql = cls.path.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()

    def test_migration_is_transactional_and_read_only(self) -> None:
        self.assertRegex(self.lower, r"(?m)^begin;")
        self.assertRegex(self.lower, r"(?m)^commit;")
        self.assertNotRegex(self.lower, r"\b(insert\s+into|update\s+public\.|delete\s+from|truncate|drop\s+table)\b")

    def test_outstanding_shares_and_stock_type_are_exposed(self) -> None:
        self.assertIn("'outstanding_shares'", self.lower)
        self.assertIn("'stock_type', v.stock_type", self.lower)
        self.assertIn("grant select (stock_type) on table public.calc_valuation_methods", self.lower)

    def test_rpc_remains_bounded_and_read_only(self) -> None:
        self.assertIn("security definer", self.lower)
        self.assertIn("set search_path = ''", self.lower)
        self.assertIn("limit 260", self.lower)
        self.assertNotIn("select *", self.lower)


class LeastPrivilegeOwnerMigrationTests(unittest.TestCase):
    """Contract checks for the prepared 0019 owner-hardening migration."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.path = ROOT / "supabase" / "migrations" / "0019_market_rpc_least_privilege_owner.sql"
        cls.sql = cls.path.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()

    def test_owner_is_transferred_to_the_narrow_reader_role(self) -> None:
        self.assertEqual(
            self.lower.count("owner to stocklens_market_reader"),
            2,
        )

    def test_owner_migration_verifies_low_privilege_owner(self) -> None:
        self.assertIn("stocklens_rpc_owner_not_low_privilege", self.lower)
        self.assertIn("stocklens_market_reader_role_is_not_restricted", self.lower)
        self.assertRegex(self.lower, r"(?m)^begin;")
        self.assertRegex(self.lower, r"(?m)^commit;")

    def test_owner_migration_documents_that_it_is_not_applied(self) -> None:
        self.assertIn("not yet applied", self.lower)


class LatestValuationRunRpcMigrationTests(unittest.TestCase):
    """Contract checks for the 0021 newest-snapshot-per-method RPC fix."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.path = ROOT / "supabase" / "migrations" / "0021_stock_research_latest_valuation_run.sql"
        cls.sql = cls.path.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()

    def test_migration_is_transactional_and_read_only(self) -> None:
        self.assertRegex(self.lower, r"(?m)^begin;")
        self.assertRegex(self.lower, r"(?m)^commit;")
        self.assertNotRegex(self.lower, r"\b(insert\s+into|update\s+public\.|delete\s+from|truncate|drop\s+table)\b")

    def test_valuation_rows_are_deduplicated_per_method_code(self) -> None:
        # Re-running with new assumptions creates a second run at the same
        # valuation_date, so the RPC must keep only the newest row per method.
        self.assertIn("select distinct on (v.method_code)", self.lower)
        self.assertIn("order by v.method_code, v.created_at desc, v.id", self.lower)

    def test_created_at_column_granted_for_the_tie_breaker(self) -> None:
        self.assertIn(
            "grant select (created_at) on table public.calc_valuation_methods to stocklens_market_reader",
            self.lower,
        )

    def test_rpc_stays_bounded_read_only_and_selectively_executable(self) -> None:
        self.assertIn("security definer", self.lower)
        self.assertIn("set search_path = ''", self.lower)
        self.assertIn("limit 260", self.lower)
        self.assertIn("limit 40", self.lower)
        self.assertIn("limit 100", self.lower)
        self.assertNotIn("select *", self.lower)
        self.assertIn(
            "grant execute on function public.get_stock_research_data(text) to anon, authenticated",
            self.lower,
        )



if __name__ == "__main__":
    unittest.main()
class InterestAndCurrentAssetsRpcMigrationTests(unittest.TestCase):
    """Contract checks for the 0022 fact-whitelist extension."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.path = ROOT / "supabase" / "migrations" / "0022_stock_research_interest_and_current_assets.sql"
        cls.sql = cls.path.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()

    def test_migration_is_transactional_and_read_only(self) -> None:
        self.assertRegex(self.lower, r"(?m)^begin;")
        self.assertRegex(self.lower, r"(?m)^commit;")
        self.assertNotRegex(self.lower, r"\b(insert\s+into|update\s+public\.|delete\s+from|truncate|drop\s+table)\b")

    def test_interest_expense_and_current_assets_are_exposed(self) -> None:
        # These were the two facts the UI asked for but the RPC never returned.
        self.assertIn("'interest_expense_non_operating'", self.lower)
        self.assertIn("'current_assets'", self.lower)
        self.assertIn("'total_current_asset'", self.lower)

    def test_previous_extensions_are_preserved(self) -> None:
        # 0018 added shares/stock_type and 0021 added run dedup; a rewrite must
        # not silently drop them.
        self.assertIn("'outstanding_shares'", self.lower)
        self.assertIn("'stock_type', v.stock_type", self.lower)
        self.assertIn("select distinct on (v.method_code)", self.lower)
        self.assertIn("order by v.method_code, v.created_at desc, v.id", self.lower)

    def test_rpc_stays_bounded_read_only_and_private(self) -> None:
        self.assertIn("security definer", self.lower)
        self.assertIn("set search_path = ''", self.lower)
        self.assertIn("limit 260", self.lower)
        self.assertIn("limit 40", self.lower)
        self.assertNotIn("select *", self.lower)
        self.assertIn("stocklens_raw_table_grants_must_remain_private", self.lower)
        self.assertIn(
            "grant execute on function public.get_stock_research_data(text) to anon, authenticated",
            self.lower,
        )

class BacktestRpcMigrationTests(unittest.TestCase):
    """Contract checks for the 0026 backtest RPC.

    These are offline checks on the migration text. The behaviour itself is
    verified against the live project separately (18 AUTO cases, exact workbook
    parity on revenue/earnings YoY and momentum).
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.path = ROOT / "supabase" / "migrations" / "0026_stock_research_backtest_rpc.sql"
        cls.sql = cls.path.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()

    def test_migration_is_transactional_and_does_not_change_case_data(self) -> None:
        self.assertRegex(self.lower, r"(?m)^begin;")
        self.assertRegex(self.lower, r"(?m)^commit;")
        # Only an additive column is allowed; no case rows may be touched.
        self.assertNotRegex(self.lower, r"\b(insert\s+into|update\s+public\.|delete\s+from|truncate|drop\s+table)\b")
        self.assertIn("add column if not exists trough_month integer", self.lower)

    def test_backtest_tables_are_not_granted_to_browser_roles(self) -> None:
        for role in ("anon", "authenticated"):
            for table in ("calc_backtest_cases", "calc_backtest_methods", "calculation_runs"):
                self.assertNotRegex(
                    self.lower,
                    rf"grant\s+select\s+on\s+table\s+public\.{table}\s+to\s+{role}",
                )
        self.assertIn("stocklens_backtest_raw_grants_must_remain_private", self.lower)

    def test_rpc_is_bounded_private_and_selectively_executable(self) -> None:
        self.assertIn("create or replace function public.get_stock_backtest(p_ticker text)", self.lower)
        self.assertIn("security definer", self.lower)
        self.assertIn("set search_path = ''", self.lower)
        self.assertIn(
            "revoke all on function public.get_stock_backtest(text) from public, anon, authenticated",
            self.lower,
        )
        self.assertIn(
            "grant execute on function public.get_stock_backtest(text) to anon, authenticated",
            self.lower,
        )
        # One ticker only, guarded against duplicate tickers.
        self.assertIn("i.ticker = upper(trim(p_ticker))", self.lower)
        self.assertIn("i.exchange_code = 'idx'", self.lower)
        self.assertNotIn("select *", self.lower)

    def test_run_is_scoped_to_the_newest_succeeded_backtest(self) -> None:
        self.assertIn("calculation_type = 'backtest_historical'", self.lower)
        self.assertIn("r.status = 'succeeded'", self.lower)
        self.assertIn("order by r.completed_at desc nulls last", self.lower)
        self.assertIn("limit 1", self.lower)

    def test_context_derivation_is_point_in_time(self) -> None:
        # The current quarter may never be read past the case's analysis date,
        # and the prior quarter must be the SAME quarter a year earlier.
        self.assertIn("where q.period_end <= c.analysis_date", self.lower)
        self.assertIn("q.period_end = current_q.period_end - interval '1 year'", self.lower)
        # Momentum comes from the base year's annual row, not the latest row.
        self.assertIn("extract(year from g.period_end) = c.base_year", self.lower)
        self.assertIn("'quality_eps_momentum'", self.lower)
        self.assertIn("'quality_revenue_momentum'", self.lower)

    def test_context_keys_match_the_frontend_contract(self) -> None:
        for key in ("revenueyoy", "netincomeyoy", "epsmomentum", "revenuemomentum",
                    "roetrend", "yield", "ocfni"):
            self.assertIn(f"'{key}'", self.lower)

    def test_columns_without_a_rule_are_explicitly_null(self) -> None:
        # Inventing a rule for these would fabricate numbers, so they must be
        # null on purpose and the migration must say why.
        self.assertIn("'roetrend', null", self.lower)
        self.assertIn("'yield', null", self.lower)
        self.assertIn("'ocfni', null", self.lower)
        self.assertIn("no rule for these exists in this repository", self.lower)

    def test_security_invariants_are_checked_before_commit(self) -> None:
        self.assertIn("stocklens_backtest_rpc_grants_missing", self.lower)
        self.assertIn("stocklens_backtest_rls_disabled", self.lower)
        self.assertIn("stocklens_market_reader_role_is_not_restricted", self.lower)
        self.assertLess(self.lower.index("do $verify$"), self.lower.rindex("commit;"))

    def test_trough_month_is_added_before_it_is_granted(self) -> None:
        # `grant select (col)` validates the column exists, so ordering matters.
        add = self.lower.index("add column if not exists trough_month")
        grant = self.lower.index("peak_month, trough_month,")
        self.assertLess(add, grant)


class ActiveProjectionRpcMigrationTests(unittest.TestCase):
    """Contract checks for the 0023 active-projection extension."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.path = ROOT / "supabase" / "migrations" / "0023_stock_research_active_projection.sql"
        cls.sql = cls.path.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()

    def test_migration_is_transactional_and_read_only(self) -> None:
        self.assertRegex(self.lower, r"(?m)^begin;")
        self.assertRegex(self.lower, r"(?m)^commit;")
        self.assertNotRegex(self.lower, r"\b(insert\s+into|update\s+public\.|delete\s+from|truncate|drop\s+table)\b")

    def test_projection_is_exposed_but_bounded_to_active_scenario(self) -> None:
        self.assertIn("'projection'", self.lower)
        self.assertIn("s.status = 'active'", self.lower)
        self.assertIn("using (status = 'active')", self.lower)
        self.assertIn("limit 10", self.lower)
        # The projection_values policy must not open up non-active scenarios.
        self.assertIn("projection_values.scenario_id", self.lower)

    def test_projection_tables_are_not_granted_to_browser_roles(self) -> None:
        self.assertIn("stocklens_projection_tables_must_stay_private", self.lower)
        self.assertNotRegex(
            self.lower,
            r"grant\s+select\s+on\s+table\s+public\.projection_(scenarios|values)\s+to\s+(anon|authenticated)",
        )

    def test_earlier_extensions_are_preserved(self) -> None:
        # 0018 (shares/stock_type), 0021 (dedup) and 0022 (interest/current assets)
        # must survive this rewrite.
        self.assertIn("'outstanding_shares'", self.lower)
        self.assertIn("'stock_type', v.stock_type", self.lower)
        self.assertIn("select distinct on (v.method_code)", self.lower)
        self.assertIn("'interest_expense_non_operating'", self.lower)
        self.assertIn("'current_assets'", self.lower)

    def test_rpc_stays_bounded_read_only_and_selectively_executable(self) -> None:
        self.assertIn("security definer", self.lower)
        self.assertIn("set search_path = ''", self.lower)
        self.assertIn("limit 260", self.lower)
        self.assertIn("limit 40", self.lower)
        self.assertNotIn("select *", self.lower)
        self.assertIn(
            "grant execute on function public.get_stock_research_data(text) to anon, authenticated",
            self.lower,
        )


class MarketOverviewPageSizeMigrationTests(unittest.TestCase):
    """Contract checks for the 0027 selectable page-size migration."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.path = ROOT / "supabase" / "migrations" / "0027_market_overview_page_size.sql"
        cls.sql = cls.path.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()

    def test_migration_is_transactional_and_read_only(self) -> None:
        self.assertRegex(self.lower, r"(?m)^begin;")
        self.assertRegex(self.lower, r"(?m)^commit;")
        self.assertNotRegex(
            self.lower,
            r"\b(insert\s+into|update\s+public\.|delete\s+from|truncate|drop\s+table)\b",
        )

    def test_page_size_is_a_whitelist_with_default_eight(self) -> None:
        # A free integer would become an unbounded LIMIT, so the parameter is
        # checked against an explicit list.
        self.assertIn("p_page_size integer default 8", self.lower)
        self.assertIn("array[8, 12, 16, 20]", self.lower)
        self.assertIn("else 8", self.lower)
        self.assertNotIn("select *", self.lower)

    def test_old_one_argument_signature_is_dropped(self) -> None:
        # Keeping both signatures would make PostgREST unable to choose a
        # candidate for a `p_page`-only call.
        self.assertIn("drop function if exists public.get_market_overview_page(integer);", self.lower)
        self.assertIn("stocklens_market_rpc_old_signature_still_present", self.lower)
        self.assertIn("stocklens_market_rpc_new_signature_missing", self.lower)

    def test_function_stays_bounded_definer_and_selectively_executable(self) -> None:
        self.assertIn("security definer", self.lower)
        self.assertIn("set search_path = ''", self.lower)
        self.assertIn("i.exchange_code = 'idx'", self.lower)
        # The bound now comes from the validated CTE, not a literal.
        self.assertIn("limit (select page_size from requested)", self.lower)
        self.assertIn(
            "grant execute on function public.get_market_overview_page(integer, integer) to anon, authenticated",
            self.lower,
        )
        self.assertIn("stocklens_market_rpc_grants_missing", self.lower)
        self.assertLess(self.lower.index("do $verify$"), self.lower.rindex("commit;"))

    def test_superseded_migration_targets_the_new_signature(self) -> None:
        # 0019 hardens the RPC owner by exact signature; if it still named the
        # one-argument form it would fail after 0027 drops it.
        pending = (
            ROOT / "supabase" / "migrations" / "0019_market_rpc_least_privilege_owner.sql"
        ).read_text(encoding="utf-8").lower()
        self.assertIn(
            "alter function public.get_market_overview_page(integer, integer) owner to stocklens_market_reader;",
            pending,
        )
        self.assertNotIn("get_market_overview_page(integer) owner", pending)


if __name__ == "__main__":
    unittest.main()



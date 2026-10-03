"""Offline contract checks for the research RPC extension (0031).

The RPC is the one place the UI and n8n read business numbers from, so its
contract is pinned here: the annual-ratio section must carry a `unit_code`, the
MoS column must be exposed, the classifier section must read the right run type,
and the growth-run dedup pin must survive.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "0031_stock_research_annual_ratios_and_mos.sql"


class ResearchRpcAnnualRatiosMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()

    def test_migration_is_transactional_and_read_only(self) -> None:
        self.assertRegex(self.lower, r"(?m)^begin;")
        self.assertRegex(self.lower, r"(?m)^commit;")
        self.assertLess(self.lower.index("do $verify$"), self.lower.rindex("commit;"))
        # A read RPC must not write data.
        self.assertNotRegex(self.lower, r"\b(insert\s+into|update\s+public\.|delete\s+from|truncate)\b")

    def test_rpc_stays_a_bounded_definer(self) -> None:
        self.assertIn("create or replace function public.get_stock_research_data(p_ticker text)", self.lower)
        self.assertIn("security definer", self.lower)
        self.assertIn("set search_path = ''", self.lower)
        self.assertIn(
            "revoke all on function public.get_stock_research_data(text) from public, anon, authenticated",
            self.lower,
        )
        self.assertIn(
            "grant execute on function public.get_stock_research_data(text) to anon, authenticated",
            self.lower,
        )
        self.assertNotIn("select *", self.lower)

    def test_annual_ratios_section_carries_unit_code_and_flags(self) -> None:
        """`unit_code` is what stops a margin being read as an amount."""
        self.assertIn("'annual_ratios', coalesce(", self.lower)
        self.assertIn("calc_annual_ratios", self.lower)
        for field in ("'metric_code'", "'value_numeric'", "'unit_code'", "'calculation_status'", "'flags'"):
            self.assertIn(field, self.lower, field)

    def test_annual_ratios_keeps_refused_rows(self) -> None:
        """A refused ratio is information, so the section must not filter to VALID.

        `annual_growth` filters to `VALID`; `annual_ratios` deliberately does not,
        because dropping a refused CAGR would make the year look absent instead of
        unavailable.
        """
        ratios_section = self.lower.index("stock_annual_ratios as")
        ratios_sql = self.lower[ratios_section:ratios_section + 1200]
        self.assertNotIn("calculation_status = 'valid'", ratios_sql)
        growth_section = self.lower.index("stock_annual_growth as")
        growth_sql = self.lower[growth_section:growth_section + 1200]
        self.assertIn("calculation_status = 'valid'", growth_sql)

    def test_mos_is_exposed_beside_gap_ratio(self) -> None:
        """Both ratios are stored and both are exposed; they are different numbers."""
        self.assertIn("'gap_ratio', v.gap_ratio", self.lower)
        self.assertIn("'mos', v.mos", self.lower)


class ResearchRpcSectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.lower = cls.sql.lower()

    def test_classification_reads_the_descriptive_run(self) -> None:
        """The classifier's run type is `CLASSIFICATION_DESCRIPTIVE`.

        Reading the wrong type silently yields a null section, which is how the
        first attempt shipped an empty classification.
        """
        self.assertIn("'classification_descriptive'", self.lower)
        self.assertIn("'stock_classification'", self.lower)
        self.assertIn("classification_final_type", self.lower)
        self.assertIn("classification_confidence", self.lower)

    def test_data_quality_warnings_are_derived_from_stored_flags(self) -> None:
        self.assertIn("'data_quality'", self.lower)
        self.assertIn("'warnings'", self.lower)
        self.assertIn("shares_carried_forward", self.lower)
        self.assertIn("total_assets_reconciliation_mismatch", self.lower)
        self.assertIn("mos_not_applicable", self.lower)
        self.assertIn("point_in_time_unavailable_date", self.lower)

    def test_growth_run_pin_is_preserved(self) -> None:
        """Without the pin a second growth run doubles every annual ratio."""
        self.assertIn("latest_growth_run", self.lower)
        self.assertIn("calculation_run_id = run.id", self.lower)
        self.assertIn("order by r.completed_at desc nulls last", self.lower)

    def test_ratio_reads_are_bounded(self) -> None:
        for bound in ("limit 200", "limit 260", "limit 100", "limit 40"):
            self.assertIn(bound, self.lower, bound)

    def test_classification_grants_are_column_level(self) -> None:
        """`has_table_privilege` is false for a column grant, so the check is per column."""
        self.assertIn(
            "grant select (instrument_id, metric_code, value_numeric, classification_code, calculation_status, availability_status)",
            self.lower,
        )
        self.assertIn("has_column_privilege(", self.lower)
        self.assertIn("stocklens_classification_reader_grant_missing", self.lower)

    def test_browser_roles_cannot_read_the_raw_tables(self) -> None:
        self.assertIn("stocklens_raw_table_grants_must_remain_private", self.lower)
        self.assertNotRegex(
            self.lower,
            r"grant\s+select\s+on\s+table\s+public\.(calc_annual_ratios|calc_metrics_classification)\s+to\s+(anon|authenticated)",
        )

    def test_verify_block_checks_every_new_section(self) -> None:
        for marker in (
            "stocklens_annual_ratios_section_missing",
            "stocklens_mos_section_missing",
            "stocklens_unit_code_missing",
            "stocklens_classification_section_missing",
            "stocklens_classification_run_type_wrong",
            "stocklens_data_quality_section_missing",
            "stocklens_growth_run_pin_missing",
        ):
            self.assertIn(marker, self.lower, marker)


if __name__ == "__main__":
    unittest.main()

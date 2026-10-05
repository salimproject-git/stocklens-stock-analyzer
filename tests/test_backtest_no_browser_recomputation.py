"""Guard: the Backtest tab must not compute business figures in the browser.

The user-entry-price simulation was removed on purpose. It let the reader type an
entry price and recompute a "Simulated Verdict" plus per-horizon returns, which
meant a second implementation of the verdict rule living in TypeScript while the
database already stored the answer. These tests fail if that pattern returns.

They are text assertions, not behaviour tests, because the risk being guarded
against is *re-introducing a recomputation*, which shows up as new arithmetic in
the adapter and a new input control in the tab.

The consensus badge is the second figure with the same history: the tab used to
derive it from the five intrinsic values, and the derived answer disagreed with
the stored one on 44 cases because the browser does not know the "at least three
valid methods" rule (docs/CONSENSUS_ARCHITECTURE.md section 2.3). It now reads
`calc_backtest_cases.consensus`, and the tests below keep it that way.
"""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
TAB = FRONTEND / "components" / "stock-research" / "backtest-tab-content.tsx"
BACKTEST = FRONTEND / "lib" / "analysis" / "backtest.ts"
ADAPTER = FRONTEND / "lib" / "backtest-adapter.ts"
BARREL = FRONTEND / "lib" / "analysis" / "index.ts"
MOCK = FRONTEND / "data" / "mock-stock-details.ts"


class BacktestNoBrowserRecomputationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tab = TAB.read_text(encoding="utf-8")
        cls.backtest = BACKTEST.read_text(encoding="utf-8")
        cls.adapter = ADAPTER.read_text(encoding="utf-8")
        cls.barrel = BARREL.read_text(encoding="utf-8")
        cls.mock = MOCK.read_text(encoding="utf-8")

    def test_entry_price_simulation_is_gone(self) -> None:
        """The panel, its state and its verdict function must all be absent."""
        for needle in (
            "Your Entry Simulation",
            "Reset to Analysis Price",
            "Simulated Verdict",
            "appliedEntry",
            "simulatedVerdict",
            "calculateSimulatedVerdict",
            "EditablePriceCell",
        ):
            self.assertNotIn(needle, self.tab, f"{needle} still present in the tab")
            self.assertNotIn(needle, self.backtest, f"{needle} still present in backtest.ts")

    def test_verdict_thresholds_have_one_owner(self) -> None:
        """The +20%/-15% pair belongs to the Python engine, not to TypeScript.

        `backtest_engine.py` defines `VERDICT_UPSIDE`/`VERDICT_DOWNSIDE`. A copy
        in `backtest.ts` is how the two implementations drifted apart before.
        """
        self.assertNotIn("upsideThreshold", self.backtest)
        self.assertNotIn("downsideThreshold", self.backtest)
        engine = (ROOT / "supabase" / "backtest_engine.py").read_text(encoding="utf-8")
        self.assertIn("VERDICT_UPSIDE = Decimal('1.20')", engine)
        self.assertIn("VERDICT_DOWNSIDE = Decimal('0.85')", engine)

    def test_no_longer_exported(self) -> None:
        self.assertNotIn("calculateSimulatedVerdict", self.barrel)
        self.assertNotIn("closeAtBacktestHorizon", self.barrel)

    def test_analysis_price_is_read_not_edited(self) -> None:
        """The tab renders the stored price; it must not hold price state."""
        for needle in ("analysisPrices", "setAnalysisPrices", "updateAnalysisPrice", "onPriceChange"):
            self.assertNotIn(needle, self.tab, f"{needle} still present in the tab")
        # The price is only ever read. Any assignment must derive from a case
        # object (`item.analysisPrice` / `testCase.analysisPrice`), never from a
        # control or a fresh literal.
        self.assertRegex(self.tab, r"price\(item\.analysisPrice\)")
        assignments = re.findall(r"analysisPrice\s*=(?!=)\s*([^;\n]+)", self.tab)
        self.assertTrue(assignments, "expected the price to be read somewhere")
        for rhs in assignments:
            self.assertIn(
                ".analysisPrice",
                rhs,
                f"analysis price assigned from something other than the stored case: {rhs.strip()}",
            )

    def test_adapter_shows_stored_verdicts(self) -> None:
        """`backtest-adapter.ts` passes the stored verdict through unchanged."""
        self.assertIn("verdict: toVerdict(testCase.verdict)", self.adapter)
        self.assertIn("verdictMos: toVerdict(testCase.verdictMos)", self.adapter)

    def test_no_inline_price_arithmetic_in_the_tab(self) -> None:
        """A return recomputed from a user price is the pattern being removed.

        Percentages may still be *formatted* (`value * 100`), but dividing by a
        price to produce a return is a business calculation and belongs in SQL.
        """
        offenders = re.findall(r"\w+\s*/\s*(?:item\.)?analysisPrice\s*-\s*1", self.tab)
        self.assertEqual(offenders, [], f"return recomputed in the tab: {offenders}")

    def test_consensus_is_read_from_the_stored_value(self) -> None:
        """`Consensus by Method` reads `calc_backtest_cases.consensus`.

        The stored column is the only source with three states. A browser rule
        built on `classifyMethodsAbovePrice(...).classification` has two, so it
        reported `OVERVALUED` on the 44 cases the database marked `N/A`.
        """
        self.assertNotRegex(
            self.tab,
            r"classify(?:Methods|IntrinsicValues)AbovePrice\([^;]*?\.classification",
            "the tab classifies intrinsic values again instead of reading the stored consensus",
        )
        self.assertIn("consensusFromStoredValue", self.tab)
        self.assertIn("testCase.consensus", self.tab)

    def test_missing_consensus_denominator_reads_na(self) -> None:
        """The three-method floor is applied, so `0|0` can never become a verdict."""
        self.assertIn("backtestMethodology.classification.methodUndervaluedMinimum", self.tab)
        self.assertIn('testCase.mosMain === null ? "N/A"', self.tab)

    def test_adapter_forwards_the_stored_consensus(self) -> None:
        """`backtest-adapter.ts` must not drop the stored consensus again.

        It used to have zero references to it, which is what left the tab with
        nothing to read.
        """
        for needle in (
            "consensus: testCase.consensus",
            "consensusUndervalued: testCase.consensusUndervalued",
            "consensusValid: testCase.consensusValid",
        ):
            self.assertIn(needle, self.adapter, f"{needle} missing from the adapter")

    def test_detail_drawer_renders_all_stored_method_intrinsic_values(self) -> None:
        """Method IVs are already in the RPC payload and must be visible in detail."""
        self.assertIn('aria-label="Intrinsic value by method"', self.tab)
        self.assertIn("methods.map((method)", self.tab)
        self.assertIn("price(method.intrinsicValue)", self.tab)
        self.assertIn("method.calculationStatus", self.tab)
        self.assertIn("method.flags.map((flag)", self.tab)
        self.assertIn("method.details.reason", self.tab)
        for method_code in (
            "PETER_LYNCH",
            "TYPE_SECTOR_WEIGHTED",
            "MEAN_REVERSION_PBV",
            "DDM",
            "DISCOUNTED_EARNINGS",
        ):
            self.assertIn(method_code, self.tab)

    def test_detail_view_looks_up_intrinsic_values_by_stored_method_code(self) -> None:
        self.assertIn("testCase.methods.find((item) => item.methodCode === methodCode)", self.tab)
        for method_code in (
            "PETER_LYNCH",
            "TYPE_SECTOR_WEIGHTED",
            "MEAN_REVERSION_PBV",
            "DDM",
            "DISCOUNTED_EARNINGS",
        ):
            self.assertIn(f'methodValue(item, "{method_code}")', self.tab)

    def test_adapter_preserves_method_status_and_provenance_flags(self) -> None:
        self.assertIn("calculationStatus: method.calculationStatus", self.adapter)
        self.assertIn("flags: method.flags", self.adapter)
        self.assertIn("details: method.details", self.adapter)

    def test_sample_data_stores_its_consensus_too(self) -> None:
        """The sample dataset feeds the same reader, so it stores literals as well.

        Deriving them for the sample rows while reading them for stored rows
        would keep the very second implementation this test file removes.
        """
        self.assertIn("consensus: seed.consensus", self.mock)
        self.assertIn("consensus: string;", self.mock)
        self.assertNotIn("classifyMethodsAbovePrice", self.mock)


if __name__ == "__main__":
    unittest.main()

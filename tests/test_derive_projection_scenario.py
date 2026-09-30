"""Offline checks for the derived projection scenario builder.

Pins the workbook `DataInputProyeksi` derivation rules that let valuation run
for a ticker whose owner has not supplied a hand-filled workbook sheet:

    flow items   = sum(Q1..Q_asof) * 4 / as_of_quarter
    stock items  = value at Q_asof
    avg DPR      = TRIMMEAN(annual DPS/EPS window, 0.4)
    potential DPS = forward EPS * avg DPR

The AUTO fixture below is the real canonical Q1/Q2 2026 data plus the stored
`WORKBOOK_2026_Q2` forecast, so a change to these rules fails loudly instead of
silently producing different valuations.
"""

from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'supabase'))

from calculation_v1_common import CalculationError  # noqa: E402
from calculate_valuation import normalise_classifier_type  # noqa: E402
from valuation_engine import STOCK_TYPES  # noqa: E402
from derive_projection_scenario import (  # noqa: E402
    FLOW_METRICS,
    STOCK_METRICS,
    annual_dpr_series,
    annual_share_count,
    available_metrics,
    build_scenario,
    ensure_single_active_scenario,
    index_facts,
    quarter_number,
    resolve_base_quarter,
    to_display,
    trimmean,
)


BILLION = Decimal('1000000000')

# AUTO 2026 Q1/Q2 canonical actuals (IDR) as stored in financial_facts.
AUTO_ACTUALS = {
    '2026-Q1': {
        'REVENUE': '5256848000000',
        'COST_OF_REVENUE': '4414982000000',
        'INTEREST_EXPENSE_NON_OPERATING': '9056000000',
        'EARNINGS': '558949000000',
        'OPERATING_CASH_FLOW': '410715000000',
        'TOTAL_CURRENT_ASSET': '10746385000000',
        'CURRENT_LIABILITIES': '4849741000000',
        'TOTAL_LIABILITIES': '6072354000000',
        'TOTAL_EQUITY': '17489722000000',
    },
    '2026-Q2': {
        'REVENUE': '5595855000000',
        'COST_OF_REVENUE': '4749754000000',
        'INTEREST_EXPENSE_NON_OPERATING': '9224000000',
        'EARNINGS': '592486000000',
        'OPERATING_CASH_FLOW': '339738000000',
        'TOTAL_CURRENT_ASSET': '11056363000000',
        'CURRENT_LIABILITIES': '5459244000000',
        'TOTAL_LIABILITIES': '6686521000000',
        'TOTAL_EQUITY': '17195384000000',
    },
}

# AUTO annual earnings/shares and the annual DPS series used for DPR.
AUTO_ANNUAL = {
    2019: {'EARNINGS': '739672000000', 'OUTSTANDING_SHARES': '4819733000'},
    2020: {'EARNINGS': '-1020000000', 'OUTSTANDING_SHARES': '4819730941'},
    2021: {'EARNINGS': '611348000000', 'OUTSTANDING_SHARES': '4813763780'},
    2022: {'EARNINGS': '1326575000000', 'OUTSTANDING_SHARES': '4823909091'},
    2023: {'EARNINGS': '1842435000000', 'OUTSTANDING_SHARES': '4819733000'},
    2024: {'EARNINGS': '2033641000000', 'OUTSTANDING_SHARES': '4819733000'},
    2025: {'EARNINGS': '2205022000000', 'OUTSTANDING_SHARES': '4819733000'},
}
AUTO_DPS = {2020: '42', 2021: '26.5', 2022: '62', 2023: '128', 2024: '189', 2025: '192'}

# The stored AUTO WORKBOOK_2026_Q2 forecast, in displayed M Rp (DPS in Rp).
AUTO_WORKBOOK = {
    'REVENUE': 21705,
    'COST_OF_REVENUE': -18329,
    'INTEREST_EXPENSE_NON_OPERATING': 37,
    'EARNINGS': 2303,
    'OPERATING_CASH_FLOW': 1501,
    'TOTAL_CURRENT_ASSET': 11056,
    'CURRENT_LIABILITIES': 5459,
    'TOTAL_LIABILITIES': 6687,
    'TOTAL_EQUITY': 17195,
    'POTENTIAL_DPS': 114,
}


def _period(period_id: str, period_type: str, label: str, end: str) -> dict[str, object]:
    return {
        'id': period_id,
        'period_type': period_type,
        'period_label': label,
        'period_end': end,
    }


def _facts_for(period_id: str, values: dict[str, str]) -> list[dict[str, object]]:
    return [
        {
            'financial_period_id': period_id,
            'metric_code': metric,
            'value_numeric': value,
            'unit_code': 'IDR',
            'quality_status': 'VALID',
            'revision_key': 'CURRENT',
        }
        for metric, value in values.items()
    ]


class ClassifierTypeMappingTests(unittest.TestCase):
    """`calculate_valuation.normalise_classifier_type` contract."""

    def test_asset_play_fallthrough_maps_to_asset_play(self) -> None:
        """Score-10 fall-through is modelled as ASSET PLAY by the engine.

        The workbook's score ladder has no branch for score 10, so a ticker whose
        only matching rule is ASSET PLAY is reported as UNCLASSIFIED (GOLD). The
        engine and the reference tables model that as ASSET PLAY, so rejecting it
        would leave such a ticker permanently unvaluable.
        """
        self.assertEqual(
            normalise_classifier_type('UNCLASSIFIED', asset_play_matched=True),
            'ASSET PLAY',
        )

    def test_unclassified_without_a_matching_rule_is_rejected(self) -> None:
        """No rule matched means no defensible type; do not invent one.

        INDF matches none of the six rules. Mapping it to ASSET PLAY would
        silently apply an asset-based methodology the classifier never chose.
        """
        with self.assertRaises(CalculationError) as ctx:
            normalise_classifier_type('UNCLASSIFIED', asset_play_matched=False)
        self.assertIn('CLASSIFICATION_UNCLASSIFIED_NO_RULE_MATCHED', str(ctx.exception))

    def test_known_types_pass_through_unchanged(self) -> None:
        for stock_type in STOCK_TYPES:
            self.assertEqual(normalise_classifier_type(stock_type), stock_type)

    def test_surrounding_whitespace_and_case_are_tolerated(self) -> None:
        self.assertEqual(normalise_classifier_type('  slow grower '), 'SLOW GROWER')

    def test_unknown_type_is_rejected(self) -> None:
        with self.assertRaises(CalculationError) as ctx:
            normalise_classifier_type('NOT A TYPE')
        self.assertIn('CLASSIFICATION_FINAL_TYPE_UNSUPPORTED', str(ctx.exception))


class DerivedProjectionScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.quarter_periods = [
            _period('q1', 'QUARTER', '2026-Q1', '2026-03-31'),
            _period('q2', 'QUARTER', '2026-Q2', '2026-06-30'),
        ]
        self.annual_periods = [
            _period(f'y{year}', 'ANNUAL', str(year), f'{year}-12-31')
            for year in sorted(AUTO_ANNUAL)
        ]
        raw_facts: list[dict[str, object]] = []
        quarter_ids = {'2026-Q1': 'q1', '2026-Q2': 'q2'}
        for label, values in AUTO_ACTUALS.items():
            raw_facts.extend(_facts_for(quarter_ids[label], values))
        raw_facts.extend(self._annual_facts())
        self.index = index_facts(raw_facts)
        self.dividends = [
            {'fact_type': 'ANNUAL_TOTAL', 'period_year': year, 'amount_per_share': dps}
            for year, dps in AUTO_DPS.items()
        ]

    @staticmethod
    def _annual_facts() -> list[dict[str, object]]:
        facts: list[dict[str, object]] = []
        for year, values in AUTO_ANNUAL.items():
            facts.extend(_facts_for(f'y{year}', values))
        return facts

    def _build(self, **overrides: object) -> dict[str, object]:
        kwargs: dict[str, object] = {
            'ticker': 'AUTO',
            'instrument': {
                'id': 'inst-1',
                'ticker': 'AUTO',
                'company_name': 'Astra Otoparts Tbk',
            },
            'annual_periods': self.annual_periods,
            'quarter_periods': self.quarter_periods,
            'index': self.index,
            'dividend_rows': self.dividends,
        }
        kwargs.update(overrides)
        return build_scenario(**kwargs)  # type: ignore[arg-type]

    def test_base_quarter_is_the_latest_complete_quarter(self) -> None:
        base = resolve_base_quarter(self.quarter_periods, self.index)
        self.assertEqual(base['period_label'], '2026-Q2')

    def test_earlier_quarter_becomes_base_when_later_one_is_incomplete(self) -> None:
        # Without Q2 facts the scenario must fall back to Q1 only, not fail.
        partial = index_facts(
            _facts_for('q1', AUTO_ACTUALS['2026-Q1']) + self._annual_facts()
        )
        base = resolve_base_quarter(self.quarter_periods, partial)
        self.assertEqual(base['period_label'], '2026-Q1')

    def test_missing_quarter_raises_instead_of_inventing_values(self) -> None:
        with self.assertRaises(CalculationError) as ctx:
            resolve_base_quarter(self.quarter_periods, {})
        self.assertIn('NO_COMPLETE_QUARTER_AVAILABLE', str(ctx.exception))

    def test_quarter_number_parses_quarter_end_months(self) -> None:
        self.assertEqual(quarter_number('2026-03-31'), 1)
        self.assertEqual(quarter_number('2026-06-30'), 2)
        self.assertEqual(quarter_number('2026-09-30'), 3)
        self.assertEqual(quarter_number('2026-12-31'), 4)

    def test_flow_metrics_are_annualised_run_rate(self) -> None:
        scenario = self._build()
        by_code = {p['metric_code']: p for p in scenario['projections']}  # type: ignore[union-attr]
        # (Q1 + Q2) * 4 / 2 == (Q1 + Q2) * 2
        for metric in ('REVENUE', 'EARNINGS', 'OPERATING_CASH_FLOW'):
            total = Decimal(AUTO_ACTUALS['2026-Q1'][metric]) + Decimal(
                AUTO_ACTUALS['2026-Q2'][metric]
            )
            self.assertEqual(
                by_code[metric]['source_display_value'], str(to_display(total * 2))
            )

    def test_stock_metrics_come_from_the_latest_quarter(self) -> None:
        scenario = self._build()
        by_code = {p['metric_code']: p for p in scenario['projections']}  # type: ignore[union-attr]
        for metric in STOCK_METRICS:
            expected = to_display(Decimal(AUTO_ACTUALS['2026-Q2'][metric]))
            self.assertEqual(by_code[metric]['source_display_value'], str(expected))

    def test_derived_forecast_matches_the_stored_workbook_scenario(self) -> None:
        scenario = self._build()
        by_code = {p['metric_code']: p for p in scenario['projections']}  # type: ignore[union-attr]
        for metric, expected in AUTO_WORKBOOK.items():
            self.assertEqual(
                int(by_code[metric]['source_display_value']),
                expected,
                f'{metric} diverged from the stored workbook forecast',
            )

    def test_cogs_keeps_the_workbook_negative_sign_convention(self) -> None:
        scenario = self._build()
        by_code = {p['metric_code']: p for p in scenario['projections']}  # type: ignore[union-attr]
        self.assertTrue(int(by_code['COST_OF_REVENUE']['source_display_value']) < 0)
        self.assertEqual(by_code['COST_OF_REVENUE']['unit_code'], 'IDR')

    def test_money_is_stored_in_full_idr_not_display_billions(self) -> None:
        scenario = self._build()
        revenue = next(
            p
            for p in scenario['projections']  # type: ignore[union-attr]
            if p['metric_code'] == 'REVENUE'
        )
        self.assertEqual(revenue['value_numeric'], str(21705 * BILLION))
        dps = next(
            p
            for p in scenario['projections']  # type: ignore[union-attr]
            if p['metric_code'] == 'POTENTIAL_DPS'
        )
        self.assertEqual(dps['unit_code'], 'IDR_PER_SHARE')
        self.assertEqual(dps['value_numeric'], '114')

    def test_average_dpr_uses_trimmean_over_the_full_window(self) -> None:
        series = annual_dpr_series(
            self.annual_periods, self.dividends, self.index, years_available=7
        )
        # 2019 has no DPS and contributes 0; 2020 is loss-making and negative.
        self.assertEqual(len(series), 7)
        self.assertEqual(series[0], Decimal(0))
        self.assertLess(series[1], 0)
        average = trimmean(series, Decimal('0.4'))
        self.assertIsNotNone(average)
        self.assertEqual(
            str(average.quantize(Decimal('0.000001'))),  # type: ignore[union-attr]
            '0.237726',
        )

    def test_dpr_skipping_a_mid_window_year_would_change_the_result(self) -> None:
        # Guards the rule that every year in the window contributes (a year with
        # no DPS contributes 0 rather than being dropped). Removing a *middle*
        # year's dividend changes the trimmed mean; extremes are trimmed anyway.
        full = trimmean(
            annual_dpr_series(
                self.annual_periods, self.dividends, self.index, years_available=7
            ),
            Decimal('0.4'),
        )
        sparse_dividends = [d for d in self.dividends if d['period_year'] != 2023]
        sparse = trimmean(
            annual_dpr_series(
                self.annual_periods, sparse_dividends, self.index, years_available=7
            ),
            Decimal('0.4'),
        )
        self.assertNotEqual(full, sparse)

    def test_shortening_the_years_available_window_changes_dpr(self) -> None:
        # The workbook ties Range_DPR to Years_Avail, so the window length is
        # part of the definition rather than a cosmetic option.
        full = trimmean(
            annual_dpr_series(
                self.annual_periods, self.dividends, self.index, years_available=7
            ),
            Decimal('0.4'),
        )
        shorter = trimmean(
            annual_dpr_series(
                self.annual_periods, self.dividends, self.index, years_available=5
            ),
            Decimal('0.4'),
        )
        self.assertNotEqual(full, shorter)

    def test_annual_share_count_rounds_to_whole_millions(self) -> None:
        shares = annual_share_count(self.annual_periods, self.index)
        self.assertEqual(shares, Decimal('4820000000'))

    def test_expected_historical_mirrors_every_quarter_used(self) -> None:
        scenario = self._build()
        expected = scenario['expected_historical']  # type: ignore[assignment]
        self.assertEqual(set(expected), {'Q1', 'Q2'})
        for metric in FLOW_METRICS:
            self.assertIn(metric, expected['Q1'])
        for metric in STOCK_METRICS:
            self.assertIn(metric, expected['Q2'])

    def test_metric_absent_from_every_quarter_is_omitted_not_zeroed(self) -> None:
        """A permanently absent line item must not block or distort the scenario.

        GOLD reports ``interest_expense_non_operating`` as null in all 26 of its
        quarters. Requiring it produced NO_COMPLETE_QUARTER_AVAILABLE and blocked
        the whole pipeline; emitting a zero would misstate the run-rate. The
        metric is therefore left out of the projection entirely.
        """
        quarter_periods = [
            _period('q1', 'QUARTER', '2026-Q1', '2026-03-31'),
            _period('q2', 'QUARTER', '2026-Q2', '2026-06-30'),
        ]
        # Same facts as AUTO, minus the interest line the provider never sends.
        raw_facts: list[dict[str, object]] = []
        for period_id, label in (('q1', '2026-Q1'), ('q2', '2026-Q2')):
            values = {
                metric: value
                for metric, value in AUTO_ACTUALS[label].items()
                if metric != 'INTEREST_EXPENSE_NON_OPERATING'
            }
            raw_facts.extend(_facts_for(period_id, values))
        # Annual facts are needed for the share count and the DPR series.
        raw_facts.extend(self._annual_facts())
        index = index_facts(raw_facts)

        base = resolve_base_quarter(quarter_periods, index)
        self.assertEqual(str(base['period_label']), '2026-Q2')
        self.assertNotIn('INTEREST_EXPENSE_NON_OPERATING', available_metrics(quarter_periods, index))

        scenario = build_scenario(
            ticker='TEST',
            instrument={'ticker': 'TEST'},
            annual_periods=self.annual_periods,
            quarter_periods=quarter_periods,
            index=index,
            dividend_rows=self.dividends,
        )
        emitted = {p['metric_code'] for p in scenario['projections']}  # type: ignore[union-attr]
        self.assertNotIn('INTEREST_EXPENSE_NON_OPERATING', emitted)
        # Everything the ticker does report is still produced.
        for metric in ('REVENUE', 'EARNINGS', 'OPERATING_CASH_FLOW'):
            self.assertIn(metric, emitted)

    def test_no_usable_facts_still_reports_incomplete_quarter(self) -> None:
        with self.assertRaises(CalculationError) as ctx:
            resolve_base_quarter(self.quarter_periods, {})
        self.assertIn('NO_COMPLETE_QUARTER_AVAILABLE', str(ctx.exception))

    def test_expected_historical_cogs_is_negative_for_validator(self) -> None:
        scenario = self._build()
        expected = scenario['expected_historical']  # type: ignore[assignment]
        self.assertTrue(expected['Q1']['COST_OF_REVENUE'].startswith('-'))

    def test_no_dividend_history_falls_back_to_zero_dpr_like_the_workbook(self) -> None:
        # The workbook formula is IFERROR(TRIMMEAN(Range_DPR, 0.4), 0), so a
        # ticker with no dividend facts yields DPR 0 rather than an error. The
        # resulting DPS of 0 makes DDM non-applicable instead of misleading.
        scenario = self._build(dividend_rows=[])
        self.assertEqual(scenario['average_dpr_ratio'], '0.000000')
        dps = next(
            p
            for p in scenario['projections']  # type: ignore[union-attr]
            if p['metric_code'] == 'POTENTIAL_DPS'
        )
        self.assertEqual(dps['value_numeric'], '0')

    def test_missing_annual_facts_fails_rather_than_guessing_dpr(self) -> None:
        # Without annual facts there is no share count and no EPS series, so the
        # scenario must refuse instead of inventing either input.
        with self.assertRaises(CalculationError) as ctx:
            self._build(annual_periods=[])
        self.assertIn('OUTSTANDING_SHARES_NOT_FOUND', str(ctx.exception))

    def test_annual_shares_without_earnings_fails_instead_of_zero_dpr(self) -> None:
        # Shares exist but no annual earnings means the DPR series is empty; the
        # builder must report that rather than silently returning no ratios.
        shares_only = index_facts(
            _facts_for('q1', AUTO_ACTUALS['2026-Q1'])
            + _facts_for('q2', AUTO_ACTUALS['2026-Q2'])
            + [
                _facts_for(
                    'y2025',
                    {'OUTSTANDING_SHARES': AUTO_ANNUAL[2025]['OUTSTANDING_SHARES']},
                )[0]
            ]
        )
        with self.assertRaises(CalculationError) as ctx:
            self._build(index=shares_only)
        self.assertIn('AVERAGE_DPR_NOT_DERIVABLE', str(ctx.exception))

    def test_trimmean_drops_an_even_number_of_extremes(self) -> None:
        values = [Decimal(v) for v in ('1', '2', '3', '4', '5', '100')]
        # 6 items * 0.4 -> 2 excluded (one per side) -> mean of 2,3,4,5 == 3.5
        self.assertEqual(trimmean(values, Decimal('0.4')), Decimal('3.5'))

    def test_trimmean_of_empty_series_is_none(self) -> None:
        self.assertIsNone(trimmean([], Decimal('0.4')))

    def test_second_active_scenario_is_refused(self) -> None:
        # AUTO already has the owner's WORKBOOK_2026_Q2 ACTIVE; adding a derived
        # one would make calculate_valuation.py fail with NOT_UNIQUE.
        with self.assertRaises(CalculationError) as ctx:
            ensure_single_active_scenario(
                [{'scenario_code': 'WORKBOOK_2026_Q2', 'scenario_version': 1}],
                scenario_code='DERIVED_2026_Q2',
                scenario_version=1,
            )
        self.assertIn('ACTIVE_SCENARIO_ALREADY_EXISTS', str(ctx.exception))

    def test_reapplying_the_same_scenario_version_is_allowed(self) -> None:
        # Idempotent re-run of the identical scenario must not be blocked.
        ensure_single_active_scenario(
            [{'scenario_code': 'DERIVED_2026_Q2', 'scenario_version': 1}],
            scenario_code='DERIVED_2026_Q2',
            scenario_version=1,
        )

    def test_bumping_the_scenario_version_is_refused_while_old_one_is_active(self) -> None:
        # A v2 alongside an ACTIVE v1 would also break the single-scenario rule.
        with self.assertRaises(CalculationError) as ctx:
            ensure_single_active_scenario(
                [{'scenario_code': 'DERIVED_2026_Q2', 'scenario_version': 1}],
                scenario_code='DERIVED_2026_Q2',
                scenario_version=2,
            )
        self.assertIn('ACTIVE_SCENARIO_ALREADY_EXISTS', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
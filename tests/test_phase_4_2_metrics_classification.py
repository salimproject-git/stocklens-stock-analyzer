"""Offline AUTO checks for the seven-year MetricsClassification calculation."""

from __future__ import annotations

import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for candidate in (str(REPO_ROOT), str(REPO_ROOT / 'supabase')):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from calculate_quarterly_growth_quality import (  # noqa: E402
    calculate_annual_growth_outputs,
    classify_metrics_classification,
)
from calculation_v1_common import CalculationError  # noqa: E402

FIXTURE = REPO_ROOT / 'tests' / 'fixtures' / 'auto_financials.json'


def fixture_data() -> dict:
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def annual_rows(years_available: int = 7) -> tuple[dict, list[dict]]:
    data = fixture_data()
    rows = calculate_annual_growth_outputs(
        data['periods'],
        data['facts'],
        'offline-auto',
        f'offline-auto-{years_available}y',
        years_available=years_available,
    )
    return data, rows


class AnnualWindowTests(unittest.TestCase):
    def test_seven_year_window_reproduces_metrics_classification_periods(self) -> None:
        _data, rows = annual_rows(7)
        by_code = {row['metric_code']: row for row in rows}

        self.assertEqual(by_code['YEARS_AVAILABLE']['value_numeric'], '7')
        self.assertEqual(by_code['YEARS_COMPARE']['value_numeric'], '5')
        self.assertLess(
            abs(
                Decimal(by_code['GROWTH_REVENUE_CAGR_LONG']['value_numeric'])
                - Decimal('0.04320553666520399')
            ),
            Decimal('1e-15'),
        )
        self.assertLess(
            abs(
                Decimal(by_code['GROWTH_REVENUE_CAGR_SHORT']['value_numeric'])
                - Decimal('0.10895962318518992')
            ),
            Decimal('1e-15'),
        )
        self.assertEqual(by_code['QUALITY_REVENUE_MOMENTUM']['value_numeric'], '1')
        self.assertEqual(by_code['QUALITY_EPS_MOMENTUM']['value_numeric'], '1')

    def test_explicit_six_year_window_selects_latest_six_annual_periods(self) -> None:
        _data, rows = annual_rows(6)
        by_code = {row['metric_code']: row for row in rows}
        self.assertEqual(by_code['YEARS_AVAILABLE']['value_numeric'], '6')
        self.assertEqual(by_code['YEARS_COMPARE']['value_numeric'], '3')

    def test_window_cannot_exceed_available_history(self) -> None:
        data = fixture_data()
        with self.assertRaisesRegex(CalculationError, 'YEARS_AVAILABLE_OUT_OF_RANGE'):
            calculate_annual_growth_outputs(
                data['periods'], data['facts'], 'offline-auto', 'bad-window',
                years_available=8,
            )


class ClassificationRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        _data, self.growth_rows = annual_rows(7)

    def classify(self, **overrides) -> list[dict]:
        inputs = {
            'growth_rows': self.growth_rows,
            'instrument_id': 'offline-auto',
            'run_id': 'offline-classification',
            'sector': 'Consumer Cyclicals',
            'projected_net_income': '2205022000000',
            'payout_ratio': '0.27',
            'historical_roe_average': '0.0938',
            'projected_pbv': '0.66',
            'pbv_percentile': '0.5060',
            'projected_pe': '4.92',
            'projected_peg': '0.25',
            'historical_dividend_yield': '0.0518',
        }
        inputs.update(overrides)
        return classify_metrics_classification(**inputs)

    def test_auto_rule_flags_system_recommendation_and_confidence(self) -> None:
        rows = self.classify()
        by_code = {row['metric_code']: row for row in rows}

        expected_flags = {
            'CLASSIFICATION_SLOW_GROWER': '1',
            'CLASSIFICATION_STALWART': '0',
            'CLASSIFICATION_FAST_GROWER': '0',
            'CLASSIFICATION_CYCLICAL': '1',
            'CLASSIFICATION_ASSET_PLAY': '0',
            'CLASSIFICATION_TURN_AROUND': '0',
        }
        for metric, value in expected_flags.items():
            self.assertEqual(by_code[metric]['value_numeric'], value, metric)
        self.assertEqual(
            by_code['CLASSIFICATION_SYSTEM_RECOMMENDATION']['classification_code'],
            'CYCLICAL',
        )
        self.assertEqual(
            by_code['CLASSIFICATION_FINAL_TYPE']['classification_code'], 'CYCLICAL'
        )
        self.assertEqual(by_code['CLASSIFICATION_CONFIDENCE']['value_numeric'], '0.7')
        self.assertIn(
            'REGISTRY_VERSION_UPDATE_REQUIRED',
            by_code['CLASSIFICATION_CONFIDENCE']['flags'],
        )

    def test_energy_override_precedes_scores_and_manual_override_sets_final_type(self) -> None:
        rows = self.classify(
            sector='Energy', projected_net_income='-1', manual_override='STALWART'
        )
        by_code = {row['metric_code']: row for row in rows}
        self.assertEqual(
            by_code['CLASSIFICATION_SYSTEM_RECOMMENDATION']['classification_code'],
            'CYCLICAL',
        )
        self.assertEqual(
            by_code['CLASSIFICATION_FINAL_TYPE']['classification_code'], 'STALWART'
        )

    def test_standalone_cyclical_rule_can_differ_from_system_recommendation(self) -> None:
        rows = self.classify(
            sector='Consumer Non-Cyclicals',
            projected_net_income='1',
            payout_ratio='0',
            historical_roe_average='0.1',
            projected_pbv='1',
            pbv_percentile='0.5',
            gpm_stability='0.21',
            projected_pe='10',
            projected_peg='1',
            historical_dividend_yield='0.01',
        )
        by_code = {row['metric_code']: row for row in rows}
        self.assertEqual(by_code['CLASSIFICATION_CYCLICAL']['value_numeric'], '1')
        self.assertEqual(
            by_code['CLASSIFICATION_SYSTEM_RECOMMENDATION']['classification_code'],
            'UNCLASSIFIED',
        )

    def test_asset_play_score_falls_through_system_rec_ifs(self) -> None:
        rows = self.classify(
            sector='Technology',
            projected_net_income='1',
            payout_ratio='0',
            historical_roe_average='0.1',
            projected_pbv='0.7',
            pbv_percentile='0.1',
            projected_pe='10',
            projected_peg='1',
            historical_dividend_yield='0.01',
        )
        by_code = {row['metric_code']: row for row in rows}
        self.assertEqual(by_code['CLASSIFICATION_ASSET_PLAY']['value_numeric'], '1')
        self.assertEqual(
            by_code['CLASSIFICATION_SYSTEM_RECOMMENDATION']['classification_code'],
            'UNCLASSIFIED',
        )


class DividendRatioTests(unittest.TestCase):
    """``DataInput!B28`` (DPR) and ``B29`` (Yield), blueprint 5.7 / 5.8.

    The two metrics are the only annual rows that read a non-fundamental input:
    DPS comes from ``dividend_facts`` and the yield denominator is a year-end
    *price*, not a fact. These tests pin the formula, the price basis and the
    missing-input behaviour without a database.
    """

    def annual_rows(
        self,
        *,
        dividend_rows=(),
        prices=(),
        years_available: int = 7,
    ) -> list[dict]:
        data = fixture_data()
        return calculate_annual_growth_outputs(
            data['periods'],
            data['facts'],
            'offline-auto',
            'offline-dividend',
            years_available=years_available,
            dividend_rows=dividend_rows,
            prices=prices,
        )

    @staticmethod
    def anchor_period() -> dict:
        data = fixture_data()
        return max(
            (p for p in data['periods'] if p.get('period_type') == 'ANNUAL'),
            key=lambda p: str(p.get('period_end') or ''),
        )

    def test_metrics_are_emitted_even_without_dividend_inputs(self) -> None:
        """Both rows always exist, so a gap is visible rather than absent."""
        by_code = {row['metric_code']: row for row in self.annual_rows()}
        for metric in ('DIVIDEND_PAYOUT_RATIO', 'DIVIDEND_YIELD'):
            self.assertIn(metric, by_code, metric)
            self.assertIsNone(by_code[metric]['value_numeric'], metric)
            self.assertEqual(
                by_code[metric]['calculation_status'], 'UNAVAILABLE', metric
            )

    def test_payout_ratio_is_dps_over_eps(self) -> None:
        """``B28 = B26/B30``: DPS divided by the same EPS the CAGR rows read."""
        data = fixture_data()
        anchor = self.anchor_period()

        rows = self.annual_rows(
            dividend_rows=[
                {
                    'fact_type': 'ANNUAL_TOTAL',
                    'period_year': int(str(anchor['period_end'])[:4]),
                    'amount_per_share': '4',
                }
            ]
        )
        by_code = {row['metric_code']: row for row in rows}

        # Independent recomputation from the same fixture facts: the fixture has a
        # stored EPS fact, which is what `_eps_value` prefers over deriving one.
        eps_facts = [
            f for f in data['facts']
            if str(f.get('financial_period_id')) == str(anchor['id'])
            and str(f.get('metric_code')) == 'EPS'
            and str(f.get('revision_key') or 'CURRENT') == 'CURRENT'
        ]
        eps = Decimal(str(eps_facts[0]['value_numeric']))
        # The engine stores 30 significant digits, so compare numerically.
        self.assertLess(
            abs(
                Decimal(by_code['DIVIDEND_PAYOUT_RATIO']['value_numeric'])
                - Decimal(4) / eps
            ),
            Decimal('1e-25'),
        )

    def test_yield_uses_year_end_close_not_latest_price(self) -> None:
        """``B29 = B26/B25`` with a year-end PIT close (blueprint 5.8, critical)."""
        anchor_end = str(self.anchor_period()['period_end'])
        anchor_year = int(anchor_end[:4])

        rows = self.annual_rows(
            dividend_rows=[
                {
                    'fact_type': 'ANNUAL_TOTAL',
                    'period_year': anchor_year,
                    'amount_per_share': '10',
                }
            ],
            prices=[
                # A later, higher price must NOT be selected.
                {'trading_date': f'{anchor_year}-12-30', 'close_price': '100'},
                {'trading_date': anchor_end, 'close_price': '200'},
                {'trading_date': f'{anchor_year + 1}-06-30', 'close_price': '9999'},
            ],
        )
        by_code = {row['metric_code']: row for row in rows}
        # 10 / 200 = 0.05, not 10/100 and not 10/9999.
        self.assertEqual(by_code['DIVIDEND_YIELD']['value_numeric'], '0.05')

    def test_missing_dividend_year_reports_missing_not_zero(self) -> None:
        """A year with no recorded dividend is ``UNAVAILABLE``, never ``0``."""
        by_code = {row['metric_code']: row for row in self.annual_rows()}
        self.assertIn(
            'DIVIDEND_PER_SHARE_MISSING',
            by_code['DIVIDEND_PAYOUT_RATIO']['flags'],
        )
        self.assertIn(
            'DIVIDEND_PER_SHARE_MISSING', by_code['DIVIDEND_YIELD']['flags']
        )

    def test_recorded_zero_dividend_is_a_valid_value(self) -> None:
        """A skipped dividend is a real zero, distinct from "not loaded"."""
        anchor_end = str(self.anchor_period()['period_end'])
        rows = self.annual_rows(
            dividend_rows=[
                {
                    'fact_type': 'ANNUAL_TOTAL',
                    'period_year': int(anchor_end[:4]),
                    'amount_per_share': '0',
                }
            ],
            prices=[{'trading_date': anchor_end, 'close_price': '50'}],
        )
        by_code = {row['metric_code']: row for row in rows}
        self.assertEqual(by_code['DIVIDEND_PAYOUT_RATIO']['value_numeric'], '0')
        self.assertEqual(by_code['DIVIDEND_YIELD']['value_numeric'], '0')
        self.assertEqual(by_code['DIVIDEND_YIELD']['calculation_status'], 'VALID')
        self.assertNotIn(
            'DIVIDEND_PER_SHARE_MISSING', by_code['DIVIDEND_YIELD']['flags']
        )

    def test_missing_year_end_price_reports_price_missing(self) -> None:
        """No close in that fiscal year -> ``PRICE_MISSING``, not a zero yield."""
        anchor_end = str(self.anchor_period()['period_end'])
        rows = self.annual_rows(
            dividend_rows=[
                {
                    'fact_type': 'ANNUAL_TOTAL',
                    'period_year': int(anchor_end[:4]),
                    'amount_per_share': '10',
                }
            ],
            prices=[{'trading_date': '2001-01-02', 'close_price': '5'}],
        )
        by_code = {row['metric_code']: row for row in rows}
        self.assertIsNone(by_code['DIVIDEND_YIELD']['value_numeric'])
        self.assertIn('PRICE_MISSING', by_code['DIVIDEND_YIELD']['flags'])

    def test_provenance_flag_does_not_block_the_division(self) -> None:
        """``EPS_DERIVED_FROM_EARNINGS`` marks provenance, not a missing input.

        ``_rri`` documents this distinction; the dividend ratios must respect it
        too, otherwise every year whose EPS is derived from EARNINGS /
        OUTSTANDING_SHARES would silently lose its payout ratio. The fixture
        stores an EPS fact, so it is removed here to force the derived path.
        """
        data = fixture_data()
        anchor = self.anchor_period()
        facts_without_eps = [
            f for f in data['facts']
            if not (
                str(f.get('financial_period_id')) == str(anchor['id'])
                and str(f.get('metric_code')) == 'EPS'
            )
        ]
        rows = calculate_annual_growth_outputs(
            data['periods'],
            facts_without_eps,
            'offline-auto',
            'offline-dividend',
            years_available=7,
            dividend_rows=[
                {
                    'fact_type': 'ANNUAL_TOTAL',
                    'period_year': int(str(anchor['period_end'])[:4]),
                    'amount_per_share': '4',
                }
            ],
        )
        by_code = {row['metric_code']: row for row in rows}
        payout = by_code['DIVIDEND_PAYOUT_RATIO']
        self.assertIsNotNone(payout['value_numeric'])
        self.assertEqual(payout['calculation_status'], 'VALID')
        self.assertIn('EPS_DERIVED_FROM_EARNINGS', payout['flags'])


    def test_negative_eps_refuses_the_payout_ratio(self) -> None:
        """A loss-making year has no meaningful payout ratio.

        The workbook emits a huge negative percentage here (AUTO 2020 =
        `-19846%`, which blueprint 5.7 itself calls an outlier). This module
        follows its own `ratio_result` convention instead: ``NULL`` plus
        ``NEGATIVE_DENOMINATOR``, so the UI shows "Not available" rather than a
        meaningless negative number.
        """
        data = fixture_data()
        anchor = self.anchor_period()
        negative_eps_facts = [
            {
                **f,
                'value_numeric': '-5',
            }
            if (
                str(f.get('financial_period_id')) == str(anchor['id'])
                and str(f.get('metric_code')) == 'EPS'
            )
            else f
            for f in data['facts']
        ]
        rows = calculate_annual_growth_outputs(
            data['periods'],
            negative_eps_facts,
            'offline-auto',
            'offline-dividend',
            years_available=7,
            dividend_rows=[
                {
                    'fact_type': 'ANNUAL_TOTAL',
                    'period_year': int(str(anchor['period_end'])[:4]),
                    'amount_per_share': '4',
                }
            ],
        )
        by_code = {row['metric_code']: row for row in rows}
        payout = by_code['DIVIDEND_PAYOUT_RATIO']
        self.assertIsNone(payout['value_numeric'])
        self.assertIn('NEGATIVE_DENOMINATOR', payout['flags'])


if __name__ == '__main__':
    unittest.main()
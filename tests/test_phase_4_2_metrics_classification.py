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


if __name__ == '__main__':
    unittest.main()
from __future__ import annotations

import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'supabase'))

from calculation_v1_common import CalculationError  # noqa: E402
from store_projection_scenario import (  # noqa: E402
    build_projection_rows,
    scenario_hash,
    validate_historical_values,
)


SCENARIO_PATH = ROOT / 'supabase' / 'projection_auto_2026_q2.json'


class ProjectionScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scenario = json.loads(SCENARIO_PATH.read_text(encoding='utf-8'))

    def _actual_facts(self) -> dict[str, dict[str, dict[str, object]]]:
        actual: dict[str, dict[str, dict[str, object]]] = {}
        expected = self.scenario['expected_historical']
        for quarter, metrics in expected.items():
            label = f"{self.scenario['projection_year']}-{quarter}"
            actual[label] = {}
            for metric_code, display in metrics.items():
                number = Decimal(display) * Decimal('1000000000')
                if metric_code == 'COST_OF_REVENUE':
                    number = abs(number)
                actual[label][metric_code] = {
                    'financial_period_id': f'{label}-id',
                    'metric_code': metric_code,
                    'value_numeric': str(number),
                    'unit_code': 'IDR',
                    'quality_status': 'VALID',
                }
        return actual

    def test_supplied_scenario_has_exactly_ten_forecast_values(self) -> None:
        rows = build_projection_rows(self.scenario, scenario_id='scenario-test')
        self.assertEqual(len(rows), 10)
        self.assertEqual(
            {row['metric_code'] for row in rows},
            {item['metric_code'] for item in self.scenario['projections']},
        )

    def test_forecast_currency_is_stored_in_idr_not_display_billions(self) -> None:
        rows = build_projection_rows(self.scenario, scenario_id='scenario-test')
        revenue = next(row for row in rows if row['metric_code'] == 'REVENUE')
        dps = next(row for row in rows if row['metric_code'] == 'POTENTIAL_DPS')
        self.assertEqual(revenue['value_numeric'], '21705000000000')
        self.assertEqual(revenue['unit_code'], 'IDR')
        self.assertEqual(dps['value_numeric'], '114')
        self.assertEqual(dps['unit_code'], 'IDR_PER_SHARE')

    def test_historical_display_values_match_canonical_rounding(self) -> None:
        report = validate_historical_values(
            self.scenario,
            self._actual_facts(),
            instrument_id='instrument-auto',
            base_period_id='period-q2',
        )
        self.assertEqual(report['status'], 'MATCHED_TO_CANONICAL_ACTUALS')
        self.assertEqual(len(report['quarters']['Q1']), 9)
        self.assertEqual(len(report['quarters']['Q2']), 9)

    def test_canonical_positive_cogs_matches_negative_workbook_sign_by_magnitude(self) -> None:
        actual = self._actual_facts()
        q1 = actual['2026-Q1']['COST_OF_REVENUE']
        q1['value_numeric'] = '4414982000000'
        report = validate_historical_values(
            self.scenario, actual,
            instrument_id='instrument-auto', base_period_id='period-q2',
        )
        self.assertEqual(
            report['quarters']['Q1']['COST_OF_REVENUE']['expected_display'], '-4415'
        )

    def test_material_historical_mismatch_is_rejected(self) -> None:
        actual = self._actual_facts()
        actual['2026-Q1']['REVENUE']['value_numeric'] = '1000000000000'
        with self.assertRaisesRegex(CalculationError, 'HISTORICAL_VALUE_MISMATCH'):
            validate_historical_values(
                self.scenario, actual,
                instrument_id='instrument-auto', base_period_id='period-q2',
            )

    def test_scenario_hash_is_stable(self) -> None:
        reordered = dict(reversed(list(self.scenario.items())))
        self.assertEqual(scenario_hash(self.scenario), scenario_hash(reordered))


if __name__ == '__main__':
    unittest.main()
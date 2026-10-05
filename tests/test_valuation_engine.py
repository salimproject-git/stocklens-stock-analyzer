from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'supabase'))

from valuation_engine import (  # noqa: E402
    ValuationError,
    calculate_daily_valuation_status,
    calculate_valuation_snapshot,
    comparison_years,
)
from calculation_methodology_registry import supplemental_methodology_seeds  # noqa: E402
from calculation_registry import sha256_json, sha256_text  # noqa: E402


def fixture_inputs():
    instrument_id = 'instrument-1'
    annual_periods = []
    quarterly_periods = []
    facts = []
    annual_data = [
        ('2020-12-31', '2020', '100', '10', '50', '10'),
        ('2021-12-31', '2021', '110', '11', '55', '10'),
        ('2022-12-31', '2022', '121', '12', '60', '10'),
        ('2023-12-31', '2023', '133.1', '13', '65', '10'),
        ('2024-12-31', '2024', '146.41', '14', '70', '10'),
        ('2025-12-31', '2025', '161.051', '16', '80', '10'),
    ]
    for index, (end, label, revenue, earnings, equity, shares) in enumerate(annual_data):
        period_id = f'annual-{index}'
        annual_periods.append({
            'id': period_id, 'instrument_id': instrument_id,
            'period_type': 'ANNUAL', 'period_label': label,
            'period_end': end, 'report_date': end, 'available_date': end,
        })
        for metric, value in (
            ('REVENUE', revenue), ('EARNINGS', earnings),
            ('TOTAL_EQUITY', equity), ('OUTSTANDING_SHARES', shares),
            ('CURRENT_ASSETS', '90'), ('TOTAL_LIABILITIES', '30'),
        ):
            facts.append({
                'financial_period_id': period_id,
                'metric_code': metric,
                'value_numeric': value,
                'quality_status': 'VALID',
                'revision_key': 'CURRENT',
            })
    for year in range(2021, 2026):
        for q, md in enumerate(('03-31', '06-30', '09-30', '12-31'), start=1):
            end = f'{year}-{md}'
            period_id = f'q-{year}-{q}'
            period = {
                'id': period_id, 'instrument_id': instrument_id,
                'period_type': 'QUARTER', 'period_label': f'{year}-Q{q}',
                'period_end': end, 'report_date': end, 'available_date': end,
            }
            quarterly_periods.append(period)
            for metric, value in (
                ('TOTAL_EQUITY', '80'), ('REVENUE', '25'),
                ('TOTAL_CURRENT_ASSET', '45'), ('TOTAL_LIABILITIES', '30'),
            ):
                facts.append({
                    'financial_period_id': period_id,
                    'metric_code': metric,
                    'value_numeric': value,
                    'quality_status': 'VALID',
                    'revision_key': 'CURRENT',
                })
    q2_2026 = {
        'id': 'q-2026-2', 'instrument_id': instrument_id,
        'period_type': 'QUARTER', 'period_label': '2026-Q2',
        'period_end': '2026-06-30', 'report_date': '2026-06-30',
        'available_date': '2026-08-01',
    }
    quarterly_periods.append(q2_2026)
    facts.extend([
        {'financial_period_id': 'q-2026-2', 'metric_code': 'REVENUE', 'value_numeric': '45', 'quality_status': 'VALID'},
        {'financial_period_id': 'q-2026-2', 'metric_code': 'TOTAL_EQUITY', 'value_numeric': '85', 'quality_status': 'VALID'},
    ])
    prices = [
        {'trading_date': f'{year}-12-30', 'close_price': str(20 + year - 2020)}
        for year in range(2020, 2026)
    ] + [{'trading_date': '2026-09-25', 'close_price': '40'}]
    scenario = {
        'id': 'scenario-1', 'input_hash': 'a' * 64,
        'as_of_financial_period_id': 'q-2026-2',
        'years_available': 6,
        'projected_shares_outstanding': '10',
        'values': {
            'EARNINGS': '20', 'TOTAL_EQUITY': '1000',
            'TOTAL_CURRENT_ASSET': '1200', 'TOTAL_LIABILITIES': '200',
            'POTENTIAL_DPS': '2',
        },
    }
    return annual_periods, quarterly_periods, facts, prices, scenario


class ValuationEngineTests(unittest.TestCase):
    def test_supplemental_valuation_methodology_hashes_are_stable(self) -> None:
        rows = supplemental_methodology_seeds()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['method_code'], 'VALUATION_CURRENT')
        self.assertEqual(row['formula_hash'], sha256_text(row['formula_text']))
        self.assertEqual(row['parameter_hash'], sha256_json(row['parameter_spec']))

    def test_comparison_years_uses_workbook_ladder_and_explicit_override(self) -> None:
        self.assertEqual(comparison_years(7), 5)
        self.assertEqual(comparison_years(6), 3)
        self.assertEqual(comparison_years(4), 2)
        self.assertEqual(comparison_years(2), 0)
        self.assertEqual(comparison_years(6, 4), 4)
        self.assertEqual(comparison_years(2, 0), 0)
        with self.assertRaisesRegex(ValuationError, 'YEARS_COMPARE_OUT_OF_RANGE'):
            comparison_years(4, 4)

    def test_cyclical_peter_lynch_selects_forward_bvps_times_one(self) -> None:
        annual, quarters, facts, prices, scenario = fixture_inputs()
        result = calculate_valuation_snapshot(
            ticker='AUTO', sector='Consumer Cyclicals', stock_type='CYCLICAL',
            annual_periods=annual, quarterly_periods=quarters, facts=facts,
            prices=prices, scenario=scenario, valuation_date='2026-09-25',
            years_available=6,
            sector_weights={'w_pe': '3', 'w_pbv': '1'},
            type_weights={'w_pe': '0', 'w_pbv': '10'},
        )
        method = next(row for row in result['methods'] if row['method_code'] == 'PETER_LYNCH')
        self.assertEqual(method['details']['selected_branch'], 'CYCLICAL_PBV')
        self.assertEqual(method['intrinsic_value'], Decimal('100'))
        self.assertEqual(result['years_available'], 6)
        self.assertEqual(result['years_compare'], 3)

    def test_missing_risk_free_rate_is_unavailable_and_other_methods_compute(self) -> None:
        annual, quarters, facts, prices, scenario = fixture_inputs()
        result = calculate_valuation_snapshot(
            ticker='AUTO', sector='Consumer Cyclicals', stock_type='CYCLICAL',
            annual_periods=annual, quarterly_periods=quarters, facts=facts,
            prices=prices, scenario=scenario, valuation_date='2026-09-25',
            sector_weights={'w_pe': '3', 'w_pbv': '1'},
            type_weights={'w_pe': '0', 'w_pbv': '10'},
        )
        ddm = next(row for row in result['methods'] if row['method_code'] == 'DDM')
        self.assertIsNone(ddm['intrinsic_value'])
        self.assertEqual(ddm['calculation_status'], 'UNAVAILABLE')
        self.assertIn('RISK_FREE_RATE_UNRESOLVED', ddm['flags'])
        self.assertEqual(result['current_price'], Decimal('40'))

    def test_risk_free_rate_requires_a_source_and_enables_rate_methods(self) -> None:
        annual, quarters, facts, prices, scenario = fixture_inputs()
        result = calculate_valuation_snapshot(
            ticker='AUTO', sector='Consumer Cyclicals', stock_type='CYCLICAL',
            annual_periods=annual, quarterly_periods=quarters, facts=facts,
            prices=prices, scenario=scenario, valuation_date='2026-09-25',
            risk_free_rate='0.0633', risk_free_source='test reference',
            sector_weights={'w_pe': '3', 'w_pbv': '1'},
            type_weights={'w_pe': '0', 'w_pbv': '10'},
        )
        ddm = next(row for row in result['methods'] if row['method_code'] == 'DDM')
        self.assertEqual(ddm['calculation_status'], 'VALID')
        self.assertGreater(ddm['intrinsic_value'], Decimal(0))

    def test_available_date_presence_controls_point_in_time_flag(self) -> None:
        annual, quarters, facts, prices, scenario = fixture_inputs()
        for period in annual:
            period['available_date'] = None
        result = calculate_valuation_snapshot(
            ticker='AUTO', sector='Consumer Cyclicals', stock_type='CYCLICAL',
            annual_periods=annual, quarterly_periods=quarters, facts=facts,
            prices=prices, scenario=scenario, valuation_date='2026-09-25',
            sector_weights={'w_pe': '3', 'w_pbv': '1'},
            type_weights={'w_pe': '0', 'w_pbv': '10'},
        )
        peter = next(row for row in result['methods'] if row['method_code'] == 'PETER_LYNCH')
        self.assertIn('POINT_IN_TIME_UNVERIFIED', peter['flags'])

    def test_unknown_reference_weight_fails_closed(self) -> None:
        annual, quarters, facts, prices, scenario = fixture_inputs()
        result = calculate_valuation_snapshot(
            ticker='AUTO', sector='Unknown sector', stock_type='CYCLICAL',
            annual_periods=annual, quarterly_periods=quarters, facts=facts,
            prices=prices, scenario=scenario, valuation_date='2026-09-25',
            type_weights={'w_pe': '0', 'w_pbv': '10'},
        )
        weighted = next(row for row in result['methods'] if row['method_code'] == 'TYPE_SECTOR_WEIGHTED')
        self.assertIsNone(weighted['intrinsic_value'])
        self.assertIn('SECTOR_WEIGHT_UNCLASSIFIED', weighted['flags'])

    def test_mean_reversion_flags_annual_share_proxy(self) -> None:
        annual, quarters, facts, prices, scenario = fixture_inputs()
        result = calculate_valuation_snapshot(
            ticker='AUTO', sector='Consumer Cyclicals', stock_type='CYCLICAL',
            annual_periods=annual, quarterly_periods=quarters, facts=facts,
            prices=prices, scenario=scenario, valuation_date='2026-09-25',
            sector_weights={'w_pe': '3', 'w_pbv': '1'},
            type_weights={'w_pe': '0', 'w_pbv': '10'},
        )
        mean = next(row for row in result['methods'] if row['method_code'] == 'MEAN_REVERSION_PBV')
        self.assertIsNotNone(mean['intrinsic_value'])
        self.assertEqual(mean['calculation_status'], 'APPROXIMATED')
        self.assertIn('QUARTERLY_SHARES_ANNUAL_PROXY', mean['flags'])

    def test_available_years_cannot_exceed_actual_annual_history(self) -> None:
        annual, quarters, facts, prices, scenario = fixture_inputs()
        with self.assertRaisesRegex(ValuationError, 'YEARS_AVAILABLE_EXCEEDS_HISTORY'):
            calculate_valuation_snapshot(
                ticker='AUTO', sector='Consumer Cyclicals', stock_type='CYCLICAL',
                annual_periods=annual, quarterly_periods=quarters, facts=facts,
                prices=prices, scenario=scenario, valuation_date='2026-09-25',
                years_available=7,
            )

    def test_valuation_date_must_not_precede_projection_base_period(self) -> None:
        annual, quarters, facts, prices, scenario = fixture_inputs()
        with self.assertRaisesRegex(ValuationError, 'VALUATION_DATE_BEFORE_PROJECTION_BASE'):
            calculate_valuation_snapshot(
                ticker='AUTO', sector='Consumer Cyclicals', stock_type='CYCLICAL',
                annual_periods=annual, quarterly_periods=quarters, facts=facts,
                prices=prices, scenario=scenario, valuation_date='2026-06-29',
            )


class ValuationMethodMosTests(unittest.TestCase):
    """Workbook rule D6: `MoS = (IV - price) / IV`, which is not `gap_ratio`.

    `gap_ratio` divides by the *price*. For the AUTO DDM row the two are -0.5739
    and -1.3467 from identical inputs, so storing one under the other's name would
    be wrong by a wide margin.
    """

    def snapshot(self, **overrides):
        annual, quarters, facts, prices, scenario = fixture_inputs()
        kwargs = {
            'ticker': 'AUTO', 'sector': 'Consumer Cyclicals', 'stock_type': 'CYCLICAL',
            'annual_periods': annual, 'quarterly_periods': quarters, 'facts': facts,
            'prices': prices, 'scenario': scenario, 'valuation_date': '2026-09-25',
            'sector_weights': {'w_pe': '3', 'w_pbv': '1'},
            'type_weights': {'w_pe': '0', 'w_pbv': '10'},
        }
        kwargs.update(overrides)
        return calculate_valuation_snapshot(**kwargs)

    def test_mos_divides_by_the_intrinsic_value_not_the_price(self) -> None:
        result = self.snapshot()
        method = next(
            row for row in result['methods']
            if row['intrinsic_value'] is not None and row['intrinsic_value'] > 0
        )
        price = method['current_price']
        intrinsic = method['intrinsic_value']
        self.assertEqual(method['mos'], (intrinsic - price) / intrinsic)
        self.assertEqual(method['gap_ratio'], (intrinsic - price) / price)
        # The two are genuinely different numbers, so neither can stand in for
        # the other.
        self.assertNotEqual(method['mos'], method['gap_ratio'])

    def test_every_method_row_carries_a_mos_key(self) -> None:
        result = self.snapshot()
        self.assertTrue(result['methods'])
        for method in result['methods']:
            self.assertIn('mos', method, method['method_code'])

    def test_unavailable_intrinsic_value_has_no_mos_and_no_flag(self) -> None:
        """No IV means no ratio at all - not a zero, and not a refusal flag."""
        result = self.snapshot()
        ddm = next(row for row in result['methods'] if row['method_code'] == 'DDM')
        self.assertIsNone(ddm['intrinsic_value'])
        self.assertIsNone(ddm['mos'])
        self.assertNotIn('MOS_DENOMINATOR_ZERO', ddm['flags'])
        self.assertNotIn('MOS_NOT_APPLICABLE', ddm['flags'])

    def test_zero_intrinsic_value_is_flagged_as_a_zero_denominator(self) -> None:
        """IV = 0 is undefined, so the row is flagged rather than given a value.

        The workbook writes `N/A (Skip)` for exactly this case.
        """
        from valuation_engine import FLAG_MOS_DENOMINATOR_ZERO

        annual, quarters, facts, prices, scenario = fixture_inputs()
        # Force Peter Lynch's forward BVPS to zero by zeroing projected equity.
        scenario = dict(scenario, values={**scenario['values'], 'TOTAL_EQUITY': '0'})
        result = calculate_valuation_snapshot(
            ticker='AUTO', sector='Consumer Cyclicals', stock_type='CYCLICAL',
            annual_periods=annual, quarterly_periods=quarters, facts=facts,
            prices=prices, scenario=scenario, valuation_date='2026-09-25',
            sector_weights={'w_pe': '3', 'w_pbv': '1'},
            type_weights={'w_pe': '0', 'w_pbv': '10'},
        )
        zero_iv = [row for row in result['methods'] if row['intrinsic_value'] == 0]
        self.assertTrue(zero_iv, 'fixture no longer produces a zero-IV method')
        for method in zero_iv:
            self.assertIsNone(method['mos'], method['method_code'])
            self.assertIn(FLAG_MOS_DENOMINATOR_ZERO, method['flags'], method['method_code'])


class ValuationFrequencyTests(unittest.TestCase):
    def test_intrinsic_snapshot_excludes_quote_from_hash_and_method_rows(self) -> None:
        annual, quarters, facts, prices, scenario = fixture_inputs()
        base = calculate_valuation_snapshot(
            ticker='AUTO', sector='Consumer Cyclicals', stock_type='CYCLICAL',
            annual_periods=annual, quarterly_periods=quarters, facts=facts,
            prices=prices, scenario=scenario, valuation_date='2026-09-25',
            include_daily_status=False,
        )
        changed_quote = [*prices, {'trading_date': '2026-09-25', 'close_price': '9999'}]
        changed = calculate_valuation_snapshot(
            ticker='AUTO', sector='Consumer Cyclicals', stock_type='CYCLICAL',
            annual_periods=annual, quarterly_periods=quarters, facts=facts,
            prices=changed_quote, scenario=scenario, valuation_date='2026-09-25',
            include_daily_status=False,
        )
        self.assertEqual(base['fundamental_input_hash'], changed['fundamental_input_hash'])
        self.assertTrue(all('current_price' not in row and 'mos' not in row for row in base['methods']))

    def test_daily_status_changes_without_recalculating_intrinsic_values(self) -> None:
        methods = [
            {'method_code': 'PETER_LYNCH', 'intrinsic_value': '120', 'calculation_status': 'VALID'},
            {'method_code': 'TYPE_SECTOR_WEIGHTED', 'intrinsic_value': '100', 'calculation_status': 'VALID'},
            {'method_code': 'DDM', 'intrinsic_value': '-10', 'calculation_status': 'VALID'},
        ]
        first = calculate_daily_valuation_status(methods, current_price='90', preferred_method_code='PETER_LYNCH')
        second = calculate_daily_valuation_status(methods, current_price='110', preferred_method_code='PETER_LYNCH')
        self.assertEqual(first['methods'][0]['intrinsic_value'], second['methods'][0]['intrinsic_value'])
        self.assertNotEqual(first['methods'][0]['gap_ratio'], second['methods'][0]['gap_ratio'])
        self.assertEqual(first['based_method_code'], 'PETER_LYNCH')

    def test_daily_method_rows_are_json_safe_decimal_strings(self) -> None:
        import json

        result = calculate_daily_valuation_status(
            [{'method_code': 'PETER_LYNCH', 'intrinsic_value': '120', 'calculation_status': 'VALID'}],
            current_price='90', preferred_method_code='PETER_LYNCH',
        )
        row = result['methods'][0]
        row = {key: str(value) if isinstance(value, Decimal) else value for key, value in row.items()}
        json.dumps(row, allow_nan=False)
        self.assertEqual(row['intrinsic_value'], '120')
        self.assertEqual(row['gap_ratio'], '0.3333333333333333333333333333')


if __name__ == '__main__':
    unittest.main()
"""Offline checks for the stock-type classifier input derivation.

These tests pin the two unit traps that ``derive_classifier_inputs`` exists to
handle, and verify the workbook reproductions that were validated against the
stored AUTO Q2 2026 workbook:

* ``Metric_PE_Fwd`` / ``Metric_PBV_Fwd`` are **multiples** (price / forward
  per-share value), not the price-style ``PE_PROJECTED`` / ``PBV_PROJECTED``
  that ``valuation_engine`` stores.
* ``gpm_stability`` is a **ratio** (the workbook's displayed ``GPM Range`` is
  that ratio x 100).

The tests are offline: they build inputs from the saved fixture and never call
Supabase or the Sectors API.
"""

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
)
from derive_classifier_inputs import (  # noqa: E402
    CLASSIFIER_INPUT_CODES,
    DIRECT_INPUT_CODES,
    GROWTH_ROW_INPUT_CODES,
    derive_classifier_inputs,
    percentrank_inc,
    trimmean,
)

FIXTURE = REPO_ROOT / 'tests' / 'fixtures' / 'auto_financials.json'
PRICE_FIXTURE = REPO_ROOT / 'tests' / 'fixtures' / 'auto_prices_daily.json'


def fixture_financials() -> dict:
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def fixture_prices() -> list[dict]:
    """Return the price rows from the fixture.

    The fixture wraps its rows: ``{"ticker": ..., "prices": [...]}``.
    """
    payload = json.loads(PRICE_FIXTURE.read_text(encoding='utf-8'))
    return payload['prices']


def annual_growth_rows() -> list[dict]:
    data = fixture_financials()
    return calculate_annual_growth_outputs(
        data['periods'],
        data['facts'],
        'offline-auto',
        'offline-classification-inputs',
        years_available=7,
    )


def derive(**overrides) -> dict:
    data = fixture_financials()
    inputs = {
        'annual_periods': data['periods'],
        'facts': data['facts'],
        'prices': fixture_prices(),
        'dividend_rows': [],
        'scenario_values': {
            'EARNINGS': '2302870000000',
            'TOTAL_EQUITY': '14500000000000',
        },
        'projected_shares_outstanding': '10000000000',
        'growth_rows': annual_growth_rows(),
    }
    inputs.update(overrides)
    return derive_classifier_inputs(**inputs)


class TrimmeanTests(unittest.TestCase):
    def test_trims_even_count_from_both_tails(self) -> None:
        # 10 values, 20% trim -> 2 excluded (one per tail).
        values = [Decimal(n) for n in range(1, 11)]
        self.assertEqual(trimmean(values, Decimal('0.2')), Decimal('5.5'))

    def test_empty_series_has_no_value(self) -> None:
        self.assertIsNone(trimmean([], Decimal('0.2')))


class PercentRankTests(unittest.TestCase):
    def test_clamps_below_minimum_and_above_maximum(self) -> None:
        series = [Decimal('1'), Decimal('2'), Decimal('3')]
        self.assertEqual(percentrank_inc(series, Decimal('0.5')), Decimal(0))
        self.assertEqual(percentrank_inc(series, Decimal('9')), Decimal(1))

    def test_interpolates_inside_the_series(self) -> None:
        series = [Decimal('1'), Decimal('2'), Decimal('3'), Decimal('4'), Decimal('5')]
        self.assertEqual(percentrank_inc(series, Decimal('3')), Decimal('0.5'))

    def test_single_entry_series_is_degenerate(self) -> None:
        self.assertEqual(percentrank_inc([Decimal('2')], Decimal('2')), Decimal(0))
        self.assertIsNone(percentrank_inc([], Decimal('2')))


class InputSetTests(unittest.TestCase):
    def test_every_input_is_derived_for_the_fixture(self) -> None:
        inputs = derive()
        self.assertEqual(set(inputs), set(CLASSIFIER_INPUT_CODES))
        for code in CLASSIFIER_INPUT_CODES:
            self.assertIsNotNone(inputs[code], f'{code} must be derivable')

    def test_growth_row_inputs_are_not_direct_keywords(self) -> None:
        """The four growth inputs travel through ``growth_rows``, not kwargs."""
        self.assertEqual(
            set(GROWTH_ROW_INPUT_CODES),
            {'revenue_long', 'revenue_cov', 'revenue_momentum', 'eps_long'},
        )
        for code in GROWTH_ROW_INPUT_CODES:
            self.assertNotIn(code, DIRECT_INPUT_CODES)

    def test_revenue_cagr_matches_the_stored_annual_result(self) -> None:
        rows = annual_growth_rows()
        by_code = {row['metric_code']: row for row in rows}
        inputs = derive(growth_rows=rows)
        self.assertEqual(
            inputs['revenue_long'],
            Decimal(by_code['GROWTH_REVENUE_CAGR_LONG']['value_numeric']),
        )


class UnitTrapTests(unittest.TestCase):
    """The two traps that make this module necessary."""

    def test_projected_multiples_are_price_divided_by_forward_per_share(self) -> None:
        prices = fixture_prices()
        latest = max(prices, key=lambda row: str(row['trading_date']))
        price = Decimal(str(latest['close_price']))

        inputs = derive(
            scenario_values={'EARNINGS': '1000000000', 'TOTAL_EQUITY': '5000000000'},
            projected_shares_outstanding='100000000',
        )
        # eps_fwd = 10, bvps_fwd = 50 -> PE 1/10 of price, PBV 1/50 of price.
        self.assertEqual(inputs['projected_pe'], price / Decimal('10'))
        self.assertEqual(inputs['projected_pbv'], price / Decimal('50'))

    def test_gpm_stability_is_a_ratio_not_percentage_points(self) -> None:
        """The classifier compares this against 0.2, so it cannot be x100."""
        inputs = derive()
        self.assertLess(inputs['gpm_stability'], Decimal('1'))
        # It is the difference of two gross-margin ratios, so it is bounded by 1.
        self.assertGreaterEqual(inputs['gpm_stability'], Decimal('0'))

    def test_peg_uses_eps_cagr_as_a_percentage(self) -> None:
        """`PE_fwd / (EPS_CAGR_Long * 100)`, matching the workbook's x100."""
        inputs = derive()
        expected = inputs['projected_pe'] / (inputs['eps_long'] * 100)
        self.assertEqual(inputs['projected_peg'], expected)

    def test_peg_is_unavailable_when_eps_growth_is_not_positive(self) -> None:
        rows = [
            row for row in annual_growth_rows()
            if row['metric_code'] != 'GROWTH_EPS_CAGR_LONG'
        ]
        rows.append({
            'metric_code': 'GROWTH_EPS_CAGR_LONG',
            'value_numeric': '-0.05',
            'calculation_status': 'VALID',
        })
        self.assertIsNone(derive(growth_rows=rows)['projected_peg'])


class MissingInputTests(unittest.TestCase):
    def test_missing_projection_yields_unavailable_multiples(self) -> None:
        inputs = derive(scenario_values={})
        self.assertIsNone(inputs['projected_pe'])
        self.assertIsNone(inputs['projected_pbv'])
        self.assertIsNone(inputs['pbv_percentile'])
        self.assertIsNone(inputs['projected_peg'])

    def test_dividend_series_defaults_to_zero_when_absent(self) -> None:
        """A year with no dividend contributes DPS 0, not a skipped year."""
        inputs = derive(dividend_rows=[])
        self.assertEqual(inputs['historical_dividend_yield'], Decimal(0))
        self.assertEqual(inputs['payout_ratio'], Decimal(0))


if __name__ == '__main__':
    unittest.main()

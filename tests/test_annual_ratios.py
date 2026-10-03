"""Offline checks for the annual ratio layer (`calc_annual_ratios`).

These pin the rules agreed in `docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md`
Langkah 1, using the AUTO fixture whose workbook values are known:

    EPS   457.47   (workbook `DataInput!B30` 2025)
    BVPS 3519.58   (workbook `DataInput!B42` 2025)
    ROE      13.0% (workbook `MetricsClassification` ROE 2025)
    GM       16.9% (workbook `DataInput!B27/B20`)
    NPM      11.1% (workbook `MetricsClassification` NPM)

The share basis is the workbook's single latest annual count, rounded to whole
millions, which is why EPS here is the template's EPS rather than a per-year
variant.
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
    ANNUAL_RATIO_METRICS,
    ANNUAL_RATIO_UNITS,
    calculate_annual_ratio_outputs,
    latest_share_count,
)
from calculation_v1_common import divide  # noqa: E402

FIXTURE = REPO_ROOT / 'tests' / 'fixtures' / 'auto_financials.json'


def fixture_data() -> dict:
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def ratio_rows(
    years_available: int | None = 7,
    *,
    facts: list[dict] | None = None,
) -> list[dict]:
    data = fixture_data()
    return calculate_annual_ratio_outputs(
        data['periods'],
        data['facts'] if facts is None else facts,
        'offline-auto',
        'offline-ratio',
        years_available=years_available,
    )


def by_code(rows: list[dict]) -> dict[str, dict]:
    return {row['metric_code']: row for row in rows}


def annual_periods(data: dict) -> list[dict]:
    return sorted(
        (p for p in data['periods'] if p.get('period_type') == 'ANNUAL'),
        key=lambda p: str(p.get('period_end') or ''),
    )


class AnnualRatioMetricSetTests(unittest.TestCase):
    def test_every_ratio_metric_is_emitted_exactly_once(self) -> None:
        rows = ratio_rows()
        emitted = [row['metric_code'] for row in rows]
        self.assertEqual(len(emitted), len(ANNUAL_RATIO_METRICS))
        for code in ANNUAL_RATIO_METRICS:
            self.assertIn(code, emitted, code)

    def test_every_row_carries_its_unit_label(self) -> None:
        """The unit is what stops a margin being read as an amount."""
        for row in ratio_rows():
            self.assertTrue(row.get('unit_code'), row['metric_code'])
            self.assertEqual(row['unit_code'], ANNUAL_RATIO_UNITS[row['metric_code']])

    def test_units_match_the_metric_kind(self) -> None:
        for code in ('EPS', 'BVPS'):
            self.assertEqual(ANNUAL_RATIO_UNITS[code], 'IDR_PER_SHARE')
        for code in ('ROE', 'GROSS_MARGIN', 'NET_MARGIN',
                     'REVENUE_CAGR_WINDOW', 'EARNINGS_CAGR_WINDOW'):
            self.assertEqual(ANNUAL_RATIO_UNITS[code], 'RATIO')
        for code in ('TOTAL_ASSETS', 'TOTAL_ASSETS_DERIVED'):
            self.assertEqual(ANNUAL_RATIO_UNITS[code], 'IDR')

    def test_rows_anchor_to_the_latest_annual_period(self) -> None:
        data = fixture_data()
        latest = annual_periods(data)[-1]
        for row in ratio_rows():
            self.assertEqual(row['financial_period_id'], str(latest['id']))
            self.assertEqual(row['observation_date'], latest['period_end'])


class AnnualRatioValueTests(unittest.TestCase):
    """Pin the values against the workbook's own AUTO figures."""

    def test_eps_and_bvps_match_the_workbook(self) -> None:
        """AUTO's workbook EPS/BVPS come from the full-precision latest share count.

        AUTO's newest reported count is 4_819_733_000, which the workbook's
        `=Proj_Shares` uses **without** rounding to Juta. Rounding it to
        4_820_000_000 would give EPS 457.4734 instead of the workbook's 457.4988.
        """
        rows = by_code(ratio_rows())
        self.assertLess(
            abs(Decimal(rows['EPS']['value_numeric']) - Decimal('457.50')),
            Decimal('0.01'),
        )
        self.assertLess(
            abs(Decimal(rows['BVPS']['value_numeric']) - Decimal('3519.8')),
            Decimal('0.05'),
        )

    def test_margins_and_roe_match_the_workbook(self) -> None:
        rows = by_code(ratio_rows())
        self.assertLess(
            abs(Decimal(rows['GROSS_MARGIN']['value_numeric']) - Decimal('0.169099473375244')),
            Decimal('1e-12'),
        )
        self.assertLess(
            abs(Decimal(rows['NET_MARGIN']['value_numeric']) - Decimal('0.110767420175665')),
            Decimal('1e-12'),
        )
        self.assertLess(
            abs(Decimal(rows['ROE']['value_numeric']) - Decimal('0.129979506474212')),
            Decimal('1e-12'),
        )

    def test_revenue_cagr_window_matches_the_growth_layer_window(self) -> None:
        """The window CAGR must agree with `GROWTH_REVENUE_CAGR_LONG`.

        Both describe the same seven-year revenue bridge, so a disagreement would
        mean the two layers disagree about which years a snapshot covers.
        """
        rows = by_code(ratio_rows())
        self.assertLess(
            abs(
                Decimal(rows['REVENUE_CAGR_WINDOW']['value_numeric'])
                - Decimal('0.04320553666520399')
            ),
            Decimal('1e-15'),
        )

    def test_shares_are_the_latest_annual_count_not_a_per_year_count(self) -> None:
        """EPS/BVPS divide by ONE share count, taken from the newest reported year.

        The workbook writes `=Proj_Shares` in every column of the shares row, so
        2019's EPS uses the newest reported count rather than 2019's own. AUTO's
        counts differ slightly per year (2019 = 4_819_733_000, 2021 = 4_813_763_780),
        so a per-year divisor would give a different EPS for 2019 and 2021. This
        pins that the same figure is used for both.
        """
        data = fixture_data()
        periods = annual_periods(data)
        latest = periods[-1]
        rows = by_code(ratio_rows())

        earnings = None
        equity = None
        shares_raw = None
        for fact in data['facts']:
            if str(fact.get('financial_period_id')) != str(latest['id']):
                continue
            if fact.get('metric_code') == 'EARNINGS':
                earnings = Decimal(str(fact['value_numeric']))
            if fact.get('metric_code') == 'TOTAL_EQUITY':
                equity = Decimal(str(fact['value_numeric']))
            if fact.get('metric_code') == 'OUTSTANDING_SHARES':
                shares_raw = Decimal(str(fact['value_numeric']))

        # No rounding: the workbook uses the reported count as it stands.
        self.assertEqual(Decimal(rows['EPS']['value_numeric']), divide(earnings, shares_raw))
        self.assertEqual(Decimal(rows['BVPS']['value_numeric']), divide(equity, shares_raw))

    def test_one_share_count_divides_every_year_of_the_table(self) -> None:
        """A 1-year window and a 7-year window must give the SAME EPS/BVPS.

        The workbook's shares row is a single `=Proj_Shares` repeated across every
        column, so a snapshot's window must not change the divisor. If it did, the
        earliest year's snapshot would silently use that year's own count - the bug
        that made ITMG 2021 report 6139.41 instead of the workbook's 6010.73.
        """
        data = fixture_data()
        periods = annual_periods(data)
        periods.sort(key=lambda p: str(p['period_end']), reverse=True)
        shares, shares_flags = latest_share_count(periods, data['facts'])
        self.assertIsNotNone(shares)
        self.assertEqual(shares_flags, [])

        for metric in ('EPS', 'BVPS'):
            values = set()
            for window_size in (1, 3, 7):
                rows = calculate_annual_ratio_outputs(
                    periods[:window_size],
                    data['facts'],
                    'offline-auto',
                    'offline-ratio',
                    shares=shares,
                    shares_flags=shares_flags,
                )
                values.add(Decimal(by_code(rows)[metric]['value_numeric']))
            self.assertEqual(len(values), 1, f'{metric} changed with the window')

    def test_total_assets_uses_the_reported_figure(self) -> None:
        """Decision S1: the reported value is official, the identity is kept beside it."""
        rows = by_code(ratio_rows())
        self.assertEqual(rows['TOTAL_ASSETS']['calculation_status'], 'VALID')
        self.assertEqual(
            Decimal(rows['TOTAL_ASSETS']['value_numeric']),
            Decimal('22615479000000'),
        )
        # The reconstruction is stored too, and is flagged as a reconstruction.
        self.assertEqual(
            Decimal(rows['TOTAL_ASSETS_DERIVED']['value_numeric']),
            Decimal('22615479000000'),
        )
        self.assertIn(
            'TOTAL_ASSETS_DERIVED_FROM_IDENTITY',
            rows['TOTAL_ASSETS_DERIVED']['flags'],
        )
        # AUTO's identity is exact, so the reported row must not be flagged.
        self.assertNotIn(
            'TOTAL_ASSETS_RECONCILIATION_MISMATCH', rows['TOTAL_ASSETS']['flags']
        )


class AnnualRatioGuardTests(unittest.TestCase):
    """Every refusal must be flagged, so "zero" never reads as "not available"."""

    def test_zero_equity_refuses_roe_with_denominator_zero(self) -> None:
        rows = by_code(self.rows_with_fact('TOTAL_EQUITY', '0'))
        self.assertIsNone(rows['ROE']['value_numeric'])
        self.assertEqual(rows['ROE']['calculation_status'], 'UNAVAILABLE')
        self.assertIn('DENOMINATOR_ZERO', rows['ROE']['flags'])

    def test_zero_revenue_refuses_both_margins(self) -> None:
        rows = by_code(self.rows_with_fact('REVENUE', '0'))
        for code in ('GROSS_MARGIN', 'NET_MARGIN'):
            self.assertIsNone(rows[code]['value_numeric'], code)
            self.assertIn('DENOMINATOR_ZERO', rows[code]['flags'], code)

    def test_negative_equity_refuses_roe_with_negative_denominator(self) -> None:
        rows = by_code(self.rows_with_fact('TOTAL_EQUITY', '-1000'))
        self.assertIsNone(rows['ROE']['value_numeric'])
        self.assertIn('NEGATIVE_DENOMINATOR', rows['ROE']['flags'])

    def test_missing_earnings_reports_the_missing_input(self) -> None:
        rows = by_code(self.rows_without_fact('EARNINGS'))
        self.assertIsNone(rows['EPS']['value_numeric'])
        self.assertIn('EARNINGS_MISSING', rows['EPS']['flags'])
        self.assertIn('EARNINGS_MISSING', rows['ROE']['flags'])

    def test_cagr_is_refused_when_the_window_starts_in_a_loss(self) -> None:
        """ARII and GOLD both start their windows in a loss.

        The honest output is "not available", not a linear-normalised stand-in.
        `NEGATIVE_BASE` records which guard fired.
        """
        data = fixture_data()
        periods = annual_periods(data)
        oldest = periods[0]
        facts = [
            dict(fact, value_numeric='-500')
            if (str(fact.get('financial_period_id')) == str(oldest['id'])
                and fact.get('metric_code') == 'EARNINGS')
            else fact
            for fact in data['facts']
        ]
        rows = by_code(ratio_rows(facts=facts))
        self.assertIsNone(rows['EARNINGS_CAGR_WINDOW']['value_numeric'])
        self.assertEqual(rows['EARNINGS_CAGR_WINDOW']['calculation_status'], 'UNAVAILABLE')
        self.assertIn('NEGATIVE_BASE', rows['EARNINGS_CAGR_WINDOW']['flags'])
        # The revenue window is untouched: only the earnings series was changed.
        self.assertIsNotNone(rows['REVENUE_CAGR_WINDOW']['value_numeric'])

    def test_reconciliation_mismatch_is_flagged_but_keeps_the_reported_value(self) -> None:
        """A disagreement between reported and reconstructed assets is recorded.

        The reported figure stays official (decision S1); the flag is the whole
        point of storing both, because the identity is not exact for every row
        (ARII, INKP and ITMG 2019 differ by 1 IDR).
        """
        rows = by_code(self.rows_with_fact('TOTAL_ASSETS', '1'))
        self.assertEqual(Decimal(rows['TOTAL_ASSETS']['value_numeric']), Decimal('1'))
        self.assertIn(
            'TOTAL_ASSETS_RECONCILIATION_MISMATCH', rows['TOTAL_ASSETS']['flags']
        )
        self.assertIsNotNone(rows['TOTAL_ASSETS_DERIVED']['value_numeric'])

    def test_missing_reported_assets_falls_back_to_the_identity(self) -> None:
        """Before the reported figure is ingested the reconstruction supplies it."""
        rows = by_code(self.rows_without_fact('TOTAL_ASSETS'))
        self.assertIsNotNone(rows['TOTAL_ASSETS']['value_numeric'])
        self.assertIn(
            'TOTAL_ASSETS_DERIVED_FROM_IDENTITY', rows['TOTAL_ASSETS']['flags']
        )

    # -- helpers -------------------------------------------------------------

    def rows_with_fact(self, metric_code: str, value: str) -> list[dict]:
        data = fixture_data()
        latest = annual_periods(data)[-1]
        facts = [
            dict(fact, value_numeric=value)
            if (str(fact.get('financial_period_id')) == str(latest['id'])
                and fact.get('metric_code') == metric_code)
            else fact
            for fact in data['facts']
        ]
        return ratio_rows(facts=facts)

    def rows_without_fact(self, metric_code: str) -> list[dict]:
        data = fixture_data()
        facts = [fact for fact in data['facts'] if fact.get('metric_code') != metric_code]
        return ratio_rows(facts=facts)


class AnnualRatioWindowTests(unittest.TestCase):
    def test_a_single_year_window_refuses_the_cagr(self) -> None:
        """One period means zero year-over-year steps, so no rate exists."""
        rows = by_code(ratio_rows(1))
        for code in ('REVENUE_CAGR_WINDOW', 'EARNINGS_CAGR_WINDOW'):
            self.assertIsNone(rows[code]['value_numeric'], code)
            self.assertIn('CAGR_PERIOD_ZERO', rows[code]['flags'], code)

    def test_a_shorter_window_changes_only_the_window_metrics(self) -> None:
        """ROE and the margins are levels, so a shorter window must not move them."""
        full = by_code(ratio_rows(7))
        short = by_code(ratio_rows(5))
        for code in ('ROE', 'GROSS_MARGIN', 'NET_MARGIN', 'EPS', 'BVPS', 'TOTAL_ASSETS'):
            self.assertEqual(full[code]['value_numeric'], short[code]['value_numeric'], code)
        self.assertNotEqual(
            full['REVENUE_CAGR_WINDOW']['value_numeric'],
            short['REVENUE_CAGR_WINDOW']['value_numeric'],
        )

    def test_no_annual_periods_emits_a_refused_row_for_every_metric(self) -> None:
        data = fixture_data()
        rows = calculate_annual_ratio_outputs(
            [p for p in data['periods'] if p.get('period_type') == 'QUARTER'],
            data['facts'],
            'offline-auto',
            'offline-ratio',
        )
        self.assertEqual(len(rows), len(ANNUAL_RATIO_METRICS))
        for row in rows:
            self.assertIsNone(row['value_numeric'])
            self.assertEqual(row['calculation_status'], 'UNAVAILABLE')
            self.assertIn('SERIES_INSUFFICIENT', row['flags'])

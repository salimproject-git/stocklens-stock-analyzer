"""Offline check: EPS/BVPS reproduce the five sample workbooks.

`Data/Sample Data/*.txt` are exports of the real workbooks. Their `DataInput` sheet
holds the reported years in columns 2..8 (column 1 is the projection year), and the
`Shares Outstanding [Juta]` row is the formula `=Proj_Shares` repeated across every
column. That single figure divides every year, which is why 2021's EPS uses the
newest reported count rather than 2021's own.

This test exists because the first implementation got that wrong: it resolved the
count per snapshot, so the earliest year used its own count and 41 of the 70
workbook cells did not match (ITMG 2021 EPS was 6139.41 instead of 6010.73).
"""

from __future__ import annotations

import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / 'supabase'))

from calculate_quarterly_growth_quality import (  # noqa: E402
    calculate_annual_ratio_outputs,
    latest_share_count,
)

SAMPLES = REPO_ROOT / 'Data' / 'Sample Data'
RAW = REPO_ROOT / 'Data' / 'Raw'

#: Workbook column order in the annual `DataInput` blocks.
COLUMN_YEARS = [2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019]

#: Tickers that ship a sample workbook export.
SAMPLE_TICKERS = ('AUTO', 'BIRD', 'ERAA', 'GEMA', 'ITMG', 'SIDO')


def decimal_or_none(value: str | None) -> Decimal | None:
    if value is None or not str(value).strip():
        return None
    try:
        return Decimal(str(value).strip())
    except Exception:
        return None


def workbook_cells(ticker: str) -> dict[tuple[str, int], Decimal]:
    """`{(metric, year): value}` from the workbook export."""
    path = SAMPLES / f'{ticker} Quarter 2 2026.txt'
    if not path.exists():
        return {}
    cells: dict[tuple[str, int], Decimal] = {}
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        label = line.split('|')[0]
        if label.startswith('EPS (Earning Per Share)'):
            metric = 'EPS'
        elif label.startswith('BVPS (Book Value per Share)'):
            metric = 'BVPS'
        else:
            continue
        for year, cell in zip(COLUMN_YEARS, line.split('|')[1:9]):
            value = decimal_or_none(cell)
            if value is not None:
                cells[(metric, year)] = value
    return cells


def canonical_rows(ticker: str) -> list[dict]:
    """The provider's own annual rows, which are what the loader ingests."""
    path = RAW / ticker / 'company_report_annual.json'
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding='utf-8'))['financials']['historical_financials']
    return sorted(rows, key=lambda row: int(row['year']))


def as_facts(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Shape the raw rows like canonical periods/facts so the engine can read them."""
    periods: list[dict] = []
    facts: list[dict] = []
    for row in rows:
        period_id = f'p-{row["year"]}'
        periods.append({
            'id': period_id,
            'period_type': 'ANNUAL',
            'period_label': str(row['year']),
            'period_end': f'{row["year"]}-12-31',
            'statement_scope': 'UNKNOWN',
        })
        for code, field in (
            ('EARNINGS', 'earnings'),
            ('TOTAL_EQUITY', 'total_equity'),
            ('OUTSTANDING_SHARES', 'outstanding_shares'),
        ):
            value = row.get(field)
            if value is None:
                continue
            facts.append({
                'financial_period_id': period_id,
                'metric_code': code,
                'value_numeric': str(value),
                'quality_status': 'VALID',
                'revision_key': 'CURRENT',
            })
    return periods, facts


class WorkbookShareBasisTests(unittest.TestCase):
    def test_the_latest_reported_count_is_used_without_rounding(self) -> None:
        """The workbook's `=Proj_Shares` is the reported count, not a rounded one.

        Rounding to whole millions would satisfy AUTO and ERAA but break ITMG
        (0/14 cells) and BIRD (7/14), so the rule must be full precision.
        """
        rows = canonical_rows('ITMG')
        periods, facts = as_facts(rows)
        periods.sort(key=lambda period: period['period_end'], reverse=True)

        shares, flags = latest_share_count(periods, facts)

        self.assertEqual(flags, [])
        self.assertEqual(shares, Decimal('1129677000'))
        # ITMG's newest count is 1_129_677_000, which is NOT a whole million.
        self.assertNotEqual(shares, Decimal('1130000000'))

    def test_a_missing_latest_count_walks_back(self) -> None:
        """BIRD 2025 reports no count, so 2024 supplies the single value."""
        rows = canonical_rows('BIRD')
        periods, facts = as_facts(rows)
        periods.sort(key=lambda period: period['period_end'], reverse=True)

        shares, flags = latest_share_count(periods, facts)

        self.assertEqual(shares, Decimal('2502100000'))
        self.assertEqual(flags, ['SHARES_CARRIED_FORWARD'])

    def test_eps_and_bvps_match_every_workbook_cell(self) -> None:
        """Every reported year in every sample workbook must reproduce exactly."""
        checked = 0
        mismatches: list[str] = []
        for ticker in SAMPLE_TICKERS:
            expected_cells = workbook_cells(ticker)
            rows = canonical_rows(ticker)
            if not expected_cells or not rows:
                continue
            periods, facts = as_facts(rows)
            periods.sort(key=lambda period: period['period_end'], reverse=True)
            shares, shares_flags = latest_share_count(periods, facts)
            self.assertIsNotNone(shares, ticker)

            for period in periods:
                year = int(period['period_label'])
                rows_out = calculate_annual_ratio_outputs(
                    [period], facts, ticker, 'offline-workbook',
                    shares=shares, shares_flags=shares_flags,
                )
                by_code = {row['metric_code']: row for row in rows_out}
                for metric in ('EPS', 'BVPS'):
                    expected = expected_cells.get((metric, year))
                    got = by_code[metric]['value_numeric']
                    if expected is None or got is None:
                        continue
                    checked += 1
                    # The workbook prints one decimal, so half a unit is the tolerance.
                    if abs(Decimal(got) - expected) >= Decimal('0.05'):
                        mismatches.append(
                            f'{ticker} {metric} {year}: workbook={expected} engine={got}'
                        )

        self.assertEqual(mismatches, [], '\n'.join(mismatches))
        # 5 workbooks x 7 reported years x 2 metrics.
        self.assertEqual(checked, 70)


if __name__ == '__main__':
    unittest.main()

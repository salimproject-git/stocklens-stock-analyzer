"""Offline checks that AUTO import plans follow the approved field map."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (str(ROOT), str(ROOT / 'supabase')):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import load_annual_financials_to_supabase as annual  # noqa: E402
import load_dividend_to_supabase as dividend  # noqa: E402
import load_identity_to_supabase as identity  # noqa: E402
import load_quarterly_financials_to_supabase as quarterly  # noqa: E402

RAW_AUTO = ROOT / 'Data' / 'Raw' / 'AUTO'


def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


class AutoLoaderMappingTests(unittest.TestCase):
    def test_annual_plans_include_only_approved_fields_and_annual_shares(self) -> None:
        payload = load_json(RAW_AUTO / 'company_report_annual.json')
        rows, _ = annual.validate_source(payload, 'AUTO')

        plans = annual.make_fact_plans(rows)
        expected_annual_fields = {
            'revenue', 'cost_of_revenue', 'interest_expense_non_operating', 'earnings',
            'operating_cash_flow', 'gross_profit', 'current_assets', 'current_liabilities',
            'total_liabilities', 'total_equity', 'total_assets',
        }
        expected = expected_annual_fields | {'outstanding_shares'}

        self.assertEqual(set(annual.ANNUAL_FIELDS), expected_annual_fields)
        self.assertEqual(len(plans), 7 * len(expected))
        self.assertEqual({plan['source_field'] for plan in plans}, expected)
        self.assertIn('gross_profit', {plan['source_field'] for plan in plans})
        self.assertNotIn('eps', {plan['source_field'] for plan in plans})
        # `total_assets` is loaded so the *reported* figure has a canonical home
        # (decision S1). `operating_pnl` stays out: the workbook template has no
        # Operating Profit row and nothing consumes it (decision S2).
        self.assertIn('total_assets', {plan['source_field'] for plan in plans})
        self.assertNotIn('operating_pnl', {plan['source_field'] for plan in plans})
        self.assertTrue(
            all(plan['unit_code'] == 'SHARES' for plan in plans if plan['source_field'] == 'outstanding_shares')
        )

    def test_annual_source_does_not_require_eps_for_canonical_mapping(self) -> None:
        payload = load_json(RAW_AUTO / 'company_report_annual.json')
        payload['financials'].pop('historical_eps')

        rows, _ = annual.validate_source(payload, 'AUTO')

        self.assertEqual(len(annual.make_fact_plans(rows)), 7 * 12)

    def test_quarterly_validation_keeps_raw_fields_but_plans_only_approved_fields(self) -> None:
        date_index = quarterly.load_date_index(ROOT / 'Data' / 'Raw', 'AUTO')
        records, _, _ = quarterly.load_quarterly_records(ROOT / 'Data' / 'Raw', 'AUTO', date_index)

        plans = quarterly.make_fact_plans(records)

        self.assertEqual(len(records), 26)
        self.assertEqual(len(plans), 26 * len(quarterly.QUARTERLY_FIELDS))
        self.assertEqual({plan['source_field'] for plan in plans}, set(quarterly.QUARTERLY_FIELDS))
        self.assertEqual(
            set(quarterly.QUARTERLY_FIELDS),
            {
                'revenue', 'cost_of_revenue', 'interest_expense_non_operating', 'earnings',
                'operating_cash_flow', 'gross_profit', 'total_current_asset', 'current_liabilities',
                'total_liabilities', 'total_equity',
            },
        )
        self.assertIn('gross_profit', {plan['source_field'] for plan in plans})
        self.assertNotIn('outstanding_shares', {plan['source_field'] for plan in plans})

    def test_auto_date_index_accepts_a_new_official_quarter(self) -> None:
        payload = load_json(RAW_AUTO / quarterly.DATE_INDEX_FILE)
        payload['2026'].append(['2026-09-30', 'q3'])

        date_index = quarterly.parse_date_index(payload, 'AUTO')

        self.assertEqual(len(date_index), 27)
        self.assertEqual(date_index['2026-09-30']['period_label'], '2026-Q3')

    def test_dividend_plans_only_include_annual_total_dps(self) -> None:
        payload = load_json(RAW_AUTO / 'company_report_dividend.json')
        payload['dividend'].pop('dividend_ttm', None)
        payload['dividend'].pop('payout_ratio', None)
        for entry in payload['dividend']['historical_dividends'].values():
            entry.pop('total_yield', None)
        source = dividend.validate_source(payload, 'AUTO')
        plans = dividend.make_fact_plans(source, 'AUTO')

        self.assertEqual(len(plans), 7)
        self.assertTrue(all(plan['fact_type'] == 'ANNUAL_TOTAL' for plan in plans))
        self.assertEqual(
            next(plan for plan in plans if plan['period_year'] == 2025)['amount_per_share'],
            192,
        )

    def test_company_mapping_uses_only_approved_identity_fields(self) -> None:
        payload = load_json(RAW_AUTO / 'company_report_info.json')
        values = identity.source_values(payload, 'AUTO')

        self.assertEqual(values['legal_name'], 'Astra Otoparts Tbk')
        self.assertEqual(values['sector_name'], 'Consumer Cyclicals')
        self.assertEqual(values['subsector_name'], 'Automobiles & Components')
        self.assertEqual(set(values), {
            'provider_identity', 'legal_name', 'company_name', 'provider_symbol',
            'sector_name', 'subsector_name',
            'sector_name', 'subsector_name',
        })


if __name__ == '__main__':
    unittest.main()
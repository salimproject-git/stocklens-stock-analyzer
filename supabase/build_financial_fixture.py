#!/usr/bin/env python3
"""
build_financial_fixture.py
==========================

Phase 4.2 - Builds the offline growth/quality test fixture for ticker AUTO.

Why a fixture
-------------
The Phase 4.2 growth and quality layers must be verifiable **without** network
access and without a live database, so their behaviour cannot change between CI
runs. This script dumps the canonical ``financial_periods`` and
``financial_facts`` rows for one instrument into
``tests/fixtures/{ticker}_financials.json`` together with the workbook values
that the Phase 4 blueprint records for AUTO.

The dump is a faithful projection of canonical data: it selects the columns the
calculation layer reads and does not transform any value. Amounts stay raw IDR,
``EPS`` stays IDR per share and ``OUTSTANDING_SHARES`` stays a raw share count.

Usage
-----
    python supabase/build_financial_fixture.py AUTO
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

#: Fixture directory, relative to the repository root.
FIXTURE_DIR = Path(__file__).resolve().parent.parent / 'tests' / 'fixtures'

#: Workbook values recorded in the Phase 4 blueprint for AUTO, used as the
#: offline expectations. Every one of these is reproduced exactly by the engine.
EXPECTED_ANNUAL: dict[str, str] = {
    'GROWTH_REVENUE_CAGR_LONG': '0.04320553666520399',
    'GROWTH_REVENUE_CAGR_SHORT': '0.10895962318518992',
    'GROWTH_REVENUE_YOY': '0.043676416687415065',
    'GROWTH_REVENUE_COV': '0.15781626002544882',
    'GROWTH_EPS_CAGR_LONG': '0.19967136094934035',
    'GROWTH_CURRENT_ASSET_YOY': '0.12272273788915',
    'GROWTH_ASSET_GROWTH_GAP': '-0.07904632120173494',
    'QUALITY_NWC_TO_REVENUE': '0.2738083026411009',
    'QUALITY_NWC_INTENSITY_CHANGE': '0.043010329117029594',
    'QUALITY_REVENUE_MOMENTUM': '1',
}

#: Values the blueprint records but which are expected to differ, with the
#: documented reason. Kept here so each difference stays visible instead of
#: being silently tolerated.
EXPECTED_DIFFERENCES: dict[str, str] = {
    'GROWTH_EPS_CAGR_SHORT': (
        'Workbook MetricsClassification!B14 = 432.55725490196073; engine = '
        '432.55707019803884 (delta 1.847e-4, relative 4.3e-7). Cause is proven, '
        'not guessed: the workbook uses ONE flat share count '
        '(DataInput!C41:I41 = 4819.733 Juta = 4,819,733,000 shares) for every '
        'year, whereas canonical OUTSTANDING_SHARES is period-correct and 2020 '
        'is 4,819,730,941. The 2,059-share difference in the 2020 denominator '
        'is amplified 2,043x because the 2020 EPS base is negative and near '
        'zero (the linear-normalised branch divides by ABS(start) ~ 0.2116). '
        'This is the annual analogue of gap G-SHARES-Q and is documented, not '
        'patched: the engine uses canonical period-correct shares.'
    ),
    'FORENSIC_DEBT_GROWTH_GAP': (
        'Workbook FinancialHealth!B16 = -432.480773116347; engine = '
        '-432.48058841242511. Same root cause as GROWTH_EPS_CAGR_SHORT: B16 is '
        'liabilities_CAGR - EPS_CAGR, so it inherits the 2,059-share '
        'difference in the 2020 EPS base, amplified by the negative base. The '
        'liabilities side matches exactly. The registry also records that the '
        'formula contradicts its own D16 diagnostic text (debt vs EPS, not debt '
        'vs profit).'
    ),
    'FORENSIC_MARGIN_SPIKE': (
        'Workbook FinancialHealth!B17 = -0.10170156076836084; engine = '
        '0.020915320530145704. Cause is proven: Excel row 2019 has blank COGS, '
        'so its 2019 gross margin falls back to 100 percent and the 7-year mean '
        'margin becomes 0.27079. Canonical GROSS_PROFIT for 2019 is '
        '2,188.244 bn over revenue 15,444.775 bn, i.e. a 0.14168 margin, giving '
        'a mean of 0.14819. Latest margin is 0.16911 in both engines. '
        'Blueprint gap G-2019-COGS, documented not fixed.'
    ),
}


def required_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise RuntimeError(f'SUPABASE_CONFIGURATION_MISSING: {name}')
    return value


def _session(url: str, key: str) -> tuple[requests.Session, str]:
    session = requests.Session()
    session.headers.update(
        {
            'apikey': key,
            'Authorization': 'Bearer ' + key,
            'Content-Type': 'application/json',
        }
    )
    return session, url.strip().rstrip('/') + '/rest/v1'


def fetch_instrument(session: requests.Session, rest: str, ticker: str) -> str:
    rows = session.get(
        rest + '/instruments',
        params={'ticker': 'eq.' + ticker, 'select': 'id,ticker,provider_symbol'},
        timeout=60,
    ).json()
    if len(rows) != 1:
        raise RuntimeError(f'INSTRUMENT_NOT_FOUND_OR_NOT_UNIQUE: {ticker}')
    return rows[0]['id']


def _paged(
    session: requests.Session, rest: str, table: str, params: dict[str, str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    page_size = 1000
    while True:
        page = session.get(
            rest + '/' + table,
            params={**params, 'limit': str(page_size), 'offset': str(offset)},
            timeout=120,
        ).json()
        if not isinstance(page, list):
            raise RuntimeError(f'{table}: QUERY_FAILED')
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return rows


def build_fixture(ticker: str) -> dict[str, Any]:
    session, rest = _session(
        required_env('SUPABASE_URL'), required_env('SUPABASE_SERVICE_ROLE_KEY')
    )
    instrument_id = fetch_instrument(session, rest, ticker)

    periods = _paged(
        session,
        rest,
        'financial_periods',
        {
            'instrument_id': 'eq.' + instrument_id,
            'select': 'id,period_type,period_label,period_end,period_basis,'
                      'statement_scope,report_date,available_date',
            'order': 'period_end.asc',
        },
    )
    facts = _paged(
        session,
        rest,
        'financial_facts',
        {
            'select': 'financial_period_id,metric_code,value_numeric,unit_code,'
                      'quality_status,revision_key',
            'order': 'metric_code.asc',
        },
    )
    period_ids = {row['id'] for row in periods}
    facts = [row for row in facts if row['financial_period_id'] in period_ids]

    return {
        'ticker': ticker,
        'source': (
            'public.financial_periods + public.financial_facts '
            '(canonical, unmodified projection)'
        ),
        'unit': {
            'amounts': 'IDR (raw)',
            'EPS': 'IDR per share',
            'OUTSTANDING_SHARES': 'shares (raw count, no x1000)',
        },
        'period_count': len(periods),
        'fact_count': len(facts),
        'expected_annual': EXPECTED_ANNUAL,
        'expected_differences': EXPECTED_DIFFERENCES,
        'periods': periods,
        'facts': facts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Build the Phase 4.2 financial fixture')
    parser.add_argument('ticker', nargs='?', default='AUTO')
    args = parser.parse_args(argv)

    fixture = build_fixture(args.ticker.upper())
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    target = FIXTURE_DIR / f'{args.ticker.lower()}_financials.json'
    target.write_text(
        json.dumps(fixture, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    print(
        f'wrote {target} '
        f'({fixture["period_count"]} periods, {fixture["fact_count"]} facts)'
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())

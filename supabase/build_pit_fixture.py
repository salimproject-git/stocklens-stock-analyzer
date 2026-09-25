#!/usr/bin/env python3
"""
build_pit_fixture.py
====================

Phase 4.1 - Builds the offline PIT test fixture for ticker AUTO.

Why a fixture
-------------
The Layer-1 PIT primitives must be verifiable **without** network access and
without a live database, so their behaviour cannot change between CI runs. This
script dumps the canonical `prices_daily` rows for one instrument into
`Testing/fixtures/{ticker}_prices_daily.json`, together with the expected
year-end prices and the expected 3-month average volume recorded in the Phase 4
blueprint.

The dump is a faithful projection of canonical data: it selects only
`trading_date`, `close_price` and `volume`, and it does not transform any
value. Prices stay IDR per share and volume stays share volume.

Usage
-----
    python supabase/build_pit_fixture.py AUTO
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
FIXTURE_DIR = Path(__file__).resolve().parent.parent / 'Testing' / 'fixtures'

#: Year-end prices verified in the Phase 4 blueprint (section 4.11.4).
#: 2019 is `null` because canonical price history starts 2020-01-02, so
#: `year_end_price(2019)` must return `None` rather than a substituted value.
EXPECTED_YEAR_END_PRICES: dict[str, str | None] = {
    '2019': None,
    '2020': '1115',
    '2021': '1155',
    '2022': '1460',
    '2023': '2360',
    '2024': '2300',
    '2025': '2690',
}

#: Expected `avg_volume_3m('2026-06-30')` from the Phase 4 blueprint.
EXPECTED_AVG_VOLUME_3M_AS_OF = '2026-06-30'
EXPECTED_AVG_VOLUME_3M = '2449150.8474576273'

#: Expected latest close and its trading date.
EXPECTED_LATEST_CLOSE = '3340'
EXPECTED_LATEST_TRADING_DATE = '2026-09-24'


def required_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise RuntimeError(f'SUPABASE_CONFIGURATION_MISSING: {name}')
    return value


def fetch_prices(url: str, key: str, ticker: str) -> list[dict[str, Any]]:
    """Fetch one instrument's daily prices from the canonical table."""
    session = requests.Session()
    session.headers.update(
        {
            'apikey': key,
            'Authorization': 'Bearer ' + key,
            'Content-Type': 'application/json',
        }
    )
    rest = url.strip().rstrip('/') + '/rest/v1'

    instruments = session.get(
        rest + '/instruments',
        params={'ticker': 'eq.' + ticker, 'select': 'id,ticker,provider_symbol'},
        timeout=60,
    ).json()
    if len(instruments) != 1:
        raise RuntimeError(f'INSTRUMENT_NOT_FOUND_OR_NOT_UNIQUE: {ticker}')
    instrument_id = instruments[0]['id']

    rows: list[dict[str, Any]] = []
    offset = 0
    page_size = 1000
    while True:
        page = session.get(
            rest + '/prices_daily',
            params={
                'instrument_id': 'eq.' + instrument_id,
                'select': 'trading_date,close_price,volume',
                'order': 'trading_date.asc',
                'limit': str(page_size),
                'offset': str(offset),
            },
            timeout=120,
        ).json()
        if not isinstance(page, list):
            raise RuntimeError('PRICES_QUERY_FAILED')
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size

    return rows


def build_fixture(ticker: str) -> dict[str, Any]:
    rows = fetch_prices(
        required_env('SUPABASE_URL'), required_env('SUPABASE_SERVICE_ROLE_KEY'), ticker
    )
    return {
        'ticker': ticker,
        'source': 'public.prices_daily (canonical, unmodified projection)',
        'unit': {'close_price': 'IDR per share', 'volume': 'shares'},
        'row_count': len(rows),
        'expected': {
            'year_end_prices': EXPECTED_YEAR_END_PRICES,
            'avg_volume_3m_as_of': EXPECTED_AVG_VOLUME_3M_AS_OF,
            'avg_volume_3m': EXPECTED_AVG_VOLUME_3M,
            'latest_close': EXPECTED_LATEST_CLOSE,
            'latest_trading_date': EXPECTED_LATEST_TRADING_DATE,
        },
        'prices': rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Build the Phase 4.1 PIT fixture')
    parser.add_argument('ticker', nargs='?', default='AUTO')
    args = parser.parse_args(argv)

    fixture = build_fixture(args.ticker.upper())
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    target = FIXTURE_DIR / f'{args.ticker.lower()}_prices_daily.json'
    target.write_text(json.dumps(fixture, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(f'wrote {target} ({fixture["row_count"]} rows)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

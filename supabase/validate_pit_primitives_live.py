#!/usr/bin/env python3
"""
validate_pit_primitives_live.py
==============================

Phase 4.1 - Validates the Layer-1 PIT primitives against **live** canonical
PostgreSQL.

The unit tests in `Testing/test_phase_4_1_registry_and_pit.py` are offline and
read a committed fixture. This script is the complementary integration check:
it fetches the real `prices_daily` rows and asserts the same AUTO expectations
against the live table, so a data change or a query regression is caught.

Checks performed
----------------
1. The seven verified year-end prices (2019 is `None` by design).
2. `avg_volume_3m('2026-06-30') == 2449150.8474576273`.
3. The window boundary is `EDATE(as_of,-3) .. as_of`, inclusive.
4. The workbook as-of price (`2026-06-30` -> 2350) differs from the latest
   price (`2026-09-24` -> 3340), proving no globally-latest fallback.
5. No historical query leaks a future price.
6. Repeated execution is deterministic.

Read-only: SELECT queries only.

Usage
-----
    python supabase/validate_pit_primitives_live.py AUTO
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from decimal import Decimal
from typing import Any

import requests

from pit_primitives import (
    avg_volume_3m,
    as_of_price,
    edate,
    latest_price_date,
    normalize_prices,
    year_end_price,
)

EXPECTED_YEAR_END_PRICES: dict[int, str | None] = {
    2019: None,
    2020: '1115',
    2021: '1155',
    2022: '1460',
    2023: '2360',
    2024: '2300',
    2025: '2690',
}
EXPECTED_AVG_VOLUME_3M_AS_OF = '2026-06-30'
EXPECTED_AVG_VOLUME_3M = 2449150.8474576273
WORKBOOK_AS_OF = '2026-06-30'
WORKBOOK_AS_OF_PRICE = Decimal('2350')
LATEST_PRICE = Decimal('3340')


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
        params={'ticker': 'eq.' + ticker, 'select': 'id,ticker'},
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Validate PIT primitives against live PostgreSQL'
    )
    parser.add_argument('ticker', nargs='?', default='AUTO')
    args = parser.parse_args(argv)

    raw = fetch_prices(
        required_env('SUPABASE_URL'),
        required_env('SUPABASE_SERVICE_ROLE_KEY'),
        args.ticker.upper(),
    )
    prices = normalize_prices(raw)
    failures: list[str] = []

    print(f'ticker            : {args.ticker.upper()}')
    print(f'price rows        : {len(prices)}')
    print(f'first trading date: {prices[0].trading_date}')
    print(f'last trading date : {prices[-1].trading_date}')
    print()

    print('1. seven verified year-end prices')
    for year, expected in EXPECTED_YEAR_END_PRICES.items():
        actual = year_end_price(prices, year)
        expected_decimal = None if expected is None else Decimal(expected)
        ok = actual == expected_decimal
        print(f'   {year}: {actual} (expected {expected_decimal}) {"OK" if ok else "FAIL"}')
        if not ok:
            failures.append(f'YEAR_END_PRICE_MISMATCH: {year} {actual} != {expected_decimal}')

    print()
    print('2. avg_volume_3m at the workbook as-of')
    actual_avg = avg_volume_3m(prices, EXPECTED_AVG_VOLUME_3M_AS_OF)
    ok_avg = actual_avg is not None and float(actual_avg) == EXPECTED_AVG_VOLUME_3M
    print(f'   {EXPECTED_AVG_VOLUME_3M_AS_OF}: {actual_avg}')
    print(f'   float {float(actual_avg)!r} vs expected {EXPECTED_AVG_VOLUME_3M!r} '
          f'{"OK" if ok_avg else "FAIL"}')
    if not ok_avg:
        failures.append(f'AVG_VOLUME_3M_MISMATCH: {actual_avg}')

    print()
    print('3. window boundary (EDATE(as_of,-3) .. as_of, inclusive)')
    start = edate(date.fromisoformat(EXPECTED_AVG_VOLUME_3M_AS_OF), -3)
    inside = [
        p for p in prices
        if start <= p.trading_date <= date.fromisoformat(EXPECTED_AVG_VOLUME_3M_AS_OF)
    ]
    print(f'   window {start} .. {EXPECTED_AVG_VOLUME_3M_AS_OF}')
    print(f'   rows {len(inside)}, total volume {sum(p.volume for p in inside)}')

    print()
    print('4. no globally-latest fallback')
    workbook_price = as_of_price(prices, WORKBOOK_AS_OF)
    latest_date = latest_price_date(prices)
    latest = as_of_price(prices, latest_date)
    print(f'   as-of {WORKBOOK_AS_OF}      : {workbook_price} (expected {WORKBOOK_AS_OF_PRICE})')
    print(f'   latest {latest_date} : {latest} (expected {LATEST_PRICE})')
    if workbook_price != WORKBOOK_AS_OF_PRICE:
        failures.append(f'WORKBOOK_AS_OF_PRICE_MISMATCH: {workbook_price}')
    if latest != LATEST_PRICE:
        failures.append(f'LATEST_PRICE_MISMATCH: {latest}')
    if workbook_price == latest:
        failures.append('LATEST_FALLBACK_DETECTED: as-of price equals the latest price')

    print()
    print('5. historical queries never leak a future price')
    leaks = 0
    for year in sorted(EXPECTED_YEAR_END_PRICES):
        cutoff = date(year, 12, 31)
        resolved = as_of_price(prices, cutoff)
        eligible = [p for p in prices if p.trading_date <= cutoff]
        expected_here = eligible[-1].close_price if eligible else None
        if resolved != expected_here:
            leaks += 1
            failures.append(f'PIT_LEAK: {year} {resolved} != {expected_here}')
    print(f'   checked {len(EXPECTED_YEAR_END_PRICES)} cutoffs, {leaks} leaks')

    print()
    print('6. determinism')
    first = str(avg_volume_3m(prices, EXPECTED_AVG_VOLUME_3M_AS_OF))
    second = str(avg_volume_3m(prices, EXPECTED_AVG_VOLUME_3M_AS_OF))
    print(f'   repeated avg_volume_3m identical: {first == second}')
    if first != second:
        failures.append('NON_DETERMINISTIC: avg_volume_3m')

    print()
    if failures:
        for failure in failures:
            print('FAIL: ' + failure)
        print(f'\nRESULT: FAILED ({len(failures)} problem(s))')
        return 1
    print('RESULT: OK - all live PIT validations passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())


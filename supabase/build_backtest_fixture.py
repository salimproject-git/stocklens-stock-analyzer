#!/usr/bin/env python3
"""
build_backtest_fixture.py
=========================

Fase 1 - Membangun fixture backtest offline per ticker.

Kenapa fixture terpisah
-----------------------
`tests/fixtures/auto_prices_daily.json` dibangun `build_pit_fixture.py` untuk
Phase 4.1 dan **hanya** memuat `trading_date`, `close_price`, `volume`. Fixture
itu dikunci oleh `tests/test_phase_4_1_registry_and_pit.py` (row count dan nilai
ekspektasi), jadi kolom `high_price` / `low_price` tidak ditambahkan ke sana:
mengubah fixture beku untuk kebutuhan fase lain adalah cara drift dimulai.

Fixture backtest karena itu berdiri sendiri dan memuat apa yang dibutuhkan
rumus Tahap B: periode annual + kuartal, dan harga harian lengkap dengan
`high_price` / `low_price` **apa adanya dari database**. Nilai nol tidak
dibersihkan di sini: substitusi `High = 0 ? Close : High` adalah aturan engine
yang justru harus diuji, bukan sesuatu yang boleh disembunyikan oleh fixture.

Ticker yang wajib dibangun
--------------------------
* ``AUTO`` - nol baris `high_price = 0`; dipakai untuk parity workbook.
* ``GEMA`` - 195 baris `high_price = 0`; tanpa ticker ini bug substitusi tidak
  akan tertangkap (lihat `docs/BACKTEST_ARCHITECTURE.md` bagian 1).

Usage
-----
    python supabase/build_backtest_fixture.py AUTO GEMA
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

#: Baris `high_price = 0` per ticker, terverifikasi di `docs/BACKTEST_ARCHITECTURE.md`.
#: Disimpan di fixture supaya uji bisa menolak fixture yang salah ticker.
EXPECTED_ZERO_HIGH_ROWS = {
    'AUTO': 0,
    'GEMA': 195,
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


def _paged(
    session: requests.Session, rest: str, table: str, params: dict[str, str]
) -> list[dict[str, Any]]:
    """Ambil seluruh halaman `table` tanpa transformasi nilai."""
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


def fetch_instrument(session: requests.Session, rest: str, ticker: str) -> dict[str, Any]:
    rows = session.get(
        rest + '/instruments',
        params={
            'ticker': 'eq.' + ticker,
            'select': 'id,ticker,company_name,sector_name',
        },
        timeout=60,
    ).json()
    if len(rows) != 1:
        raise RuntimeError(f'INSTRUMENT_NOT_FOUND_OR_NOT_UNIQUE: {ticker}')
    return rows[0]


def build_fixture(ticker: str, *, include_prices: bool = True) -> dict[str, Any]:
    session, rest = _session(
        required_env('SUPABASE_URL'), required_env('SUPABASE_SERVICE_ROLE_KEY')
    )
    instrument = fetch_instrument(session, rest, ticker)
    instrument_id = str(instrument['id'])

    periods = _paged(
        session,
        rest,
        'financial_periods',
        {
            'instrument_id': 'eq.' + instrument_id,
            'select': 'id,instrument_id,period_type,period_label,period_end,available_date',
            'order': 'period_end.asc',
        },
    )
    prices: list[dict[str, Any]] = []
    if include_prices:
        prices = _paged(
            session,
            rest,
            'prices_daily',
            {
                'instrument_id': 'eq.' + instrument_id,
                'select': 'trading_date,close_price,high_price,low_price',
                'order': 'trading_date.asc',
            },
        )

    zero_high = sum(1 for row in prices if row.get('high_price') == 0)
    expected_zero = EXPECTED_ZERO_HIGH_ROWS.get(ticker)
    if include_prices and expected_zero is not None and zero_high != expected_zero:
        # Fixture yang tidak lagi memuat baris nol akan membuat uji substitusi
        # lulus tanpa benar-benar menguji apa pun. Kegagalan seperti itu tidak
        # terlihat, jadi diperlakukan sebagai error.
        #
        # Pemeriksaan ini hanya berlaku bila harga memang diambil: dengan
        # `--periods-only` tidak ada harga, sehingga `zero_high` selalu 0 dan
        # membandingkannya akan gagal untuk alasan yang salah.
        raise RuntimeError(
            f'ZERO_HIGH_ROW_COUNT_CHANGED: {ticker}: expected {expected_zero}, found {zero_high}'
        )

    return {
        'ticker': ticker,
        'instrument_id': instrument_id,
        'sector_name': instrument.get('sector_name'),
        'source': (
            'public.financial_periods + public.prices_daily '
            '(canonical, unmodified projection)'
        ),
        'unit': {
            'close_price': 'IDR per share',
            'high_price': 'IDR per share',
            'low_price': 'IDR per share',
        },
        'period_count': len(periods),
        'price_count': len(prices),
        'zero_high_rows': zero_high,
        'periods': periods,
        'prices': prices,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Build the Fase 1 backtest fixtures')
    parser.add_argument(
        'tickers',
        nargs='*',
        default=['AUTO', 'GEMA'],
        help='Tickers to dump. DSSA/GOLD/WIFI are case-count only by default.',
    )
    parser.add_argument(
        '--periods-only',
        action='store_true',
        help=(
            'Skip prices. Used for the case-count fixtures: the case list only '
            'needs financial_periods, and a price dump for those tickers would '
            'add megabytes to the repository for no test value.'
        ),
    )
    args = parser.parse_args(argv)

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for raw in args.tickers:
        ticker = raw.upper().replace('.JK', '')
        fixture = build_fixture(ticker, include_prices=not args.periods_only)
        suffix = '_periods' if args.periods_only else ''
        target = FIXTURE_DIR / f'{ticker.lower()}_backtest{suffix}.json'
        target.write_text(json.dumps(fixture, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        print(
            f'wrote {target} '
            f'({fixture["period_count"]} periods, {fixture["price_count"]} prices, '
            f'{fixture["zero_high_rows"]} zero-high rows)'
        )
    return 0


if __name__ == '__main__':
    sys.exit(main())

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import requests

from raw_storage_source import ProvenanceIndex, RawStorageSource

DEFAULT_RAW_ROOT = Path(r'D:\Stock Analyzer\Data\Raw')
BUCKET = 'stocklens_raw'
DIVIDEND_FILE = 'company_report_dividend.json'
STORAGE_CATEGORY = 'dividend'
SOURCE_LABEL = 'CURRENT'
EXPECTED_YEARS = tuple(range(2020, 2027))


class LoaderError(RuntimeError):
    pass


def required_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise LoaderError(f'Environment variable belum di-set: {name}')
    return value


def is_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def load_source(raw_root: Path, ticker: str) -> tuple[dict[str, Any], Path, str]:
    """DEBUG/VERIFICATION ONLY. Local disk is not the pipeline source."""
    path = raw_root / ticker / DIVIDEND_FILE
    if not path.is_file():
        raise LoaderError(f'DIVIDEND_SOURCE_NOT_FOUND: {path}')
    content = path.read_bytes()
    try:
        payload = json.loads(content.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LoaderError(f'DIVIDEND_SOURCE_INVALID_JSON: {path}: {error}') from error
    if not isinstance(payload, dict):
        raise LoaderError('DIVIDEND_SOURCE_INVALID_SHAPE: expected an object')
    return payload, path, hashlib.sha256(content).hexdigest()


def load_source_from_storage(ticker: str) -> tuple[dict[str, Any], str, str]:
    """PRIMARY source: Supabase Storage. Returns (payload, storage_path, sha256)."""
    source = RawStorageSource(ticker)
    storage_path = source.storage_path(STORAGE_CATEGORY, DIVIDEND_FILE)
    content = source.read(STORAGE_CATEGORY, DIVIDEND_FILE)
    try:
        payload = json.loads(content.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LoaderError(f'DIVIDEND_SOURCE_INVALID_JSON: {BUCKET}/{storage_path}: {error}') from error
    if not isinstance(payload, dict):
        raise LoaderError('DIVIDEND_SOURCE_INVALID_SHAPE: expected an object')
    return payload, storage_path, hashlib.sha256(content).hexdigest()


def validate_source(payload: dict[str, Any], ticker: str) -> dict[str, Any]:
    symbol = payload.get('symbol')
    if not isinstance(symbol, str) or symbol.upper() != f'{ticker}.JK':
        raise LoaderError(f'DIVIDEND_SYMBOL_CONFLICT: {symbol!r}')
    company_name = payload.get('company_name')
    if not isinstance(company_name, str) or not company_name.strip():
        raise LoaderError('DIVIDEND_SOURCE_MISSING: company_name')
    dividend = payload.get('dividend')
    if not isinstance(dividend, dict):
        raise LoaderError('DIVIDEND_SOURCE_INVALID_SHAPE: dividend must be an object')
    historical = dividend.get('historical_dividends')
    if not isinstance(historical, dict):
        raise LoaderError('DIVIDEND_SOURCE_INVALID_SHAPE: historical_dividends must be an object')
    years = tuple(sorted(int(year) for year in historical if str(year).isdigit()))
    if ticker == 'AUTO' and years != EXPECTED_YEARS:
        raise LoaderError(f'DIVIDEND_YEAR_RANGE: expected {EXPECTED_YEARS}, got {years}')
    if len(years) != len(historical) or len(set(years)) != len(years):
        raise LoaderError('DIVIDEND_YEAR_KEYS_INVALID')
    for year in EXPECTED_YEARS if ticker == 'AUTO' else years:
        entry = historical.get(str(year))
        if not isinstance(entry, dict):
            raise LoaderError(f'DIVIDEND_YEAR_INVALID: {year}')
        for field in ('total_yield', 'total_dividend'):
            if field not in entry:
                raise LoaderError(f'DIVIDEND_FIELD_MISSING: {year}.{field}')
            value = entry[field]
            if value is not None and not is_number(value):
                raise LoaderError(f'DIVIDEND_FIELD_INVALID: {year}.{field}')
    for field in ('dividend_ttm', 'payout_ratio'):
        if field not in dividend:
            raise LoaderError(f'DIVIDEND_AGGREGATE_MISSING: {field}')
        value = dividend[field]
        if value is not None and not is_number(value):
            raise LoaderError(f'DIVIDEND_AGGREGATE_INVALID: {field}')
    return dividend


def make_fact_plans(dividend: dict[str, Any], ticker: str) -> list[dict[str, Any]]:
    historical = dividend['historical_dividends']
    plans: list[dict[str, Any]] = []
    years = EXPECTED_YEARS if ticker == 'AUTO' else tuple(sorted(int(year) for year in historical))
    for year in years:
        entry = historical[str(year)]
        plans.append({
            'fact_type': 'ANNUAL_TOTAL',
            'period_year': year,
            'event_date': None,
            'amount_per_share': entry['total_dividend'],
            'yield_ratio': None,
            'currency_code': 'IDR',
            'source_label': SOURCE_LABEL,
            'source_payload_id': None,
            'source_field': f'historical_dividends.{year}.total_dividend',
        })
        plans.append({
            'fact_type': 'YIELD',
            'period_year': year,
            'event_date': None,
            'amount_per_share': None,
            'yield_ratio': entry['total_yield'],
            'currency_code': 'IDR',
            'source_label': SOURCE_LABEL,
            'source_payload_id': None,
            'source_field': f'historical_dividends.{year}.total_yield',
        })
    plans.extend((
        {
            'fact_type': 'TTM', 'period_year': None, 'event_date': None,
            'amount_per_share': dividend['dividend_ttm'], 'yield_ratio': None,
            'currency_code': 'IDR', 'source_label': SOURCE_LABEL,
            'source_payload_id': None, 'source_field': 'dividend.dividend_ttm',
        },
        {
            'fact_type': 'PAYOUT_RATIO', 'period_year': None, 'event_date': None,
            'amount_per_share': None, 'yield_ratio': dividend['payout_ratio'],
            'currency_code': 'IDR', 'source_label': SOURCE_LABEL,
            'source_payload_id': None, 'source_field': 'dividend.payout_ratio',
        },
    ))
    return plans


class Supabase:
    def __init__(self, url: str, key: str):
        self.base_url = url.rstrip('/') + '/rest/v1'
        self.session = requests.Session()
        self.session.headers.update({'apikey': key, 'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})

    def get_all(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        page_size = 1000
        while True:
            page_params = dict(params)
            page_params['limit'] = str(page_size)
            page_params['offset'] = str(offset)
            response = self.session.get(self.base_url + '/' + table, params=page_params, timeout=60)
            if not response.ok:
                raise LoaderError(f'Supabase GET {table} failed ({response.status_code}): {response.text[:1000]}')
            page = response.json()
            if not isinstance(page, list):
                raise LoaderError(f'Supabase GET {table} returned a non-list response')
            rows.extend(page)
            if len(page) < page_size:
                return rows
            offset += page_size

    def insert_rows(self, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        response = self.session.post(self.base_url + '/' + table, json=rows, headers={'Prefer': 'return=minimal'}, timeout=120)
        if not response.ok:
            raise LoaderError(f'Supabase INSERT {table} failed ({response.status_code}): {response.text[:1000]}')


def verify_provenance(db: Supabase, run_id: str, ticker: str, checksum: str) -> str:
    storage_path = f'sectors/{ticker}/{STORAGE_CATEGORY}/{DIVIDEND_FILE}'
    rows = db.get_all('ingestion_files', {'ingestion_run_id': 'eq.' + run_id, 'storage_bucket': 'eq.' + BUCKET, 'storage_path': 'eq.' + storage_path, 'select': 'id,checksum_sha256,status'})
    if not rows:
        raise LoaderError(f'PROVENANCE_NOT_FOUND: {storage_path} for run {run_id}')
    if len(rows) != 1:
        raise LoaderError(f'PROVENANCE_NOT_UNIQUE: {storage_path} returned {len(rows)} rows')
    row = rows[0]
    if row.get('status') not in {'UPLOADED', 'SKIPPED'}:
        raise LoaderError('PROVENANCE_NOT_READY: ' + storage_path)
    if row.get('checksum_sha256') != checksum:
        raise LoaderError('PROVENANCE_CHECKSUM_CONFLICT: ' + storage_path)
    return row['id']


def resolve_instrument(db: Supabase, ticker: str) -> str:
    rows = db.get_all('instruments', {'exchange_code': 'eq.IDX', 'ticker': 'eq.' + ticker, 'select': 'id,exchange_code,ticker'})
    if len(rows) == 0:
        raise LoaderError(f'INSTRUMENT_NOT_FOUND: IDX/{ticker}')
    if len(rows) > 1:
        raise LoaderError(f'INSTRUMENT_NOT_UNIQUE: IDX/{ticker} returned {len(rows)} rows')
    return rows[0]['id']


def values_equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except (InvalidOperation, ValueError):
        return left == right


def fact_matches(existing: dict[str, Any], intended: dict[str, Any]) -> bool:
    fields = ('fact_type', 'period_year', 'event_date', 'amount_per_share', 'yield_ratio', 'currency_code', 'source_label', 'source_payload_id')
    for field in fields:
        if field in ('amount_per_share', 'yield_ratio'):
            if not values_equal(existing.get(field), intended[field]):
                return False
        elif existing.get(field) != intended[field]:
            return False
    return True


def fetch_existing_fact(db: Supabase, instrument_id: str, plan: dict[str, Any]) -> list[dict[str, Any]]:
    period_filter = 'is.null' if plan['period_year'] is None else 'eq.' + str(plan['period_year'])
    return db.get_all('dividend_facts', {
        'instrument_id': 'eq.' + instrument_id,
        'fact_type': 'eq.' + plan['fact_type'],
        'period_year': period_filter,
        'source_label': 'eq.' + plan['source_label'],
        'select': 'id,instrument_id,fact_type,period_year,event_date,amount_per_share,yield_ratio,currency_code,source_label,source_payload_id',
    })


def preflight(db: Supabase, instrument_id: str, plans: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    inserts: list[dict[str, Any]] = []
    skips: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for plan in plans:
        existing = fetch_existing_fact(db, instrument_id, plan)
        if len(existing) > 1:
            conflicts.append({'plan': plan, 'existing': existing, 'reason': 'NON_UNIQUE_EXISTING'})
        elif not existing:
            inserts.append(plan)
        elif fact_matches(existing[0], plan):
            skips.append(plan)
        else:
            conflicts.append({'plan': plan, 'existing': existing[0], 'reason': 'VALUE_CONFLICT'})
    return inserts, skips, conflicts


def main() -> None:
    parser = argparse.ArgumentParser(description='Load dividend JSON (Storage-first) into public.dividend_facts')
    parser.add_argument('ticker')
    parser.add_argument('--ingestion-run-id', help='Optional raw-storage ingestion_runs.id cross-check')
    parser.add_argument('--source', choices=['storage', 'local'], default='storage',
                        help='Pipeline source. Default storage (local is debug-only).')
    parser.add_argument('--raw-root', default=str(DEFAULT_RAW_ROOT), help='Debug-only local root')
    args = parser.parse_args()
    ticker = args.ticker.upper().replace('.JK', '')

    if args.source == 'storage':
        payload, storage_path, checksum = load_source_from_storage(ticker)
        source_label = f'{BUCKET}/{storage_path}'
    else:
        payload, local_path, checksum = load_source(Path(args.raw_root), ticker)
        storage_path = f'sectors/{ticker}/{STORAGE_CATEGORY}/{DIVIDEND_FILE}'
        source_label = str(local_path)

    dividend = validate_source(payload, ticker)
    plans = make_fact_plans(dividend, ticker)
    expected_count = len(EXPECTED_YEARS) * 2 + 2 if ticker == 'AUTO' else len(plans)
    if len(plans) != expected_count:
        raise LoaderError(f'CANONICAL_FACT_COUNT: expected {expected_count}, got {len(plans)}')
    db = Supabase(required_env('SUPABASE_URL'), required_env('SUPABASE_SERVICE_ROLE_KEY'))
    provenance_id = ProvenanceIndex(
        required_env('SUPABASE_URL'),
        required_env('SUPABASE_SERVICE_ROLE_KEY'),
    ).resolve(storage_path, checksum)
    if args.ingestion_run_id:
        verify_provenance(db, args.ingestion_run_id, ticker, checksum)
    instrument_id = resolve_instrument(db, ticker)
    inserts, skips, conflicts = preflight(db, instrument_id, plans)
    if conflicts:
        for conflict in conflicts[:20]:
            print(str(conflict), file=sys.stderr)
        raise LoaderError(f'CONFLICT: {len(conflicts)} existing rows differ; no rows were written')
    rows = [
        {
            'instrument_id': instrument_id,
            **{field: plan[field] for field in (
                'fact_type', 'period_year', 'event_date', 'amount_per_share',
                'yield_ratio', 'currency_code', 'source_label', 'source_payload_id',
            )},
        }
        for plan in inserts
    ]
    db.insert_rows('dividend_facts', rows)
    verified: list[dict[str, Any]] = []
    for plan in plans:
        existing = fetch_existing_fact(db, instrument_id, plan)
        if len(existing) != 1 or not fact_matches(existing[0], plan):
            raise LoaderError('FINAL_VERIFICATION_FAILED: ' + plan['source_field'])
        verified.append(existing[0])
    print('ticker=' + ticker)
    print('source=' + args.source)
    print('raw_source=' + source_label)
    print('instrument_id=' + instrument_id)
    print('identity_ingestion_file_id=' + provenance_id)
    print('checksum_sha256=' + checksum)
    print('fact_count=' + str(len(plans)))
    print('inserted_fact_count=' + str(len(inserts)))
    print('skipped_fact_count=' + str(len(skips)))
    print('conflict_count=0')
    print('annual_total_count=' + str(sum(plan['fact_type'] == 'ANNUAL_TOTAL' for plan in plans)))
    print('yield_count=' + str(sum(plan['fact_type'] == 'YIELD' for plan in plans)))
    print('ttm_count=' + str(sum(plan['fact_type'] == 'TTM' for plan in plans)))
    print('payout_ratio_count=' + str(sum(plan['fact_type'] == 'PAYOUT_RATIO' for plan in plans)))
    print('verified_file_count=1')
    print('checksum_failure_count=0')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'FAILED: {error}', file=sys.stderr)
        raise SystemExit(1) from error

# Load local daily raw JSON into canonical prices_daily.
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import requests

DEFAULT_RAW_ROOT = Path(r'D:\Stock Analyzer\Data\Raw')
BUCKET = 'stocklens_raw'
EXPECTED_FIELDS = ('open', 'high', 'low', 'close', 'volume', 'market_cap')

def required_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise RuntimeError(f'Environment variable belum di-set: {name}')
    return value

def is_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)

def parse_trading_date(value: Any, path: Path, index: int) -> str:
    if not isinstance(value, str):
        raise RuntimeError(f'INVALID_RECORD: {path} record {index} date must be a string')
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise RuntimeError(f'INVALID_RECORD: {path} record {index} invalid date {value}') from error
    return value

def normalized_record(record: Any, path: Path, index: int, ticker: str) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise RuntimeError(f'INVALID_RECORD: {path} record {index} is not an object')
    symbol = record.get('symbol')
    if symbol is not None and str(symbol).upper() != ticker + '.JK':
        raise RuntimeError(f'SOURCE_CONFLICT: {path} record {index} symbol {symbol} does not match {ticker}.JK')
    row = {'date': parse_trading_date(record.get('date'), path, index)}
    for field in EXPECTED_FIELDS:
        if field not in record:
            raise RuntimeError(f'INVALID_RECORD: {path} record {index} missing {field}')
        value = record.get(field)
        if value is not None and not is_number(value):
            raise RuntimeError(f'INVALID_RECORD: {path} record {index} {field} must be numeric or null')
        row[field] = value
    return row

def discover_daily(raw_root: Path, ticker: str) -> tuple[dict[str, dict[str, Any]], int]:
    folder = raw_root / ticker / 'daily'
    files = sorted(folder.glob('*.json')) if folder.is_dir() else []
    if not files:
        raise RuntimeError(f'No daily JSON files found under: {folder}')
    dates: dict[str, dict[str, Any]] = {}
    total_records = 0
    for path in files:
        payload = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(payload, list):
            raise RuntimeError(f'INVALID_FILE: {path} must contain a top-level list')
        for index, record in enumerate(payload, start=1):
            total_records += 1
            row = normalized_record(record, path, index, ticker)
            previous = dates.get(row['date'])
            if previous is None:
                row['_source_file'] = path.name
                dates[row['date']] = row
            elif any(previous[field] != row[field] for field in ('date',) + EXPECTED_FIELDS):
                raise RuntimeError(f'SOURCE_CONFLICT: duplicate date {row[date]} has different values')
    return dates, len(files)

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
                raise RuntimeError(f'Supabase GET {table} failed ({response.status_code}): {response.text[:1000]}')
            page = response.json()
            rows.extend(page)
            if len(page) < page_size:
                return rows
            offset += page_size

    def insert_many(self, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        response = self.session.post(
            self.base_url + '/' + table,
            json=rows,
            headers={'Prefer': 'return=minimal'},
            timeout=120,
        )
        if not response.ok:
            raise RuntimeError(f'Supabase INSERT {table} failed ({response.status_code}): {response.text[:1000]}')

def resolve_instrument(db: Supabase, ticker: str) -> str:
    rows = db.get_all('instruments', {'exchange_code': 'eq.IDX', 'ticker': 'eq.' + ticker, 'select': 'id,exchange_code,ticker'})
    if len(rows) == 0:
        raise RuntimeError(f'INSTRUMENT_NOT_FOUND: IDX/{ticker}')
    if len(rows) > 1:
        raise RuntimeError(f'INSTRUMENT_NOT_UNIQUE: IDX/{ticker} returned {len(rows)} rows')
    return rows[0]['id']

def resolve_provenance(db: Supabase, run_id: str, ticker: str, files: list[Path]) -> dict[str, str]:
    rows = db.get_all('ingestion_files', {'ingestion_run_id': 'eq.' + run_id, 'storage_bucket': 'eq.' + BUCKET, 'select': 'id,storage_path,status,checksum_sha256'})
    expected = {f'sectors/{ticker}/daily/{path.name}' for path in files}
    actual = {row['storage_path']: row for row in rows}
    missing = sorted(expected - actual.keys())
    if missing:
        raise RuntimeError('PROVENANCE_NOT_FOUND: ' + ', '.join(missing[:5]))
    invalid = [path for path in expected if actual[path]['status'] not in {'UPLOADED', 'SKIPPED'}]
    if invalid:
        raise RuntimeError('PROVENANCE_NOT_READY: ' + ', '.join(invalid[:5]))
    provenance: dict[str, str] = {}
    for local_path in files:
        storage_path = f'sectors/{ticker}/daily/{local_path.name}'
        local_checksum = hashlib.sha256(local_path.read_bytes()).hexdigest()
        if actual[storage_path]['checksum_sha256'] != local_checksum:
            raise RuntimeError(f'PROVENANCE_CHECKSUM_CONFLICT: {storage_path}')
        provenance[local_path.name] = actual[storage_path]['id']
    return provenance

def same_value(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return left == right

def compare_price(raw: dict[str, Any], existing: dict[str, Any]) -> bool:
    return all(same_value(raw[field], existing[column]) for field, column in {
        'open': 'open_price', 'high': 'high_price', 'low': 'low_price',
        'close': 'close_price', 'volume': 'volume', 'market_cap': 'market_cap',
    }.items())

def create_canonical_row(instrument_id: str, raw: dict[str, Any], provenance_id: str) -> dict[str, Any]:
    return {
        'instrument_id': instrument_id,
        'trading_date': raw['date'],
        'open_price': raw['open'],
        'high_price': raw['high'],
        'low_price': raw['low'],
        'close_price': raw['close'],
        'volume': raw['volume'],
        'market_cap': raw['market_cap'],
        'currency_code': 'IDR',
        'source_ingestion_file_id': provenance_id,
    }

def main() -> None:
    parser = argparse.ArgumentParser(description='Load local daily JSON into public.prices_daily')
    parser.add_argument('ticker')
    parser.add_argument('--ingestion-run-id', required=True, help='Raw-storage ingestion_runs.id')
    parser.add_argument('--raw-root', default=str(DEFAULT_RAW_ROOT))
    args = parser.parse_args()
    ticker = args.ticker.upper().replace('.JK', '')
    raw_by_date, file_count = discover_daily(Path(args.raw_root), ticker)
    db = Supabase(required_env('SUPABASE_URL'), required_env('SUPABASE_SERVICE_ROLE_KEY'))
    instrument_id = resolve_instrument(db, ticker)
    file_names = sorted((Path(args.raw_root) / ticker / 'daily').glob('*.json'))
    provenance = resolve_provenance(db, args.ingestion_run_id, ticker, file_names)
    existing_rows = db.get_all('prices_daily', {'instrument_id': 'eq.' + instrument_id, 'select': 'id,trading_date,open_price,high_price,low_price,close_price,volume,market_cap'})
    existing_by_date = {row['trading_date']: row for row in existing_rows}
    inserts: list[dict[str, Any]] = []
    skipped = 0
    conflicts: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for trading_date in sorted(raw_by_date):
        raw = raw_by_date[trading_date]
        existing = existing_by_date.get(trading_date)
        if existing is None:
            inserts.append(create_canonical_row(instrument_id, raw, provenance[raw['_source_file']]))
        elif compare_price(raw, existing):
            skipped += 1
        else:
            conflicts.append((trading_date, existing, raw))
    if conflicts:
        for trading_date, existing, raw in conflicts[:20]:
            print(f'CONFLICT ticker={ticker} date={trading_date} existing={existing} local={raw}', file=sys.stderr)
        raise RuntimeError(f'CONFLICT: {len(conflicts)} existing canonical rows differ; no rows were written')
    db.insert_many('prices_daily', inserts)
    final_rows = db.get_all('prices_daily', {'instrument_id': 'eq.' + instrument_id, 'select': 'trading_date'})
    final_dates = sorted(row['trading_date'] for row in final_rows)
    print(f'ticker={ticker}')
    print(f'raw_file_count={file_count}')
    print(f'raw_unique_record_count={len(raw_by_date)}')
    print(f'inserted_count={len(inserts)}')
    print(f'skipped_count={skipped}')
    print('conflict_count=0')
    print(f'canonical_row_count={len(final_rows)}')
    print(f'earliest_canonical_date={final_dates[0] if final_dates else None}')
    print(f'latest_canonical_date={final_dates[-1] if final_dates else None}')

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'FAILED: {error}', file=sys.stderr)
        raise SystemExit(1) from error

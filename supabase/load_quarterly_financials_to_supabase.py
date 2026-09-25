from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import requests

from raw_storage_source import ProvenanceIndex, RawStorageSource

DEFAULT_RAW_ROOT = Path(r'D:\Stock Analyzer\Data\Raw')
BUCKET = 'stocklens_raw'
DATE_INDEX_FILE = 'quarterly_financial_dates.json'
QUARTERLY_DIRECTORY = 'quarterly'
PERIOD_TYPE = 'QUARTER'
PERIOD_BASIS = 'STANDALONE'
STATEMENT_SCOPE = 'UNKNOWN'
REVISION_KEY = 'CURRENT'
EXPECTED_AUTO_PERIODS = {
    (year, quarter)
    for year in range(2020, 2026)
    for quarter in ('q1', 'q2', 'q3', 'q4')
} | {(2026, 'q1'), (2026, 'q2')}

QUARTERLY_FIELDS = (
    'premium_income',
    'premium_expense',
    'net_premium_income',
    'non_interest_income',
    'revenue',
    'operating_expense',
    'provision',
    'operating_pnl',
    'non_operating_income_or_loss',
    'earnings_before_tax',
    'tax',
    'minorities',
    'earnings',
    'gross_profit',
    'interest_expense_non_operating',
    'ebit',
    'ebitda',
    'cost_of_revenue',
    'total_assets',
    'non_interest_bearing_liabilities',
    'cash_only',
    'total_liabilities',
    'total_equity',
    'total_debt',
    'stockholders_equity',
    'total_non_current_assets',
    'current_liabilities',
    'cash_and_short_term_investments',
    'non_loan_assets',
    'total_current_asset',
    'total_non_current_liabilities',
    'financing_cash_flow',
    'operating_cash_flow',
    'investing_cash_flow',
    'net_cash_flow',
    'capital_expenditure',
    'free_cash_flow',
)
METRIC_CODES = {field: field.upper() for field in QUARTERLY_FIELDS}
QUARTER_MONTH_DAY = {
    'q1': (3, 31),
    'q2': (6, 30),
    'q3': (9, 30),
    'q4': (12, 31),
}


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


def parse_iso_date(value: Any, context: str) -> str:
    if not isinstance(value, str):
        raise LoaderError(f'INVALID_DATE: {context} must be an ISO date string')
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise LoaderError(f'INVALID_DATE: {context}={value}') from error
    if parsed.isoformat() != value:
        raise LoaderError(f'INVALID_DATE_FORMAT: {context}={value}')
    return value


def quarter_from_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    for quarter, (month, day) in QUARTER_MONTH_DAY.items():
        if (parsed.month, parsed.day) == (month, day):
            return quarter
    raise LoaderError(f'INVALID_QUARTER_END: {value}')


def load_json(path: Path) -> tuple[Any, str]:
    content = path.read_bytes()
    try:
        payload = json.loads(content.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LoaderError(f'INVALID_JSON: {path}: {error}') from error
    return payload, hashlib.sha256(content).hexdigest()


def load_date_index(raw_root: Path, ticker: str) -> dict[str, dict[str, Any]]:
    """DEBUG/VERIFICATION ONLY. Local disk is not the pipeline source."""
    path = raw_root / ticker / DATE_INDEX_FILE
    if not path.is_file():
        raise LoaderError(f'DATE_INDEX_NOT_FOUND: {path}')
    payload, _ = load_json(path)
    return parse_date_index(payload, ticker)


def load_date_index_from_storage(
    source: RawStorageSource,
    ticker: str,
) -> dict[str, dict[str, Any]]:
    """PRIMARY source: Supabase Storage."""
    content = source.read(QUARTERLY_DIRECTORY, DATE_INDEX_FILE)
    try:
        payload = json.loads(content.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LoaderError(
            f'INVALID_JSON: {BUCKET}/sectors/{ticker}/{QUARTERLY_DIRECTORY}/{DATE_INDEX_FILE}: {error}'
        ) from error
    return parse_date_index(payload, ticker)


def parse_date_index(payload: Any, ticker: str) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        raise LoaderError('DATE_INDEX_INVALID_SHAPE: expected an object keyed by year')
    entries: dict[str, dict[str, Any]] = {}
    seen_periods: set[str] = set()
    seen_year_quarters: set[tuple[int, str]] = set()
    for year_key, year_entries in payload.items():
        if not isinstance(year_key, str) or not year_key.isdigit():
            raise LoaderError(f'DATE_INDEX_INVALID_YEAR: {year_key!r}')
        year = int(year_key)
        if not isinstance(year_entries, list):
            raise LoaderError(f'DATE_INDEX_INVALID_ENTRIES: {year_key}')
        for entry in year_entries:
            if not isinstance(entry, list) or len(entry) != 2:
                raise LoaderError(f'DATE_INDEX_INVALID_ENTRY: {year_key}: {entry!r}')
            period_end = parse_iso_date(entry[0], f'{DATE_INDEX_FILE}:{year_key}')
            quarter = entry[1]
            if quarter not in QUARTER_MONTH_DAY:
                raise LoaderError(f'DATE_INDEX_INVALID_QUARTER: {entry!r}')
            if date.fromisoformat(period_end).year != year:
                raise LoaderError(f'DATE_INDEX_YEAR_CONFLICT: {entry!r}')
            if quarter_from_date(period_end) != quarter:
                raise LoaderError(f'DATE_INDEX_QUARTER_CONFLICT: {entry!r}')
            year_quarter = (year, quarter)
            if period_end in seen_periods:
                raise LoaderError(f'DATE_INDEX_DUPLICATE_DATE: {period_end}')
            if year_quarter in seen_year_quarters:
                raise LoaderError(f'DATE_INDEX_DUPLICATE_QUARTER: {year}-{quarter}')
            seen_periods.add(period_end)
            seen_year_quarters.add(year_quarter)
            entries[period_end] = {
                'period_end': period_end,
                'period_label': f'{year}-{quarter.upper()}',
                'year': year,
                'quarter': quarter,
            }
    if ticker == 'AUTO' and seen_year_quarters != EXPECTED_AUTO_PERIODS:
        missing = sorted(EXPECTED_AUTO_PERIODS - seen_year_quarters)
        extra = sorted(seen_year_quarters - EXPECTED_AUTO_PERIODS)
        raise LoaderError(f'DATE_INDEX_AUTO_COVERAGE_CONFLICT: missing={missing}, extra={extra}')
    return entries


def load_quarterly_records(
    raw_root: Path,
    ticker: str,
    date_index: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Path], dict[str, str]]:
    folder = raw_root / ticker / QUARTERLY_DIRECTORY
    files = sorted(folder.glob('*.json')) if folder.is_dir() else []
    if not files:
        raise LoaderError(f'QUARTERLY_FILES_NOT_FOUND: {folder}')
    records: list[dict[str, Any]] = []
    paths_by_date: dict[str, Path] = {}
    checksums: dict[str, str] = {}
    expected_keys = {'symbol', 'financials_sector_metrics', 'date', *QUARTERLY_FIELDS}
    for path in files:
        period_end = path.stem
        parse_iso_date(period_end, f'quarterly filename {path.name}')
        if period_end not in date_index:
            raise LoaderError(f'QUARTERLY_FILE_NOT_INDEXED: {path.name}')
        payload, checksum = load_json(path)
        if not isinstance(payload, list) or len(payload) != 1:
            raise LoaderError(f'QUARTERLY_INVALID_SHAPE: {path} must be a one-record array')
        record = payload[0]
        if not isinstance(record, dict):
            raise LoaderError(f'QUARTERLY_INVALID_RECORD: {path}')
        if set(record) != expected_keys:
            missing = sorted(expected_keys - set(record))
            extra = sorted(set(record) - expected_keys)
            raise LoaderError(f'QUARTERLY_FIELD_MISMATCH: {path.name} missing={missing} extra={extra}')
        symbol = record.get('symbol')
        if not isinstance(symbol, str) or symbol.upper() != f'{ticker}.JK':
            raise LoaderError(f'QUARTERLY_SYMBOL_CONFLICT: {path.name} symbol={symbol!r}')
        record_date = parse_iso_date(record.get('date'), f'{path.name}.date')
        if record_date != period_end:
            raise LoaderError(f'QUARTERLY_DATE_CONFLICT: {path.name} record_date={record_date}')
        if record_date != date_index[period_end]['period_end']:
            raise LoaderError(f'QUARTERLY_INDEX_DATE_CONFLICT: {path.name}')
        for field in QUARTERLY_FIELDS:
            value = record[field]
            if value is not None and not is_number(value):
                raise LoaderError(f'QUARTERLY_INVALID_VALUE: {path.name} field={field}')
        record_copy = dict(record)
        record_copy['_period'] = date_index[period_end]
        record_copy['_source_path'] = path
        records.append(record_copy)
        paths_by_date[period_end] = path
        checksums[period_end] = checksum
    if set(paths_by_date) != set(date_index):
        missing = sorted(set(date_index) - set(paths_by_date))
        extra = sorted(set(paths_by_date) - set(date_index))
        raise LoaderError(f'QUARTERLY_FILE_COVERAGE_CONFLICT: missing={missing}, extra={extra}')
    return records, paths_by_date, checksums


def validate_quarterly_record(
    payload: Any,
    label: str,
    ticker: str,
    period_end: str,
    date_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Shared validation for one quarterly raw file (Storage or local debug)."""
    expected_keys = {'symbol', 'financials_sector_metrics', 'date', *QUARTERLY_FIELDS}

    if not isinstance(payload, list) or len(payload) != 1:
        raise LoaderError(f'QUARTERLY_INVALID_SHAPE: {label} must be a one-record array')
    record = payload[0]
    if not isinstance(record, dict):
        raise LoaderError(f'QUARTERLY_INVALID_RECORD: {label}')
    if set(record) != expected_keys:
        missing = sorted(expected_keys - set(record))
        extra = sorted(set(record) - expected_keys)
        raise LoaderError(f'QUARTERLY_FIELD_MISMATCH: {label} missing={missing} extra={extra}')
    symbol = record.get('symbol')
    if not isinstance(symbol, str) or symbol.upper() != f'{ticker}.JK':
        raise LoaderError(f'QUARTERLY_SYMBOL_CONFLICT: {label} symbol={symbol!r}')
    record_date = parse_iso_date(record.get('date'), f'{label}.date')
    if record_date != period_end:
        raise LoaderError(f'QUARTERLY_DATE_CONFLICT: {label} record_date={record_date}')
    if record_date != date_index[period_end]['period_end']:
        raise LoaderError(f'QUARTERLY_INDEX_DATE_CONFLICT: {label}')
    for field in QUARTERLY_FIELDS:
        value = record[field]
        if value is not None and not is_number(value):
            raise LoaderError(f'QUARTERLY_INVALID_VALUE: {label} field={field}')

    record_copy = dict(record)
    record_copy['_period'] = date_index[period_end]
    return record_copy


def load_quarterly_records_from_storage(
    source: RawStorageSource,
    ticker: str,
    date_index: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    """
    PRIMARY source: Supabase Storage.

    Returns (records, storage_paths_by_date, checksums_by_date).
    Only the report dates actually present in the API-provided date index are
    processed - no quarter is invented.
    """
    names = [
        name
        for name in source.names(QUARTERLY_DIRECTORY)
        if name != DATE_INDEX_FILE
    ]
    if not names:
        raise LoaderError(
            f'QUARTERLY_FILES_NOT_FOUND: {BUCKET}/sectors/{ticker}/{QUARTERLY_DIRECTORY}/'
        )

    records: list[dict[str, Any]] = []
    storage_paths_by_date: dict[str, str] = {}
    checksums: dict[str, str] = {}

    for name in names:
        period_end = name[:-len('.json')]
        parse_iso_date(period_end, f'quarterly object {name}')
        if period_end not in date_index:
            raise LoaderError(f'QUARTERLY_FILE_NOT_INDEXED: {name}')

        content = source.read(QUARTERLY_DIRECTORY, name)
        try:
            payload = json.loads(content.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise LoaderError(f'INVALID_JSON: {BUCKET}/{name}: {error}') from error

        record = validate_quarterly_record(payload, name, ticker, period_end, date_index)
        record['_source_path'] = name
        records.append(record)
        storage_paths_by_date[period_end] = source.storage_path(QUARTERLY_DIRECTORY, name)
        checksums[period_end] = hashlib.sha256(content).hexdigest()

    if set(storage_paths_by_date) != set(date_index):
        missing = sorted(set(date_index) - set(storage_paths_by_date))
        extra = sorted(set(storage_paths_by_date) - set(date_index))
        raise LoaderError(f'QUARTERLY_FILE_COVERAGE_CONFLICT: missing={missing}, extra={extra}')

    return records, storage_paths_by_date, checksums


def make_period_plan(record: dict[str, Any]) -> dict[str, Any]:
    period = record['_period']
    return {
        'period_key': (PERIOD_TYPE, period['period_end'], STATEMENT_SCOPE),
        'period_type': PERIOD_TYPE,
        'period_label': period['period_label'],
        'period_start': None,
        'period_end': period['period_end'],
        'report_date': None,
        'available_date': None,
        'period_basis': PERIOD_BASIS,
        'statement_scope': STATEMENT_SCOPE,
        'source_payload_id': None,
    }


def make_fact_plans(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    for record in records:
        period = record['_period']
        for source_field in QUARTERLY_FIELDS:
            value = record[source_field]
            plans.append({
                'period_end': period['period_end'],
                'metric_code': METRIC_CODES[source_field],
                'value_numeric': value,
                'unit_code': 'IDR',
                'currency_code': 'IDR',
                'source_field': source_field,
                'revision_key': REVISION_KEY,
                'quality_status': 'MISSING' if value is None else 'VALID',
                'source_payload_id': None,
            })
    return plans


def load_annual_rows_from_storage(source: RawStorageSource) -> list[dict[str, Any]]:
    """Read the annual raw object from Storage for the 2025 reconciliation."""
    content = source.read('annual', 'company_report_annual.json')
    payload = json.loads(content.decode('utf-8'))
    rows = payload.get('financials', {}).get('historical_financials', [])
    if not isinstance(rows, list):
        raise LoaderError('ANNUAL_SOURCE_INVALID_SHAPE_FOR_RECONCILIATION')
    return rows


def load_annual_rows_local(raw_root: Path, ticker: str) -> list[dict[str, Any]]:
    """DEBUG/VERIFICATION ONLY."""
    annual_path = raw_root / ticker / 'company_report_annual.json'
    if not annual_path.is_file():
        raise LoaderError(f'ANNUAL_SOURCE_NOT_FOUND_FOR_RECONCILIATION: {annual_path}')
    annual_payload, _ = load_json(annual_path)
    return annual_payload.get('financials', {}).get('historical_financials', [])


def verify_auto_annual_reconciliation(
    ticker: str,
    records: list[dict[str, Any]],
    annual_rows: list[dict[str, Any]],
) -> None:
    if ticker != 'AUTO':
        return
    annual_2025 = next((row for row in annual_rows if row.get('year') == 2025), None)
    if annual_2025 is None:
        raise LoaderError('ANNUAL_2025_NOT_FOUND_FOR_RECONCILIATION')
    quarterly_2025 = [row for row in records if row['_period']['year'] == 2025]
    flow_fields = (
        'revenue', 'operating_expense', 'operating_pnl', 'non_operating_income_or_loss',
        'earnings_before_tax', 'tax', 'earnings', 'gross_profit',
        'interest_expense_non_operating', 'ebit', 'ebitda', 'cost_of_revenue',
        'financing_cash_flow', 'operating_cash_flow', 'investing_cash_flow',
        'net_cash_flow', 'capital_expenditure', 'free_cash_flow',
    )
    if len(quarterly_2025) != 4:
        raise LoaderError('AUTO_2025_QUARTER_COUNT_FOR_RECONCILIATION')
    for field in flow_fields:
        values = [row[field] for row in quarterly_2025]
        if any(value is None for value in values) or sum(values) != annual_2025.get(field):
            raise LoaderError(f'AUTO_2025_FLOW_RECONCILIATION_FAILED: {field}')
    for field in ('total_assets', 'cash_only', 'total_liabilities', 'total_equity', 'total_debt', 'current_liabilities'):
        if quarterly_2025[-1][field] != annual_2025.get(field):
            raise LoaderError(f'AUTO_2025_BALANCE_RECONCILIATION_FAILED: {field}')


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

    def insert_rows(self, table: str, rows: list[dict[str, Any]], return_representation: bool) -> list[dict[str, Any]]:
        if not rows:
            return []
        response = self.session.post(self.base_url + '/' + table, json=rows, headers={'Prefer': 'return=representation' if return_representation else 'return=minimal'}, timeout=120)
        if not response.ok:
            raise LoaderError(f'Supabase INSERT {table} failed ({response.status_code}): {response.text[:1000]}')
        if not return_representation:
            return []
        result = response.json()
        if not isinstance(result, list):
            raise LoaderError(f'Supabase INSERT {table} returned a non-list response')
        return result


def verify_provenance(db: Supabase, run_id: str, ticker: str, checksums: dict[str, str]) -> dict[str, str]:
    rows = db.get_all('ingestion_files', {'ingestion_run_id': 'eq.' + run_id, 'storage_bucket': 'eq.' + BUCKET, 'select': 'id,storage_path,checksum_sha256,status'})
    by_path = {row['storage_path']: row for row in rows}
    provenance: dict[str, str] = {}
    for period_end, checksum in checksums.items():
        storage_path = f'sectors/{ticker}/quarterly/{period_end}.json'
        metadata = by_path.get(storage_path)
        if metadata is None:
            raise LoaderError('PROVENANCE_NOT_FOUND: ' + storage_path + ' for run ' + run_id)
        if metadata.get('status') not in {'UPLOADED', 'SKIPPED'}:
            raise LoaderError('PROVENANCE_NOT_READY: ' + storage_path)
        if metadata.get('checksum_sha256') != checksum:
            raise LoaderError('PROVENANCE_CHECKSUM_CONFLICT: ' + storage_path)
        provenance[period_end] = metadata['id']
    return provenance


def resolve_provenance_by_path(checksums: dict[str, str]) -> dict[str, str]:
    """
    Provenance keyed by storage path.

    Phase 1B registered one ingestion_runs row per raw file, so a single
    run_id cannot cover all 27 quarterly objects. Each row is still validated
    for status + checksum before use.
    """
    return ProvenanceIndex(
        required_env('SUPABASE_URL'),
        required_env('SUPABASE_SERVICE_ROLE_KEY'),
    ).resolve_many(checksums)


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


def period_matches(existing: dict[str, Any], intended: dict[str, Any], instrument_id: str) -> bool:
    fields = ('period_type', 'period_label', 'period_start', 'period_end', 'report_date', 'available_date', 'period_basis', 'statement_scope', 'source_payload_id')
    expected = {'instrument_id': instrument_id, **{field: intended[field] for field in fields}}
    return all(existing.get(field) == value for field, value in expected.items())


def fact_matches(existing: dict[str, Any], intended: dict[str, Any]) -> bool:
    fields = ('metric_code', 'unit_code', 'currency_code', 'source_field', 'revision_key', 'quality_status', 'source_payload_id')
    return all(existing.get(field) == intended[field] for field in fields) and values_equal(existing.get('value_numeric'), intended['value_numeric'])


def preflight(db: Supabase, instrument_id: str, period_plans: list[dict[str, Any]], fact_plans: list[dict[str, Any]]):
    existing_periods = db.get_all('financial_periods', {'instrument_id': 'eq.' + instrument_id, 'period_type': 'eq.' + PERIOD_TYPE, 'select': 'id,instrument_id,period_type,period_label,period_start,period_end,report_date,available_date,period_basis,statement_scope,source_payload_id'})
    by_key = {(row['period_type'], row['period_end'], row['statement_scope']): row for row in existing_periods}
    existing_by_end = {row['period_end']: row for row in existing_periods}
    existing_by_end_values: dict[str, list[dict[str, Any]]] = {}
    for row in existing_periods:
        existing_by_end_values.setdefault(row['period_end'], []).append(row)
    periods_by_date: dict[str, dict[str, Any]] = {}
    new_period_ends: set[str] = set()
    conflicts: list[dict[str, Any]] = []
    for plan in period_plans:
        existing = by_key.get(plan['period_key'])
        if existing is None and existing_by_end_values.get(plan['period_end']):
            conflicts.append({'kind': 'PERIOD', 'period': plan['period_end'], 'existing': existing_by_end_values[plan['period_end']], 'intended': plan})
        elif existing is None:
            new_period_ends.add(plan['period_end'])
        elif not period_matches(existing, plan, instrument_id):
            conflicts.append({'kind': 'PERIOD', 'period': plan['period_end'], 'existing': existing, 'intended': plan})
        else:
            periods_by_date[plan['period_end']] = existing
    if conflicts:
        return periods_by_date, new_period_ends, set(), conflicts
    existing_facts: list[dict[str, Any]] = []
    if periods_by_date:
        ids = ','.join(row['id'] for row in periods_by_date.values())
        existing_facts = db.get_all('financial_facts', {'financial_period_id': 'in.(' + ids + ')', 'select': 'id,financial_period_id,metric_code,value_numeric,unit_code,currency_code,source_field,revision_key,quality_status,source_payload_id'})
    facts_by_key = {(row['financial_period_id'], row['metric_code'], row['revision_key']): row for row in existing_facts}
    existing_fact_keys: set[tuple[str, str, str]] = set()
    for plan in fact_plans:
        period = periods_by_date.get(plan['period_end'])
        if period is None:
            continue
        key = (period['id'], plan['metric_code'], plan['revision_key'])
        existing = facts_by_key.get(key)
        if existing is None:
            continue
        if fact_matches(existing, plan):
            existing_fact_keys.add(key)
        else:
            conflicts.append({'kind': 'FACT', 'period': plan['period_end'], 'metric': plan['metric_code'], 'existing': existing, 'intended': plan})
    return periods_by_date, new_period_ends, existing_fact_keys, conflicts


def main() -> None:
    parser = argparse.ArgumentParser(description='Load quarterly financial JSON (Storage-first) into canonical Supabase tables')
    parser.add_argument('ticker')
    parser.add_argument('--ingestion-run-id', help='Optional raw-storage ingestion_runs.id cross-check')
    parser.add_argument('--source', choices=['storage', 'local'], default='storage',
                        help='Pipeline source. Default storage (local is debug-only).')
    parser.add_argument('--raw-root', default=str(DEFAULT_RAW_ROOT), help='Debug-only local root')
    args = parser.parse_args()
    ticker = args.ticker.upper().replace('.JK', '')

    if args.source == 'storage':
        source = RawStorageSource(ticker)
        date_index = load_date_index_from_storage(source, ticker)
        records, storage_paths_by_date, checksums = load_quarterly_records_from_storage(
            source, ticker, date_index
        )
        annual_rows = load_annual_rows_from_storage(source)
        provenance_checksums = {
            storage_path: checksums[period_end]
            for period_end, storage_path in storage_paths_by_date.items()
        }
        source_label = f'{BUCKET}/sectors/{ticker}/{QUARTERLY_DIRECTORY}/'
    else:
        raw_root = Path(args.raw_root)
        date_index = load_date_index(raw_root, ticker)
        records, paths_by_date, checksums = load_quarterly_records(raw_root, ticker, date_index)
        annual_rows = load_annual_rows_local(raw_root, ticker)
        provenance_checksums = {
            f'sectors/{ticker}/quarterly/{period_end}.json': checksum
            for period_end, checksum in checksums.items()
        }
        source_label = str(raw_root / ticker / QUARTERLY_DIRECTORY)

    verify_auto_annual_reconciliation(ticker, records, annual_rows)
    period_plans = [make_period_plan(record) for record in records]
    fact_plans = make_fact_plans(records)
    db = Supabase(required_env('SUPABASE_URL'), required_env('SUPABASE_SERVICE_ROLE_KEY'))
    provenance = resolve_provenance_by_path(provenance_checksums)
    if args.ingestion_run_id:
        verify_provenance(db, args.ingestion_run_id, ticker, checksums)
    instrument_id = resolve_instrument(db, ticker)
    periods_by_date, new_period_ends, existing_fact_keys, conflicts = preflight(db, instrument_id, period_plans, fact_plans)
    if conflicts:
        for conflict in conflicts[:20]:
            print(str(conflict), file=sys.stderr)
        raise LoaderError(f'CONFLICT: {len(conflicts)} existing rows differ; no rows were written')
    periods_to_insert = []
    for plan in period_plans:
        if plan['period_end'] in new_period_ends:
            periods_to_insert.append({'instrument_id': instrument_id, **{key: plan[key] for key in ('period_type', 'period_label', 'period_start', 'period_end', 'report_date', 'available_date', 'period_basis', 'statement_scope', 'source_payload_id')}})
    inserted_periods = db.insert_rows('financial_periods', periods_to_insert, True)
    if len(inserted_periods) != len(periods_to_insert):
        raise LoaderError('PERIOD_INSERT_COUNT_MISMATCH')
    for row in inserted_periods:
        periods_by_date[row['period_end']] = row
    facts_to_insert = []
    for plan in fact_plans:
        period = periods_by_date[plan['period_end']]
        key = (period['id'], plan['metric_code'], plan['revision_key'])
        if key in existing_fact_keys:
            continue
        facts_to_insert.append({'financial_period_id': period['id'], **{field: plan[field] for field in ('metric_code', 'value_numeric', 'unit_code', 'currency_code', 'source_field', 'revision_key', 'quality_status', 'source_payload_id')}})
    db.insert_rows('financial_facts', facts_to_insert, False)
    verified_periods = db.get_all('financial_periods', {'instrument_id': 'eq.' + instrument_id, 'period_type': 'eq.' + PERIOD_TYPE, 'select': 'id,period_label,period_end,period_basis,statement_scope'})
    period_ids = [row['id'] for row in verified_periods]
    if len(verified_periods) != len(period_plans) or sorted(row['period_end'] for row in verified_periods) != sorted(date_index):
        raise LoaderError('FINAL_PERIOD_VERIFICATION_FAILED')
    if any(row['period_basis'] != PERIOD_BASIS or row['statement_scope'] != STATEMENT_SCOPE for row in verified_periods):
        raise LoaderError('FINAL_PERIOD_METADATA_VERIFICATION_FAILED')
    verified_facts = db.get_all('financial_facts', {'financial_period_id': 'in.(' + ','.join(period_ids) + ')', 'select': 'financial_period_id,metric_code,value_numeric,unit_code,currency_code,source_field,revision_key,quality_status,source_payload_id'})
    if len(verified_facts) != len(fact_plans):
        raise LoaderError('FINAL_FACT_VERIFICATION_FAILED')
    if any(row['metric_code'] == 'EPS' for row in verified_facts):
        raise LoaderError('FINAL_EPS_VERIFICATION_FAILED')
    plans_by_key = {(plan['period_end'], plan['metric_code'], plan['source_field']): plan for plan in fact_plans}
    period_by_id = {row['id']: row['period_end'] for row in verified_periods}
    actual_facts = {(period_by_id[row['financial_period_id']], row['metric_code'], row['source_field']): row for row in verified_facts}
    if set(actual_facts) != set(plans_by_key) or any(row['source_payload_id'] is not None for row in verified_facts):
        raise LoaderError('FINAL_FACT_METADATA_VERIFICATION_FAILED')
    for key, row in actual_facts.items():
        if not fact_matches(row, plans_by_key[key]):
            raise LoaderError('FINAL_FACT_VALUE_VERIFICATION_FAILED: ' + str(key))
    print('ticker=' + ticker)
    print('source=' + args.source)
    print('raw_source=' + source_label)
    print('instrument_id=' + instrument_id)
    print('quarterly_file_count=' + str(len(records)))
    print('period_count=' + str(len(period_plans)))
    print('fact_count=' + str(len(fact_plans)))
    print('inserted_period_count=' + str(len(periods_to_insert)))
    print('skipped_period_count=' + str(len(period_plans) - len(periods_to_insert)))
    print('inserted_fact_count=' + str(len(facts_to_insert)))
    print('skipped_fact_count=' + str(len(fact_plans) - len(facts_to_insert)))
    print('conflict_count=0')
    print('earliest_period=' + min(date_index))
    print('latest_period=' + max(date_index))
    print('null_fact_count=' + str(sum(plan['value_numeric'] is None for plan in fact_plans)))
    print('eps_fact_count=0')
    print('provider_derived_fields_skipped=financials_sector_metrics')
    print('verified_file_count=' + str(len(provenance)))
    print('checksum_failure_count=0')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'FAILED: {error}', file=sys.stderr)
        raise SystemExit(1) from error

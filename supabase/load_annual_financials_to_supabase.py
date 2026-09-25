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
ANNUAL_FILE = 'company_report_annual.json'
ANNUAL_CATEGORY = 'annual'
EXPECTED_YEARS = tuple(range(2019, 2026))
PERIOD_TYPE = 'ANNUAL'
STATEMENT_SCOPE = 'UNKNOWN'
PERIOD_BASIS = 'UNKNOWN'
REVISION_KEY = 'CURRENT'

MONETARY_FIELDS = (
    'tax', 'ebit', 'ebitda', 'revenue', 'earnings', 'net_debt', 'cash_only',
    'total_debt', 'inventories', 'fixed_assets', 'gross_profit', 'total_assets',
    'total_equity', 'net_cash_flow', 'operating_pnl', 'current_assets',
    'free_cash_flow', 'long_term_debt', 'prepaid_assets', 'cost_of_revenue',
    'short_term_debt', 'operating_expense', 'retained_earnings',
    'total_liabilities', 'capital_expenditure', 'current_liabilities',
    'earnings_before_tax', 'financing_cash_flow', 'investing_cash_flow',
    'operating_cash_flow', 'cash_and_equivalents', 'non_current_liabilities',
    'non_operating_income_or_loss', 'interest_expense_non_operating',
)
SHARES_FIELD = 'outstanding_shares'
EXCLUDED_NULL_FIELDS = (
    'industry_breakdown', 'net_increased_decreased', 'total_cash_and_due_from_banks',
)
METRIC_CODES = {field: field.upper() for field in MONETARY_FIELDS}


class LoaderError(RuntimeError):
    pass


def required_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise LoaderError(f'Environment variable belum di-set: {name}')
    return value


def is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def expected_period_end(year: int) -> str:
    return f'{year:04d}-12-31'


def load_annual_source(raw_root: Path, ticker: str) -> tuple[dict[str, Any], Path, str]:
    """DEBUG/VERIFICATION ONLY. Local disk is not the pipeline source."""
    path = raw_root / ticker / ANNUAL_FILE
    if not path.is_file():
        raise LoaderError(f'ANNUAL_SOURCE_NOT_FOUND: {path}')
    content = path.read_bytes()
    try:
        payload = json.loads(content.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LoaderError(f'ANNUAL_SOURCE_INVALID_JSON: {path}: {error}') from error
    if not isinstance(payload, dict):
        raise LoaderError(f'ANNUAL_SOURCE_INVALID_SHAPE: {path} must contain an object')
    return payload, path, hashlib.sha256(content).hexdigest()


def load_annual_source_from_storage(ticker: str) -> tuple[dict[str, Any], str, str]:
    """
    PRIMARY source: Supabase Storage.

    Returns (payload, storage_path, sha256) reading the exact stored bytes.
    """
    source = RawStorageSource(ticker)
    storage_path = source.storage_path(ANNUAL_CATEGORY, ANNUAL_FILE)
    content = source.read(ANNUAL_CATEGORY, ANNUAL_FILE)
    try:
        payload = json.loads(content.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LoaderError(f'ANNUAL_SOURCE_INVALID_JSON: {BUCKET}/{storage_path}: {error}') from error
    if not isinstance(payload, dict):
        raise LoaderError(f'ANNUAL_SOURCE_INVALID_SHAPE: {BUCKET}/{storage_path} must contain an object')
    return payload, storage_path, hashlib.sha256(content).hexdigest()


def validate_source(payload: dict[str, Any], ticker: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    symbol = payload.get('symbol')
    if not isinstance(symbol, str) or not symbol.strip():
        raise LoaderError('ANNUAL_SOURCE_MISSING: symbol')
    expected_symbol = f'{ticker}.JK'
    if symbol.upper() != expected_symbol:
        raise LoaderError(f'ANNUAL_SOURCE_CONFLICT: symbol={symbol}, expected={expected_symbol}')
    company_name = payload.get('company_name')
    if not isinstance(company_name, str) or not company_name.strip():
        raise LoaderError('ANNUAL_SOURCE_MISSING: company_name')
    financials = payload.get('financials')
    if not isinstance(financials, dict):
        raise LoaderError('ANNUAL_SOURCE_INVALID_SHAPE: financials must be an object')
    rows = financials.get('historical_financials')
    if not isinstance(rows, list):
        raise LoaderError('ANNUAL_SOURCE_INVALID_SHAPE: historical_financials must be an array')
    if len(rows) != len(EXPECTED_YEARS):
        raise LoaderError(f'ANNUAL_SOURCE_ROW_COUNT: expected {len(EXPECTED_YEARS)}, got {len(rows)}')
    years: list[int] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise LoaderError(f'ANNUAL_SOURCE_INVALID_ROW: row {index} must be an object')
        year = row.get('year')
        if isinstance(year, bool) or not isinstance(year, int):
            raise LoaderError(f'ANNUAL_SOURCE_INVALID_YEAR: row {index} year must be an integer')
        years.append(year)
        for field in MONETARY_FIELDS + (SHARES_FIELD,):
            if field not in row:
                raise LoaderError(f'ANNUAL_SOURCE_MISSING_FIELD: row {index} missing {field}')
        for field, value in row.items():
            if field == 'year' or value is None:
                continue
            if not is_number(value):
                raise LoaderError(f'ANNUAL_SOURCE_INVALID_VALUE: row {index} field {field} must be numeric or null')
    if len(set(years)) != len(years) or tuple(sorted(years)) != EXPECTED_YEARS:
        raise LoaderError(f'ANNUAL_SOURCE_YEAR_RANGE: expected {EXPECTED_YEARS[0]}..{EXPECTED_YEARS[-1]}, got {sorted(years)}')
    historical_eps = financials.get('historical_eps')
    if not isinstance(historical_eps, dict):
        raise LoaderError('ANNUAL_SOURCE_INVALID_SHAPE: historical_eps must be an object')
    for year in range(2020, 2026):
        entry = historical_eps.get(str(year))
        if not isinstance(entry, dict) or 'eps' not in entry:
            raise LoaderError(f'ANNUAL_SOURCE_MISSING_EPS: historical_eps.{year}.eps')
        if entry['eps'] is not None and not is_number(entry['eps']):
            raise LoaderError(f'ANNUAL_SOURCE_INVALID_EPS: historical_eps.{year}.eps')
    return rows, financials


def make_period_plan(year: int) -> dict[str, Any]:
    period_end = expected_period_end(year)
    return {
        'period_key': (PERIOD_TYPE, period_end, STATEMENT_SCOPE),
        'period_type': PERIOD_TYPE, 'period_label': str(year), 'period_start': None,
        'period_end': period_end, 'report_date': None, 'available_date': None,
        'period_basis': PERIOD_BASIS, 'statement_scope': STATEMENT_SCOPE,
        'source_payload_id': None,
    }


def make_fact_plans(rows: list[dict[str, Any]], financials: dict[str, Any]) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    for row in rows:
        for source_field in MONETARY_FIELDS:
            value = row[source_field]
            plans.append({
                'period_year': row['year'], 'metric_code': METRIC_CODES[source_field],
                'value_numeric': value, 'unit_code': 'IDR', 'currency_code': 'IDR',
                'source_field': source_field, 'revision_key': REVISION_KEY,
                'quality_status': 'MISSING' if value is None else 'VALID',
                'source_payload_id': None,
            })
        value = row[SHARES_FIELD]
        plans.append({
            'period_year': row['year'], 'metric_code': 'OUTSTANDING_SHARES',
            'value_numeric': value, 'unit_code': 'SHARES', 'currency_code': None,
            'source_field': SHARES_FIELD, 'revision_key': REVISION_KEY,
            'quality_status': 'MISSING' if value is None else 'VALID',
            'source_payload_id': None,
        })
    for year in range(2020, 2026):
        value = financials['historical_eps'][str(year)]['eps']
        plans.append({
            'period_year': year, 'metric_code': 'EPS', 'value_numeric': value,
            'unit_code': 'IDR_PER_SHARE', 'currency_code': 'IDR',
            'source_field': f'historical_eps.{year}.eps', 'revision_key': REVISION_KEY,
            'quality_status': 'MISSING' if value is None else 'VALID',
            'source_payload_id': None,
        })
    return plans


class Supabase:
    def __init__(self, url: str, key: str):
        self.base_url = url.rstrip('/') + '/rest/v1'
        self.session = requests.Session()
        self.session.headers.update({
            'apikey': key,
            'Authorization': 'Bearer ' + key,
            'Content-Type': 'application/json',
        })

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
        prefer = 'return=representation' if return_representation else 'return=minimal'
        response = self.session.post(
            self.base_url + '/' + table,
            json=rows,
            headers={'Prefer': prefer},
            timeout=120,
        )
        if not response.ok:
            raise LoaderError(f'Supabase INSERT {table} failed ({response.status_code}): {response.text[:1000]}')
        if not return_representation:
            return []
        result = response.json()
        if not isinstance(result, list):
            raise LoaderError(f'Supabase INSERT {table} returned a non-list response')
        return result


def verify_provenance(db: Supabase, run_id: str, ticker: str, checksum: str) -> str:
    storage_path = f'sectors/{ticker}/annual/{ANNUAL_FILE}'
    rows = db.get_all('ingestion_files', {
        'ingestion_run_id': 'eq.' + run_id,
        'storage_bucket': 'eq.' + BUCKET,
        'storage_path': 'eq.' + storage_path,
        'select': 'id,checksum_sha256,status',
    })
    if not rows:
        raise LoaderError(f'PROVENANCE_NOT_FOUND: {storage_path} for run {run_id}')
    metadata = rows[0]
    if len(rows) != 1 or metadata.get('status') not in {'UPLOADED', 'SKIPPED'}:
        raise LoaderError(f'PROVENANCE_NOT_READY: {storage_path}')
    if metadata.get('checksum_sha256') != checksum:
        raise LoaderError(f'PROVENANCE_CHECKSUM_CONFLICT: {storage_path}')
    return metadata['id']
def resolve_instrument(db: Supabase, ticker: str) -> str:
    rows = db.get_all('instruments', {
        'exchange_code': 'eq.IDX', 'ticker': 'eq.' + ticker,
        'select': 'id,exchange_code,ticker',
    })
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
    fields = ('instrument_id', 'period_type', 'period_label', 'period_start', 'period_end',
              'report_date', 'available_date', 'period_basis', 'statement_scope', 'source_payload_id')
    expected = {'instrument_id': instrument_id, **{field: intended[field] for field in fields if field != 'instrument_id'}}
    return all(existing.get(field) == value for field, value in expected.items())


def fact_matches(existing: dict[str, Any], intended: dict[str, Any]) -> bool:
    fields = ('metric_code', 'unit_code', 'currency_code', 'source_field', 'revision_key', 'quality_status', 'source_payload_id')
    return all(existing.get(field) == intended[field] for field in fields) and values_equal(existing.get('value_numeric'), intended['value_numeric'])


def preflight(db: Supabase, instrument_id: str, period_plans: list[dict[str, Any]], fact_plans: list[dict[str, Any]]):
    existing_periods = db.get_all('financial_periods', {
        'instrument_id': 'eq.' + instrument_id,
        'period_type': 'eq.' + PERIOD_TYPE,
        'select': 'id,instrument_id,period_type,period_label,period_start,period_end,report_date,available_date,period_basis,statement_scope,source_payload_id',
    })
    by_key = {(row['period_type'], row['period_end'], row['statement_scope']): row for row in existing_periods}
    by_end: dict[str, list[dict[str, Any]]] = {}
    for row in existing_periods:
        by_end.setdefault(row['period_end'], []).append(row)
    existing_by_year: dict[int, dict[str, Any]] = {}
    new_years: set[int] = set()
    conflicts: list[dict[str, Any]] = []
    for plan in period_plans:
        year = int(plan['period_label'])
        existing = by_key.get(plan['period_key'])
        if existing is None and by_end.get(plan['period_end']):
            conflicts.append({'kind': 'PERIOD', 'period': year, 'existing': by_end[plan['period_end']], 'intended': plan})
        elif existing is None:
            new_years.add(year)
        elif not period_matches(existing, plan, instrument_id):
            conflicts.append({'kind': 'PERIOD', 'period': year, 'existing': existing, 'intended': plan})
        else:
            existing_by_year[year] = existing
    if conflicts:
        return existing_by_year, new_years, set(), conflicts
    existing_facts: list[dict[str, Any]] = []
    if existing_by_year:
        ids = ','.join(row['id'] for row in existing_by_year.values())
        existing_facts = db.get_all('financial_facts', {
            'financial_period_id': 'in.(' + ids + ')',
            'select': 'id,financial_period_id,metric_code,value_numeric,unit_code,currency_code,source_field,revision_key,quality_status,source_payload_id',
        })
    fact_by_key = {(row['financial_period_id'], row['metric_code'], row['revision_key']): row for row in existing_facts}
    existing_fact_keys: set[tuple[str, str, str]] = set()
    for plan in fact_plans:
        period = existing_by_year.get(plan['period_year'])
        if period is None:
            continue
        key = (period['id'], plan['metric_code'], plan['revision_key'])
        existing = fact_by_key.get(key)
        if existing is None:
            continue
        if fact_matches(existing, plan):
            existing_fact_keys.add(key)
        else:
            conflicts.append({'kind': 'FACT', 'period': plan['period_year'], 'metric': plan['metric_code'], 'existing': existing, 'intended': plan})
    return existing_by_year, new_years, existing_fact_keys, conflicts


def print_conflicts(conflicts: list[dict[str, Any]]) -> None:
    for conflict in conflicts[:20]:
        print(str(conflict), file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description='Load annual financial JSON (Storage-first) into canonical Supabase tables')
    parser.add_argument('ticker')
    parser.add_argument('--ingestion-run-id', help='Optional raw-storage ingestion_runs.id cross-check')
    parser.add_argument('--source', choices=['storage', 'local'], default='storage',
                        help='Pipeline source. Default storage (local is debug-only).')
    parser.add_argument('--raw-root', default=str(DEFAULT_RAW_ROOT), help='Debug-only local root')
    args = parser.parse_args()
    ticker = args.ticker.upper().replace('.JK', '')

    if args.source == 'storage':
        payload, storage_path, checksum = load_annual_source_from_storage(ticker)
        source_label = f'{BUCKET}/{storage_path}'
    else:
        payload, local_path, checksum = load_annual_source(Path(args.raw_root), ticker)
        storage_path = f'sectors/{ticker}/annual/{ANNUAL_FILE}'
        source_label = str(local_path)

    rows, financials = validate_source(payload, ticker)
    period_plans = [make_period_plan(row['year']) for row in rows]
    fact_plans = make_fact_plans(rows, financials)
    db = Supabase(required_env('SUPABASE_URL'), required_env('SUPABASE_SERVICE_ROLE_KEY'))
    provenance_id = ProvenanceIndex(
        required_env('SUPABASE_URL'),
        required_env('SUPABASE_SERVICE_ROLE_KEY'),
    ).resolve(storage_path, checksum)
    if args.ingestion_run_id:
        verify_provenance(db, args.ingestion_run_id, ticker, checksum)
    instrument_id = resolve_instrument(db, ticker)
    existing_by_year, new_years, existing_fact_keys, conflicts = preflight(db, instrument_id, period_plans, fact_plans)
    if conflicts:
        print_conflicts(conflicts)
        raise LoaderError(f'CONFLICT: {len(conflicts)} existing rows differ; no rows were written')
    periods_to_insert = []
    for plan in period_plans:
        if int(plan['period_label']) in new_years:
            periods_to_insert.append({
                'instrument_id': instrument_id,
                **{key: plan[key] for key in ('period_type', 'period_label', 'period_start', 'period_end', 'report_date', 'available_date', 'period_basis', 'statement_scope', 'source_payload_id')},
            })
    inserted_periods = db.insert_rows('financial_periods', periods_to_insert, True)
    if len(inserted_periods) != len(periods_to_insert):
        raise LoaderError('PERIOD_INSERT_COUNT_MISMATCH')
    for row in inserted_periods:
        existing_by_year[int(row['period_label'])] = row
    facts_to_insert = []
    for plan in fact_plans:
        period = existing_by_year[plan['period_year']]
        key = (period['id'], plan['metric_code'], plan['revision_key'])
        if key in existing_fact_keys:
            continue
        facts_to_insert.append({
            'financial_period_id': period['id'],
            'metric_code': plan['metric_code'],
            'value_numeric': plan['value_numeric'],
            'unit_code': plan['unit_code'],
            'currency_code': plan['currency_code'],
            'source_field': plan['source_field'],
            'revision_key': plan['revision_key'],
            'quality_status': plan['quality_status'],
            'source_payload_id': plan['source_payload_id'],
        })
    db.insert_rows('financial_facts', facts_to_insert, False)
    final_periods = db.get_all('financial_periods', {'instrument_id': 'eq.' + instrument_id, 'period_type': 'eq.' + PERIOD_TYPE, 'select': 'period_end'})
    final_dates = sorted(row['period_end'] for row in final_periods)
    print('ticker=' + ticker)
    print('source=' + args.source)
    print('raw_source=' + source_label)
    print('instrument_id=' + instrument_id)
    print('identity_ingestion_file_id=' + provenance_id)
    print('raw_file=' + str(storage_path))
    print('checksum_sha256=' + checksum)
    print('period_count=' + str(len(period_plans)))
    print('fact_count=' + str(len(fact_plans)))
    print('inserted_period_count=' + str(len(periods_to_insert)))
    print('skipped_period_count=' + str(len(period_plans) - len(periods_to_insert)))
    print('inserted_fact_count=' + str(len(facts_to_insert)))
    print('skipped_fact_count=' + str(len(fact_plans) - len(facts_to_insert)))
    print('conflict_count=0')
    print('earliest_period=' + (final_dates[0] if final_dates else 'None'))
    print('latest_period=' + (final_dates[-1] if final_dates else 'None'))
    print('eps_count=6')
    print('null_fact_count=' + str(sum(plan['value_numeric'] is None for plan in fact_plans)))
    print('provider_ratio_fields_skipped=historical_financial_ratio,yoy_quarter_earnings_growth,yoy_quarter_revenue_growth')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'FAILED: {error}', file=sys.stderr)
        raise SystemExit(1) from error

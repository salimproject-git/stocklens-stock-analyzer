from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import requests

from upload_raw_storage_only import StorageClient

DEFAULT_RAW_ROOT = Path(r'D:\Stock Analyzer\Data\Raw')
BUCKET = 'stocklens_raw'
INFO_FILE = 'company_report_info.json'


def required_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise RuntimeError(f'Environment variable belum di-set: {name}')
    return value


def parse_info_bytes(content: bytes, source_label: str) -> dict[str, Any]:
    """Shared validation for the raw info payload (Storage or local debug)."""
    try:
        payload = json.loads(content.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f'IDENTITY_SOURCE_INVALID_JSON: {source_label}: {error}') from error
    if not isinstance(payload, dict):
        raise RuntimeError(f'IDENTITY_SOURCE_INVALID_SHAPE: {source_label} must contain an object')
    return payload


def load_info_from_storage(
    storage: StorageClient,
    ticker: str,
) -> tuple[dict[str, Any], str, str]:
    """
    PRIMARY source of truth: the private Storage bucket.

    Reads the exact bytes of `sectors/{TICKER}/info/company_report_info.json`
    and returns (payload, storage_path, sha256). No transformation.
    """
    storage_path = f'sectors/{ticker}/info/{INFO_FILE}'
    if storage.object_info(BUCKET, storage_path) is None:
        raise RuntimeError(f'IDENTITY_SOURCE_NOT_FOUND: {BUCKET}/{storage_path}')
    content = storage.download(BUCKET, storage_path)
    payload = parse_info_bytes(content, f'{BUCKET}/{storage_path}')
    return payload, storage_path, hashlib.sha256(content).hexdigest()


def load_info(raw_root: Path, ticker: str) -> tuple[dict[str, Any], Path, str]:
    """DEBUG/VERIFICATION ONLY. Local disk is not the pipeline source."""
    path = raw_root / ticker / INFO_FILE
    if not path.is_file():
        raise RuntimeError(f'IDENTITY_SOURCE_NOT_FOUND: {path}')
    content = path.read_bytes()
    payload = parse_info_bytes(content, str(path))
    return payload, path, hashlib.sha256(content).hexdigest()


def source_values(payload: dict[str, Any], ticker: str) -> dict[str, Any]:
    overview = payload.get('overview')
    if not isinstance(overview, dict):
        raise RuntimeError('IDENTITY_SOURCE_INVALID_SHAPE: overview must be an object')
    symbol = payload.get('symbol')
    company_name = payload.get('company_name')
    provider_symbol = str(symbol).upper() if symbol is not None else None
    expected_symbol = f'{ticker}.JK'
    if not provider_symbol:
        raise RuntimeError('IDENTITY_SOURCE_MISSING: symbol')
    if provider_symbol != expected_symbol:
        raise RuntimeError(f'IDENTITY_SOURCE_CONFLICT: symbol={provider_symbol}, expected={expected_symbol}')
    if not isinstance(company_name, str) or not company_name.strip():
        raise RuntimeError('IDENTITY_SOURCE_MISSING: company_name')
    sector_name = overview.get('sector')
    subsector_name = overview.get('sub_sector')
    if subsector_name is not None and sector_name is None:
        raise RuntimeError('IDENTITY_SOURCE_INVALID: subsector exists without sector')
    listing_date = overview.get('listing_date')
    if listing_date is not None:
        try:
            date.fromisoformat(str(listing_date))
        except ValueError as error:
            raise RuntimeError(f'IDENTITY_SOURCE_INVALID: listing_date={listing_date}') from error
    return {
        'provider_identity': provider_symbol,
        'legal_name': company_name,
        'website': overview.get('website'),
        'headquarters': overview.get('address'),
        'listing_date': listing_date,
        'provider_symbol': provider_symbol,
        'sector_name': sector_name,
        'subsector_name': subsector_name,
    }


class Supabase:
    def __init__(self, url: str, key: str):
        self.base_url = url.rstrip('/') + '/rest/v1'
        self.session = requests.Session()
        self.session.headers.update({
            'apikey': key,
            'Authorization': 'Bearer ' + key,
            'Content-Type': 'application/json',
        })

    def get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        response = self.session.get(self.base_url + '/' + table, params=params, timeout=60)
        if not response.ok:
            raise RuntimeError(f'Supabase GET {table} failed ({response.status_code}): {response.text[:1000]}')
        value = response.json()
        if not isinstance(value, list):
            raise RuntimeError(f'Supabase GET {table} returned a non-list response')
        return value

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            self.base_url + '/' + table,
            params={'select': '*'},
            json=row,
            headers={'Prefer': 'return=representation'},
            timeout=60,
        )
        if not response.ok:
            raise RuntimeError(f'Supabase INSERT {table} failed ({response.status_code}): {response.text[:1000]}')
        rows = response.json()
        if not isinstance(rows, list) or len(rows) != 1:
            raise RuntimeError(f'Supabase INSERT {table} returned an unexpected response')
        return rows[0]


def verify_provenance(db: Supabase, run_id: str, ticker: str, storage_path: str, checksum: str) -> str:
    expected_path = f'sectors/{ticker}/info/{INFO_FILE}'
    if storage_path != expected_path:
        raise RuntimeError(
            f'PROVENANCE_PATH_MISMATCH: {storage_path} != {expected_path}'
        )
    runs = db.get('ingestion_runs', {
        'id': 'eq.' + run_id,
        'select': 'id,symbol',
    })
    if len(runs) != 1:
        raise RuntimeError(f'INGESTION_RUN_NOT_FOUND_OR_NOT_UNIQUE: {run_id}')
    run_symbol = str(runs[0].get('symbol', '')).upper().replace('.JK', '')
    if run_symbol != ticker:
        raise RuntimeError(f'INGESTION_RUN_TICKER_CONFLICT: run={run_symbol}, requested={ticker}')
    rows = db.get('ingestion_files', {
        'ingestion_run_id': 'eq.' + run_id,
        'storage_bucket': 'eq.' + BUCKET,
        'storage_path': 'eq.' + storage_path,
        'select': 'id,checksum_sha256,status',
    })
    if not rows:
        raise RuntimeError(f'PROVENANCE_NOT_FOUND: {storage_path} for run {run_id}')
    if len(rows) != 1:
        raise RuntimeError(f'PROVENANCE_NOT_UNIQUE: {storage_path} returned {len(rows)} rows')
    if rows[0]['status'] not in {'UPLOADED', 'SKIPPED'}:
        raise RuntimeError('PROVENANCE_NOT_READY: %s status=%s' % (storage_path, rows[0].get('status')))
    if rows[0]['checksum_sha256'] != checksum:
        raise RuntimeError(f'PROVENANCE_CHECKSUM_CONFLICT: {storage_path}')
    return rows[0]['id']

def compare_fields(existing: dict[str, Any], incoming: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    differences = []
    for field in fields:
        if incoming.get(field) is not None and existing.get(field) != incoming[field]:
            differences.append(f'{field}: existing={existing.get(field)!r}, incoming={incoming[field]!r}')
    return differences

def load_identity(db: Supabase, ticker: str, values: dict[str, Any]) -> tuple[str, list[str]]:
    company_fields = ('legal_name', 'website', 'headquarters', 'listing_date')
    companies = db.get('companies', {'provider_identity': 'eq.' + values['provider_identity'], 'select': '*'})
    notes: list[str] = []
    if len(companies) > 1:
        raise RuntimeError('COMPANY_NOT_UNIQUE: %s' % values['provider_identity'])
    if not companies:
        company = db.insert('companies', {
            'provider_identity': values['provider_identity'],
            **{field: values[field] for field in company_fields},
        })
        notes.append('company=INSERT')
    else:
        company = companies[0]
        differences = compare_fields(company, values, company_fields)
        if differences:
            notes.append('company=DIFFERENCE ' + '; '.join(differences))
        else:
            notes.append('company=SKIP')

    instruments = db.get('instruments', {
        'exchange_code': 'eq.IDX',
        'ticker': 'eq.' + ticker,
        'select': '*',
    })
    if len(instruments) > 1:
        raise RuntimeError(f'INSTRUMENT_NOT_UNIQUE: IDX/{ticker}')
    if instruments and instruments[0]['provider_symbol'] != values['provider_symbol']:
        raise RuntimeError(
            'INSTRUMENT_PROVIDER_CONFLICT: existing=%r, incoming=%r'
            % (instruments[0]['provider_symbol'], values['provider_symbol'])
        )
    if instruments:
        instrument = instruments[0]
        if instrument['company_id'] != company['id']:
            raise RuntimeError('INSTRUMENT_COMPANY_CONFLICT: existing company differs')
        notes.append('instrument=SKIP')
    else:
        instrument = db.insert('instruments', {
            'company_id': company['id'],
            'exchange_code': 'IDX',
            'ticker': ticker,
            'provider_symbol': values['provider_symbol'],
            'currency_code': 'IDR',
        })
        notes.append('instrument=INSERT')

    if values['sector_name'] is None and values['subsector_name'] is None:
        notes.append('sector=SKIP(no source sector)')
        return instrument['id'], notes
    sector_rows = db.get('sectors', {
        'taxonomy': 'eq.SECTORS_APP',
        'sector_name': 'eq.' + str(values['sector_name']),
        'subsector_name': 'eq.' + str(values['subsector_name']) if values['subsector_name'] is not None else 'is.null',
        'select': '*',
    })
    if len(sector_rows) > 1:
        raise RuntimeError('SECTOR_NOT_UNIQUE: source taxonomy row is ambiguous')
    if sector_rows:
        sector = sector_rows[0]
        notes.append('sector=SKIP')
    else:
        sector = db.insert('sectors', {
            'taxonomy': 'SECTORS_APP',
            'sector_name': values['sector_name'],
            'subsector_name': values['subsector_name'],
        })
        notes.append('sector=INSERT')

    sector_name = values['sector_name']
    subsector_name = values['subsector_name'] or ''
    relationship_key = f'IDX:{ticker}:SECTORS_APP:{sector_name}:{subsector_name}'
    classifications = db.get('instrument_sector_classifications', {
        'relationship_key': 'eq.' + relationship_key,
        'select': '*',
    })
    if len(classifications) > 1:
        raise RuntimeError(f'CLASSIFICATION_NOT_UNIQUE: {relationship_key}')
    if classifications:
        classification = classifications[0]
        if classification['instrument_id'] != instrument['id'] or classification['sector_id'] != sector['id']:
            raise RuntimeError(f'CLASSIFICATION_RELATIONSHIP_CONFLICT: {relationship_key}')
        notes.append('classification=SKIP')
    else:
        db.insert('instrument_sector_classifications', {
            'relationship_key': relationship_key,
            'instrument_id': instrument['id'],
            'sector_id': sector['id'],
            'effective_from': None,
            'effective_to': None,
            'source_payload_id': None,
        })
        notes.append('classification=INSERT(source_payload_id=NULL; Storage provenance limitation)')
    return instrument['id'], notes

def main() -> None:
    parser = argparse.ArgumentParser(description='Load raw identity from Supabase Storage into canonical tables')
    parser.add_argument('ticker')
    parser.add_argument('--ingestion-run-id', required=True, help='Raw-storage ingestion_runs.id')
    parser.add_argument(
        '--source',
        choices=['storage', 'local'],
        default='storage',
        help='Pipeline source. Default storage (local is debug-only).',
    )
    parser.add_argument('--raw-root', default=str(DEFAULT_RAW_ROOT), help='Debug-only local root')
    args = parser.parse_args()
    ticker = args.ticker.upper().replace('.JK', '')

    db = Supabase(required_env('SUPABASE_URL'), required_env('SUPABASE_SERVICE_ROLE_KEY'))

    if args.source == 'storage':
        storage = StorageClient(
            required_env('SUPABASE_URL'),
            required_env('SUPABASE_SERVICE_ROLE_KEY'),
        )
        payload, storage_path, checksum = load_info_from_storage(storage, ticker)
        source_label = f'{BUCKET}/{storage_path}'
    else:
        payload, local_path, checksum = load_info(Path(args.raw_root), ticker)
        storage_path = f'sectors/{ticker}/info/{INFO_FILE}'
        source_label = str(local_path)

    values = source_values(payload, ticker)
    provenance_id = verify_provenance(db, args.ingestion_run_id, ticker, storage_path, checksum)
    instrument_id, notes = load_identity(db, ticker, values)

    print(f'ticker={ticker}')
    print(f'source={args.source}')
    print(f'raw_source={source_label}')
    print(f'raw_checksum_sha256={checksum}')
    print(f'identity_ingestion_file_id={provenance_id}')
    print(f'company_identity={values["provider_identity"]}')
    print(f'company_legal_name={values["legal_name"]}')
    print(f'instrument_id={instrument_id}')
    for note in notes:
        print(note)
    print('provenance_limitation=instrument_sector_classifications has no ingestion_files FK; source_payload_id remains NULL')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'FAILED: {error}', file=sys.stderr)
        raise SystemExit(1) from error

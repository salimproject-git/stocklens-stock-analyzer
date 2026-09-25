#!/usr/bin/env python3
"""
ingest_raw_history.py
=====================

RAW INGESTION + HISTORY (single logical file per invocation).

Proves the flow:

    Sectors API -> raw JSON -> Supabase Storage -> ingestion history

Scope rules enforced by this script:
- Writes history ONLY into the existing baseline tables:
      `ingestion_runs`  = one ingestion execution/run
      `ingestion_files` = raw file that is stored in Storage
  No new history tables, no migrations, no canonical conversion.
- NEVER writes to canonical tables
  (companies, instruments, financial_periods, financial_facts,
   prices_daily, dividend_facts).
- Uploads the raw response AS-IS using the collector's existing write
  convention (json.dump, ensure_ascii=False, indent=2 - same as
  Phyton/01_download_sectors.py::write_json). No semantic transformation.
- NEVER overwrites an existing Storage object and never deletes anything.
- Refuses to run against a bucket other than `stocklens_raw`.

IDEMPOTENCY MATRIX (history = `ingestion_files` row for this storage_path)

    CASE A  history + Storage present
            -> SKIP API. Nothing is written at all.
            -> result: SKIP_ALREADY_INGESTED

    CASE B  history absent + Storage present
            -> do NOT hit the API, do NOT overwrite the raw file.
            -> register/repair history from the bytes already in Storage.
            -> result: REPAIRED_FROM_EXISTING_STORAGE

    CASE C  history absent + Storage absent
            -> HIT API, save raw AS-IS, upload, then record history.
            -> result: FETCHED_AND_STORED

    CASE D  history present + Storage absent
            -> never assume success; check whether the canonical target
               already exists.
            -> if canonical target is missing: RAW_MISSING_NEEDS_REFETCH
               (reported, no fake data created, no API call).

Credentials (server-side only, never printed):
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SECTORS_API_KEY

Usage:
    python .\\supabase\\ingest_raw_history.py --symbol AUTO
    python .\\supabase\\ingest_raw_history.py --symbol AUTO --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from upload_raw_storage_only import StorageClient

# ============================================================================
# CONFIG
# ============================================================================

BUCKET = 'stocklens_raw'
BASE_URL = 'https://api.sectors.app/v2'
COLLECTOR_VERSION = 'raw-history-ingest-0.1'

DEFAULT_RAW_ROOT = Path(r'D:\Stock Analyzer\Data\Raw')

SOURCE_CODE = 'SECTORS_APP'

# ----------------------------------------------------------------------------
# REQUEST CATALOG
# ----------------------------------------------------------------------------
# Every definition mirrors Phyton/01_download_sectors.py exactly (endpoint,
# method, parameters, local filename). No endpoint is invented here.
#
# `kind`:
#   'single'    -> one request -> one raw file
#   'per-date'  -> one request per report_date -> many raw files
#   'per-window'-> one request per 90-day window -> many raw files
#
# `sections` maps 1:1 to COMPANY_REPORT_SECTION_MAP in the collector.
# Local manifest produced by the collector (bookkeeping, not an API response).
MANIFEST_LOGICAL_NAME = 'manifest.json'

REQUEST_DEFINITIONS: dict[str, dict[str, Any]] = {
    # --- Company Report sections (GET /company/report/{SYMBOL}/) -----------
    'info': {
        'kind': 'single',
        'endpoint': '/company/report/{symbol}/',
        'method': 'GET',
        'sections': 'overview',
        'source_file_type': 'info',
        'logical_name': 'company_report_info.json',
        'one_file_per_request': True,
    },
    'annual': {
        'kind': 'single',
        'endpoint': '/company/report/{symbol}/',
        'method': 'GET',
        'sections': 'financials',
        'source_file_type': 'annual',
        'logical_name': 'company_report_annual.json',
        'one_file_per_request': True,
    },
    'dividend': {
        'kind': 'single',
        'endpoint': '/company/report/{symbol}/',
        'method': 'GET',
        'sections': 'dividend',
        'source_file_type': 'dividend',
        'logical_name': 'company_report_dividend.json',
        'one_file_per_request': True,
    },
    # --- Quarterly report dates (GET /company/get_quarterly_financial_dates/{SYMBOL}/)
    'quarterly-dates': {
        'kind': 'single',
        'endpoint': '/company/get_quarterly_financial_dates/{symbol}/',
        'method': 'GET',
        'sections': None,
        'source_file_type': 'quarterly',
        'logical_name': 'quarterly_financial_dates.json',
        'one_file_per_request': True,
    },
    # --- Quarterly financials (GET /financials/quarterly/{SYMBOL}/) --------
    'quarterly': {
        'kind': 'per-date',
        'endpoint': '/financials/quarterly/{symbol}/',
        'method': 'GET',
        'sections': None,
        'source_file_type': 'quarterly',
        'logical_name': '{report_date}.json',
        'one_file_per_request': True,
        'params': {'approx': 'true'},
    },
    # --- Daily prices (GET /daily/{SYMBOL}/) ------------------------------
    'daily': {
        'kind': 'per-window',
        'endpoint': '/daily/{symbol}/',
        'method': 'GET',
        'sections': None,
        'source_file_type': 'daily',
        'logical_name': '{window_start}_{window_end}.json',
        'one_file_per_request': True,
    },
    # --- Collector manifest (LOCAL bookkeeping, no API endpoint) ----------
    # Stored in Storage by the collector uploader; it has no API request.
    'manifest': {
        'kind': 'single',
        'endpoint': None,
        'method': None,
        'sections': None,
        'source_file_type': 'manifest',
        'logical_name': MANIFEST_LOGICAL_NAME,
        'one_file_per_request': True,
        'local_only': True,
    },
}

# Collector constants reused verbatim (Phyton/01_download_sectors.py).
MAX_WINDOW_DAYS = 90
DEFAULT_MIN_DATE = '2020-01-01'

# Retry policy copied from the collector (HTTP 429 backoff).
RETRY_DELAYS = [5, 10, 20, 40]
MAX_RETRIES = 4
TIMEOUT_SECONDS = 60


def required_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise RuntimeError(f'Environment variable belum di-set: {name}')
    return value


def company_report_endpoint(symbol: str) -> str:
    return f'/company/report/{symbol.upper()}/'


def build_endpoint(symbol: str, definition: dict[str, Any]) -> str:
    """Resolve the catalog endpoint template for one symbol."""
    return definition['endpoint'].format(symbol=symbol.upper())


def storage_path_for(
    symbol: str,
    definition: dict[str, Any],
    logical_name: str | None = None,
) -> str:
    """sectors/{TICKER}/{category}/{logical_name} (existing convention)."""
    name = logical_name or definition['logical_name']
    return (
        f'sectors/{symbol.upper()}/{definition["source_file_type"]}'
        f'/{name}'
    )


def local_path_for(
    raw_root: Path,
    symbol: str,
    definition: dict[str, Any],
    logical_name: str | None = None,
) -> Path:
    """Data\\Raw\\{TICKER}\\{logical_name} (collector convention)."""
    name = logical_name or definition['logical_name']
    return raw_root / symbol.upper() / name


def daily_window_name(window_start: str, window_end: str) -> str:
    return f'{window_start}_{window_end}.json'


def create_date_windows(start_date: date, end_date: date) -> list[tuple[str, str]]:
    """Same 90-day window logic as the collector (create_date_windows)."""
    if start_date > end_date:
        return []

    windows: list[tuple[str, str]] = []
    current = start_date

    while current <= end_date:
        window_end = min(
            current + timedelta(days=MAX_WINDOW_DAYS - 1),
            end_date,
        )
        windows.append((current.isoformat(), window_end.isoformat()))
        current = window_end + timedelta(days=1)

    return windows


def extract_quarterly_report_dates(raw_data: Any) -> list[str]:
    """
    Read report_date values from the quarterly dates response.

    Mirrors Phyton/01_download_sectors.py::extract_quarterly_report_dates:
    accepts plain YYYY-MM-DD strings, date-like keys, and nested containers.
    Never modifies the raw response.
    """
    found: set[str] = set()
    preferred_keys = {'report_date', 'date', 'reportDate'}

    def visit(value: Any, key_hint: str | None = None) -> None:
        if isinstance(value, str):
            try:
                parsed = date.fromisoformat(value)
            except ValueError:
                return

            normalized = parsed.isoformat()

            if key_hint in preferred_keys:
                found.add(normalized)
            elif value == normalized:
                found.add(normalized)

        elif isinstance(value, list):
            for item in value:
                visit(item, None)

        elif isinstance(value, dict):
            for key, item in value.items():
                visit(item, str(key))

    visit(raw_data)

    return sorted(found, reverse=True)


def extract_daily_window_dates(raw_data: Any) -> list[str]:
    """Read `date` values from a daily response (collector helper mirror)."""
    if not isinstance(raw_data, list):
        return []

    dates: list[str] = []

    for record in raw_data:
        if not isinstance(record, dict):
            continue

        raw_date = record.get('date')

        if not raw_date:
            continue

        try:
            dates.append(date.fromisoformat(str(raw_date)).isoformat())
        except ValueError:
            continue

    return dates


def write_json_raw(path: Path, data: Any) -> bytes:
    """
    Write the API response using the collector's existing raw convention and
    return the exact bytes written (atomic: .tmp then replace).
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.with_suffix(path.suffix + '.tmp')

    with temp_path.open('w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    temp_path.replace(path)

    return path.read_bytes()


def record_count_of(payload: Any) -> int:
    """Same convention as the existing uploader: list length, else 1."""
    return len(payload) if isinstance(payload, list) else 1


def describe_shape(payload: Any) -> str:
    if isinstance(payload, dict):
        return 'dict keys=' + ','.join(sorted(payload.keys()))
    if isinstance(payload, list):
        return f'list[{len(payload)}]'
    return type(payload).__name__


# ============================================================================
# SECTORS API CLIENT
# ============================================================================

class SectorsClient:
    """Minimal GET client using the collector's auth + retry conventions."""

    def __init__(self, api_key: str) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                'Authorization': api_key,
                'Accept': 'application/json',
                'User-Agent': 'StockAnalyzer-SectorsCollector/1.1',
            }
        )
        # Evidence of the most recent live API call (no credentials stored).
        self.last_call: dict[str, Any] = {}

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        url = f'{BASE_URL}{endpoint}'
        attempt = 0

        while True:
            started = time.time()
            response = self.session.get(url, params=params, timeout=TIMEOUT_SECONDS)
            elapsed_ms = int((time.time() - started) * 1000)

            if response.status_code == 429:
                if attempt >= MAX_RETRIES:
                    raise RuntimeError('API rate limit exhausted: ' + response.url)
                delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                attempt += 1
                print(
                    f'    RATE LIMIT (429). Waiting {delay}s before retry '
                    f'{attempt}/{MAX_RETRIES}...'
                )
                time.sleep(delay)
                continue

            if not response.ok:
                raise RuntimeError(
                    'API error (%s) %s: %s'
                    % (response.status_code, response.url, response.text[:1000])
                )

            self.last_call = {
                'request_url': response.url,
                'status_code': response.status_code,
                'elapsed_ms': elapsed_ms,
                'retries': attempt,
                'response_bytes': len(response.content),
                'response_sha256': hashlib.sha256(response.content).hexdigest(),
                'served_at_utc': datetime.now(timezone.utc).isoformat(),
            }

            return response.json()


# ============================================================================
# SUPABASE REST CLIENT (history only)
# ============================================================================

class SupabaseHistory:
    """REST access limited to ingestion_runs / ingestion_files / data_sources."""

    def __init__(self, url: str, key: str) -> None:
        self.rest_url = url.rstrip('/') + '/rest/v1'
        self.session = requests.Session()
        self.session.headers.update(
            {
                'apikey': key,
                'Authorization': 'Bearer ' + key,
            }
        )

    def rest(
        self,
        method: str,
        resource: str,
        params: dict[str, Any] | None = None,
        body: Any = None,
        prefer: str | None = None,
    ) -> Any:
        headers = {'Content-Type': 'application/json'}
        if prefer:
            headers['Prefer'] = prefer

        response = self.session.request(
            method,
            self.rest_url + '/' + resource,
            params=params,
            json=body,
            headers=headers,
            timeout=60,
        )

        if not response.ok:
            raise RuntimeError(
                'REST %s %s failed (%s): %s'
                % (method, resource, response.status_code, response.text[:1000])
            )

        return response.json() if response.text else None

    def source_id(self, source_code: str) -> str:
        rows = self.rest(
            'GET',
            'data_sources',
            {'source_code': 'eq.' + source_code, 'select': 'id', 'limit': '1'},
        )
        if not rows:
            raise RuntimeError(f'{source_code} missing from data_sources')
        return rows[0]['id']

    def history_for_path(self, storage_path: str) -> list[dict[str, Any]]:
        """`ingestion_files` rows registered for this exact storage path."""
        return self.rest(
            'GET',
            'ingestion_files',
            {
                'storage_path': 'eq.' + storage_path,
                'select': 'id,ingestion_run_id,storage_path,checksum_sha256,status,created_at',
                'order': 'created_at.desc',
            },
        ) or []

    def canonical_row_counts(self, symbol: str) -> dict[str, int]:
        """
        Read-only canonical check used by CASE D. Never inserts anything.
        """
        ticker = symbol.upper()
        provider_symbol = ticker + '.JK'

        companies = self.rest(
            'GET',
            'companies',
            {'provider_identity': 'eq.' + ticker, 'select': 'id'},
        ) or []

        instruments = self.rest(
            'GET',
            'instruments',
            {
                'or': f'(ticker.eq.{ticker},provider_symbol.eq.{provider_symbol})',
                'select': 'id',
            },
        ) or []

        counts = {
            'companies': len(companies),
            'instruments': len(instruments),
            'financial_periods': 0,
            'financial_facts': 0,
            'prices_daily': 0,
            'dividend_facts': 0,
        }

        instrument_ids = [row['id'] for row in instruments]

        if instrument_ids:
            for table in (
                'financial_periods',
                'financial_facts',
                'prices_daily',
                'dividend_facts',
            ):
                rows = self.rest(
                    'GET',
                    table,
                    {
                        'instrument_id': 'in.(' + ','.join(instrument_ids) + ')',
                        'select': 'id',
                    },
                ) or []
                counts[table] = len(rows)

        return counts

    def create_run(self, source_id: str, symbol: str) -> str:
        rows = self.rest(
            'POST',
            'ingestion_runs',
            body={
                'source_id': source_id,
                'symbol': symbol.upper(),
                'status': 'RUNNING',
                'collector_version': COLLECTOR_VERSION,
            },
            prefer='return=representation',
        )
        return rows[0]['id']

    def finish_run(self, run_id: str, status: str, error: str | None = None) -> None:
        from datetime import datetime, timezone

        body: dict[str, Any] = {
            'status': status,
            'completed_at': datetime.now(timezone.utc).isoformat(),
        }
        if error:
            body['error_message'] = error[:2000]

        self.rest(
            'PATCH',
            'ingestion_runs',
            {'id': 'eq.' + run_id},
            body,
            'return=minimal',
        )

    def record_file(self, run_id: str, item: dict[str, Any], status: str) -> dict[str, Any]:
        rows = self.rest(
            'POST',
            'ingestion_files',
            params={'on_conflict': 'ingestion_run_id,storage_path'},
            body={
                'ingestion_run_id': run_id,
                'source_file_type': item['source_file_type'],
                'storage_bucket': BUCKET,
                'storage_path': item['storage_path'],
                'checksum_sha256': item['checksum'],
                'record_count': item['record_count'],
                'first_record_date': item['first_record_date'],
                'last_record_date': item['last_record_date'],
                'status': status,
            },
            prefer='resolution=merge-duplicates,return=representation',
        )
        return rows[0]


# ============================================================================
# TARGET PLANNING
# ============================================================================

class Target:
    """One logical raw file: where it lives and how to fetch it if needed."""

    def __init__(
        self,
        request_name: str,
        source_file_type: str,
        logical_name: str,
        storage_path: str,
        local_path: Path,
        endpoint: str,
        params: dict[str, Any] | None,
    ) -> None:
        self.request_name = request_name
        self.source_file_type = source_file_type
        self.logical_name = logical_name
        self.storage_path = storage_path
        self.local_path = local_path
        self.endpoint = endpoint
        self.params = params


def metadata_for(payload: Any, source_file_type: str) -> dict[str, Any]:
    """Record metadata derived from the raw payload (no transformation)."""
    first_date = None
    last_date = None

    if source_file_type == 'daily':
        dates = extract_daily_window_dates(payload)
        if dates:
            first_date = min(dates)
            last_date = max(dates)

    return {
        'record_count': record_count_of(payload),
        'first_record_date': first_date,
        'last_record_date': last_date,
    }


def plan_single(
    symbol: str,
    name: str,
    definition: dict[str, Any],
    raw_root: Path,
) -> list[Target]:
    # Local-only artifacts (e.g. the collector manifest) have no API endpoint.
    endpoint = (
        None
        if not definition.get('endpoint')
        else build_endpoint(symbol, definition)
    )

    params: dict[str, Any] | None = None

    if definition.get('sections'):
        params = {'sections': definition['sections']}

    return [
        Target(
            request_name=name,
            source_file_type=definition['source_file_type'],
            logical_name=definition['logical_name'],
            storage_path=storage_path_for(symbol, definition),
            local_path=local_path_for(raw_root, symbol, definition),
            endpoint=endpoint,
            params=params,
        )
    ]


def plan_quarterly(
    symbol: str,
    definition: dict[str, Any],
    raw_root: Path,
    storage: StorageClient,
    report_dates: list[str],
) -> list[Target]:
    endpoint = build_endpoint(symbol, definition)
    targets: list[Target] = []

    for report_date in report_dates:
        logical_name = definition['logical_name'].format(report_date=report_date)

        targets.append(
            Target(
                request_name='quarterly',
                source_file_type=definition['source_file_type'],
                logical_name=logical_name,
                storage_path=storage_path_for(symbol, definition, logical_name),
                local_path=local_path_for(raw_root, symbol, definition, logical_name),
                endpoint=endpoint,
                params={'report_date': report_date, 'approx': 'true'},
            )
        )

    return targets


def plan_daily(
    symbol: str,
    definition: dict[str, Any],
    raw_root: Path,
    logical_names: list[str],
) -> list[Target]:
    endpoint = build_endpoint(symbol, definition)
    targets: list[Target] = []

    for logical_name in logical_names:
        window_start, _, window_end = logical_name.partition('_')
        window_end = window_end.replace('.json', '')

        targets.append(
            Target(
                request_name='daily',
                source_file_type=definition['source_file_type'],
                logical_name=logical_name,
                storage_path=storage_path_for(symbol, definition, logical_name),
                local_path=local_path_for(raw_root, symbol, definition, logical_name),
                endpoint=endpoint,
                params={'start': window_start, 'end': window_end},
            )
        )

    return targets


# ============================================================================
# RECONCILIATION
# ============================================================================

class Counters:
    def __init__(self) -> None:
        self.fetch = 0
        self.repair = 0
        self.skip = 0
        self.refetch = 0
        self.failed = 0
        self.api_calls = 0

    def line(self) -> str:
        return (
            'FETCH=%d REPAIR=%d SKIP=%d REFETCH=%d FAILED=%d API_CALLS=%d'
            % (
                self.fetch,
                self.repair,
                self.skip,
                self.refetch,
                self.failed,
                self.api_calls,
            )
        )


def fetch_and_store(
    target: Target,
    symbol: str,
    db: SupabaseHistory,
    storage: StorageClient,
    client: SectorsClient,
    source_id: str,
    counters: Counters,
    label: str,
) -> None:
    """
    CASE C / CASE D: hit the API once, save raw AS-IS, upload, record history.
    Never overwrites an existing Storage object.
    """
    run_id = db.create_run(source_id, symbol)

    try:
        print(f'    HIT API: GET {target.endpoint} params={target.params}')
        payload = client.get(target.endpoint, target.params)
        counters.api_calls += 1

        print('    --- LIVE API CALL EVIDENCE ---')
        print(f'    request_url    : {client.last_call["request_url"]}')
        print(f'    http_status    : {client.last_call["status_code"]}')
        print(f'    elapsed_ms     : {client.last_call["elapsed_ms"]}')
        print(f'    retries        : {client.last_call["retries"]}')
        print(f'    served_at_utc  : {client.last_call["served_at_utc"]}')
        print(f'    response_bytes : {client.last_call["response_bytes"]}')
        print(f'    raw_http_sha256: {client.last_call["response_sha256"]}')
        print(f'    response shape : {describe_shape(payload)}')
        print('    -----------------------------')

        # Collector write convention (json.dump ensure_ascii=False indent=2).
        content = write_json_raw(target.local_path, payload)
        checksum = hashlib.sha256(content).hexdigest()

        # Semantic proof (NOT byte-identical to the HTTP body by design).
        stored_payload = json.loads(content.decode('utf-8'))

        if stored_payload != payload:
            raise RuntimeError(
                'Stored JSON does not match the live API response payload.'
            )

        print(f'    Raw JSON saved : {target.local_path} ({len(content)} bytes)')
        print(f'    stored_sha256  : {checksum}')
        print('    stored payload identical to live API payload: True')

        if storage.object_info(BUCKET, target.storage_path) is not None:
            raise RuntimeError(
                'Storage object appeared during the run; refusing to overwrite: '
                + target.storage_path
            )

        storage.upload(BUCKET, target.storage_path, content)
        print(f'    Uploaded       : {BUCKET}/{target.storage_path}')

        metadata = metadata_for(payload, target.source_file_type)

        item = {
            'source_file_type': target.source_file_type,
            'storage_path': target.storage_path,
            'checksum': checksum,
            'record_count': metadata['record_count'],
            'first_record_date': metadata['first_record_date'],
            'last_record_date': metadata['last_record_date'],
        }

        file_row = db.record_file(run_id, item, 'UPLOADED')
        db.finish_run(run_id, 'SUCCESS')

        print(f'    RESULT: {label}')
        print(f'      ingestion_run id  : {run_id} (SUCCESS)')
        print(f'      ingestion_file id : {file_row["id"]} (UPLOADED)')
        print(f'      checksum stored   : {file_row["checksum_sha256"]}')
        print(f'      record_count      : {file_row["record_count"]}')

        if label == 'FETCHED_AND_STORED':
            counters.fetch += 1
        else:
            counters.refetch += 1

    except Exception as error:
        db.finish_run(run_id, 'FAILED', str(error))
        counters.failed += 1
        print(f'    RESULT: FAILED (run {run_id})')
        print(f'      error: {error}')


def repair_from_storage(
    target: Target,
    symbol: str,
    db: SupabaseHistory,
    storage: StorageClient,
    source_id: str,
    counters: Counters,
) -> None:
    """
    CASE B: Storage present, history absent.
    Register history from the bytes already in Storage. No API call, no
    overwrite.
    """
    raw = storage.download(BUCKET, target.storage_path)
    checksum = hashlib.sha256(raw).hexdigest()

    try:
        payload = json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeDecodeError) as error:
        counters.failed += 1
        print(f'    RESULT: RAW_INVALID_IN_STORAGE ({error})')
        return

    metadata = metadata_for(payload, target.source_file_type)

    run_id = db.create_run(source_id, symbol)

    try:
        item = {
            'source_file_type': target.source_file_type,
            'storage_path': target.storage_path,
            'checksum': checksum,
            'record_count': metadata['record_count'],
            'first_record_date': metadata['first_record_date'],
            'last_record_date': metadata['last_record_date'],
        }

        file_row = db.record_file(run_id, item, 'SKIPPED')
        db.finish_run(run_id, 'SUCCESS')
    except Exception as error:
        db.finish_run(run_id, 'FAILED', str(error))
        counters.failed += 1
        print(f'    RESULT: FAILED (run {run_id}): {error}')
        return

    counters.repair += 1

    print(f'    storage_sha256 : {checksum}')
    print(f'    JSON shape     : {describe_shape(payload)}')
    print('    RESULT: REPAIRED_FROM_EXISTING_STORAGE')
    print(f'      ingestion_run id  : {run_id} (SUCCESS)')
    print(f'      ingestion_file id : {file_row["id"]} (SKIPPED)')
    print('      Storage object    : NOT overwritten')


class LazySectorsClient:
    """Defers API-key loading and session creation until a fetch is needed."""

    def __init__(self) -> None:
        self._client: SectorsClient | None = None

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        if self._client is None:
            self._client = SectorsClient(required_env('SECTORS_API_KEY'))
        return self._client.get(endpoint, params)

    @property
    def last_call(self) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError('No API call has been made yet.')
        return self._client.last_call


def reconcile_target(
    target: Target,
    symbol: str,
    db: SupabaseHistory,
    storage: StorageClient,
    client: SectorsClient,
    source_id: str,
    counters: Counters,
    apply_changes: bool,
) -> None:
    object_info = storage.object_info(BUCKET, target.storage_path)
    history = db.history_for_path(target.storage_path)

    storage_present = object_info is not None
    history_present = len(history) > 0

    print(
        '  %-32s Storage=%-5s History=%-5s'
        % (target.logical_name, storage_present, history_present)
    )

    # CASE A ---------------------------------------------------------------
    if storage_present and history_present:
        counters.skip += 1
        print('    RESULT: SKIP_ALREADY_INGESTED (no API call, no write)')
        return

    # CASE B ---------------------------------------------------------------
    if storage_present and not history_present:
        print('    Storage present, history missing -> repair (no API call)')

        if not apply_changes:
            print('    RESULT: REPAIR_READY (dry run)')
            return

        repair_from_storage(target, symbol, db, storage, source_id, counters)
        return

    # CASE D ---------------------------------------------------------------
    if not storage_present and history_present:
        print('    Storage missing but history exists.')

        counts = db.canonical_row_counts(symbol)
        total_canonical = sum(counts.values())

        print(f'    canonical rows for {symbol}: {total_canonical}')

        if total_canonical == 0:
            print('    RESULT: RAW_MISSING_NEEDS_REFETCH')
            print('      canonical target absent -> raw must be re-fetched')
        else:
            print('    RESULT: RAW_MISSING_BUT_CANONICAL_PRESENT')

        if not apply_changes:
            print('    REFETCH_READY (dry run)')
            return

        fetch_and_store(
            target,
            symbol,
            db,
            storage,
            client,
            source_id,
            counters,
            'REFETCHED_AND_STORED',
        )
        return

    # CASE C ---------------------------------------------------------------
    print('    Storage absent, history absent -> fetch from API')

    if not apply_changes:
        print('    RESULT: FETCH_READY (dry run)')
        return

    fetch_and_store(
        target,
        symbol,
        db,
        storage,
        client,
        source_id,
        counters,
        'FETCHED_AND_STORED',
    )


# ============================================================================
# MAIN
# ============================================================================

def storage_names_for(storage: StorageClient, symbol: str, category: str) -> list[str]:
    prefix = f'sectors/{symbol.upper()}/{category}/'
    return sorted(
        path.split('/')[-1]
        for path in storage.walk(BUCKET)
        if path.startswith(prefix)
    )


def load_report_dates(
    symbol: str,
    raw_root: Path,
    definition: dict[str, Any],
    storage: StorageClient,
) -> list[str]:
    """
    Report dates come from the API-provided quarterly dates artifact.
    Prefer the local collector file, else read it back from Storage.
    Dates are never invented.
    """
    local = local_path_for(raw_root, symbol, definition)

    if local.exists():
        raw = local.read_bytes()
    else:
        storage_path = storage_path_for(symbol, definition)

        if storage.object_info(BUCKET, storage_path) is None:
            return []

        raw = storage.download(BUCKET, storage_path)

    return extract_quarterly_report_dates(json.loads(raw.decode('utf-8')))


def daily_window_names(
    symbol: str,
    raw_root: Path,
    storage: StorageClient,
) -> list[str]:
    """Windows the collector produced (local set) plus any already in Storage."""
    local_dir = raw_root / symbol.upper() / 'daily'

    names: set[str] = set()

    if local_dir.is_dir():
        names.update(path.name for path in local_dir.glob('*.json'))

    names.update(storage_names_for(storage, symbol, 'daily'))

    return sorted(names)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Raw ingestion + history reconciliation for one symbol.'
    )
    parser.add_argument('--symbol', default='AUTO', help='IDX ticker (default: AUTO)')
    parser.add_argument(
        '--request',
        dest='request_name',
        default='all',
        choices=['all'] + sorted(REQUEST_DEFINITIONS.keys()),
        help='Request family to reconcile (default: all)',
    )
    parser.add_argument(
        '--raw-root',
        default=str(DEFAULT_RAW_ROOT),
        help=f'Local raw root (default: {DEFAULT_RAW_ROOT})',
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Required to perform writes. Without it the script is read-only.',
    )
    args = parser.parse_args()

    symbol = args.symbol.upper().replace('.JK', '')
    raw_root = Path(args.raw_root)

    db = SupabaseHistory(
        required_env('SUPABASE_URL'),
        required_env('SUPABASE_SERVICE_ROLE_KEY'),
    )
    storage = StorageClient(
        required_env('SUPABASE_URL'),
        required_env('SUPABASE_SERVICE_ROLE_KEY'),
    )
    client = LazySectorsClient()

    bucket_info = storage.bucket(BUCKET)

    print('=' * 78)
    print('PHASE 1B - RAW INGESTION + HISTORY RECONCILIATION')
    print('=' * 78)
    print(f'Symbol        : {symbol}')
    print(f'Request scope : {args.request_name}')
    print(f'Raw root      : {raw_root}')
    print(
        'Storage bucket: %s  (private=%s)'
        % (bucket_info.get('id'), not bool(bucket_info.get('public')))
    )
    print(f'Apply         : {args.apply}')
    print('=' * 78)

    # ------------------------------------------------------------------
    # PLAN TARGETS
    # ------------------------------------------------------------------

    families = (
        [
            'info',
            'annual',
            'dividend',
            'quarterly-dates',
            'quarterly',
            'daily',
            'manifest',
        ]
        if args.request_name == 'all'
        else [args.request_name]
    )

    plan: list[tuple[str, list[Target]]] = []

    for name in families:
        definition = REQUEST_DEFINITIONS[name]

        if definition['kind'] == 'single':
            targets = plan_single(symbol, name, definition, raw_root)

        elif definition['kind'] == 'per-date':
            dates = load_report_dates(
                symbol,
                raw_root,
                REQUEST_DEFINITIONS['quarterly-dates'],
                storage,
            )
            print(f'  quarterly report dates from API artifact: {len(dates)}')
            targets = plan_quarterly(symbol, definition, raw_root, storage, dates)

        else:
            windows = daily_window_names(symbol, raw_root, storage)
            print(f'  daily windows from collector set + Storage: {len(windows)}')
            targets = plan_daily(symbol, definition, raw_root, windows)

        plan.append((name, targets))

    print()
    print('PLAN')
    for name, targets in plan:
        print(f'  {name:<18} {len(targets)} target file(s)')

    # ------------------------------------------------------------------
    # RECONCILE
    # ------------------------------------------------------------------

    counters = Counters()
    source_id = None

    if args.apply:
        source_id = db.source_id(SOURCE_CODE)

    for name, targets in plan:
        if not targets:
            continue

        print()
        print('-' * 78)
        print(f'FAMILY: {name}  ({len(targets)} file(s))')
        print('-' * 78)

        for target in targets:
            reconcile_target(
                target,
                symbol,
                db,
                storage,
                client,
                source_id or '',
                counters,
                args.apply,
            )

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------

    print()
    print('=' * 78)
    print('SUMMARY')
    print('=' * 78)
    print('  ' + counters.line())
    print(f'  Canonical tables touched: NO')


if __name__ == '__main__':
    main()



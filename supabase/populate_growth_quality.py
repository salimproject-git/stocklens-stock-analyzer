#!/usr/bin/env python3
"""Calculate and optionally persist annual and quarterly growth metrics.

The default mode is read-only: it fetches canonical AUTO financial data and
prints a row-count preview. Pass ``--apply`` to write one provenance-tracked
calculation run and its result rows to the existing Phase 4.2 result tables.

Annual Class-B metrics are calculated as one trailing-history snapshot per
annual period, capped at the requested maximum window (seven years by default).
Quarterly growth and quality metrics are calculated independently for every
available quarter. Use ``--ticker`` to select the instrument. This script does
not write MetricsClassification outputs because projected valuation inputs are
not stored in the canonical tables.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

import requests

SUPABASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SUPABASE_DIR.parent
if str(SUPABASE_DIR) not in sys.path:
    sys.path.insert(0, str(SUPABASE_DIR))

from calculate_quarterly_growth_quality import (  # noqa: E402
    ANNUAL_GROWTH_METRICS,
    calculate_annual_growth_outputs,
    calculate_quarterly_outputs,
)
from calculation_registry import CODE_VERSION  # noqa: E402
from calculation_v1_common import (  # noqa: E402
    CalculationError,
    SupabaseRest,
    calculation_contract,
    format_decimal,
)

METHOD_CODE = 'QUARTERLY_GROWTH_QUALITY'
METHOD_VERSION = '1.0.0'
ANNUAL_TABLE = 'calc_annual_growth_quality'
QUARTERLY_GROWTH_TABLE = 'calc_quarterly_growth'
QUARTERLY_QUALITY_TABLE = 'calc_quarterly_quality'
RESULT_TABLES = (ANNUAL_TABLE, QUARTERLY_GROWTH_TABLE, QUARTERLY_QUALITY_TABLE)
ANNUAL_PERIOD_SELECT = (
    'id,period_type,period_label,period_start,period_end,report_date,'
    'available_date,period_basis,statement_scope'
)
FACT_SELECT = (
    'id,financial_period_id,metric_code,value_numeric,quality_status,'
    'unit_code,revision_key,supersedes_fact_id'
)
UPSERT_PREFER = 'resolution=merge-duplicates,return=minimal'
PAGE_SIZE = 1000


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries without printing their contents."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def _get_json(session: requests.Session, url: str, **kwargs: Any) -> Any:
    response = session.get(url, timeout=120, **kwargs)
    if not response.ok:
        raise CalculationError(f'SUPABASE_READ_FAILED: HTTP {response.status_code}')
    return response.json()


def _paged_get(
    session: requests.Session,
    rest_url: str,
    table: str,
    params: dict[str, str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = _get_json(
            session,
            f'{rest_url}/{table}',
            params={
                **params,
                'limit': str(PAGE_SIZE),
                'offset': str(offset),
            },
        )
        if not isinstance(page, list):
            raise CalculationError(f'{table}: NON_LIST_RESPONSE')
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def _normalise_fact(fact: Mapping[str, Any]) -> dict[str, Any]:
    """Keep exact decimal input text stable in calculation and run hashes."""
    row = dict(fact)
    value = row.get('value_numeric')
    if value is not None:
        row['value_numeric'] = format_decimal(Decimal(str(value)))
    return row


def _prepare_outputs(
    *,
    periods: Sequence[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
    instrument_id: str,
    run_id: str,
    methodology_version_id: str,
    years_available: int,
) -> dict[str, list[dict[str, Any]]]:
    annual_periods = [p for p in periods if p.get('period_type') == 'ANNUAL']
    quarter_periods = [p for p in periods if p.get('period_type') == 'QUARTER']
    if not annual_periods:
        raise CalculationError('AUTO_ANNUAL_PERIODS_MISSING')
    if not quarter_periods:
        raise CalculationError('AUTO_QUARTER_PERIODS_MISSING')

    annual_periods = sorted(
        (p for p in periods if p.get('period_type') == 'ANNUAL'),
        key=lambda p: (str(p.get('period_end') or ''), str(p.get('period_label') or '')),
    )
    annual: list[dict[str, Any]] = []
    for end_index, target_period in enumerate(annual_periods):
        # Each annual row set is a reproducible snapshot as of that fiscal year.
        # Passing only the trailing N annual periods keeps year selectors useful
        # while preserving the requested maximum window for the latest year.
        start_index = max(0, end_index + 1 - years_available)
        window_periods = annual_periods[start_index:end_index + 1]
        snapshot_rows = calculate_annual_growth_outputs(
            window_periods,
            facts,
            instrument_id,
            run_id,
            methodology_version_id=methodology_version_id,
            years_available=None,
        )
        if any(row.get('financial_period_id') != str(target_period['id']) for row in snapshot_rows):
            raise CalculationError(
                'ANNUAL_SNAPSHOT_PERIOD_MISMATCH: '
                f"expected {target_period.get('period_label')}"
            )
        annual.extend(snapshot_rows)
    quarterly_growth, quarterly_quality = calculate_quarterly_outputs(
        periods,
        facts,
        instrument_id,
        run_id,
        methodology_version_id=methodology_version_id,
    )
    return {
        ANNUAL_TABLE: annual,
        QUARTERLY_GROWTH_TABLE: quarterly_growth,
        QUARTERLY_QUALITY_TABLE: quarterly_quality,
    }


def _input_snapshot(
    *,
    ticker: str,
    instrument_id: str,
    periods: Sequence[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
    years_available: int,
) -> dict[str, Any]:
    sorted_periods = sorted(
        (dict(p) for p in periods),
        key=lambda p: (str(p.get('period_end') or ''), str(p.get('period_type') or '')),
    )
    sorted_facts = sorted(
        (_normalise_fact(f) for f in facts),
        key=lambda f: (
            str(f.get('financial_period_id') or ''),
            str(f.get('metric_code') or ''),
            str(f.get('revision_key') or ''),
        ),
    )
    return {
        'ticker': ticker,
        'instrument_id': instrument_id,
        'snapshot_period_end': max(str(p.get('period_end') or '') for p in periods),
        'years_available': years_available,
        'point_in_time_status': 'UNVERIFIED_REPORT_AND_AVAILABLE_DATES_MISSING',
        'periods': sorted_periods,
        'facts': sorted_facts,
    }


def _load_live_source(
    db: SupabaseRest,
    ticker: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], str]:
    instrument_rows = db.get_all(
        'instruments',
        {
            'ticker': 'eq.' + ticker,
            'select': 'id,ticker,company_name,sector_name',
        },
    )
    if len(instrument_rows) != 1:
        raise CalculationError(f'INSTRUMENT_NOT_FOUND_OR_NOT_UNIQUE: {ticker}')
    instrument = instrument_rows[0]
    instrument_id = str(instrument['id'])

    periods = _paged_get(
        db.session,
        db.rest_url,
        'financial_periods',
        {
            'instrument_id': 'eq.' + instrument_id,
            'select': ANNUAL_PERIOD_SELECT,
            'order': 'period_end.asc',
        },
    )
    period_ids = [str(period['id']) for period in periods]
    facts: list[dict[str, Any]] = []
    # PostgREST's `in` filter supports a bounded list; AUTO has only 33 periods.
    for offset in range(0, len(period_ids), 100):
        batch = period_ids[offset:offset + 100]
        facts.extend(
            _paged_get(
                db.session,
                db.rest_url,
                'financial_facts',
                {
                    'financial_period_id': 'in.(' + ','.join(batch) + ')',
                    'revision_key': 'eq.CURRENT',
                    'select': FACT_SELECT,
                    'order': 'financial_period_id.asc,metric_code.asc',
                },
            )
        )
    return instrument, periods, facts, instrument_id


def _methodology_version_id(db: SupabaseRest) -> str:
    rows = db.get_all(
        'methodology_versions',
        {
            'method_code': 'eq.' + METHOD_CODE,
            'method_version': 'eq.' + METHOD_VERSION,
            'select': 'id,status',
        },
    )
    if len(rows) != 1:
        raise CalculationError('GROWTH_QUALITY_METHODOLOGY_VERSION_NOT_FOUND')
    if rows[0].get('status') not in ('DRAFT', 'PUBLISHED'):
        raise CalculationError('GROWTH_QUALITY_METHODOLOGY_NOT_EXECUTABLE')
    return str(rows[0]['id'])


def _assert_source(
    periods: Sequence[Mapping[str, Any]],
    years_available: int,
) -> None:
    annual = sorted(
        (p for p in periods if p.get('period_type') == 'ANNUAL'),
        key=lambda p: str(p.get('period_end') or ''),
    )
    quarters = [p for p in periods if p.get('period_type') == 'QUARTER']
    if len(annual) < years_available:
        raise CalculationError(
            f'ANNUAL_HISTORY_TOO_SHORT: {len(annual)} < {years_available}'
        )
    if len(quarters) == 0:
        raise CalculationError('QUARTER_PERIODS_MISSING')
    if any(p.get('period_type') not in ('ANNUAL', 'QUARTER') for p in periods):
        raise CalculationError('UNSUPPORTED_AUTO_PERIOD_TYPE')


def _insert_run(
    db: SupabaseRest,
    *,
    run_contract: Mapping[str, Any],
    methodology_version_id: str,
    instrument_id: str,
) -> tuple[str, bool]:
    existing = db.get_all(
        'calculation_runs',
        {
            'idempotency_key': 'eq.' + str(run_contract['idempotency_key']),
            'select': 'id,status',
        },
    )
    if existing:
        run_id = str(existing[0]['id'])
        if existing[0]['status'] == 'SUCCEEDED':
            return run_id, True
        db.request(
            'PATCH',
            'calculation_runs',
            params={'id': 'eq.' + run_id},
            payload={
                'status': 'RUNNING',
                'error_message': None,
                'completed_at': None,
            },
        )
        return run_id, False

    payload = {
        **dict(run_contract),
        'status': 'RUNNING',
        'scope_type': 'INSTRUMENT',
        'scope_id': instrument_id,
        'methodology_version_id': methodology_version_id,
    }
    created = db.request(
        'POST',
        'calculation_runs',
        payload=payload,
        headers={'Prefer': 'return=representation'},
    )
    if not isinstance(created, list) or len(created) != 1:
        raise CalculationError('CALCULATION_RUN_CREATE_FAILED')
    return str(created[0]['id']), False


def _persist_rows(
    db: SupabaseRest,
    table: str,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    if not rows:
        return
    for offset in range(0, len(rows), 500):
        batch = [dict(row) for row in rows[offset:offset + 500]]
        db.request(
            'POST',
            table,
            params={
                'on_conflict': (
                    'calculation_run_id,instrument_id,financial_period_id,metric_code'
                )
            },
            payload=batch,
            headers={'Prefer': UPSERT_PREFER},
        )


def _verify_persisted(
    db: SupabaseRest,
    run_id: str,
    expected_counts: Mapping[str, int],
) -> None:
    for table, expected in expected_counts.items():
        actual = len(
            db.get_all(
                table,
                {
                    'calculation_run_id': 'eq.' + run_id,
                    'select': 'id',
                },
            )
        )
        if actual != expected:
            raise CalculationError(
                f'PERSISTED_ROW_COUNT_MISMATCH: {table} expected={expected} actual={actual}'
            )


def _mark_run(
    db: SupabaseRest,
    run_id: str,
    *,
    status: str,
    error_message: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        'status': status,
        'error_message': error_message,
    }
    if status in ('SUCCEEDED', 'PARTIAL', 'FAILED'):
        payload['completed_at'] = datetime.now(timezone.utc).isoformat()
    db.request(
        'PATCH',
        'calculation_runs',
        params={'id': 'eq.' + run_id},
        payload=payload,
    )


def _load_offline_fixture(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], str]:
    fixture = json.loads(path.read_text(encoding='utf-8'))
    periods = fixture.get('periods')
    facts = fixture.get('facts')
    if not isinstance(periods, list) or not isinstance(facts, list):
        raise CalculationError('OFFLINE_FIXTURE_SHAPE_INVALID')
    ticker = str(fixture.get('ticker') or 'AUTO').upper()
    instrument = {
        'id': 'offline-instrument-' + ticker.lower(),
        'ticker': ticker,
        'company_name': 'offline fixture',
        'sector_name': 'Consumer Cyclicals',
    }
    return instrument, periods, facts, str(instrument['id'])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ticker', default='AUTO', help='Instrument ticker (default: AUTO).')
    parser.add_argument('--years-available', type=int, default=7)
    parser.add_argument('--apply', action='store_true', help='Persist results to Supabase.')
    parser.add_argument(
        '--offline-fixture',
        type=Path,
        help='Calculate from a local JSON fixture; never connects to or writes Supabase.',
    )
    args = parser.parse_args(argv)
    ticker = args.ticker.strip().upper()
    if args.years_available < 1:
        parser.error('--years-available must be a positive integer.')
    if args.offline_fixture and args.apply:
        parser.error('--offline-fixture cannot be combined with --apply.')

    if args.offline_fixture:
        instrument, periods, facts, instrument_id = _load_offline_fixture(args.offline_fixture)
        methodology_version_id = 'offline-methodology-version'
        db = None
    else:
        load_env_file(REPO_ROOT / '.env')
        db = SupabaseRest(
            os.getenv('SUPABASE_URL', ''),
            os.getenv('SUPABASE_SERVICE_ROLE_KEY', ''),
        )
        instrument, periods, facts, instrument_id = _load_live_source(db, ticker)
        methodology_version_id = _methodology_version_id(db)

    _assert_source(periods, args.years_available)
    snapshot = _input_snapshot(
        ticker=ticker,
        instrument_id=instrument_id,
        periods=periods,
        facts=facts,
        years_available=args.years_available,
    )
    annual_periods = [p for p in periods if p.get('period_type') == 'ANNUAL']
    quarter_periods = [p for p in periods if p.get('period_type') == 'QUARTER']
    latest_annual = max(annual_periods, key=lambda p: str(p.get('period_end') or ''))

    if args.apply and db is not None:
        run_contract = calculation_contract(
            calculation_type=METHOD_CODE,
            methodology_version_id=methodology_version_id,
            code_version=CODE_VERSION,
            source_cutoff_date=None,
            source_ingestion_run_id=None,
            scope_type='INSTRUMENT',
            scope_id=instrument_id,
            input_snapshot=snapshot,
        )
        run_id, already_succeeded = _insert_run(
            db,
            run_contract=run_contract,
            methodology_version_id=methodology_version_id,
            instrument_id=instrument_id,
        )
        if already_succeeded:
            print(f'Already populated: run={run_id} (idempotent no-op).')
            return 0
    else:
        run_id = 'offline-preview'

    output = _prepare_outputs(
        periods=periods,
        facts=facts,
        instrument_id=instrument_id,
        run_id=run_id,
        methodology_version_id=methodology_version_id,
        years_available=args.years_available,
    )
    counts = {table: len(rows) for table, rows in output.items()}
    expected_annual_metrics = {row['metric_code'] for row in output[ANNUAL_TABLE]}
    if expected_annual_metrics != set(ANNUAL_GROWTH_METRICS):
        if args.apply and db is not None:
            _mark_run(db, run_id, status='FAILED', error_message='ANNUAL_METRIC_SET_MISMATCH')
        raise CalculationError('ANNUAL_METRIC_SET_MISMATCH')

    print(f"Ticker: {ticker} ({instrument.get('company_name') or 'company name unavailable'})")
    print(
        f"Source periods: {len(annual_periods)} annual, {len(quarter_periods)} quarterly "
        f"(through {max(str(p.get('period_end') or '') for p in periods)})"
    )
    print(
        f"Annual metrics: {counts[ANNUAL_TABLE]} rows across {len(annual_periods)} year snapshots; "
        f"up to {args.years_available} years through {latest_annual.get('period_label')}"
    )
    print(
        f"Quarterly metrics: {counts[QUARTERLY_GROWTH_TABLE]} growth rows + "
        f"{counts[QUARTERLY_QUALITY_TABLE]} quality rows"
    )
    print('Classification final: not written (projection/valuation inputs are unavailable).')
    print('Point-in-time: not claimed; report_date and available_date are missing.')

    if not args.apply or db is None:
        print('DRY RUN: no Supabase rows were written.')
        return 0

    try:
        for table in RESULT_TABLES:
            _persist_rows(db, table, output[table])
        _verify_persisted(db, run_id, counts)
        _mark_run(db, run_id, status='SUCCEEDED')
    except Exception as error:
        safe_error = str(error)[:1000]
        try:
            _mark_run(db, run_id, status='PARTIAL', error_message=safe_error)
        except Exception:
            pass
        raise

    print(f'Persisted and verified: run={run_id}; rows={sum(counts.values())}.')
    for table, count in counts.items():
        print(f'  {table}: {count}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
#!/usr/bin/env python3
"""Calculate and optionally persist annual and quarterly growth metrics.

The default mode is read-only: it fetches canonical AUTO financial data and
prints a row-count preview. Pass ``--apply`` to write one provenance-tracked
calculation run and its result rows to the existing Phase 4.2 result tables.

Annual Class-B metrics are calculated as one trailing-history snapshot per
annual period, capped at the requested maximum window (seven years by default).
Quarterly growth and quality metrics are calculated independently for every
available quarter. Use ``--ticker`` to select the instrument.

MetricsClassification is written by ``populate_metrics_classification.py``,
which derives the classifier inputs from these annual results plus the active
projection scenario. Keeping the two runs separate keeps each run's
``input_snapshot`` limited to what that calculation actually consumed.
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
    ANNUAL_RATIO_METRICS,
    calculate_annual_growth_outputs,
    calculate_annual_ratio_outputs,
    calculate_quarterly_outputs,
    latest_share_count,
)
from calculation_registry import CODE_VERSION  # noqa: E402
from calculation_methodology_registry import (  # noqa: E402
    growth_quality_methodology_seed,
)
from calculation_v1_common import (  # noqa: E402
    CalculationError,
    SupabaseRest,
    calculation_contract,
    format_decimal,
)

METHOD_CODE = 'QUARTERLY_GROWTH_QUALITY'
#: 1.0.0 -> 1.1.0: the annual ratio layer was added, and EPS/BVPS changed divisor.
#:
#: `calc_annual_growth_quality` gained nine annual ratio metrics in a new table
#: (`calc_annual_ratios`), and EPS/BVPS moved from a per-snapshot share count to
#: the workbook's single `=Proj_Shares` value. The second change alters stored
#: numbers, so it needs a new version rather than overwriting 1.0.0 - the rule in
#: docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md ("jangan menimpa versi lama; naikkan
#: versi bila rumus berubah"). Runs already written keep pointing at 1.0.0.
METHOD_VERSION = '1.1.0'
ANNUAL_TABLE = 'calc_annual_growth_quality'
ANNUAL_RATIO_TABLE = 'calc_annual_ratios'
QUARTERLY_GROWTH_TABLE = 'calc_quarterly_growth'
QUARTERLY_QUALITY_TABLE = 'calc_quarterly_quality'
RESULT_TABLES = (
    ANNUAL_TABLE,
    ANNUAL_RATIO_TABLE,
    QUARTERLY_GROWTH_TABLE,
    QUARTERLY_QUALITY_TABLE,
)
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
    dividend_rows: Sequence[Mapping[str, Any]] = (),
    prices: Sequence[Mapping[str, Any]] = (),
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

    # The workbook's shares row is `=Proj_Shares` in *every* column, so one figure
    # divides every year of the table - 2021's EPS uses the newest reported count,
    # not 2021's own. It is therefore resolved once here, from the full annual
    # history, and handed to every snapshot below. Resolving it per snapshot would
    # silently fall back to that year's own count and change the number
    # (ITMG 2021 EPS: 6139.41 instead of the workbook's 6009.02).
    all_annual_periods = sorted(
        (p for p in periods if p.get('period_type') == 'ANNUAL'),
        key=lambda p: (str(p.get('period_end') or ''), str(p.get('period_label') or '')),
        reverse=True,
    )
    run_shares, run_shares_flags = latest_share_count(all_annual_periods, facts)

    annual: list[dict[str, Any]] = []
    annual_ratios: list[dict[str, Any]] = []
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
            dividend_rows=dividend_rows,
            prices=prices,
        )
        if any(row.get('financial_period_id') != str(target_period['id']) for row in snapshot_rows):
            raise CalculationError(
                'ANNUAL_SNAPSHOT_PERIOD_MISMATCH: '
                f"expected {target_period.get('period_label')}"
            )
        annual.extend(snapshot_rows)

        # The ratio layer is the same trailing-history snapshot, so a year's
        # ROE / margin / EPS is stored on that year's own row rather than only on
        # the latest one. The growth layer's window is reused verbatim so the two
        # cannot disagree about which years a snapshot covers.
        ratio_rows = calculate_annual_ratio_outputs(
            window_periods,
            facts,
            instrument_id,
            run_id,
            methodology_version_id=methodology_version_id,
            years_available=None,
            shares=run_shares,
            shares_flags=run_shares_flags,
        )
        if any(row.get('financial_period_id') != str(target_period['id']) for row in ratio_rows):
            raise CalculationError(
                'ANNUAL_RATIO_SNAPSHOT_PERIOD_MISMATCH: '
                f"expected {target_period.get('period_label')}"
            )
        annual_ratios.extend(ratio_rows)

    quarterly_growth, quarterly_quality = calculate_quarterly_outputs(
        periods,
        facts,
        instrument_id,
        run_id,
        methodology_version_id=methodology_version_id,
    )
    return {
        ANNUAL_TABLE: annual,
        ANNUAL_RATIO_TABLE: annual_ratios,
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
    dividend_rows: Sequence[Mapping[str, Any]] = (),
    prices: Sequence[Mapping[str, Any]] = (),
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
    # The dividend ratios read DPS and the year-end close, so both enter the
    # input snapshot. Without them, a changed dividend or a restated price would
    # keep the same idempotency key and the stored ratio would go stale.
    sorted_dividends = sorted(
        (
            {
                'fact_type': str(row.get('fact_type') or ''),
                'period_year': row.get('period_year'),
                'amount_per_share': (
                    None if row.get('amount_per_share') is None
                    else format_decimal(Decimal(str(row.get('amount_per_share'))))
                ),
            }
            for row in dividend_rows
        ),
        key=lambda row: (str(row.get('fact_type') or ''), str(row.get('period_year') or '')),
    )
    sorted_prices = sorted(
        (
            {
                'trading_date': str(row.get('trading_date') or ''),
                'close_price': (
                    None if row.get('close_price') is None
                    else format_decimal(Decimal(str(row.get('close_price'))))
                ),
            }
            for row in prices
        ),
        key=lambda row: str(row.get('trading_date') or ''),
    )
    return {
        'ticker': ticker,
        'instrument_id': instrument_id,
        'snapshot_period_end': max(str(p.get('period_end') or '') for p in periods),
        'years_available': years_available,
        'point_in_time_status': 'UNVERIFIED_REPORT_AND_AVAILABLE_DATES_MISSING',
        'periods': sorted_periods,
        'facts': sorted_facts,
        'dividends': sorted_dividends,
        'prices': sorted_prices,
    }


def _load_live_source(
    db: SupabaseRest,
    ticker: str,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    str,
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
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

    # Dividend ratios need DPS (per fiscal year) and the year-end close, which is
    # a price basis. Both are read here rather than in the engine because the
    # engine is pure: it must not know how to query the database.
    dividend_rows = _paged_get(
        db.session,
        db.rest_url,
        'dividend_facts',
        {
            'instrument_id': 'eq.' + instrument_id,
            'select': 'fact_type,period_year,amount_per_share,currency_code',
            'order': 'period_year.asc',
        },
    )
    prices = _paged_get(
        db.session,
        db.rest_url,
        'prices_daily',
        {
            'instrument_id': 'eq.' + instrument_id,
            'select': 'trading_date,close_price',
            'order': 'trading_date.asc',
        },
    )
    return instrument, periods, facts, instrument_id, dividend_rows, prices


def _methodology_version_id(db: SupabaseRest) -> str:
    """Find (or register) the `QUARTERLY_GROWTH_QUALITY` methodology version.

    Mirrors `run_backtest._required_methodology_id`: the registry row is created
    from the same definition the code uses, so its hashes are always reproducible.
    If the row already exists its stored hashes are compared first - a mismatch
    means the local definition changed without a version bump, and results already
    written would no longer be reproducible. That is an error, not a silent
    overwrite; raise `METHOD_VERSION` instead (1.0.0 -> 1.1.0 for the annual ratio
    layer and the workbook share basis).

    Runs already written keep pointing at their own version, so adding a version
    never changes the meaning of stored results.
    """
    seed = growth_quality_methodology_seed()
    rows = db.get_all(
        'methodology_versions',
        {
            'method_code': 'eq.' + METHOD_CODE,
            'method_version': 'eq.' + METHOD_VERSION,
            'select': 'id,status,formula_hash,parameter_hash',
        },
    )
    if len(rows) > 1:
        raise CalculationError('GROWTH_QUALITY_METHODOLOGY_NOT_UNIQUE')

    if not rows:
        created = db.request(
            'POST',
            'methodology_versions',
            payload={
                'method_code': seed['method_code'],
                'method_version': seed['method_version'],
                'method_name': seed['method_name'],
                'description': seed['description'],
                'formula_text': seed['formula_text'],
                'formula_hash': seed['formula_hash'],
                'parameter_spec': seed['parameter_spec'],
                'parameter_hash': seed['parameter_hash'],
                'code_version': seed['code_version'],
                'input_vocabulary_version': seed['input_vocabulary_version'],
                'status': seed['status'],
            },
            headers={'Prefer': 'return=representation'},
        )
        if not isinstance(created, list) or len(created) != 1:
            raise CalculationError('GROWTH_QUALITY_METHODOLOGY_CREATE_FAILED')
        return str(created[0]['id'])

    row = rows[0]
    if (
        row.get('formula_hash') != seed['formula_hash']
        or row.get('parameter_hash') != seed['parameter_hash']
    ):
        raise CalculationError('GROWTH_QUALITY_METHODOLOGY_REGISTRY_DRIFT')
    if row.get('status') not in ('DRAFT', 'PUBLISHED'):
        raise CalculationError('GROWTH_QUALITY_METHODOLOGY_NOT_EXECUTABLE')
    return str(row['id'])


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
        dividend_rows: list[dict[str, Any]] = []
        prices: list[dict[str, Any]] = []
        methodology_version_id = 'offline-methodology-version'
        db = None
    else:
        load_env_file(REPO_ROOT / '.env')
        db = SupabaseRest(
            os.getenv('SUPABASE_URL', ''),
            os.getenv('SUPABASE_SERVICE_ROLE_KEY', ''),
        )
        (
            instrument,
            periods,
            facts,
            instrument_id,
            dividend_rows,
            prices,
        ) = _load_live_source(db, ticker)
        methodology_version_id = _methodology_version_id(db)

    _assert_source(periods, args.years_available)
    snapshot = _input_snapshot(
        ticker=ticker,
        instrument_id=instrument_id,
        periods=periods,
        facts=facts,
        years_available=args.years_available,
        dividend_rows=dividend_rows,
        prices=prices,
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
        dividend_rows=dividend_rows,
        prices=prices,
    )
    counts = {table: len(rows) for table, rows in output.items()}
    expected_annual_metrics = {row['metric_code'] for row in output[ANNUAL_TABLE]}
    if expected_annual_metrics != set(ANNUAL_GROWTH_METRICS):
        if args.apply and db is not None:
            _mark_run(db, run_id, status='FAILED', error_message='ANNUAL_METRIC_SET_MISMATCH')
        raise CalculationError('ANNUAL_METRIC_SET_MISMATCH')

    # The ratio layer is verified the same way, so a metric that stops being
    # emitted fails loudly instead of quietly disappearing from the payload.
    expected_ratio_metrics = {row['metric_code'] for row in output[ANNUAL_RATIO_TABLE]}
    if expected_ratio_metrics != set(ANNUAL_RATIO_METRICS):
        if args.apply and db is not None:
            _mark_run(db, run_id, status='FAILED', error_message='ANNUAL_RATIO_METRIC_SET_MISMATCH')
        raise CalculationError('ANNUAL_RATIO_METRIC_SET_MISMATCH')

    # Every ratio row must carry its unit, because the unit is what stops a
    # consumer from reading a margin as an amount.
    if any(not row.get('unit_code') for row in output[ANNUAL_RATIO_TABLE]):
        if args.apply and db is not None:
            _mark_run(db, run_id, status='FAILED', error_message='ANNUAL_RATIO_UNIT_MISSING')
        raise CalculationError('ANNUAL_RATIO_UNIT_MISSING')

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
        f"Annual ratios: {counts[ANNUAL_RATIO_TABLE]} rows across {len(annual_periods)} year snapshots "
        f"({len(ANNUAL_RATIO_METRICS)} metrics per snapshot)"
    )
    print(
        f"Quarterly metrics: {counts[QUARTERLY_GROWTH_TABLE]} growth rows + "
        f"{counts[QUARTERLY_QUALITY_TABLE]} quality rows"
    )
    print(
        'Classification final: written separately by '
        'populate_metrics_classification.py (derives its inputs from these rows).'
    )
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
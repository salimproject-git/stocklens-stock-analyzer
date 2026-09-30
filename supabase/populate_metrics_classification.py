#!/usr/bin/env python3
"""Run the stock-type classifier and persist its output.

This closes the gap ``populate_growth_quality.py`` used to report as
"Classification final: not written". It derives the classifier inputs from
canonical data (``derive_classifier_inputs``), evaluates the workbook rules
(``classify_metrics_classification``) and stores one provenance-tracked row per
metric code in ``public.calc_metrics_classification``.

Once a ticker has a stored classification, ``calculate_valuation.py`` no longer
needs a hand-passed ``--stock-type``.

Methodology ownership
---------------------
The result is recorded against the existing ``CLASSIFICATION_DESCRIPTIVE``
methodology: "Descriptive labels derived from calculation results. No
recommendation, buy or sell semantics." That is exactly what this is. The
classifier's own thresholds stay versioned in ``public.calculation_parameters``
under the ``STOCK_TYPE_CLASSIFIER`` owner, which is the established pattern for
parameter groups that have no test-suite methodology code of their own.

Confidence
----------
``CLASSIFICATION_CONFIDENCE`` is stored with the flag
``REGISTRY_VERSION_UPDATE_REQUIRED``. The B83 confidence rule is implemented and
verified, but its registry entry is deliberately still
``UNRESOLVED_DEFINITION``, so the flag records that rather than hiding it.

Default is a dry run; pass ``--apply`` to persist.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

SUPABASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SUPABASE_DIR.parent
if str(SUPABASE_DIR) not in sys.path:
    sys.path.insert(0, str(SUPABASE_DIR))

from calculate_quarterly_growth_quality import (  # noqa: E402
    classify_metrics_classification,
)
from calculation_registry import CODE_VERSION  # noqa: E402
from calculation_v1_common import (  # noqa: E402
    CalculationError,
    SupabaseRest,
    calculation_contract,
    format_decimal,
)
from derive_classifier_inputs import (  # noqa: E402
    CLASSIFIER_INPUT_CODES,
    DIRECT_INPUT_CODES,
    GROWTH_ROW_INPUT_CODES,
    load_env_file,
    load_live_inputs,
)

METHOD_CODE = 'CLASSIFICATION_DESCRIPTIVE'
METHOD_VERSION = '1.0.0'
RESULT_TABLE = 'calc_metrics_classification'
UPSERT_PREFER = 'resolution=merge-duplicates,return=minimal'
#: The classifier always emits the same metric codes, so the row count is fixed.
EXPECTED_ROW_COUNT = 9


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
        raise CalculationError('CLASSIFICATION_METHODOLOGY_VERSION_NOT_FOUND')
    if rows[0].get('status') not in ('DRAFT', 'PUBLISHED'):
        raise CalculationError('CLASSIFICATION_METHODOLOGY_NOT_EXECUTABLE')
    return str(rows[0]['id'])


def _input_snapshot(
    *,
    ticker: str,
    instrument_id: str,
    sector: str | None,
    inputs: Mapping[str, Decimal | None],
    growth_run_id: str,
    years_available: int,
) -> dict[str, Any]:
    """Canonical snapshot of everything the classification depends on."""
    return {
        'ticker': ticker,
        'instrument_id': instrument_id,
        'sector': sector,
        'years_available': years_available,
        'annual_growth_run_id': growth_run_id,
        'classifier_inputs': {
            code: None if inputs.get(code) is None else format_decimal(inputs[code])
            for code in CLASSIFIER_INPUT_CODES
        },
    }


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
            payload={'status': 'RUNNING', 'error_message': None, 'completed_at': None},
        )
        return run_id, False

    created = db.request(
        'POST',
        'calculation_runs',
        payload={
            **dict(run_contract),
            'status': 'RUNNING',
            'scope_type': 'INSTRUMENT',
            'scope_id': instrument_id,
            'methodology_version_id': methodology_version_id,
        },
        headers={'Prefer': 'return=representation'},
    )
    if not isinstance(created, list) or len(created) != 1:
        raise CalculationError('CLASSIFICATION_RUN_CREATE_FAILED')
    return str(created[0]['id']), False


def _mark_run(
    db: SupabaseRest,
    run_id: str,
    *,
    status: str,
    error_message: str | None = None,
) -> None:
    payload: dict[str, Any] = {'status': status, 'error_message': error_message}
    if status in ('SUCCEEDED', 'PARTIAL', 'FAILED'):
        payload['completed_at'] = datetime.now(timezone.utc).isoformat()
    db.request('PATCH', 'calculation_runs', params={'id': 'eq.' + run_id}, payload=payload)


def _persist_rows(
    db: SupabaseRest,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    if not rows:
        return
    db.request(
        'POST',
        RESULT_TABLE,
        params={'on_conflict': 'calculation_run_id,instrument_id,metric_code'},
        payload=[dict(row) for row in rows],
        headers={'Prefer': UPSERT_PREFER},
    )


def _verify_persisted(db: SupabaseRest, run_id: str, expected: int) -> None:
    actual = len(
        db.get_all(RESULT_TABLE, {'calculation_run_id': 'eq.' + run_id, 'select': 'id'})
    )
    if actual != expected:
        raise CalculationError(
            f'PERSISTED_ROW_COUNT_MISMATCH: {RESULT_TABLE} expected={expected} actual={actual}'
        )


def build_rows(
    *,
    inputs: Mapping[str, Decimal | None],
    instrument_id: str,
    run_id: str,
    sector: str | None,
    methodology_version_id: str | None,
    manual_override: str | None = None,
) -> list[dict[str, Any]]:
    """Evaluate the classifier and shape its rows for persistence.

    Four classifier inputs (``revenue_long``, ``revenue_cov``,
    ``revenue_momentum``, ``eps_long``) are read out of the ``growth_rows``
    argument rather than a keyword, so the derived values are re-expressed as
    Class-B result rows before the call. That keeps the classifier's own input
    contract untouched.
    """
    growth_rows = [
        {
            'metric_code': metric_code,
            'value_numeric': None if inputs.get(code) is None else format_decimal(inputs[code]),
            'calculation_status': (
                'UNAVAILABLE' if inputs.get(code) is None else 'VALID'
            ),
        }
        for code, metric_code in GROWTH_ROW_INPUT_CODES.items()
    ]
    rows = classify_metrics_classification(
        growth_rows=growth_rows,
        instrument_id=instrument_id,
        run_id=run_id,
        sector=sector,
        methodology_version_id=methodology_version_id,
        manual_override=manual_override,
        **{code: inputs.get(code) for code in DIRECT_INPUT_CODES},
    )
    shaped: list[dict[str, Any]] = []
    for row in rows:
        shaped.append({
            'calculation_run_id': run_id,
            'methodology_version_id': methodology_version_id,
            'instrument_id': instrument_id,
            'metric_code': row['metric_code'],
            'value_numeric': row.get('value_numeric'),
            'classification_code': row.get('classification_code'),
            'manual_override': row.get('manual_override'),
            'calculation_status': row['calculation_status'],
            'availability_status': row.get('availability_status', 'READY'),
            'flags': row.get('flags') or [],
        })
    return shaped


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ticker', required=True, help='IDX ticker, e.g. SIDO')
    parser.add_argument('--scenario-code', help='Active scenario code when several are active.')
    parser.add_argument('--years-available', type=int, default=7)
    parser.add_argument(
        '--manual-override',
        help='Workbook B81 stock-type override. The rule result is still stored.',
    )
    parser.add_argument('--apply', action='store_true', help='Persist results to Supabase.')
    args = parser.parse_args(argv)

    ticker = args.ticker.strip().upper().replace('.JK', '')
    load_env_file(REPO_ROOT / '.env')
    db = SupabaseRest(os.getenv('SUPABASE_URL', ''), os.getenv('SUPABASE_SERVICE_ROLE_KEY', ''))

    instrument, inputs, instrument_id, growth_run_id = load_live_inputs(
        db,
        ticker=ticker,
        scenario_code=args.scenario_code,
        years_available=args.years_available,
    )
    sector = instrument.get('sector_name')
    methodology_version_id = _methodology_version_id(db) if args.apply else None

    snapshot = _input_snapshot(
        ticker=ticker,
        instrument_id=instrument_id,
        sector=sector,
        inputs=inputs,
        growth_run_id=growth_run_id,
        years_available=args.years_available,
    )

    run_id = 'offline-preview'
    if args.apply:
        run_contract = calculation_contract(
            calculation_type=METHOD_CODE,
            methodology_version_id=str(methodology_version_id),
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
            methodology_version_id=str(methodology_version_id),
            instrument_id=instrument_id,
        )
        if already_succeeded:
            print(f'Already classified: run={run_id} (idempotent no-op).')
            return 0

    rows = build_rows(
        inputs=inputs,
        instrument_id=instrument_id,
        run_id=run_id,
        sector=sector,
        methodology_version_id=methodology_version_id,
        manual_override=args.manual_override,
    )
    by_code = {row['metric_code']: row for row in rows}

    print(f"Ticker: {ticker} ({sector or 'sector unknown'})")
    print(f"Growth run: {growth_run_id}")
    print('Classifier inputs:')
    for code in CLASSIFIER_INPUT_CODES:
        value = inputs.get(code)
        print(f'  {code}: {value if value is not None else "UNAVAILABLE"}')
    print('Rule flags:')
    for code in (
        'CLASSIFICATION_SLOW_GROWER',
        'CLASSIFICATION_STALWART',
        'CLASSIFICATION_FAST_GROWER',
        'CLASSIFICATION_CYCLICAL',
        'CLASSIFICATION_ASSET_PLAY',
        'CLASSIFICATION_TURN_AROUND',
    ):
        print(f"  {code}: {by_code[code]['value_numeric']}")
    print(f"System recommendation: {by_code['CLASSIFICATION_SYSTEM_RECOMMENDATION']['classification_code']}")
    print(f"Final type: {by_code['CLASSIFICATION_FINAL_TYPE']['classification_code']}")
    print(f"Confidence: {by_code['CLASSIFICATION_CONFIDENCE']['value_numeric']}")

    if not args.apply:
        print('DRY RUN: no Supabase rows were written.')
        return 0

    if len(rows) != EXPECTED_ROW_COUNT:
        raise CalculationError(
            f'CLASSIFIER_ROW_COUNT_UNEXPECTED: {len(rows)} != {EXPECTED_ROW_COUNT}'
        )

    try:
        _persist_rows(db, rows)
        _verify_persisted(db, run_id, len(rows))
        _mark_run(db, run_id, status='SUCCEEDED')
    except Exception as error:
        try:
            _mark_run(db, run_id, status='PARTIAL', error_message=str(error)[:1000])
        except Exception:
            pass
        raise

    print(f'Persisted and verified: run={run_id}; rows={len(rows)}.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

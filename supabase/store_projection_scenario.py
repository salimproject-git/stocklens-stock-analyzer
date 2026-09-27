#!/usr/bin/env python3
"""Validate and store a workbook projection scenario in Supabase.

Historical quarters are verified against canonical actual facts and are not
copied. Only the forecast/assumption values are inserted into the projection
tables. Default execution is a dry-run; pass ``--apply`` to persist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

SUPABASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SUPABASE_DIR.parent
if str(SUPABASE_DIR) not in sys.path:
    sys.path.insert(0, str(SUPABASE_DIR))

from calculation_v1_common import CalculationError, SupabaseRest  # noqa: E402

SCENARIOS_TABLE = 'projection_scenarios'
VALUES_TABLE = 'projection_values'
BILLION_IDR = Decimal('1000000000')


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def scenario_hash(scenario: Mapping[str, Any]) -> str:
    """Hash submitted assumptions and forecast values deterministically."""
    relevant = {
        key: scenario[key]
        for key in (
            'ticker', 'scenario_code', 'scenario_version', 'projection_year',
            'as_of_quarter', 'years_available', 'average_dpr_ratio',
            'manual_dpr_ratio', 'projected_shares_outstanding', 'source_name',
            'source_reference', 'projections', 'expected_historical',
        )
    }
    return hashlib.sha256(_canonical_json(relevant).encode('utf-8')).hexdigest()


def validate_historical_values(
    scenario: Mapping[str, Any],
    actuals: Mapping[str, Mapping[str, Mapping[str, Any]]],
    *,
    instrument_id: str,
    base_period_id: str,
) -> dict[str, Any]:
    """Verify rounded workbook Q1/Q2 display values against canonical facts.

    Money displayed as ``M Rp`` is one billion IDR in the supplied template.
    COGS is shown negative in the template, while canonical raw COGS is stored
    positive; for validation only compare absolute values. Actual facts remain
    unchanged and their original sign is recorded in the validation report.
    """
    expected = scenario.get('expected_historical')
    if not isinstance(expected, Mapping):
        raise CalculationError('EXPECTED_HISTORICAL_VALUES_MISSING')

    comparisons: dict[str, Any] = {}
    for quarter_label, metrics in expected.items():
        if quarter_label not in ('Q1', 'Q2') or not isinstance(metrics, Mapping):
            raise CalculationError(f'UNSUPPORTED_HISTORICAL_QUARTER: {quarter_label}')
        actual_period_label = f"{scenario['projection_year']}-{quarter_label}"
        actual_metrics = actuals.get(actual_period_label)
        if actual_metrics is None:
            raise CalculationError(f'HISTORICAL_PERIOD_MISSING: {actual_period_label}')
        quarter_comparisons: dict[str, Any] = {}
        for metric_code, display_value in metrics.items():
            fact = actual_metrics.get(str(metric_code))
            if fact is None or fact.get('value_numeric') is None:
                raise CalculationError(
                    f'HISTORICAL_FACT_MISSING: {actual_period_label} {metric_code}'
                )
            if fact.get('quality_status') not in ('VALID', 'ESTIMATED'):
                raise CalculationError(
                    f'HISTORICAL_FACT_NOT_USABLE: {actual_period_label} {metric_code}'
                )
            try:
                expected_display = Decimal(str(display_value))
                actual_numeric = Decimal(str(fact['value_numeric']))
            except (InvalidOperation, KeyError) as error:
                raise CalculationError(
                    f'HISTORICAL_VALUE_NOT_NUMERIC: {actual_period_label} {metric_code}'
                ) from error

            actual_display = actual_numeric / BILLION_IDR
            if metric_code == 'COST_OF_REVENUE':
                # The source API/canonical fact is positive while the workbook
                # presentation is negative. Preserve both signs and only compare
                # their magnitudes to verify that they refer to the same amount.
                difference = abs(abs(actual_display) - abs(expected_display))
            else:
                difference = abs(actual_display - expected_display)
            if difference >= Decimal('0.5'):
                raise CalculationError(
                    'HISTORICAL_VALUE_MISMATCH: '
                    f'{actual_period_label} {metric_code} '
                    f'workbook={expected_display} actual={actual_display}'
                )
            quarter_comparisons[str(metric_code)] = {
                'expected_display': str(expected_display),
                'actual_idr': str(fact['value_numeric']),
                'actual_display': str(actual_display),
                'unit_code': fact.get('unit_code'),
                'quality_status': fact.get('quality_status'),
                'financial_period_id': fact.get('financial_period_id'),
            }
        comparisons[quarter_label] = quarter_comparisons

    return {
        'status': 'MATCHED_TO_CANONICAL_ACTUALS',
        'instrument_id': instrument_id,
        'as_of_financial_period_id': base_period_id,
        'display_unit': '1 M Rp = 1,000,000,000 IDR',
        'cogs_sign_note': 'Workbook COGS is displayed negative; canonical raw COGS is positive. Historical validation compares magnitude only; actual facts are not modified.',
        'quarters': comparisons,
    }


def build_projection_rows(
    scenario: Mapping[str, Any],
    *,
    scenario_id: str,
) -> list[dict[str, Any]]:
    """Convert JSON projection entries into rows for the projection_values table."""
    year = int(scenario['projection_year'])
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for projection in scenario.get('projections', []):
        metric_code = str(projection['metric_code'])
        if metric_code in seen:
            raise CalculationError(f'DUPLICATE_PROJECTION_METRIC: {metric_code}')
        seen.add(metric_code)
        value = Decimal(str(projection['value_numeric']))
        if not value.is_finite():
            raise CalculationError(f'PROJECTION_VALUE_NOT_FINITE: {metric_code}')
        rows.append({
            'scenario_id': scenario_id,
            'metric_code': metric_code,
            'projection_year': year,
            'period_label': str(year),
            'value_numeric': str(value),
            'unit_code': str(projection['unit_code']),
            'source_kind': str(projection.get('source_kind') or 'WORKBOOK_INPUT'),
            'source_display_value': str(projection['source_display_value']),
            'source_note': str(projection.get('source_note') or ''),
        })
    if not rows:
        raise CalculationError('PROJECTION_VALUES_EMPTY')
    return rows


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


def _live_preflight(
    db: SupabaseRest,
    scenario: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, dict[str, Any]]], dict[str, Any]]:
    ticker = str(scenario['ticker']).upper()
    instruments = db.get_all(
        'instruments',
        {'ticker': 'eq.' + ticker, 'select': 'id,ticker,company_name,sector_name'},
    )
    if len(instruments) != 1:
        raise CalculationError(f'INSTRUMENT_NOT_FOUND_OR_NOT_UNIQUE: {ticker}')
    instrument = instruments[0]
    instrument_id = str(instrument['id'])
    year = int(scenario['projection_year'])
    quarter = int(scenario['as_of_quarter'])
    base_label = f'{year}-Q{quarter}'

    periods: dict[str, dict[str, Any]] = {}
    actuals: dict[str, dict[str, dict[str, Any]]] = {}
    for q in range(1, quarter + 1):
        label = f'{year}-Q{q}'
        rows = db.get_all(
            'financial_periods',
            {
                'instrument_id': 'eq.' + instrument_id,
                'period_type': 'eq.QUARTER',
                'period_label': 'eq.' + label,
                'select': 'id,period_label,period_end,period_type',
            },
        )
        if len(rows) != 1:
            raise CalculationError(f'HISTORICAL_PERIOD_NOT_UNIQUE: {label}')
        period = rows[0]
        periods[label] = period
        facts = db.get_all(
            'financial_facts',
            {
                'financial_period_id': 'eq.' + str(period['id']),
                'revision_key': 'eq.CURRENT',
                'select': 'financial_period_id,metric_code,value_numeric,unit_code,quality_status,revision_key',
            },
        )
        actuals[label] = {str(fact['metric_code']): fact for fact in facts}
    if base_label not in periods:
        raise CalculationError(f'BASE_QUARTER_NOT_FOUND: {base_label}')
    return instrument, actuals, periods[base_label]


def _create_or_get_scenario(
    db: SupabaseRest,
    *,
    scenario: Mapping[str, Any],
    instrument_id: str,
    base_period_id: str,
    validation: Mapping[str, Any],
    input_hash: str,
) -> tuple[str, bool]:
    existing = db.get_all(
        SCENARIOS_TABLE,
        {
            'instrument_id': 'eq.' + instrument_id,
            'scenario_code': 'eq.' + str(scenario['scenario_code']),
            'scenario_version': 'eq.' + str(scenario['scenario_version']),
            'select': 'id,status,input_hash',
        },
    )
    if existing:
        current = existing[0]
        if current.get('input_hash') != input_hash:
            raise CalculationError(
                'PROJECTION_SCENARIO_VERSION_CONFLICT: '
                'change scenario_version before changing any saved input.'
            )
        if current.get('status') == 'ACTIVE':
            return str(current['id']), True
        raise CalculationError(
            'PROJECTION_SCENARIO_EXISTS_NOT_ACTIVE: review this draft before retrying.'
        )

    payload = {
        'instrument_id': instrument_id,
        'as_of_financial_period_id': base_period_id,
        'scenario_code': str(scenario['scenario_code']),
        'scenario_version': int(scenario['scenario_version']),
        'projection_year': int(scenario['projection_year']),
        'as_of_quarter': int(scenario['as_of_quarter']),
        'years_available': int(scenario['years_available']),
        'average_dpr_ratio': str(Decimal(str(scenario['average_dpr_ratio']))),
        'manual_dpr_ratio': (
            None if scenario.get('manual_dpr_ratio') is None
            else str(Decimal(str(scenario['manual_dpr_ratio'])))
        ),
        'projected_shares_outstanding': str(
            Decimal(str(scenario['projected_shares_outstanding']))
        ),
        'status': 'DRAFT',
        'source_name': str(scenario['source_name']),
        'source_reference': str(scenario.get('source_reference') or ''),
        'input_hash': input_hash,
        'historical_validation': dict(validation),
    }
    created = db.request(
        'POST', SCENARIOS_TABLE, payload=payload,
        headers={'Prefer': 'return=representation'},
    )
    if not isinstance(created, list) or len(created) != 1:
        raise CalculationError('PROJECTION_SCENARIO_CREATE_FAILED')
    return str(created[0]['id']), False


def _persist_scenario(
    db: SupabaseRest,
    *,
    scenario: Mapping[str, Any],
    instrument_id: str,
    base_period_id: str,
    validation: Mapping[str, Any],
    input_hash: str,
) -> tuple[str, bool]:
    scenario_id, already_active = _create_or_get_scenario(
        db,
        scenario=scenario,
        instrument_id=instrument_id,
        base_period_id=base_period_id,
        validation=validation,
        input_hash=input_hash,
    )
    if already_active:
        return scenario_id, True

    existing_values = db.get_all(
        VALUES_TABLE,
        {'scenario_id': 'eq.' + scenario_id, 'select': 'metric_code'},
    )
    if existing_values:
        # Never mix old and new values for a scenario version.
        raise CalculationError('PROJECTION_SCENARIO_HAS_PARTIAL_VALUES')
    rows = build_projection_rows(scenario, scenario_id=scenario_id)
    db.request('POST', VALUES_TABLE, payload=rows, headers={'Prefer': 'return=minimal'})
    stored_values = db.get_all(
        VALUES_TABLE,
        {
            'scenario_id': 'eq.' + scenario_id,
            'select': 'metric_code,value_numeric,unit_code',
        },
    )
    if len(stored_values) != len(rows):
        raise CalculationError(
            f'PROJECTION_VALUE_COUNT_MISMATCH: expected={len(rows)} actual={len(stored_values)}'
        )
    db.request(
        'PATCH', SCENARIOS_TABLE,
        params={'id': 'eq.' + scenario_id},
        payload={'status': 'ACTIVE'},
    )
    return scenario_id, False


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--scenario', type=Path,
        default=SUPABASE_DIR / 'projection_auto_2026_q2.json',
        help='JSON input scenario (default: AUTO Q2 2026).',
    )
    parser.add_argument('--apply', action='store_true', help='Persist to Supabase.')
    args = parser.parse_args(argv)
    scenario = json.loads(args.scenario.read_text(encoding='utf-8'))
    input_hash = scenario_hash(scenario)
    expected_count = len(scenario.get('projections', []))
    if not expected_count:
        raise CalculationError('PROJECTION_VALUES_EMPTY')

    load_env_file(REPO_ROOT / '.env')
    db = SupabaseRest(
        os.getenv('SUPABASE_URL', ''),
        os.getenv('SUPABASE_SERVICE_ROLE_KEY', ''),
    )
    instrument, actuals, base_period = _live_preflight(db, scenario)
    validation = validate_historical_values(
        scenario,
        actuals,
        instrument_id=str(instrument['id']),
        base_period_id=str(base_period['id']),
    )
    rows = build_projection_rows(scenario, scenario_id='dry-run')

    print(f"Instrument: {instrument['ticker']} — {instrument.get('company_name') or ''}")
    print(
        f"Base: {base_period['period_label']} (financial_period_id={base_period['id']}); "
        f"historical inputs matched Q1–Q{scenario['as_of_quarter']} actuals."
    )
    print(
        f"Scenario: {scenario['scenario_code']} v{scenario['scenario_version']}; "
        f"projection year {scenario['projection_year']}; {len(rows)} projected values."
    )
    print('Historical actuals are referenced and validated; they will not be copied.')
    print(f"Input hash: {input_hash}")
    if not args.apply:
        print('DRY RUN: no rows were written.')
        return 0

    scenario_id, already_active = _persist_scenario(
        db,
        scenario=scenario,
        instrument_id=str(instrument['id']),
        base_period_id=str(base_period['id']),
        validation=validation,
        input_hash=input_hash,
    )
    if already_active:
        print(f'Already stored and active: scenario_id={scenario_id} (idempotent no-op).')
    else:
        print(
            f'Stored and verified: scenario_id={scenario_id}, '
            f'projection_values={expected_count}, status=ACTIVE.'
        )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
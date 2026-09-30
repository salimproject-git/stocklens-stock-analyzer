#!/usr/bin/env python3
"""Calculate and optionally persist a workbook-style current valuation snapshot."""

from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

SUPABASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SUPABASE_DIR.parent
if str(SUPABASE_DIR) not in sys.path:
    sys.path.insert(0, str(SUPABASE_DIR))

from calculation_v1_common import CalculationError, SupabaseRest, calculation_contract  # noqa: E402
from valuation_engine import (  # noqa: E402
    CODE_VERSION,
    REFERENCE_VERSION,
    DEFAULT_YEARS_COMPARE,
    STOCK_TYPES,
    ValuationError,
    calculate_valuation_snapshot,
    decimal_text,
    decimal_value,
)

METHOD_CODE = 'VALUATION_CURRENT'
METHOD_VERSION = '1.0.0'
INPUT_TABLE = 'calc_valuation_inputs'
METHOD_TABLE = 'calc_valuation_methods'
PAGE_SIZE = 1000

#: `rate_code` of the 10Y SBN yield row in `risk_free_rate_reference`.
REFERENCE_RATE_CODE = 'SBN_10Y_YIELD'


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


def _pages(db: SupabaseRest, table: str, params: Mapping[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = db.get_all(table, {**dict(params), 'limit': str(PAGE_SIZE), 'offset': str(offset)})
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def _postgrest_in(values: list[str]) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator='')
    writer.writerow(values)
    return 'in.(' + stream.getvalue() + ')'


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _required_methodology_id(db: SupabaseRest) -> str:
    rows = db.get_all('methodology_versions', {
        'method_code': 'eq.VALUATION_CURRENT',
        'method_version': 'eq.1.0.0',
        'select': 'id,status',
    })
    if len(rows) != 1 or rows[0].get('status') not in ('DRAFT', 'PUBLISHED'):
        raise CalculationError('VALUATION_METHODOLOGY_NOT_FOUND_OR_NOT_EXECUTABLE')
    from calculation_methodology_registry import supplemental_methodology_seeds
    from calculation_registry import sha256_json, sha256_text

    expected = supplemental_methodology_seeds()[0]
    if (
        expected.get('formula_hash') != sha256_text(expected['formula_text'])
        or expected.get('parameter_hash') != sha256_json(expected['parameter_spec'])
    ):
        raise CalculationError('VALUATION_METHODOLOGY_LOCAL_HASH_INVALID')
    stored_full = db.get_all('methodology_versions', {
        'id': 'eq.' + str(rows[0]['id']),
        'select': 'formula_hash,parameter_hash',
    })
    if len(stored_full) != 1 or any(
        stored_full[0].get(key) != expected[key]
        for key in ('formula_hash', 'parameter_hash')
    ):
        raise CalculationError('VALUATION_METHODOLOGY_REGISTRY_DRIFT')
    return str(rows[0]['id'])


def _methodology_parameters(db: SupabaseRest) -> dict[str, Any]:
    rows = db.get_all('methodology_versions', {
        'method_code': 'eq.VALUATION_CURRENT',
        'method_version': 'eq.1.0.0',
        'select': 'parameter_spec',
    })
    if len(rows) != 1:
        raise CalculationError('VALUATION_METHODOLOGY_PARAMETERS_NOT_FOUND')
    spec = dict(rows[0].get('parameter_spec') or {})
    return spec


def _reference_type_name(stock_type: str) -> str:
    return {
        'SLOW GROWER': 'Slow Grower',
        'STALWART': 'Stalwart',
        'FAST GROWER': 'Fast Grower',
        'CYCLICAL': 'Cyclical',
        'TURN AROUND': 'Turn around',
        'ASSET PLAY': 'Asset Play',
    }[stock_type.upper().replace('_', ' ')]


def resolve_risk_free_rate(db: SupabaseRest, rate_code: str = REFERENCE_RATE_CODE) -> tuple[str, str]:
    """Resolve a risk-free rate and its provenance from `risk_free_rate_reference`.

    Returns ``(rate_text, source_text)`` ready to pass to the valuation engine.
    The newest dated ``MARKET_OBSERVATION`` row wins; when no dated observation
    exists, the single ``is_default`` row is used (the workbook constant).

    The rate is never invented: a missing reference row is a hard error, and the
    returned source text always names the row that produced the number so the
    value stays auditable in `calc_valuation_inputs.details`.
    """
    rows = db.get_all('risk_free_rate_reference', {
        'reference_version': 'eq.' + REFERENCE_VERSION,
        'rate_code': 'eq.' + rate_code,
        'select': 'rate,observation_date,source_kind,source_name,source_reference,is_default',
        'order': 'observation_date.desc.nullslast',
    })
    if not rows:
        raise CalculationError(f'RISK_FREE_RATE_REFERENCE_MISSING:{rate_code}')

    dated = [row for row in rows if row.get('observation_date')]
    if dated:
        chosen = dated[0]
    else:
        defaults = [row for row in rows if row.get('is_default')]
        if len(defaults) != 1:
            raise CalculationError(f'RISK_FREE_RATE_REFERENCE_DEFAULT_ROW_INVALID:{rate_code}')
        chosen = defaults[0]

    rate = decimal_value(chosen.get('rate'))
    if rate is None or rate <= 0:
        raise CalculationError(f'RISK_FREE_RATE_REFERENCE_VALUE_INVALID:{rate_code}')

    observation_date = chosen.get('observation_date') or 'no observation date recorded'
    source = (
        f"{chosen.get('source_kind')} via {chosen.get('source_name')} "
        f"({chosen.get('source_reference')}); observation_date={observation_date}"
    )
    return decimal_text(rate), source


def _persist_batch(db: SupabaseRest, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    conflict = 'calculation_run_id,instrument_id,as_of_financial_period_id,metric_code'
    if table == METHOD_TABLE:
        conflict = 'calculation_run_id,instrument_id,as_of_financial_period_id,method_code'
    for offset in range(0, len(rows), 250):
        db.request(
            'POST', table,
            params={'on_conflict': conflict},
            payload=rows[offset:offset + 250],
            headers={'Prefer': 'resolution=merge-duplicates,return=minimal'},
        )


def _write_run_status(db: SupabaseRest, run_id: str, status: str, error: str | None = None) -> None:
    payload: dict[str, Any] = {'status': status, 'error_message': error}
    if status in ('SUCCEEDED', 'FAILED', 'PARTIAL'):
        payload['completed_at'] = datetime.now(timezone.utc).isoformat()
    db.request('PATCH', 'calculation_runs', params={'id': 'eq.' + run_id}, payload=payload)


def _store(db: SupabaseRest, result: Mapping[str, Any], instrument_id: str, methodology_id: str) -> str:
    run_snapshot = copy.deepcopy(dict(result['input_snapshot']))
    run_snapshot.update({
        'reference_version': REFERENCE_VERSION,
        'code_version': CODE_VERSION,
    })
    run_contract = calculation_contract(
        calculation_type='VALUATION_CURRENT',
        methodology_version_id=methodology_id,
        code_version=CODE_VERSION,
        source_cutoff_date=str(result['valuation_date']),
        source_ingestion_run_id=None,
        scope_type='INSTRUMENT',
        scope_id=instrument_id,
        input_snapshot=run_snapshot,
    )
    existing = db.get_all('calculation_runs', {
        'idempotency_key': 'eq.' + run_contract['idempotency_key'],
        'select': 'id,status',
    })
    if existing and existing[0]['status'] == 'SUCCEEDED':
        return str(existing[0]['id'])
    if existing:
        run_id = str(existing[0]['id'])
        db.request('PATCH', 'calculation_runs', params={'id': 'eq.' + run_id}, payload={
            'status': 'RUNNING', 'error_message': None, 'completed_at': None,
        })
    else:
        payload = {
            **run_contract,
            'status': 'RUNNING',
            'scope_type': 'INSTRUMENT',
            'scope_id': instrument_id,
            'methodology_version_id': methodology_id,
        }
        created = db.request(
            'POST', 'calculation_runs', payload=payload,
            headers={'Prefer': 'return=representation'},
        )
        if not isinstance(created, list) or len(created) != 1:
            raise CalculationError('VALUATION_RUN_CREATE_FAILED')
        run_id = str(created[0]['id'])

    as_of_id = str(result['as_of_financial_period_id'])
    scenario_id = result.get('projection_scenario_id')
    common = {
        'calculation_run_id': run_id,
        'methodology_version_id': methodology_id,
        'instrument_id': instrument_id,
        'as_of_financial_period_id': as_of_id,
        'projection_scenario_id': scenario_id,
        'valuation_date': result['valuation_date'],
    }
    input_rows = [
        {
            **common,
            'metric_code': row['metric_code'],
            'value_numeric': decimal_text(row['value_numeric']),
            'value_text': row.get('value_text'),
            'unit_code': row['unit_code'],
            'calculation_status': row['calculation_status'],
            'flags': row['flags'],
            'details': _json_value(row['details']),
        }
        for row in result['inputs']
    ]
    method_rows = [
        {
            **common,
            'method_code': row['method_code'],
            'method_name': row['method_name'],
            'stock_type': row['stock_type'],
            'years_available': row['years_available'],
            'years_compare': row['years_compare'],
            'intrinsic_value': decimal_text(row['intrinsic_value']),
            'current_price': decimal_text(row['current_price']),
            'gap_ratio': decimal_text(row['gap_ratio']),
            'verdict': row['verdict'],
            'calculation_status': row['calculation_status'],
            'flags': row['flags'],
            'details': _json_value(row['details']),
        }
        for row in result['methods']
    ]

    try:
        _persist_batch(db, INPUT_TABLE, input_rows)
        _persist_batch(db, METHOD_TABLE, method_rows)
        for table, expected in ((INPUT_TABLE, len(input_rows)), (METHOD_TABLE, len(method_rows))):
            stored = _pages(db, table, {
                'calculation_run_id': 'eq.' + run_id,
                'instrument_id': 'eq.' + instrument_id,
                'select': 'id',
            })
            if len(stored) != expected:
                raise CalculationError(f'VALUATION_VERIFY_COUNT_MISMATCH:{table}:{len(stored)}:{expected}')
        _write_run_status(db, run_id, 'SUCCEEDED')
    except Exception as error:
        try:
            _write_run_status(db, run_id, 'PARTIAL', str(error)[:1000])
        except Exception:
            pass
        raise
    return run_id


def calculate_live(
    db: SupabaseRest,
    *,
    ticker: str,
    stock_type: str | None,
    scenario_code: str | None,
    valuation_date: str | None,
    years_available: int | None,
    years_compare: int | None,
    risk_free_rate: str | None,
    risk_free_source: str | None,
) -> tuple[dict[str, Any], str, str]:
    instruments = db.get_all('instruments', {
        'exchange_code': 'eq.IDX', 'ticker': 'eq.' + ticker,
        'select': 'id,ticker,company_name,sector_name',
    })
    if len(instruments) != 1:
        raise CalculationError('INSTRUMENT_NOT_FOUND_OR_NOT_UNIQUE')
    instrument = instruments[0]
    instrument_id = str(instrument['id'])
    # The classifier is the source of truth. An explicit --stock-type is an
    # override for investigation only, never the default path.
    if stock_type is None:
        stock_type, classification_run_id = _resolve_stock_type(db, instrument_id)
        print(
            f'Stock type resolved from classifier: {stock_type} '
            f'(run={classification_run_id})'
        )
    selected_type = stock_type.upper().replace('_', ' ')
    if selected_type == 'TURNAROUND':
        selected_type = 'TURN AROUND'
    scenarios = db.get_all('projection_scenarios', {
        'instrument_id': 'eq.' + instrument_id,
        'status': 'eq.ACTIVE',
        'select': 'id,as_of_financial_period_id,projection_year,as_of_quarter,years_available,projected_shares_outstanding,input_hash,scenario_code,status',
    })
    if scenario_code:
        scenarios = [row for row in scenarios if row.get('scenario_code') == scenario_code]
    if len(scenarios) != 1:
        raise CalculationError('ACTIVE_PROJECTION_SCENARIO_NOT_UNIQUE: provide --scenario-code if multiple')
    scenario = dict(scenarios[0])
    scenario_periods = db.get_all('financial_periods', {
        'id': 'eq.' + str(scenario['as_of_financial_period_id']),
        'select': 'period_end',
    })
    if len(scenario_periods) != 1:
        raise CalculationError('PROJECTION_BASE_PERIOD_NOT_FOUND')
    scenario_as_of_date = str(scenario_periods[0]['period_end'])
    if valuation_date is not None and valuation_date < scenario_as_of_date:
        raise CalculationError('VALUATION_DATE_BEFORE_PROJECTION_BASE')
    projection_rows = db.get_all('projection_values', {
        'scenario_id': 'eq.' + str(scenario['id']),
        'select': 'metric_code,value_numeric,unit_code',
    })
    scenario['values'] = {row['metric_code']: row['value_numeric'] for row in projection_rows}

    periods = _pages(db, 'financial_periods', {
        'instrument_id': 'eq.' + instrument_id,
        'select': 'id,period_type,period_label,period_end,report_date,available_date,period_basis,statement_scope',
        'order': 'period_end.asc',
    })
    period_ids = [str(row['id']) for row in periods]
    if not period_ids:
        raise CalculationError('FINANCIAL_PERIODS_MISSING')
    facts: list[dict[str, Any]] = []
    for offset in range(0, len(period_ids), 100):
        facts.extend(_pages(db, 'financial_facts', {
            'financial_period_id': _postgrest_in(period_ids[offset:offset + 100]),
            'select': 'financial_period_id,metric_code,value_numeric,unit_code,quality_status,revision_key',
        }))
    prices = _pages(db, 'prices_daily', {
        'instrument_id': 'eq.' + instrument_id,
        'select': 'trading_date,close_price',
        'order': 'trading_date.asc',
    })
    valuation_date = valuation_date or max((str(row['trading_date']) for row in prices), default='')
    if not valuation_date:
        raise CalculationError('PRICE_HISTORY_MISSING')
    periods = [row for row in periods if str(row.get('period_end') or '') <= scenario_as_of_date]
    period_ids = [str(row['id']) for row in periods]
    facts = []
    for offset in range(0, len(period_ids), 100):
        facts.extend(_pages(db, 'financial_facts', {
            'financial_period_id': _postgrest_in(period_ids[offset:offset + 100]),
            'select': 'financial_period_id,metric_code,value_numeric,unit_code,quality_status,revision_key',
        }))
    chosen_years = int(scenario['years_available']) if years_available is None else years_available
    sector_weights = db.get_all('valuation_sector_weights', {
        'reference_version': 'eq.' + REFERENCE_VERSION,
        'sector_name': 'eq.' + str(instrument.get('sector_name') or ''),
        'select': 'sector_name,w_pe,w_pbv,w_ddm,w_graham,w_peg',
    })
    type_weights = db.get_all('valuation_type_weights', {
        'reference_version': 'eq.' + REFERENCE_VERSION,
        'stock_type': 'eq.' + _reference_type_name(selected_type),
        'select': 'stock_type,w_pe,w_pbv,w_ddm,w_graham,w_peg',
    })
    # User-provided reference table has explicit Min ICR; this row is persisted
    # even though the five current valuation methods do not consume the threshold.
    type_thresholds = db.get_all('valuation_type_thresholds', {
        'reference_version': 'eq.' + REFERENCE_VERSION,
        'stock_type': 'eq.' + _reference_type_name(selected_type),
        'select': 'stock_type,max_der,min_cr,min_icr',
    })
    methodology_id = _required_methodology_id(db)
    valuation_parameters = _methodology_parameters(db)
    effective_compare = None if years_compare is None else int(years_compare)
    result = calculate_valuation_snapshot(
        ticker=ticker,
        sector=instrument.get('sector_name'),
        stock_type=stock_type,
        annual_periods=[row for row in periods if row['period_type'] == 'ANNUAL'],
        quarterly_periods=[row for row in periods if row['period_type'] == 'QUARTER'],
        facts=facts,
        prices=prices,
        scenario=scenario,
        valuation_date=valuation_date,
        years_available=chosen_years,
        years_compare=effective_compare,
        risk_free_rate=risk_free_rate,
        risk_free_source=risk_free_source,
        sector_weights=sector_weights[0] if sector_weights else None,
        type_weights=type_weights[0] if type_weights else None,
        type_thresholds=type_thresholds[0] if type_thresholds else None,
        valuation_parameters=valuation_parameters,
    )
    return result, instrument_id, methodology_id


def normalise_classifier_type(stock_type: str, asset_play_matched: bool = False) -> str:
    """Map a stored classifier type onto a valuation-engine stock type.

    ``UNCLASSIFIED`` has two very different causes and they must not be
    conflated:

    * **Score-10 fall-through.** ASSET PLAY matched, but the workbook's score
      ladder has no branch for score 10, so the IFS falls through to
      ``UNCLASSIFIED`` (GOLD). The valuation engine and the reference tables both
      model that situation as ``ASSET PLAY``, so ``asset_play_matched=True`` maps
      it there.
    * **No rule matched at all.** Nothing matched, so there is no defensible type
      (INDF). Valuing such a ticker as an asset play would invent a methodology
      the classifier never chose, so this stays an error and the ticker must be
      given an explicit ``--stock-type`` if a valuation is genuinely wanted.
    """
    normalized = stock_type.strip().upper()
    if normalized == 'UNCLASSIFIED':
        if asset_play_matched:
            return 'ASSET PLAY'
        raise CalculationError(
            'CLASSIFICATION_UNCLASSIFIED_NO_RULE_MATCHED: no stock-type rule '
            'matched, so no type can be derived. Pass an explicit --stock-type '
            'to value this ticker.'
        )
    if normalized not in STOCK_TYPES:
        raise CalculationError(f'CLASSIFICATION_FINAL_TYPE_UNSUPPORTED: {stock_type}')
    return normalized


def _resolve_stock_type(db: SupabaseRest, instrument_id: str) -> tuple[str, str]:
    """Resolve the stock type from the persisted classifier result.

    Returns ``(stock_type, run_id)``. The classifier is the source of truth, so
    a valuation run no longer needs a hand-passed ``--stock-type``. A ticker
    without a stored classification must be classified first; guessing a type
    would silently change every downstream method, so this fails closed.

    The ASSET PLAY rule flag is read alongside the final type because
    ``UNCLASSIFIED`` needs it to be interpreted (see
    :func:`normalise_classifier_type`).
    """
    rows = db.get_all('calc_metrics_classification', {
        'instrument_id': 'eq.' + instrument_id,
        'metric_code': 'in.(CLASSIFICATION_FINAL_TYPE,CLASSIFICATION_ASSET_PLAY)',
        'calculation_status': 'eq.VALID',
        'select': 'metric_code,classification_code,value_numeric,calculation_run_id',
        'order': 'created_at.desc',
    })
    if not rows:
        raise CalculationError(
            'CLASSIFICATION_RESULT_NOT_FOUND: run populate_metrics_classification.py first'
        )
    by_code: dict[str, dict[str, Any]] = {}
    for row in rows:
        # Rows arrive newest-first, so the first sighting is the latest run.
        by_code.setdefault(str(row['metric_code']), row)

    final_row = by_code.get('CLASSIFICATION_FINAL_TYPE')
    if final_row is None:
        raise CalculationError('CLASSIFICATION_FINAL_TYPE_MISSING')
    stock_type = str(final_row.get('classification_code') or '').strip()
    if not stock_type:
        raise CalculationError('CLASSIFICATION_FINAL_TYPE_EMPTY')

    asset_play_row = by_code.get('CLASSIFICATION_ASSET_PLAY')
    asset_play_matched = (
        asset_play_row is not None
        and str(asset_play_row.get('value_numeric') or '').strip() == '1'
    )
    return (
        normalise_classifier_type(stock_type, asset_play_matched),
        str(final_row['calculation_run_id']),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ticker', required=True, help='IDX ticker, e.g. AUTO')
    parser.add_argument(
        '--stock-type',
        choices=[*STOCK_TYPES, 'TURNAROUND'],
        help=(
            'Explicit classification override. Default: the persisted '
            'CLASSIFICATION_FINAL_TYPE for the ticker.'
        ),
    )
    parser.add_argument('--scenario-code', help='Active scenario code when the ticker has multiple active scenarios.')
    parser.add_argument('--valuation-date', help='Market price cutoff date; default latest available daily close.')
    parser.add_argument('--years-available', type=int, help='Default: scenario years_available.')
    parser.add_argument('--years-compare', type=int, help='Default: workbook ladder from years_available.')
    parser.add_argument('--risk-free-rate', help='Optional decimal rate, e.g. 0.0633; required for DDM/discounted earnings.')
    parser.add_argument('--risk-free-source', help='Required source/date/reference whenever --risk-free-rate is supplied.')
    parser.add_argument(
        '--risk-free-from-reference',
        action='store_true',
        help='Resolve --risk-free-rate and --risk-free-source from public.risk_free_rate_reference.',
    )
    parser.add_argument('--apply', action='store_true', help='Persist valuation snapshot to Supabase.')
    args = parser.parse_args(argv)
    if args.risk_free_from_reference and (args.risk_free_rate or args.risk_free_source):
        parser.error('--risk-free-from-reference cannot be combined with --risk-free-rate/--risk-free-source.')
    if (args.risk_free_rate is None) != (args.risk_free_source is None):
        parser.error('--risk-free-rate and --risk-free-source must be supplied together.')
    load_env_file(REPO_ROOT / '.env')
    db = SupabaseRest(os.getenv('SUPABASE_URL', ''), os.getenv('SUPABASE_SERVICE_ROLE_KEY', ''))
    risk_free_rate = args.risk_free_rate
    risk_free_source = args.risk_free_source
    if args.risk_free_from_reference:
        risk_free_rate, risk_free_source = resolve_risk_free_rate(db)
        print(f'Risk-free rate resolved from reference table: {risk_free_rate} ({risk_free_source})')
    result, instrument_id, methodology_id = calculate_live(
        db,
        ticker=args.ticker.upper().replace('.JK', ''),
        stock_type=args.stock_type,
        scenario_code=args.scenario_code,
        valuation_date=args.valuation_date,
        years_available=args.years_available,
        years_compare=args.years_compare,
        risk_free_rate=risk_free_rate,
        risk_free_source=risk_free_source,
    )
    compact_result = {
        **{key: value for key, value in result.items() if key not in ('input_snapshot', 'input_hash')},
        'input_hash': result['input_hash'],
    }
    print(json.dumps(_json_value(compact_result), ensure_ascii=False, indent=2))
    if not args.apply:
        print('DRY RUN: no Supabase rows were written.')
        return 0
    run_id = _store(db, result, instrument_id, methodology_id)
    print(f'Persisted and verified: run_id={run_id}; inputs={len(result["inputs"])}; methods={len(result["methods"])}')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (CalculationError, ValuationError) as error:
        print(f'FAILED: {error}', file=sys.stderr)
        raise SystemExit(1) from error
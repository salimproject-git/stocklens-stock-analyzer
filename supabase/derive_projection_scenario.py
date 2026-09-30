#!/usr/bin/env python3
"""Derive a quarterly projection scenario from canonical actuals.

Reproduces the workbook's ``DataInputProyeksi`` derivation so a scenario can be
produced for any ticker whose actuals already exist in the canonical tables.
This is what lets valuation and (later) backtest run for a ticker whose owner
has not supplied a hand-filled workbook sheet.

Derivation rules (verified against the stored AUTO Q2 2026 workbook scenario):

  flow items   = sum(Q1..Q_asof) * 4 / as_of_quarter   (annualised run-rate)
  stock items  = value at Q_asof                       (latest balance sheet)
  avg DPR      = TRIMMEAN(annual DPS/EPS series, 0.4)
  potential DPS = (projected EARNINGS / projected shares) * avg DPR

Only the latest available quarter is used, so a ticker with Q1 reported and Q2
not yet reported still yields a scenario built purely from Q1.

Money is stored the way the workbook presents it: rounded to whole M Rp, then
multiplied by 1,000,000,000 IDR. COGS stays negative to match the workbook sign
convention (canonical raw COGS is positive; the validator compares magnitude).

Default is a dry run that writes a scenario JSON file. Pass ``--apply`` to also
persist it through ``store_projection_scenario.py`` so the same validation and
provenance path is used for every scenario.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping, Sequence

SUPABASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SUPABASE_DIR.parent
if str(SUPABASE_DIR) not in sys.path:
    sys.path.insert(0, str(SUPABASE_DIR))

from calculation_v1_common import CalculationError, SupabaseRest  # noqa: E402

BILLION_IDR = Decimal('1000000000')

# Flow metrics are annualised from the quarters available so far; balance-sheet
# metrics are carried from the latest available quarter.
FLOW_METRICS = (
    'REVENUE',
    'COST_OF_REVENUE',
    'INTEREST_EXPENSE_NON_OPERATING',
    'EARNINGS',
    'OPERATING_CASH_FLOW',
)
STOCK_METRICS = (
    'TOTAL_CURRENT_ASSET',
    'CURRENT_LIABILITIES',
    'TOTAL_LIABILITIES',
    'TOTAL_EQUITY',
)
# COGS is presented negative in the workbook; canonical raw COGS is positive.
NEGATED_METRICS = ('COST_OF_REVENUE',)
USABLE_QUALITY = ('VALID', 'ESTIMATED')
TRIMMEAN_PERCENT = Decimal('0.4')
DEFAULT_YEARS_AVAILABLE = 7


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries without printing their contents."""
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


def to_display(value: Decimal) -> int:
    """Round an IDR amount to the whole M Rp the workbook displays."""
    return int((value / BILLION_IDR).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def trimmean(values: Sequence[Decimal], percent: Decimal) -> Decimal | None:
    """Excel TRIMMEAN: drop INT(n*percent) points (even) and average the rest."""
    if not values:
        return None
    ordered = sorted(values)
    count = len(ordered)
    excluded = int(count * percent)
    if excluded % 2:
        excluded -= 1
    trimmed = ordered[excluded // 2: count - (excluded // 2)] if excluded else ordered
    if not trimmed:
        return None
    return sum(trimmed) / Decimal(len(trimmed))


def _postgrest_in(values: Sequence[str]) -> str:
    """Build a PostgREST `in.(...)` filter without importing csv machinery."""
    escaped = []
    for value in values:
        if any(ch in value for ch in ',"()'):
            escaped.append('"' + value.replace('"', '\\"') + '"')
        else:
            escaped.append(value)
    return 'in.(' + ','.join(escaped) + ')'


def fetch_instrument(db: SupabaseRest, ticker: str) -> Mapping[str, Any]:
    rows = db.get_all(
        'instruments',
        {'ticker': 'eq.' + ticker, 'select': 'id,ticker,company_name,sector_name'},
    )
    if len(rows) != 1:
        raise CalculationError(f'INSTRUMENT_NOT_FOUND_OR_NOT_UNIQUE: {ticker}')
    return rows[0]


def fetch_periods(db: SupabaseRest, instrument_id: str) -> list[Mapping[str, Any]]:
    return db.get_all(
        'financial_periods',
        {
            'instrument_id': 'eq.' + instrument_id,
            'select': 'id,period_type,period_label,period_end',
            'order': 'period_end.asc',
        },
    )


def fetch_facts(
    db: SupabaseRest,
    period_ids: Sequence[str],
) -> list[Mapping[str, Any]]:
    facts: list[Mapping[str, Any]] = []
    for offset in range(0, len(period_ids), 100):
        facts.extend(
            db.get_all(
                'financial_facts',
                {
                    'financial_period_id': _postgrest_in(period_ids[offset:offset + 100]),
                    'revision_key': 'eq.CURRENT',
                    'select': (
                        'financial_period_id,metric_code,value_numeric,'
                        'unit_code,quality_status,revision_key'
                    ),
                },
            )
        )
    return facts


def index_facts(
    facts: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Mapping[str, Any]]]:
    index: dict[str, dict[str, Mapping[str, Any]]] = {}
    for fact in facts:
        if fact.get('quality_status') not in USABLE_QUALITY:
            continue
        if fact.get('value_numeric') is None:
            continue
        period_id = str(fact.get('financial_period_id'))
        index.setdefault(period_id, {})[str(fact.get('metric_code'))] = fact
    return index


def quarter_number(period_end: str) -> int:
    month = int(period_end[5:7])
    if month not in (3, 6, 9, 12):
        raise CalculationError(f'QUARTER_END_MONTH_UNSUPPORTED: {period_end}')
    return month // 3


def fact_amount(
    index: Mapping[str, Mapping[str, Mapping[str, Any]]],
    period_id: str,
    metric_code: str,
) -> Decimal | None:
    fact = index.get(period_id, {}).get(metric_code)
    if not fact:
        return None
    value = fact.get('value_numeric')
    return None if value is None else Decimal(str(value))


def available_metrics(
    quarter_periods: Sequence[Mapping[str, Any]],
    index: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> set[str]:
    """Metric codes present in at least one usable quarter.

    A metric the provider never returns for a ticker (GOLD's
    ``INTEREST_EXPENSE_NON_OPERATING`` is null in every one of its 26 quarters)
    is structurally unavailable, not a data defect to wait for. Requiring it
    would block the whole scenario, so callers drop such metrics from the
    required set and omit them from the output instead of inventing a zero.
    """
    present: set[str] = set()
    for period in quarter_periods:
        present |= set(index.get(str(period['id']), {}))
    return present


def resolve_base_quarter(
    quarter_periods: Sequence[Mapping[str, Any]],
    index: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> Mapping[str, Any]:
    """Latest quarter whose facts cover every *available* flow and stock metric.

    Using the newest complete quarter means a ticker with only Q1 reported still
    produces a scenario, and Q2/Q3/Q4 replace it as soon as they land.

    Metrics that no quarter provides are excluded from the requirement, so a
    ticker with a permanently absent line item still yields a scenario built
    from everything it does report.
    """
    available = available_metrics(quarter_periods, index)
    required = {metric for metric in (set(FLOW_METRICS) | set(STOCK_METRICS)) if metric in available}
    if not required:
        # No usable facts at all. Report the same code as a genuinely incomplete
        # quarter: either way there is nothing to build a run-rate from, and the
        # empty-required case would otherwise match the first period vacuously.
        raise CalculationError('NO_COMPLETE_QUARTER_AVAILABLE')
    for period in sorted(
        quarter_periods,
        key=lambda row: str(row.get('period_end') or ''),
        reverse=True,
    ):
        present = set(index.get(str(period['id']), {}))
        if required <= present:
            return period
    raise CalculationError('NO_COMPLETE_QUARTER_AVAILABLE')


def annual_share_count(
    annual_periods: Sequence[Mapping[str, Any]],
    index: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> Decimal:
    """Latest annual shares outstanding, rounded to whole millions like the workbook."""
    for period in sorted(
        annual_periods,
        key=lambda row: str(row.get('period_end') or ''),
        reverse=True,
    ):
        shares = fact_amount(index, str(period['id']), 'OUTSTANDING_SHARES')
        if shares is not None and shares > 0:
            millions = (shares / Decimal(1000000)).quantize(
                Decimal('1'), rounding=ROUND_HALF_UP
            )
            return millions * Decimal(1000000)
    raise CalculationError('OUTSTANDING_SHARES_NOT_FOUND')


def annual_dpr_series(
    annual_periods: Sequence[Mapping[str, Any]],
    dividend_rows: Sequence[Mapping[str, Any]],
    index: Mapping[str, Mapping[str, Mapping[str, Any]]],
    *,
    years_available: int = DEFAULT_YEARS_AVAILABLE,
) -> list[Decimal]:
    """Annual DPS/EPS ratios, the workbook's `Range_DPR` series.

    The workbook range spans ``Years_Avail`` annual columns ending at the latest
    year. Every year in that window contributes a value:

    * a year with no dividend fact contributes DPS = 0 (DPR = 0), and
    * a loss-making year contributes a negative DPR.

    Neither is skipped. That is exactly why the workbook wraps the range in
    ``TRIMMEAN(..., 0.4)``: the outlier years are trimmed by the aggregate, not
    by the input list. Skipping them here would change the trimmed mean and
    therefore the potential DPS.
    """
    dps_by_year: dict[int, Decimal] = {}
    for row in dividend_rows:
        if str(row.get('fact_type')) != 'ANNUAL_TOTAL':
            continue
        year = row.get('period_year')
        amount = row.get('amount_per_share')
        if year is None or amount is None:
            continue
        dps_by_year[int(year)] = Decimal(str(amount))

    usable: list[tuple[int, Decimal]] = []
    for period in sorted(annual_periods, key=lambda row: str(row.get('period_end') or '')):
        label = str(period.get('period_label') or '')
        if not label.isdigit():
            continue
        earnings = fact_amount(index, str(period['id']), 'EARNINGS')
        shares = fact_amount(index, str(period['id']), 'OUTSTANDING_SHARES')
        if earnings is None or shares is None or shares <= 0:
            continue
        usable.append((int(label), earnings / shares))

    window = usable[-years_available:] if years_available > 0 else usable
    series: list[Decimal] = []
    for year, eps in window:
        if eps == 0:
            # A zero EPS has no defined payout ratio; the workbook's DPS/EPS
            # would be a divide-by-zero, so the year cannot contribute.
            continue
        series.append(dps_by_year.get(year, Decimal(0)) / eps)
    return series


def build_scenario(
    *,
    ticker: str,
    instrument: Mapping[str, Any],
    annual_periods: Sequence[Mapping[str, Any]],
    quarter_periods: Sequence[Mapping[str, Any]],
    index: Mapping[str, Mapping[str, Mapping[str, Any]]],
    dividend_rows: Sequence[Mapping[str, Any]],
    years_available: int = DEFAULT_YEARS_AVAILABLE,
    scenario_code: str | None = None,
    scenario_version: int = 1,
) -> dict[str, Any]:
    """Assemble a workbook-shaped scenario dict from canonical actuals."""
    available = available_metrics(quarter_periods, index)
    base_period = resolve_base_quarter(quarter_periods, index)
    base_end = str(base_period.get('period_end') or '')
    as_of_quarter = quarter_number(base_end)
    projection_year = int(base_end[:4])

    # Complete quarters of the base year, ascending. Only quarters whose facts
    # are loaded take part, so the annualised run-rate never mixes missing data.
    year_quarters: list[Mapping[str, Any]] = []
    for period in sorted(quarter_periods, key=lambda row: str(row.get('period_end') or '')):
        end = str(period.get('period_end') or '')
        if int(end[:4]) != projection_year:
            continue
        if str(period['id']) not in index:
            continue
        year_quarters.append(period)

    if not year_quarters:
        raise CalculationError('BASE_YEAR_QUARTERS_MISSING')
    quarter_count = len(year_quarters)

    projections: list[dict[str, Any]] = []
    for metric in FLOW_METRICS:
        if metric not in available:
            # Structurally unavailable for this ticker; omit rather than invent a
            # zero, which would misstate the run-rate.
            continue
        total = Decimal(0)
        for period in year_quarters:
            amount = fact_amount(index, str(period['id']), metric)
            if amount is None:
                raise CalculationError(f'BASE_QUARTER_FACT_MISSING: {metric}')
            total += amount
        display = to_display(total * 4 / quarter_count)
        if metric in NEGATED_METRICS:
            display = -display
        projections.append({
            'metric_code': metric,
            'value_numeric': str(display * BILLION_IDR),
            'unit_code': 'IDR',
            'source_kind': 'WORKBOOK_FORMULA_OUTPUT',
            'source_display_value': str(display),
            'source_note': (
                f'Annualised from Q1-Q{as_of_quarter} actual run-rate '
                f'({quarter_count} quarter(s), x 4/{quarter_count}).'
            ),
        })

    for metric in STOCK_METRICS:
        if metric not in available:
            continue
        amount = fact_amount(index, str(base_period['id']), metric)
        if amount is None:
            raise CalculationError(f'BASE_QUARTER_FACT_MISSING: {metric}')
        display = to_display(amount)
        projections.append({
            'metric_code': metric,
            'value_numeric': str(display * BILLION_IDR),
            'unit_code': 'IDR',
            'source_kind': 'WORKBOOK_FORMULA_OUTPUT',
            'source_display_value': str(display),
            'source_note': f'Carried from Q{as_of_quarter} balance sheet.',
        })

    shares = annual_share_count(annual_periods, index)
    dpr_series = annual_dpr_series(
        annual_periods, dividend_rows, index, years_available=years_available
    )
    average_dpr = trimmean(dpr_series, TRIMMEAN_PERCENT)
    if average_dpr is None:
        raise CalculationError('AVERAGE_DPR_NOT_DERIVABLE')

    projected_earnings = Decimal(
        next(p['value_numeric'] for p in projections if p['metric_code'] == 'EARNINGS')
    )
    eps_fwd = projected_earnings / shares
    potential_dps = (eps_fwd * average_dpr).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    projections.append({
        'metric_code': 'POTENTIAL_DPS',
        'value_numeric': str(potential_dps),
        'unit_code': 'IDR_PER_SHARE',
        'source_kind': 'WORKBOOK_FORMULA_OUTPUT',
        'source_display_value': str(potential_dps),
        'source_note': 'EPS forward x TRIMMEAN(annual DPS/EPS, 0.4); workbook DPR formula.',
    })

    expected_historical: dict[str, dict[str, str]] = {}
    for period in year_quarters:
        label = str(period.get('period_label') or '')
        quarter_label = label.split('-')[-1]
        metrics: dict[str, str] = {}
        for metric in FLOW_METRICS:
            amount = fact_amount(index, str(period['id']), metric)
            if amount is None:
                continue
            display = to_display(amount)
            if metric in NEGATED_METRICS:
                display = -display
            metrics[metric] = str(display)
        for metric in STOCK_METRICS:
            amount = fact_amount(index, str(period['id']), metric)
            if amount is not None:
                metrics[metric] = str(to_display(amount))
        expected_historical[quarter_label] = metrics

    return {
        'ticker': str(instrument['ticker']),
        'scenario_code': scenario_code or f'DERIVED_{projection_year}_Q{as_of_quarter}',
        'scenario_version': scenario_version,
        'projection_year': projection_year,
        'as_of_quarter': as_of_quarter,
        'years_available': years_available,
        'average_dpr_ratio': str(average_dpr.quantize(Decimal('0.000001'))),
        'manual_dpr_ratio': None,
        'projected_shares_outstanding': str(shares),
        'source_name': 'Derived from canonical actuals (DataInputProyeksi formula)',
        'source_reference': (
            f'flow=(Q1..Q{as_of_quarter}) x 4/{quarter_count}; stock=Q{as_of_quarter}; '
            f'DPR=TRIMMEAN({len(dpr_series)} annual DPS/EPS, 0.4)'
        ),
        'projections': projections,
        'expected_historical': expected_historical,
    }


def fetch_dividends(db: SupabaseRest, instrument_id: str) -> list[Mapping[str, Any]]:
    return db.get_all(
        'dividend_facts',
        {
            'instrument_id': 'eq.' + instrument_id,
            'select': 'fact_type,period_year,amount_per_share',
        },
    )


def fetch_active_scenarios(
    db: SupabaseRest, instrument_id: str
) -> list[Mapping[str, Any]]:
    return db.get_all(
        'projection_scenarios',
        {
            'instrument_id': 'eq.' + instrument_id,
            'status': 'eq.ACTIVE',
            'select': 'id,scenario_code,scenario_version',
        },
    )


def ensure_single_active_scenario(
    existing: Sequence[Mapping[str, Any]],
    *,
    scenario_code: str,
    scenario_version: int,
) -> None:
    """Refuse to add a second ACTIVE scenario for the same instrument.

    ``calculate_valuation.py`` requires exactly one ACTIVE scenario per ticker
    and fails with ACTIVE_PROJECTION_SCENARIO_NOT_UNIQUE otherwise, so creating a
    second one here would break valuation instead of improving it.
    """
    conflicting = [
        row
        for row in existing
        if not (
            str(row.get('scenario_code')) == scenario_code
            and int(row.get('scenario_version') or 0) == scenario_version
        )
    ]
    if conflicting:
        codes = ', '.join(
            f"{row.get('scenario_code')} v{row.get('scenario_version')}"
            for row in conflicting
        )
        raise CalculationError(
            'ACTIVE_SCENARIO_ALREADY_EXISTS: '
            f'{codes}. Reuse it, or bump --scenario-version for a new version.'
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ticker', help='IDX ticker, e.g. AMRT')
    parser.add_argument(
        '--years-available',
        type=int,
        default=DEFAULT_YEARS_AVAILABLE,
        help=f'Years available for the valuation window (default: {DEFAULT_YEARS_AVAILABLE}).',
    )
    parser.add_argument('--scenario-code', help='Override the generated scenario code.')
    parser.add_argument('--scenario-version', type=int, default=1)
    parser.add_argument(
        '--out',
        type=Path,
        help='Scenario JSON path (default: supabase/projection_<ticker>_<code>.json).',
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Also persist through store_projection_scenario.py (validated path).',
    )
    args = parser.parse_args(argv)

    ticker = args.ticker.upper().replace('.JK', '')
    load_env_file(REPO_ROOT / '.env')
    db = SupabaseRest(
        os.getenv('SUPABASE_URL', ''),
        os.getenv('SUPABASE_SERVICE_ROLE_KEY', ''),
    )

    instrument = fetch_instrument(db, ticker)
    periods = fetch_periods(db, str(instrument['id']))
    facts = fetch_facts(db, [str(row['id']) for row in periods])
    index = index_facts(facts)
    annual_periods = [row for row in periods if row.get('period_type') == 'ANNUAL']
    quarter_periods = [row for row in periods if row.get('period_type') == 'QUARTER']
    dividends = fetch_dividends(db, str(instrument['id']))

    scenario = build_scenario(
        ticker=ticker,
        instrument=instrument,
        annual_periods=annual_periods,
        quarter_periods=quarter_periods,
        index=index,
        dividend_rows=dividends,
        years_available=args.years_available,
        scenario_code=args.scenario_code,
        scenario_version=args.scenario_version,
    )

    out_path = args.out or (
        SUPABASE_DIR / f'projection_{ticker.lower()}_{scenario["scenario_code"].lower()}.json'
    )

    print(f"Instrument: {scenario['ticker']} — {instrument.get('company_name') or ''}")
    print(
        f"Base: {scenario['projection_year']}-Q{scenario['as_of_quarter']} "
        f"(latest complete quarter; annualised flow run-rate)"
    )
    print(
        f"Scenario: {scenario['scenario_code']} v{scenario['scenario_version']}; "
        f"DPR={scenario['average_dpr_ratio']}; shares={scenario['projected_shares_outstanding']}"
    )
    print(f"Historical quarters validated: {', '.join(sorted(scenario['expected_historical']))}")
    for projection in scenario['projections']:
        print(
            f"  {projection['metric_code']:<34} "
            f"{projection['source_display_value']:>12} {projection['unit_code']}"
        )

    if not args.apply:
        # A dry run is the only case that needs a file: the scenario must survive
        # the process so it can be inspected or fed to store_projection_scenario.
        out_path.write_text(
            json.dumps(scenario, indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8',
        )
        print(f"Scenario JSON: {out_path}")
        print('DRY RUN: no Supabase rows were written.')
        return 0

    # Guard before writing: a second ACTIVE scenario for the same ticker would
    # break calculate_valuation.py, which requires exactly one.
    existing_active = fetch_active_scenarios(db, str(instrument['id']))
    ensure_single_active_scenario(
        existing_active,
        scenario_code=str(scenario['scenario_code']),
        scenario_version=int(scenario['scenario_version']),
    )

    # Persist straight from memory. The scenario came from canonical tables, so
    # writing it to a file and reading it back would add a stale-on-disk copy of
    # data that already lives in Supabase, with no validation benefit: the
    # writer's own preflight re-reads the actuals from the database either way.
    from store_projection_scenario import persist_scenario  # noqa: PLC0415

    return persist_scenario(scenario, apply=True, db=db)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except CalculationError as error:
        print(f'FAILED: {error}', file=sys.stderr)
        raise SystemExit(1) from error

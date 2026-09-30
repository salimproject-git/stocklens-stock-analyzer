#!/usr/bin/env python3
"""Derive the MetricsClassification inputs the stock-type classifier consumes.

``classify_metrics_classification`` in ``calculate_quarterly_growth_quality.py``
implements the workbook rules exactly, but it takes eleven caller-supplied
inputs. Nothing was producing them, which is why the classifier was never wired
and ``calculate_valuation.py --stock-type`` stayed a manual flag.

This module derives those inputs from canonical data plus the active projection
scenario, so classification becomes automatic.

Derivations (all verified against the stored AUTO Q2 2026 workbook):

=============================  ==================================================
Input                          Rule
=============================  ==================================================
``revenue_long``               trailing-window REVENUE CAGR, taken from the annual
                               ``GROWTH_REVENUE_CAGR_LONG`` result
``revenue_cov``                ``GROWTH_REVENUE_COV`` result
``revenue_momentum``           ``QUALITY_REVENUE_MOMENTUM`` result
``eps_long``                   ``GROWTH_EPS_CAGR_LONG`` result
``projected_net_income``       active scenario ``EARNINGS``
``projected_pe``               ``current_price / EPS_FWD``  (workbook ``Metric_PE_Fwd``)
``projected_pbv``              ``current_price / BVPS_FWD`` (workbook ``Metric_PBV_Fwd``)
``projected_peg``              ``projected_pe / (eps_long * 100)``
``historical_roe_average``     ``AVERAGE(EARNINGS / TOTAL_EQUITY)`` over annual history
``historical_dividend_yield``  ``TRIMMEAN(DPS / year-end price, 0.2)``
``payout_ratio``               ``TRIMMEAN(DPS / EPS, 0.2)``
``pbv_percentile``             ``PERCENTRANK.INC`` of ``projected_pbv`` in the
                               annual PBV series, clamped to ``[0, 1]``
``gpm_stability``              annual gross-margin range, as a ratio
                               (workbook ``GPM Range`` is the same value x 100)
=============================  ==================================================

Two unit traps are handled explicitly, because the workbook mixes them:

* ``Metric_PE_Fwd`` / ``Metric_PBV_Fwd`` are **multiples** (price / forward
  per-share value). ``valuation_engine`` names its own ``PE_PROJECTED`` /
  ``PBV_PROJECTED`` differently -- those are *prices*
  (``eps_fwd * pe_average``) -- so they cannot be reused here.
* ``gpm_stability`` is compared against ``0.2`` inside the classifier, so it must
  be a **ratio**. The workbook's displayed ``GPM Range`` is that ratio x 100.
"""

from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

SUPABASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SUPABASE_DIR.parent
if str(SUPABASE_DIR) not in sys.path:
    sys.path.insert(0, str(SUPABASE_DIR))

from calculate_quarterly_growth_quality import _result_value  # noqa: E402
from calculation_v1_common import (  # noqa: E402
    CalculationError,
    SupabaseRest,
    to_decimal,
)

DEFAULT_YEARS_AVAILABLE = 7
#: Excel `TRIMMEAN(..., 0.2)` -- 10% trimmed from each tail.
TRIMMEAN_PERCENT = Decimal('0.2')

ANNUAL_PERIOD_SELECT = (
    'id,period_type,period_label,period_end,period_start,report_date,'
    'available_date,period_basis,statement_scope'
)
FACT_SELECT = (
    'id,financial_period_id,metric_code,value_numeric,quality_status,'
    'unit_code,revision_key,supersedes_fact_id'
)

#: PostgREST caps an unpaginated response, so large series must be paged.
PAGE_SIZE = 1000

#: Inputs this module produces, in emit order.
CLASSIFIER_INPUT_CODES: tuple[str, ...] = (
    'revenue_long',
    'revenue_cov',
    'revenue_momentum',
    'eps_long',
    'projected_net_income',
    'payout_ratio',
    'historical_roe_average',
    'projected_pbv',
    'pbv_percentile',
    'projected_pe',
    'projected_peg',
    'historical_dividend_yield',
    'gpm_stability',
)

#: Inputs the classifier reads out of its ``growth_rows`` argument rather than
#: from a keyword. They must be passed as Class-B result rows, not as kwargs.
GROWTH_ROW_INPUT_CODES: dict[str, str] = {
    'revenue_long': 'GROWTH_REVENUE_CAGR_LONG',
    'revenue_cov': 'GROWTH_REVENUE_COV',
    'revenue_momentum': 'QUALITY_REVENUE_MOMENTUM',
    'eps_long': 'GROWTH_EPS_CAGR_LONG',
}

#: Inputs the classifier accepts as direct keyword arguments.
DIRECT_INPUT_CODES: tuple[str, ...] = tuple(
    code for code in CLASSIFIER_INPUT_CODES if code not in GROWTH_ROW_INPUT_CODES
)


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


def trimmean(values: Sequence[Decimal], percent: Decimal) -> Decimal | None:
    """Excel ``TRIMMEAN``: drop ``INT(n * percent)`` points (forced even), average rest.

    Mirrors ``derive_projection_scenario.trimmean`` so the historical payout and
    dividend-yield aggregates trim exactly like the projection driver does.
    """
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


def percentrank_inc(series: Sequence[Decimal], value: Decimal) -> Decimal | None:
    """Excel ``PERCENTRANK.INC`` clamped to ``[0, 1]``.

    The workbook wraps this in ``IF(CurrentPBV <= MIN, 0, IF(CurrentPBV >= MAX, 1,
    PERCENTRANK.INC(...)))``, so the clamps are applied here for one call site.
    Ties average their ranks, matching Excel's inclusive convention.
    """
    if not series:
        return None
    ordered = sorted(series)
    if value <= ordered[0]:
        return Decimal(0)
    if value >= ordered[-1]:
        return Decimal(1)
    if len(ordered) == 1:
        return Decimal(0)
    below = sum(1 for item in ordered if item < value)
    equal = sum(1 for item in ordered if item == value)
    rank = Decimal(below) + Decimal(equal - 1) / 2 if equal > 1 else Decimal(below)
    return rank / Decimal(len(ordered) - 1)


def _year_end_price(
    prices: Sequence[Mapping[str, Any]],
    period_end: str,
) -> Decimal | None:
    """Last close in the calendar year of ``period_end``, on or before it."""
    year_start = period_end[:4] + '-01-01'
    eligible = [
        row for row in prices
        if year_start <= str(row.get('trading_date') or '') <= period_end
        and row.get('close_price') is not None
    ]
    if not eligible:
        return None
    selected = max(eligible, key=lambda row: str(row.get('trading_date') or ''))
    return to_decimal(selected.get('close_price'))


def _latest_price(prices: Sequence[Mapping[str, Any]]) -> Decimal | None:
    if not prices:
        return None
    selected = max(prices, key=lambda row: str(row.get('trading_date') or ''))
    return to_decimal(selected.get('close_price'))


def _pages(db: SupabaseRest, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    """Read every page of ``table``.

    ``SupabaseRest.get_all`` performs a single unpaginated GET, and PostgREST
    caps that response. ``prices_daily`` exceeds the cap for a single ticker, so
    an unpaginated read silently truncates the series and every year-end price
    is then wrong. Mirrors ``calculate_valuation._pages``.
    """
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = db.get_all(
            table, {**params, 'limit': str(PAGE_SIZE), 'offset': str(offset)}
        )
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def _facts_by_period(
    facts: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Mapping[str, Any]]]:
    """Index current, usable facts by period and metric code."""
    index: dict[str, dict[str, Mapping[str, Any]]] = {}
    for fact in facts:
        if str(fact.get('revision_key') or 'CURRENT') != 'CURRENT':
            continue
        if str(fact.get('quality_status') or 'VALID') in ('MISSING', 'INVALID'):
            continue
        period_id = str(fact.get('financial_period_id') or '')
        index.setdefault(period_id, {})[str(fact.get('metric_code'))] = fact
    return index


def _fact(
    index: Mapping[str, Mapping[str, Mapping[str, Any]]],
    period_id: str,
    metric_code: str,
) -> Decimal | None:
    fact = index.get(period_id, {}).get(metric_code)
    if fact is None:
        return None
    return to_decimal(fact.get('value_numeric'))


def derive_classifier_inputs(
    *,
    annual_periods: Sequence[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
    prices: Sequence[Mapping[str, Any]],
    dividend_rows: Sequence[Mapping[str, Any]],
    scenario_values: Mapping[str, Any],
    projected_shares_outstanding: Any,
    growth_rows: Sequence[Mapping[str, Any]],
    years_available: int = DEFAULT_YEARS_AVAILABLE,
) -> dict[str, Decimal | None]:
    """Derive every classifier input from canonical data.

    ``growth_rows`` must be the annual growth/quality result rows for the latest
    snapshot, because ``revenue_long`` and friends are the *stored* Class-B
    results rather than a recomputation. Passing them keeps the classifier
    consistent with what the research RPC already serves.
    """
    index = _facts_by_period(facts)
    annual = sorted(
        (dict(row) for row in annual_periods if row.get('period_type') == 'ANNUAL'),
        key=lambda row: str(row.get('period_end') or ''),
    )
    if not annual:
        raise CalculationError('CLASSIFIER_ANNUAL_PERIODS_MISSING')
    window = annual[-years_available:] if years_available > 0 else annual

    shares_fwd = to_decimal(projected_shares_outstanding)
    earnings_fwd = to_decimal(scenario_values.get('EARNINGS'))
    equity_fwd = to_decimal(scenario_values.get('TOTAL_EQUITY'))
    eps_fwd = None if earnings_fwd is None or not shares_fwd else earnings_fwd / shares_fwd
    bvps_fwd = None if equity_fwd is None or not shares_fwd else equity_fwd / shares_fwd

    current_price = _latest_price(prices)

    # Multiples the classifier compares against thresholds. `Metric_PE_Fwd` and
    # `Metric_PBV_Fwd` are price / forward per-share value, not a projection of
    # the historical average multiple (which is what the engine stores).
    projected_pe = (
        None if current_price is None or not eps_fwd else current_price / eps_fwd
    )
    projected_pbv = (
        None if current_price is None or not bvps_fwd else current_price / bvps_fwd
    )

    revenue_long = _result_value(growth_rows, 'GROWTH_REVENUE_CAGR_LONG')
    revenue_cov = _result_value(growth_rows, 'GROWTH_REVENUE_COV')
    revenue_momentum = _result_value(growth_rows, 'QUALITY_REVENUE_MOMENTUM')
    eps_long = _result_value(growth_rows, 'GROWTH_EPS_CAGR_LONG')

    # `IF(Metric_EPS_CAGR_Long <= 0, "N/A", PE_fwd / (EPS_CAGR_Long * 100))`.
    projected_peg = (
        None if projected_pe is None or eps_long is None or eps_long <= 0
        else projected_pe / (eps_long * 100)
    )

    roe_values: list[Decimal] = []
    gpm_ratios: list[Decimal] = []
    for period in window:
        period_id = str(period.get('id') or '')
        earnings = _fact(index, period_id, 'EARNINGS')
        equity = _fact(index, period_id, 'TOTAL_EQUITY')
        if earnings is not None and equity:
            roe_values.append(earnings / equity)
        gross_profit = _fact(index, period_id, 'GROSS_PROFIT')
        revenue = _fact(index, period_id, 'REVENUE')
        if gross_profit is not None and revenue:
            gpm_ratios.append(gross_profit / revenue)

    historical_roe_average = (
        sum(roe_values) / Decimal(len(roe_values)) if roe_values else None
    )

    # The workbook's `GPM Range` is (MAX - MIN) * 100; the classifier's
    # `margin_stability > 0.2` test expects the same quantity as a ratio.
    gpm_stability = max(gpm_ratios) - min(gpm_ratios) if gpm_ratios else None

    dps_by_year: dict[int, Decimal] = {}
    for row in dividend_rows:
        if str(row.get('fact_type')) != 'ANNUAL_TOTAL':
            continue
        year = row.get('period_year')
        amount = to_decimal(row.get('amount_per_share'))
        if year is None or amount is None:
            continue
        dps_by_year[int(year)] = amount

    yield_series: list[Decimal] = []
    payout_series: list[Decimal] = []
    pbv_series: list[Decimal] = []
    for period in window:
        period_id = str(period.get('id') or '')
        label = str(period.get('period_label') or '')
        if not label.isdigit():
            continue
        price = _year_end_price(prices, str(period.get('period_end') or ''))
        dps = dps_by_year.get(int(label), Decimal(0))
        if price is not None and price > 0:
            yield_series.append(dps / price)
        earnings = _fact(index, period_id, 'EARNINGS')
        shares = _fact(index, period_id, 'OUTSTANDING_SHARES')
        equity = _fact(index, period_id, 'TOTAL_EQUITY')
        if earnings is not None and shares:
            eps = earnings / shares
            # `TRIMMEAN(IF(Range_EPS > 0, DPS/EPS), 0.2)` -- loss years excluded.
            if eps > 0:
                payout_series.append(dps / eps)
            if price is not None and price > 0 and equity:
                bvps = equity / shares
                if bvps > 0:
                    pbv_series.append(price / bvps)

    historical_dividend_yield = trimmean(yield_series, TRIMMEAN_PERCENT)
    payout_ratio = trimmean(payout_series, TRIMMEAN_PERCENT)
    pbv_percentile = (
        None if projected_pbv is None else percentrank_inc(pbv_series, projected_pbv)
    )

    return {
        'revenue_long': revenue_long,
        'revenue_cov': revenue_cov,
        'revenue_momentum': revenue_momentum,
        'eps_long': eps_long,
        'projected_net_income': earnings_fwd,
        'payout_ratio': payout_ratio,
        'historical_roe_average': historical_roe_average,
        'projected_pbv': projected_pbv,
        'pbv_percentile': pbv_percentile,
        'projected_pe': projected_pe,
        'projected_peg': projected_peg,
        'historical_dividend_yield': historical_dividend_yield,
        'gpm_stability': gpm_stability,
    }


def _latest_growth_run_id(db: SupabaseRest, instrument_id: str) -> str:
    """Latest SUCCEEDED QUARTERLY_GROWTH_QUALITY run for the instrument."""
    runs = db.get_all('calculation_runs', {
        'scope_id': 'eq.' + instrument_id,
        'calculation_type': 'eq.QUARTERLY_GROWTH_QUALITY',
        'status': 'eq.SUCCEEDED',
        'select': 'id,created_at',
        'order': 'created_at.desc',
        'limit': '1',
    })
    if not runs:
        raise CalculationError('ANNUAL_GROWTH_QUALITY_RUN_NOT_FOUND')
    return str(runs[0]['id'])


def load_live_inputs(
    db: SupabaseRest,
    *,
    ticker: str,
    scenario_code: str | None = None,
    years_available: int = DEFAULT_YEARS_AVAILABLE,
) -> tuple[dict[str, Any], dict[str, Decimal | None], str, str]:
    """Fetch canonical data and derive classifier inputs for one ticker.

    Returns ``(instrument, inputs, instrument_id, growth_run_id)``. The growth
    run id is returned because the annual Class-B rows the classifier consumes
    are pinned to that run, and the caller persists its own run against the same
    inputs.
    """
    instruments = db.get_all('instruments', {
        'ticker': 'eq.' + ticker,
        'select': 'id,ticker,company_name,sector_name',
    })
    if len(instruments) != 1:
        raise CalculationError(f'INSTRUMENT_NOT_FOUND_OR_NOT_UNIQUE: {ticker}')
    instrument = instruments[0]
    instrument_id = str(instrument['id'])

    scenarios = db.get_all('projection_scenarios', {
        'instrument_id': 'eq.' + instrument_id,
        'status': 'eq.ACTIVE',
        'select': (
            'id,scenario_code,as_of_financial_period_id,projected_shares_outstanding,'
            'years_available,status'
        ),
    })
    if scenario_code:
        scenarios = [row for row in scenarios if row.get('scenario_code') == scenario_code]
    if len(scenarios) != 1:
        raise CalculationError(
            'ACTIVE_PROJECTION_SCENARIO_NOT_UNIQUE: pass scenario_code when several are active'
        )
    scenario = dict(scenarios[0])
    projection_rows = db.get_all('projection_values', {
        'scenario_id': 'eq.' + str(scenario['id']),
        'select': 'metric_code,value_numeric',
    })
    scenario_values = {row['metric_code']: row['value_numeric'] for row in projection_rows}

    periods = db.get_all('financial_periods', {
        'instrument_id': 'eq.' + instrument_id,
        'select': ANNUAL_PERIOD_SELECT,
        'order': 'period_end.asc',
    })
    period_ids = [str(row['id']) for row in periods]
    if not period_ids:
        raise CalculationError('FINANCIAL_PERIODS_MISSING')
    facts: list[dict[str, Any]] = []
    for offset in range(0, len(period_ids), 100):
        facts.extend(db.get_all('financial_facts', {
            'financial_period_id': 'in.(' + ','.join(period_ids[offset:offset + 100]) + ')',
            'revision_key': 'eq.CURRENT',
            'select': FACT_SELECT,
        }))

    prices = _pages(db, 'prices_daily', {
        'instrument_id': 'eq.' + instrument_id,
        'select': 'trading_date,close_price',
        'order': 'trading_date.asc',
    })
    if not prices:
        raise CalculationError('PRICE_HISTORY_MISSING')

    dividend_rows = db.get_all('dividend_facts', {
        'instrument_id': 'eq.' + instrument_id,
        'select': 'fact_type,period_year,amount_per_share',
    })

    growth_run_id = _latest_growth_run_id(db, instrument_id)
    # `calc_annual_growth_quality` stores one snapshot per annual period, so the
    # same metric code appears once per year. The classifier consumes the latest
    # snapshot only; filtering by run alone would return the oldest year first.
    annual_periods = [row for row in periods if row.get('period_type') == 'ANNUAL']
    if not annual_periods:
        raise CalculationError('CLASSIFIER_ANNUAL_PERIODS_MISSING')
    latest_annual_id = str(
        max(annual_periods, key=lambda row: str(row.get('period_end') or ''))['id']
    )
    growth_rows = db.get_all('calc_annual_growth_quality', {
        'instrument_id': 'eq.' + instrument_id,
        'calculation_run_id': 'eq.' + growth_run_id,
        'financial_period_id': 'eq.' + latest_annual_id,
        'select': 'metric_code,value_numeric,calculation_status',
    })

    inputs = derive_classifier_inputs(
        annual_periods=periods,
        facts=facts,
        prices=prices,
        dividend_rows=dividend_rows,
        scenario_values=scenario_values,
        projected_shares_outstanding=scenario.get('projected_shares_outstanding'),
        growth_rows=growth_rows,
        years_available=years_available,
    )
    return instrument, inputs, instrument_id, growth_run_id


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ticker', required=True, help='IDX ticker, e.g. SIDO')
    parser.add_argument('--scenario-code', help='Active scenario code when several are active.')
    parser.add_argument('--years-available', type=int, default=DEFAULT_YEARS_AVAILABLE)
    args = parser.parse_args(argv)

    load_env_file(REPO_ROOT / '.env')
    db = SupabaseRest(os.getenv('SUPABASE_URL', ''), os.getenv('SUPABASE_SERVICE_ROLE_KEY', ''))
    instrument, inputs, _instrument_id, growth_run_id = load_live_inputs(
        db,
        ticker=args.ticker.strip().upper().replace('.JK', ''),
        scenario_code=args.scenario_code,
        years_available=args.years_available,
    )
    print(f"Ticker: {instrument['ticker']} ({instrument.get('sector_name') or 'sector unknown'})")
    print(f'Growth run: {growth_run_id}')
    for code in CLASSIFIER_INPUT_CODES:
        value = inputs.get(code)
        print(f'  {code}: {value if value is not None else "UNAVAILABLE"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

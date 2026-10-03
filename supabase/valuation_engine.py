"""Pure valuation-current calculations for the workbook's five methods.

All money inputs use canonical IDR and raw outstanding-share counts. Returned
per-share amounts are IDR/share; the workbook's display scaling is not applied.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
import re
from typing import Any, Mapping, Sequence

from calculation_registry import sha256_json
from calculation_v1_common import DECIMAL_PRECISION

#: Margin-of-safety refusal flags, workbook rule D6. Defined here rather than
#: imported from `backtest_engine` so this module keeps its single dependency on
#: the shared layer; `tests/test_valuation_engine.py` pins the literals.
FLAG_MOS_DENOMINATOR_ZERO = 'MOS_DENOMINATOR_ZERO'
FLAG_MOS_NOT_APPLICABLE = 'MOS_NOT_APPLICABLE'

CODE_VERSION = 'stocklens-valuation-v1'
REFERENCE_VERSION = '1.0.0'
DEFAULT_YEARS_COMPARE = {
    'years_avail_ge_7': 5,
    'years_avail_ge_5': 3,
    'years_avail_ge_3': 2,
    'default': 0,
}
STOCK_TYPES = ('SLOW GROWER', 'STALWART', 'FAST GROWER', 'CYCLICAL', 'TURN AROUND', 'ASSET PLAY')

PER_TARGETS = {
    'SLOW GROWER': ('8', '12'),
    'STALWART': ('10', '16'),
    'STALWART_FINANCIAL': ('15', '25'),
}
TARGET_PBV = {
    'CONSERVATIVE_BOTTOM': Decimal('0.4'),
    'MODERATE_BOTTOM': Decimal('0.5'),
    'AGGRESSIVE_BOTTOM': Decimal('0.7'),
    'CONSERVATIVE_TOP': Decimal('0.8'),
    'MODERATE_TOP': Decimal('1'),
    'AGGRESSIVE_TOP': Decimal('1.2'),
}
TYPE_MODE = {
    'FAST GROWER': 'AGGRESSIVE',
    'CYCLICAL': 'MODERATE',
    'ASSET PLAY': 'MODERATE',
    'STALWART': 'MODERATE',
    'TURN AROUND': 'CONSERVATIVE',
}
METHOD_NAMES = {
    'PETER_LYNCH': 'Peter Lynch Algo [Adaptive Stock Type]',
    'TYPE_SECTOR_WEIGHTED': 'Type & Sector Weighted [Blended Rule]',
    'MEAN_REVERSION_PBV': 'Mean Reversion PBV [Asset]',
    'DDM': 'Dividend Discount Model [Cash Flow]',
    'DISCOUNTED_EARNINGS': 'Discounted Earnings Model [Growth]',
}


class ValuationError(RuntimeError):
    pass


def decimal_value(value: Any) -> Decimal | None:
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        raise ValuationError('VALUATION_VALUE_NOT_NUMERIC')
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValuationError('VALUATION_VALUE_NOT_NUMERIC') from error
    if not result.is_finite():
        raise ValuationError('VALUATION_VALUE_NOT_FINITE')
    return result


def decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value == 0:
        return '0'
    return format(value.normalize(), 'f')


def _safe_id(row: Mapping[str, Any]) -> str:
    return str(row.get('id') or row.get('financial_period_id') or '')


def _facts_by_period(facts: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Mapping[str, Any]]]:
    result: dict[str, dict[str, Mapping[str, Any]]] = {}
    for fact in facts:
        period_id = str(fact.get('financial_period_id') or '')
        code = str(fact.get('metric_code') or '')
        if period_id and code:
            # A current, valid canonical fact is unique per period/code/revision.
            previous = result.setdefault(period_id, {}).get(code)
            if previous is None or str(fact.get('revision_key') or '') == 'CURRENT':
                result[period_id][code] = fact
    return result


def _fact_value(
    fact_index: Mapping[str, Mapping[str, Mapping[str, Any]]],
    period: Mapping[str, Any],
    metric_code: str,
) -> Decimal | None:
    fact = fact_index.get(_safe_id(period), {}).get(metric_code)
    if not fact or fact.get('quality_status') in ('MISSING', 'INVALID'):
        return None
    return decimal_value(fact.get('value_numeric'))


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    return sum(values, Decimal(0)) / Decimal(len(values)) if values else None


def _stdev_pop(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    mean = _mean(values)
    assert mean is not None
    variance = sum(((value - mean) ** 2 for value in values), Decimal(0)) / Decimal(len(values))
    return variance.sqrt()


def _ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return numerator / denominator


def comparison_years(years_available: int, override: int | None = None) -> int:
    if years_available < 1:
        raise ValuationError('YEARS_AVAILABLE_INVALID')
    if override is not None:
        if override < 0 or override >= years_available:
            raise ValuationError('YEARS_COMPARE_OUT_OF_RANGE')
        return override
    return comparison_years_from_ladder(years_available, override, DEFAULT_YEARS_COMPARE)


def comparison_years_from_ladder(
    years_available: int,
    override: int | None,
    ladder_values: Mapping[str, Any],
) -> int:
    if years_available < 1:
        raise ValuationError('YEARS_AVAILABLE_INVALID')
    if override is not None:
        if override < 0 or override >= years_available:
            raise ValuationError('YEARS_COMPARE_OUT_OF_RANGE')
        return override
    for key, value in sorted(
        ((int(key.rsplit('_', 1)[1]), int(value)) for key, value in ladder_values.items()
         if key.startswith('years_avail_ge_')),
        reverse=True,
    ):
        if years_available >= key:
            return value
    return int(ladder_values.get('default', 0))


def normalize_stock_type(stock_type: str) -> str:
    normalized = ' '.join(stock_type.upper().replace('_', ' ').split())
    if normalized == 'TURNAROUND':
        normalized = 'TURN AROUND'
    if normalized not in STOCK_TYPES:
        raise ValuationError('STOCK_TYPE_UNKNOWN')
    return normalized


def _growth_rate(values: Sequence[Decimal], years: int) -> Decimal | None:
    if years <= 0 or len(values) < years + 1:
        return None
    start, end = values[-(years + 1)], values[-1]
    if start <= 0 or end < 0:
        return None
    if end == 0:
        return Decimal('-1')
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        return (end / start) ** (Decimal(1) / Decimal(years)) - Decimal(1)


def _fast_grower_per_multiple(expression: Any, growth_rate: Decimal) -> Decimal:
    """Evaluate the registered ``growth_rate * 100 * factor`` expression."""
    match = re.fullmatch(
        r'\s*growth_rate\s*\*\s*100\s*\*\s*([0-9]+(?:\.[0-9]+)?)\s*',
        str(expression),
        flags=re.IGNORECASE,
    )
    if not match:
        raise ValuationError('FAST_GROWER_PER_EXPRESSION_INVALID')
    return growth_rate * Decimal(100) * Decimal(match.group(1))


def _status_for(value: Decimal | None, flags: Sequence[str] = ()) -> str:
    if value is None:
        return 'UNAVAILABLE'
    if any(flag != 'POINT_IN_TIME_UNVERIFIED' for flag in flags):
        return 'APPROXIMATED'
    return 'VALID'


def _point_in_time_flags(periods: Sequence[Mapping[str, Any]]) -> list[str]:
    if any(not row.get('available_date') or not row.get('report_date') for row in periods):
        return ['POINT_IN_TIME_UNVERIFIED']
    return []


def _year_end_price(
    prices: Sequence[Mapping[str, Any]],
    period_end: str,
) -> Decimal | None:
    selected = _year_end_price_row(prices, period_end)
    return decimal_value(selected.get('close_price')) if selected else None


def _year_end_price_row(
    prices: Sequence[Mapping[str, Any]],
    period_end: str,
) -> Mapping[str, Any] | None:
    target_year = int(period_end[:4])
    target_date = date.fromisoformat(period_end)
    year_start = date(target_year, 1, 1).isoformat()
    eligible = [
        row for row in prices
        if year_start <= str(row.get('trading_date') or '') <= target_date.isoformat()
        and row.get('close_price') is not None
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda row: str(row.get('trading_date') or ''))


def calculate_valuation_snapshot(
    *,
    ticker: str,
    sector: str | None,
    stock_type: str,
    annual_periods: Sequence[Mapping[str, Any]],
    quarterly_periods: Sequence[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
    prices: Sequence[Mapping[str, Any]],
    scenario: Mapping[str, Any],
    valuation_date: str,
    years_available: int | None = None,
    years_compare: int | None = None,
    risk_free_rate: Any = None,
    risk_free_source: str | None = None,
    sector_weights: Mapping[str, Any] | None = None,
    type_weights: Mapping[str, Any] | None = None,
    type_thresholds: Mapping[str, Any] | None = None,
    valuation_parameters: Mapping[str, Any] | None = None,
    include_daily_status: bool = True,
) -> dict[str, Any]:
    """Compute valuation inputs and the five workbook method snapshots.

    Unresolved/missing inputs return explicit UNAVAILABLE results. The sole
    documented approximation is annual shares carried to quarterly PBV history.
    """
    normalized_type = normalize_stock_type(stock_type)
    params = dict(valuation_parameters or {})
    compare_ladder = params.get('years_compare_thresholds', DEFAULT_YEARS_COMPARE)
    as_of_period_id = str(scenario.get('as_of_financial_period_id') or '')
    if not as_of_period_id:
        raise ValuationError('PROJECTION_BASE_PERIOD_MISSING')
    all_periods = [dict(row) for row in [*annual_periods, *quarterly_periods]]
    period_by_id = {_safe_id(row): row for row in all_periods}
    if as_of_period_id not in period_by_id:
        raise ValuationError('PROJECTION_BASE_PERIOD_NOT_FOUND')
    as_of_period = period_by_id[as_of_period_id]
    as_of_end = str(as_of_period.get('period_end') or '')
    if not as_of_end:
        raise ValuationError('PROJECTION_BASE_PERIOD_END_MISSING')
    try:
        as_of_date = date.fromisoformat(valuation_date)
    except ValueError as error:
        raise ValuationError('VALUATION_DATE_INVALID') from error
    if as_of_date < date.fromisoformat(as_of_end):
        raise ValuationError('VALUATION_DATE_BEFORE_PROJECTION_BASE')

    available_years = int(
        scenario.get('years_available') if years_available is None
        else years_available
    )
    if available_years <= 0:
        raise ValuationError('YEARS_AVAILABLE_INVALID')
    if available_years <= 0:
        raise ValuationError('YEARS_AVAILABLE_INVALID')
    annual = sorted(
        (dict(row) for row in annual_periods if str(row.get('period_end') or '') <= as_of_end),
        key=lambda row: str(row.get('period_end') or ''),
    )
    if not annual:
        raise ValuationError('ANNUAL_PERIODS_MISSING')
    if available_years > len(annual):
        raise ValuationError('YEARS_AVAILABLE_EXCEEDS_HISTORY')
    annual = annual[-available_years:]
    annual_pit_flags = _point_in_time_flags(annual)
    compare_years = comparison_years_from_ladder(available_years, years_compare, compare_ladder)
    quarter = sorted(
        (dict(row) for row in quarterly_periods if str(row.get('period_end') or '') <= as_of_end),
        key=lambda row: str(row.get('period_end') or ''),
    )
    fact_index = _facts_by_period(facts)

    annual_revenue = [_fact_value(fact_index, row, 'REVENUE') for row in annual]
    annual_revenue_valid = [value for value in annual_revenue if value is not None]
    revenue_long = (
        _growth_rate(annual_revenue, len(annual_revenue) - 1)
        if all(value is not None for value in annual_revenue) else None
    )
    revenue_short = (
        _growth_rate(annual_revenue, compare_years)
        if compare_years > 0 and all(value is not None for value in annual_revenue) else None
    )
    annual_eps: list[tuple[Mapping[str, Any], Decimal]] = []
    annual_bvps: list[tuple[Mapping[str, Any], Decimal]] = []
    for period in annual:
        earnings = _fact_value(fact_index, period, 'EARNINGS')
        equity = _fact_value(fact_index, period, 'TOTAL_EQUITY')
        shares = _fact_value(fact_index, period, 'OUTSTANDING_SHARES')
        eps = _ratio(earnings, shares)
        bvps = _ratio(equity, shares)
        if eps is not None:
            annual_eps.append((period, eps))
        if bvps is not None:
            annual_bvps.append((period, bvps))

    eps_mean = _mean([value for _, value in annual_eps])
    pe_outlier_factor = Decimal(str(params.get('pe_average_outlier_factor', '0.25')))
    pe_history: list[Decimal] = []
    for period, eps in annual_eps:
        period_end = str(period.get('period_end') or '')
        price = _year_end_price(prices, period_end)
        if price is not None and price > 0 and eps_mean is not None and eps > eps_mean * pe_outlier_factor and eps != 0:
            pe_history.append(price / eps)
    pe_average = _mean(pe_history)

    pbv_history: list[tuple[str, Decimal]] = []
    for period, bvps in annual_bvps:
        price = _year_end_price(prices, str(period.get('period_end') or ''))
        if price is not None and price > 0 and bvps > 0:
            pbv_history.append((str(period.get('period_end') or ''), price / bvps))
    pbv_average = _mean([value for _, value in pbv_history])
    pbv_compare = _mean([value for _, value in pbv_history[-compare_years:]]) if compare_years else None

    scenario_values: Mapping[str, Any] = scenario.get('values') or {}

    def projected(code: str) -> Decimal | None:
        return decimal_value(scenario_values.get(code))

    shares_fwd = decimal_value(scenario.get('projected_shares_outstanding'))
    earnings_fwd = projected('EARNINGS')
    equity_fwd = projected('TOTAL_EQUITY')
    current_assets_actual = _fact_value(fact_index, as_of_period, 'CURRENT_ASSETS')
    if current_assets_actual is None:
        current_assets_actual = _fact_value(fact_index, as_of_period, 'TOTAL_CURRENT_ASSET')
    liabilities_actual = _fact_value(fact_index, as_of_period, 'TOTAL_LIABILITIES')
    eps_fwd = _ratio(earnings_fwd, shares_fwd)
    bvps_fwd = _ratio(equity_fwd, shares_fwd)
    liquidation_value = _ratio(
        None if current_assets_actual is None or liabilities_actual is None else current_assets_actual - liabilities_actual,
        shares_fwd,
    )
    pe_projected = None if eps_fwd is None or pe_average is None else eps_fwd * pe_average
    pbv_projected = None if bvps_fwd is None or pbv_average is None else bvps_fwd * pbv_average

    eligible_prices = [
        row for row in prices
        if str(row.get('trading_date') or '') <= as_of_date.isoformat() and row.get('close_price') is not None
    ]
    latest_price = max(eligible_prices, key=lambda row: str(row['trading_date'])) if eligible_prices else None
    current_price = decimal_value(latest_price.get('close_price')) if latest_price else None
    current_price_date = str(latest_price.get('trading_date')) if latest_price else None

    # The current growth input is latest actual quarterly revenue versus the
    # same standalone quarter one year earlier.
    current_quarter_index = next(
        (index for index, row in enumerate(quarter) if _safe_id(row) == as_of_period_id),
        None,
    )
    previous_same_quarter = None
    if current_quarter_index is not None:
        current_q_label = str(quarter[current_quarter_index].get('period_label') or '')[-2:]
        previous_same_quarter = next(
            (row for row in reversed(quarter[:current_quarter_index])
             if str(row.get('period_label') or '')[-2:] == current_q_label),
            None,
        )
    qrev_now = _fact_value(fact_index, as_of_period, 'REVENUE')
    qrev_prior = (
        _fact_value(fact_index, previous_same_quarter, 'REVENUE')
        if previous_same_quarter is not None else None
    )
    revenue_growth_now = _ratio(
        None if qrev_now is None or qrev_prior is None else qrev_now - qrev_prior,
        qrev_prior,
    )
    momentum = (
        'ACCELERATING' if revenue_short is not None and revenue_long is not None and revenue_short > revenue_long
        else 'SLOWING' if revenue_short is not None and revenue_long is not None
        else None
    )

    target_per_by_type = params.get('target_per_by_type', PER_TARGETS)
    target_pbv_by_mode = params.get('target_pbv_by_mode')
    type_to_mode = params.get('type_to_valuation_mode', TYPE_MODE)
    mode = str(type_to_mode.get(normalized_type, type_to_mode.get(normalized_type.title(), 'Conservative'))).upper()
    type_key = (
        'STALWART_FINANCIAL'
        if normalized_type == 'STALWART' and 'FINANCIAL' in (sector or '').upper()
        else normalized_type
    )
    if normalized_type in ('CYCLICAL', 'ASSET PLAY', 'TURN AROUND'):
        type_key = normalized_type
    if normalized_type == 'FAST GROWER':
        fast_targets = target_per_by_type.get('FAST GROWER', {})
        if not isinstance(fast_targets, Mapping):
            raise ValuationError('FAST_GROWER_PER_TARGETS_INVALID')
        per_bottom = (
            None if revenue_short is None
            else _fast_grower_per_multiple(fast_targets.get('bottom'), revenue_short)
        )
        per_top = (
            None if revenue_short is None
            else _fast_grower_per_multiple(fast_targets.get('top'), revenue_short)
        )
    elif type_key in target_per_by_type:
        targets = target_per_by_type[type_key]
        if isinstance(targets, Mapping):
            per_bottom, per_top = Decimal(str(targets['bottom'])), Decimal(str(targets['top']))
        else:
            per_bottom, per_top = (Decimal(str(value)) for value in targets)
    elif type_key == 'DEFAULT' and 'DEFAULT' in target_per_by_type:
        targets = target_per_by_type['DEFAULT']
        if isinstance(targets, Mapping):
            per_bottom, per_top = Decimal(str(targets['bottom'])), Decimal(str(targets['top']))
        else:
            per_bottom = per_top = Decimal(str(targets))
    else:
        per_bottom = per_top = Decimal(0)
    per_fair_bottom = None if per_bottom is None or eps_fwd is None else per_bottom * eps_fwd
    per_fair_top = None if per_top is None or eps_fwd is None else per_top * eps_fwd

    if target_pbv_by_mode:
        pbv_bottom_multiple = Decimal(str(target_pbv_by_mode[f'{mode.title()}_bottom']))
        pbv_top_multiple = Decimal(str(target_pbv_by_mode[f'{mode.title()}_top']))
    else:
        pbv_bottom_multiple = TARGET_PBV[f'{mode}_BOTTOM']
        pbv_top_multiple = TARGET_PBV[f'{mode}_TOP']
    asset_target = None if bvps_fwd is None else bvps_fwd * pbv_bottom_multiple
    cyclical_target = None if bvps_fwd is None else bvps_fwd * pbv_top_multiple

    if normalized_type == 'TURN AROUND':
        peter_lynch = liquidation_value
        peter_branch = 'LIQUIDATION_VALUE'
    elif normalized_type == 'ASSET PLAY':
        peter_lynch = asset_target
        peter_branch = 'ASSET_PBV'
    elif normalized_type == 'CYCLICAL':
        peter_lynch = cyclical_target
        peter_branch = 'CYCLICAL_PBV'
    elif revenue_growth_now is None or revenue_long is None:
        peter_lynch = None
        peter_branch = 'GROWTH_INPUTS_UNAVAILABLE'
    elif revenue_growth_now > revenue_long and revenue_short is not None and revenue_long is not None and revenue_short <= revenue_long:
        peter_lynch = None if per_fair_bottom is None or per_fair_top is None else (per_fair_bottom + per_fair_top) / 2
        peter_branch = 'PER_RANGE_MIDPOINT'
    elif revenue_growth_now > revenue_long and revenue_short is not None and revenue_long is not None and revenue_short > revenue_long:
        peter_lynch = per_fair_top
        peter_branch = 'PER_TOP'
    elif revenue_growth_now < revenue_long:
        peter_lynch = per_fair_bottom
        peter_branch = 'PER_BOTTOM'
    else:
        peter_lynch = None if per_fair_bottom is None or per_fair_top is None else (per_fair_bottom + per_fair_top) / 2
        peter_branch = 'PER_RANGE_MIDPOINT'

    sector_weight = dict(sector_weights or {})
    type_weight = dict(type_weights or {})
    thresholds = dict(type_thresholds or {})
    missing_weight_flags: list[str] = []
    if not sector or not sector_weight:
        missing_weight_flags.append('SECTOR_WEIGHT_UNCLASSIFIED')
    if not type_weight:
        missing_weight_flags.append('TYPE_WEIGHT_UNCLASSIFIED')
    if missing_weight_flags or pe_projected is None or pbv_projected is None:
        weighted_value = None
        weight_pe = weight_pbv = None
    else:
        weight_pe = (Decimal(str(sector_weight['w_pe'])) + Decimal(str(type_weight['w_pe']))) / 2
        weight_pbv = (Decimal(str(sector_weight['w_pbv'])) + Decimal(str(type_weight['w_pbv']))) / 2
        denominator = weight_pe + weight_pbv
        weighted_value = None if denominator == 0 else (pe_projected * weight_pe + pbv_projected * weight_pbv) / denominator

    years_quarter_window = compare_years * 4
    quarterly_window = quarter[-years_quarter_window:] if years_quarter_window else []
    window_pit_flags = _point_in_time_flags(quarterly_window)
    all_periods_pit_flags = _point_in_time_flags([*annual, *quarterly_window, as_of_period])
    shares_by_year = [
        (int(str(period.get('period_end') or '')[:4]), _fact_value(fact_index, period, 'OUTSTANDING_SHARES'))
        for period in annual
    ]
    quarterly_pbvs: list[Decimal] = []
    quarter_proxy_count = 0
    for period in quarterly_window:
        equity = _fact_value(fact_index, period, 'TOTAL_EQUITY')
        price = _year_end_price(prices, str(period.get('period_end') or ''))
        fiscal_year = int(str(period.get('period_end') or '')[:4])
        eligible_shares = [(year, value) for year, value in shares_by_year if year <= fiscal_year and value is not None]
        shares = max(eligible_shares, key=lambda item: item[0])[1] if eligible_shares else None
        if shares is not None:
            quarter_proxy_count += 1
        historical_bvps = _ratio(equity, shares)
        if price is not None and price > 0 and historical_bvps is not None and historical_bvps > 0:
            quarterly_pbvs.append(price / historical_bvps)
    min_quarters = int(params.get('mean_reversion_min_quarters', 3))
    if len(quarterly_pbvs) < min_quarters or bvps_fwd is None:
        mean_reversion = None
        mean_reversion_flags = ['INSUFFICIENT_VALID_PBV_HISTORY']
    else:
        pbv_mean = _mean(quarterly_pbvs)
        pbv_stdev = _stdev_pop(quarterly_pbvs)
        assert pbv_mean is not None and pbv_stdev is not None
        mean_reversion = max((pbv_mean - pbv_stdev) * bvps_fwd, Decimal(0))
        mean_reversion_flags = [
            'QUARTERLY_SHARES_ANNUAL_PROXY',
            'QUARTER_END_PRICE_PROXY',
            *window_pit_flags,
        ]

    rfr = decimal_value(risk_free_rate)
    rfr_resolved = rfr is not None and bool((risk_free_source or '').strip())
    dps_fwd = projected('POTENTIAL_DPS')
    if not rfr_resolved:
        ddm_value = None
        discounted_earnings_value = None
        rate_flags = ['RISK_FREE_RATE_UNRESOLVED']
    else:
        rate_flags = []
        wacc = rfr + Decimal(str(params.get('equity_risk_premium_ddm', '0.06')))
        ddm_cap = Decimal(str(params.get('ddm_growth_cap', '0.04')))
        ddm_growth = None if revenue_long is None else min(ddm_cap, max(Decimal(0), revenue_long))
        ddm_value = (
            None if dps_fwd is None or ddm_growth is None or wacc <= ddm_growth
            else dps_fwd * (Decimal(1) + ddm_growth) / (wacc - ddm_growth)
        )
        earnings_growth = None if revenue_long is None else min(
            Decimal(str(params.get('discounted_earnings_growth_cap', '0.15'))),
            max(Decimal(0), revenue_long),
        )
        if eps_fwd is None or earnings_growth is None or pe_average is None:
            discounted_earnings_value = None
        else:
            pe_capped = min(pe_average, Decimal(str(params.get('discounted_earnings_per_cap', '25'))))
            disc_rate = rfr + Decimal(str(params.get('discounted_earnings_discount_premium', '0.04')))
            horizon = int(params.get('discounted_earnings_horizon_years', 5))
            future_eps = eps_fwd * (Decimal(1) + earnings_growth) ** horizon
            discounted_earnings_value = max(future_eps * pe_capped / ((Decimal(1) + disc_rate) ** horizon), Decimal(0))

    input_values: dict[str, tuple[Decimal | None, str, list[str], dict[str, Any]]] = {
        **({'CURRENT_PRICE': (current_price, 'IDR_PER_SHARE', [] if current_price is not None else ['CURRENT_PRICE_MISSING'], {'price_date': current_price_date})} if include_daily_status else {}),
        'EPS_FWD': (eps_fwd, 'IDR_PER_SHARE', [] if eps_fwd is not None else ['FORWARD_EARNINGS_OR_SHARES_MISSING'], {}),
        'BVPS_FWD': (bvps_fwd, 'IDR_PER_SHARE', [] if bvps_fwd is not None else ['FORWARD_EQUITY_OR_SHARES_MISSING'], {}),
        'REVENUE_CAGR_LONG': (revenue_long, 'RATIO', [] if revenue_long is not None else ['REVENUE_HISTORY_INSUFFICIENT'], {}),
        'REVENUE_CAGR_COMPARE': (revenue_short, 'RATIO', [] if revenue_short is not None else ['COMPARISON_REVENUE_HISTORY_INSUFFICIENT'], {'momentum': momentum}),
        'REVENUE_GROWTH_ACTUAL': (revenue_growth_now, 'RATIO', [] if revenue_growth_now is not None else ['PRIOR_ANNUAL_REVENUE_MISSING'], {}),
        'REVENUE_MOMENTUM': (None, 'TEXT', [] if momentum is not None else ['COMPARISON_REVENUE_HISTORY_INSUFFICIENT'], {'label': momentum}),
        'PER_AVG_LONG': (pe_average, 'MULTIPLE', [] if pe_average is not None else ['VALID_HISTORICAL_PER_MISSING'], {'observation_count': len(pe_history)}),
        'PBV_AVG_LONG': (pbv_average, 'MULTIPLE', [] if pbv_average is not None else ['VALID_HISTORICAL_PBV_MISSING'], {'observation_count': len(pbv_history)}),
        'PBV_AVG_COMPARE': (pbv_compare, 'MULTIPLE', [] if pbv_compare is not None else ['COMPARISON_HISTORICAL_PBV_MISSING'], {'observation_count': min(len(pbv_history), compare_years)}),
        'PE_PROJECTED': (pe_projected, 'IDR_PER_SHARE', [] if pe_projected is not None else ['EPS_OR_PER_HISTORY_MISSING'], {}),
        'PBV_PROJECTED': (pbv_projected, 'IDR_PER_SHARE', [] if pbv_projected is not None else ['BVPS_OR_PBV_HISTORY_MISSING'], {}),
        'PER_FAIR_VALUE_BOTTOM': (per_fair_bottom, 'IDR_PER_SHARE', [] if per_fair_bottom is not None else ['PER_BOTTOM_INPUT_MISSING'], {'target_per': decimal_text(per_bottom)}),
        'PER_FAIR_VALUE_TOP': (per_fair_top, 'IDR_PER_SHARE', [] if per_fair_top is not None else ['PER_TOP_INPUT_MISSING'], {'target_per': decimal_text(per_top)}),
        'LIQUIDATION_VALUE': (liquidation_value, 'IDR_PER_SHARE', [] if liquidation_value is not None else ['CURRENT_ASSETS_OR_LIABILITIES_MISSING'], {'basis_period_id': as_of_period_id}),
        'ASSET_PLAY_TARGET_PBV': (asset_target, 'IDR_PER_SHARE', [] if asset_target is not None else ['BVPS_FWD_MISSING'], {'target_pbv': decimal_text(pbv_bottom_multiple), 'mode': mode}),
        'CYCLICAL_TARGET_PBV': (cyclical_target, 'IDR_PER_SHARE', [] if cyclical_target is not None else ['BVPS_FWD_MISSING'], {'target_pbv': decimal_text(pbv_top_multiple), 'mode': mode}),
        'WEIGHT_PE': (weight_pe, 'WEIGHT', missing_weight_flags, {}),
        'WEIGHT_PBV': (weight_pbv, 'WEIGHT', missing_weight_flags, {}),
        'SECTOR_WEIGHT_PE': (decimal_value(sector_weight.get('w_pe')), 'WEIGHT', [] if sector_weight else ['SECTOR_WEIGHT_UNCLASSIFIED'], {}),
        'SECTOR_WEIGHT_PBV': (decimal_value(sector_weight.get('w_pbv')), 'WEIGHT', [] if sector_weight else ['SECTOR_WEIGHT_UNCLASSIFIED'], {}),
        'SECTOR_WEIGHT_DDM': (decimal_value(sector_weight.get('w_ddm')), 'WEIGHT', [] if sector_weight else ['SECTOR_WEIGHT_UNCLASSIFIED'], {}),
        'SECTOR_WEIGHT_GRAHAM': (decimal_value(sector_weight.get('w_graham')), 'WEIGHT', [] if sector_weight else ['SECTOR_WEIGHT_UNCLASSIFIED'], {}),
        'SECTOR_WEIGHT_PEG': (decimal_value(sector_weight.get('w_peg')), 'WEIGHT', [] if sector_weight else ['SECTOR_WEIGHT_UNCLASSIFIED'], {}),
        'TYPE_WEIGHT_PE': (decimal_value(type_weight.get('w_pe')), 'WEIGHT', [] if type_weight else ['TYPE_WEIGHT_UNCLASSIFIED'], {}),
        'TYPE_WEIGHT_PBV': (decimal_value(type_weight.get('w_pbv')), 'WEIGHT', [] if type_weight else ['TYPE_WEIGHT_UNCLASSIFIED'], {}),
        'TYPE_WEIGHT_DDM': (decimal_value(type_weight.get('w_ddm')), 'WEIGHT', [] if type_weight else ['TYPE_WEIGHT_UNCLASSIFIED'], {}),
        'TYPE_WEIGHT_GRAHAM': (decimal_value(type_weight.get('w_graham')), 'WEIGHT', [] if type_weight else ['TYPE_WEIGHT_UNCLASSIFIED'], {}),
        'TYPE_WEIGHT_PEG': (decimal_value(type_weight.get('w_peg')), 'WEIGHT', [] if type_weight else ['TYPE_WEIGHT_UNCLASSIFIED'], {}),
        'THRESHOLD_MAX_DER': (decimal_value(thresholds.get('max_der')), 'MULTIPLE', [] if thresholds else ['TYPE_THRESHOLD_UNCLASSIFIED'], {}),
        'THRESHOLD_MIN_CR': (decimal_value(thresholds.get('min_cr')), 'MULTIPLE', [] if thresholds else ['TYPE_THRESHOLD_UNCLASSIFIED'], {}),
        'THRESHOLD_MIN_ICR': (decimal_value(thresholds.get('min_icr')), 'MULTIPLE', [] if thresholds else ['TYPE_THRESHOLD_UNCLASSIFIED'], {}),
        'YEARS_AVAILABLE': (Decimal(available_years), 'YEARS', [], {}),
        'YEARS_COMPARE': (Decimal(compare_years), 'YEARS', [], {}),
        'PETER_LYNCH_FAIR_VALUE': (peter_lynch, 'IDR_PER_SHARE', [] if peter_lynch is not None else ['PETER_LYNCH_INPUT_MISSING'], {'branch': peter_branch}),
        'ASSET_PLAY_TARGET_PBV': (asset_target, 'IDR_PER_SHARE', [] if asset_target is not None else ['BVPS_FWD_MISSING'], {'target_pbv': decimal_text(pbv_bottom_multiple), 'mode': mode}),
        'DDM_INTRINSIC_VALUE': (ddm_value, 'IDR_PER_SHARE', rate_flags if not rfr_resolved else ([] if ddm_value is not None else ['DDM_INPUT_MISSING_OR_INVALID']), {'risk_free_rate_source': risk_free_source}),
        'DISCOUNTED_EARNINGS_INTRINSIC_VALUE': (discounted_earnings_value, 'IDR_PER_SHARE', rate_flags if not rfr_resolved else ([] if discounted_earnings_value is not None else ['DISCOUNTED_EARNINGS_INPUT_MISSING']), {'risk_free_rate_source': risk_free_source}),
        'MEAN_REVERSION_PBV_INTRINSIC_VALUE': (mean_reversion, 'IDR_PER_SHARE', mean_reversion_flags, {'valid_quarters': len(quarterly_pbvs), 'window_quarters': len(quarterly_window), 'annual_share_proxy_quarters': quarter_proxy_count}),
    }

    raw_methods = {
        'PETER_LYNCH': (peter_lynch, [] if peter_lynch is not None else ['PETER_LYNCH_INPUT_MISSING'], {'selected_branch': peter_branch}),
        'TYPE_SECTOR_WEIGHTED': (weighted_value, missing_weight_flags if missing_weight_flags else ([] if weighted_value is not None else ['WEIGHTED_INPUT_MISSING']), {'pe_component': decimal_text(pe_projected), 'pbv_component': decimal_text(pbv_projected), 'weight_pe': decimal_text(weight_pe), 'weight_pbv': decimal_text(weight_pbv)}),
        'MEAN_REVERSION_PBV': (mean_reversion, mean_reversion_flags, {'valid_quarters': len(quarterly_pbvs), 'window_quarters': len(quarterly_window)}),
        'DDM': (ddm_value, rate_flags if not rfr_resolved else ([] if ddm_value is not None else ['DDM_INPUT_MISSING_OR_INVALID']), {'risk_free_rate_source': risk_free_source}),
        'DISCOUNTED_EARNINGS': (discounted_earnings_value, rate_flags if not rfr_resolved else ([] if discounted_earnings_value is not None else ['DISCOUNTED_EARNINGS_INPUT_MISSING']), {'risk_free_rate_source': risk_free_source}),
    }
    methods: list[dict[str, Any]] = []
    def current_verdict(value: Decimal | None) -> str:
        if value is None or value <= 0 or current_price is None or current_price <= 0:
            return 'NOT_APPLICABLE'
        return 'UNDERVALUED' if current_price < value else 'OVERVALUED'

    def current_mos(value: Decimal | None) -> tuple[Decimal | None, list[str]]:
        if value is None or current_price is None:
            return None, []
        if value == 0:
            return None, [FLAG_MOS_DENOMINATOR_ZERO]
        if value < 0:
            return None, [FLAG_MOS_NOT_APPLICABLE]
        return (value - current_price) / value, []

    for method_code, (value, flags, details) in raw_methods.items():
        status = _status_for(value, flags)
        method_row = {
            'method_code': method_code,
            'method_name': METHOD_NAMES[method_code],
            'stock_type': normalized_type,
            'years_available': available_years,
            'intrinsic_value': value,
            'calculation_status': status,
            'flags': list(dict.fromkeys(
                flags + (all_periods_pit_flags if value is not None else []) + annual_pit_flags
            )),
            'details': details,
        }
        if include_daily_status:
            mos_value, mos_flags = current_mos(value)
            method_row.update({
                'current_price': current_price,
                'gap_ratio': None if value is None or current_price is None or current_price == 0 else (value-current_price)/current_price,
                'mos': mos_value,
                'verdict': current_verdict(value),
                'flags': list(dict.fromkeys(method_row['flags'] + mos_flags)),
            })
        methods.append(method_row)

    inputs: list[dict[str, Any]] = []
    for metric_code, (value, unit_code, flags, details) in input_values.items():
        status = _status_for(value, flags)
        if metric_code == 'REVENUE_MOMENTUM' and momentum is not None:
            status = 'VALID'
        inputs.append({
            'metric_code': metric_code,
            'value_numeric': value,
            'value_text': momentum if metric_code == 'REVENUE_MOMENTUM' else None,
            'unit_code': unit_code,
            'calculation_status': status,
            'flags': list(dict.fromkeys(flags + (annual_pit_flags if value is not None else []))),
            'details': details,
        })

    methodology_parameters = {
        **params,
        'comparison_ladder': compare_ladder,
        'per_targets': target_per_by_type,
        'target_pbv': target_pbv_by_mode or {key: decimal_text(value) for key, value in TARGET_PBV.items()},
        'type_to_mode': type_to_mode,
        'ddm_growth_cap': str(params.get('ddm_growth_cap', '0.04')),
        'ddm_equity_risk_premium': str(params.get('equity_risk_premium_ddm', '0.06')),
        'discounted_earnings_growth_cap': str(params.get('discounted_earnings_growth_cap', '0.15')),
        'discounted_earnings_per_cap': str(params.get('discounted_earnings_per_cap', '25')),
        'discounted_earnings_discount_premium': str(params.get('discounted_earnings_discount_premium', '0.04')),
        'discounted_earnings_horizon_years': str(params.get('discounted_earnings_horizon_years', '5')),
        'mean_reversion_min_quarters': min_quarters,
        'pe_average_outlier_factor': str(pe_outlier_factor),
        'risk_free_rate': decimal_text(rfr) if rfr_resolved else None,
        'risk_free_rate_source': risk_free_source if rfr_resolved else None,
        'quarterly_shares_policy': 'latest_annual_share_count_as_approximation',
        'sector_weights': {key: str(value) for key, value in sector_weight.items()},
        'type_weights': {key: str(value) for key, value in type_weight.items()},
        'type_thresholds': {key: str(value) for key, value in thresholds.items()},
    }
    period_price_observations: list[dict[str, Any]] = []
    for period in [*annual, *quarterly_window]:
        selected_price = _year_end_price_row(prices, str(period.get('period_end') or ''))
        if selected_price:
            period_price_observations.append({
                'period_id': _safe_id(period),
                'trading_date': str(selected_price.get('trading_date')),
                'close_price': decimal_text(decimal_value(selected_price.get('close_price'))),
            })
    historical_cutoff = as_of_end
    fundamental_input_snapshot = {
        'ticker': ticker,
        'sector': sector,
        'stock_type': normalized_type,
        'historical_price_cutoff': historical_cutoff,
        'as_of_period_id': as_of_period_id,
        'as_of_period_end': as_of_end,
        'projection_scenario_id': scenario.get('id'),
        'projection_input_hash': scenario.get('input_hash'),
        'risk_free_rate': decimal_text(rfr) if rfr_resolved else None,
        'risk_free_rate_source': risk_free_source if rfr_resolved else None,
        'years_available': available_years,
        'years_compare': compare_years,
        'risk_free_rate': decimal_text(rfr) if rfr_resolved else None,
        'risk_free_rate_source': risk_free_source if rfr_resolved else None,
        'methodology_parameters': methodology_parameters,
        'annual_period_ids': [_safe_id(row) for row in annual],
        'quarter_period_ids': [_safe_id(row) for row in quarterly_window],
        'financial_facts': [
            {'period_id': period_id, 'metric_code': metric_code, 'value': decimal_text(decimal_value(fact.get('value_numeric')))}
            for period_id, metrics in sorted(fact_index.items())
            for metric_code, fact in sorted(metrics.items())
            if period_id in {_safe_id(row) for row in [*annual, *quarterly_window, as_of_period]}
        ],
        'prices': period_price_observations,
    }
    input_snapshot = dict(fundamental_input_snapshot)
    if include_daily_status:
        input_snapshot.update({
            'valuation_date': as_of_date.isoformat(),
            'valuation_price_date': current_price_date,
            'current_price': decimal_text(current_price),
        })
    return {
        'ticker': ticker,
        'sector': sector,
        'stock_type': normalized_type,
        'valuation_date': as_of_date.isoformat(),
        'snapshot_date': as_of_end,
        'historical_price_cutoff': as_of_end,
        'as_of_financial_period_id': as_of_period_id,
        'projection_scenario_id': scenario.get('id'),
        'years_available': available_years,
        'years_compare': compare_years,
        'current_price': current_price,
        'current_price_date': current_price_date,
        'inputs': inputs,
        'methods': methods,
        'input_snapshot': input_snapshot,
        'fundamental_input_snapshot': fundamental_input_snapshot,
        'fundamental_input_hash': sha256_json(fundamental_input_snapshot),
        'input_hash': sha256_json(input_snapshot),
    }


def calculate_daily_valuation_status(
    fundamental_methods: Sequence[Mapping[str, Any]],
    *,
    current_price: Any,
    minimum_consensus_methods: int = 3,
    mos_threshold: Any = '0.30',
    preferred_method_code: str | None = None,
    valuation_date: str | None = None,
) -> dict[str, Any]:
    """Compare immutable intrinsic values to one daily quote; never values fundamentals."""
    price = decimal_value(current_price)
    if price is None or price <= 0:
        raise ValuationError('DAILY_PRICE_INVALID')
    if minimum_consensus_methods <= 0:
        raise ValuationError('DAILY_CONSENSUS_MINIMUM_INVALID')
    threshold = decimal_value(mos_threshold)
    if threshold is None or threshold < 0:
        raise ValuationError('DAILY_MOS_THRESHOLD_INVALID')

    methods: list[dict[str, Any]] = []
    for source in fundamental_methods:
        value = decimal_value(source.get('intrinsic_value'))
        source_flags = list(source.get('flags') or [])
        valid = value is not None and source.get('calculation_status') in ('VALID', 'APPROXIMATED')
        verdict = (
            'NOT_APPLICABLE' if not valid or value is None or value <= 0
            else ('UNDERVALUED' if price < value else 'OVERVALUED')
        )
        gap = None if value is None else (value - price) / price
        mos = None
        flags = list(source_flags)
        if value == 0:
            flags.append(FLAG_MOS_DENOMINATOR_ZERO)
        elif value is not None and value < 0:
            flags.append(FLAG_MOS_NOT_APPLICABLE)
        elif value is not None:
            mos = (value - price) / value
        methods.append({
            'method_code': str(source.get('method_code') or ''),
            'intrinsic_value': value,
            'current_price': price,
            'gap_ratio': gap,
            'mos': mos,
            'verdict': verdict,
            'calculation_status': source.get('calculation_status') if valid else 'UNAVAILABLE',
            'flags': list(dict.fromkeys(flags)),
        })

    valid_rows = [
        row for row in methods
        if row['calculation_status'] in ('VALID', 'APPROXIMATED')
        and row['intrinsic_value'] is not None
        and row['verdict'] in ('UNDERVALUED', 'OVERVALUED')
    ]
    undervalued_count = sum(row['verdict'] == 'UNDERVALUED' for row in valid_rows)
    consensus = 'N/A' if len(valid_rows) < minimum_consensus_methods else (
        'UNDERVALUED' if undervalued_count * 2 > len(valid_rows) else 'OVERVALUED'
    )
    preferred = next((row for row in valid_rows if row['method_code'] == preferred_method_code and row['intrinsic_value'] > 0), None)
    if preferred is None:
        preferred = next((row for row in valid_rows if row['method_code'] in ('PETER_LYNCH', 'TYPE_SECTOR_WEIGHTED') and row['intrinsic_value'] > 0), None)
    mos_value = preferred.get('mos') if preferred else None
    return {
        'valuation_date': valuation_date,
        'current_price': price,
        'methods': methods,
        'consensus_verdict': consensus,
        'valid_method_count': len(valid_rows),
        'undervalued_method_count': undervalued_count,
        'based_method_code': preferred.get('method_code') if preferred else None,
        'based_mos': mos_value,
        'based_mos_verdict': 'N/A' if mos_value is None else ('UNDERVALUED' if mos_value >= threshold else 'OVERVALUED'),
        'mos_threshold': threshold,
    }
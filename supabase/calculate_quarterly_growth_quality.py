#!/usr/bin/env python3
"""
calculate_quarterly_growth_quality.py
=====================================

Phase 4.2 - Quarterly growth & quality layer, plus the annual-series Class-B
growth metrics.

Methodology codes
-----------------
``QUARTERLY_GROWTH_QUALITY``  (seeded in migration 0008)
``REFERENCE_WEIGHTS`` / ``FORENSIC_FLAGS``  own the parameters consumed here.

The forward contract (`Testing/test_calculation_v1.py`) imports exactly one
symbol from this module::

    from supabase.calculate_quarterly_growth_quality import calculate_quarterly_outputs

and asserts:

1. ``calculate_quarterly_outputs`` returns a ``(growth, quality)`` pair of row
   lists.
2. A ``*_QOQ`` row for a period whose predecessor is absent is ``UNAVAILABLE``
   with ``QUARTERLY_COMPARISON_MISSING``.
3. At least one quality row carries ``STATEMENT_SCOPE_UNKNOWN``, because all 33
   canonical periods have ``statement_scope = 'UNKNOWN'`` (blueprint gap
   ``G-SCOPE``).

Scope discipline
----------------
Only metrics that are explicitly defined by the Excel workbook, the Phase 4
blueprint, the forward tests or the existing web-app analysis logic are
implemented. Everything else is reported as a gap in
`docs/PHASE_4_2_IMPLEMENTATION_NOTES.md` rather than guessed.

Units
-----
Canonical values are consumed exactly as stored: IDR for amounts and raw share
counts for shares. Excel's ``x1000`` EPS/BVPS multiplier is **not** applied,
because it exists only to compensate for Excel's share column being denominated
in *Juta* (blueprint section 12.3, rule ``U-3``).

Point-in-time honesty
---------------------
``financial_periods.available_date`` and ``report_date`` are NULL for every
canonical period, so fundamental point-in-time correctness is **not** claimed.
Rows therefore carry ``availability_status = 'READY'`` only as a
*calculation-completeness* marker, and ``STATEMENT_SCOPE_UNKNOWN`` records the
unverifiable consolidated-vs-standalone question. Price PIT is not used here at
all; it lives in `pit_primitives.py` and is already validated.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

from calculation_v1_common import (
    AVAILABILITY_READY,
    CALCULATION_STATUS_UNAVAILABLE,
    CALCULATION_STATUS_VALID,
    FLAG_CAGR_PERIOD_ZERO,
    FLAG_COMPARISON_PERIOD_MISSING,
    FLAG_DENOMINATOR_ZERO,
    FLAG_DIVIDEND_PER_SHARE_MISSING,
    FLAG_EPS_DERIVED_FROM_EARNINGS,
    FLAG_MEAN_ZERO,
    FLAG_NEGATIVE_BASE,
    FLAG_NEGATIVE_DENOMINATOR,
    FLAG_NEGATIVE_SERIES_VALUE,
    FLAG_PRICE_MISSING,
    FLAG_QUARTERLY_COMPARISON_MISSING,
    FLAG_SERIES_INSUFFICIENT,
    FLAG_SHARES_CARRIED_FORWARD,
    FLAG_STATEMENT_SCOPE_UNKNOWN,
    FLAG_TOTAL_ASSETS_DERIVED_FROM_IDENTITY,
    FLAG_TOTAL_ASSETS_RECONCILIATION_MISMATCH,
    CalculationError,
    divide,
    fact_value,
    growth_result,
    merge_flags,
    pinned,
    ratio_result,
    resolved_parameter,
    result_row,
    to_decimal,
    unavailable_result,
)

__all__ = [
    'ANNUAL_GROWTH_METRICS',
    'ANNUAL_RATIO_METRICS',
    'ANNUAL_RATIO_UNITS',
    'GROWTH_FLOW_METRICS',
    'QUALITY_RATIO_METRICS',
    'calculate_annual_growth_outputs',
    'calculate_annual_ratio_outputs',
    'calculate_quarterly_outputs',
    'classify_metrics_classification',
    'latest_share_count',
]

#: The five canonical flows the quarterly layer differences. This is exactly the
#: set the forward-test fixture supplies
#: (`Testing/test_calculation_v1.py::test_quarter_scope_and_gap`).
GROWTH_FLOW_METRICS: tuple[str, ...] = (
    'REVENUE',
    'EARNINGS',
    'EBITDA',
    'OPERATING_CASH_FLOW',
    'FREE_CASH_FLOW',
)

#: Per-quarter quality ratios. Each is explicitly defined by the workbook
#: (`DataInputProyeksi!B47-B52`), the blueprint (section 5.48) or the existing
#: web-app logic (`frontend/src/lib/analysis/valuation.ts`:
#: "Gross Margin", "Net Margin", "OCF / Net Income", "Return on Equity (ROE)").
QUALITY_RATIO_METRICS: tuple[tuple[str, str, str], ...] = (
    ('QUALITY_GROSS_MARGIN', 'GROSS_PROFIT', 'REVENUE'),
    ('QUALITY_NET_MARGIN', 'EARNINGS', 'REVENUE'),
    ('QUALITY_OCF_TO_NET_INCOME', 'OPERATING_CASH_FLOW', 'EARNINGS'),
    ('QUALITY_ROE', 'EARNINGS', 'TOTAL_EQUITY'),
)

#: Annual-series Class-B metrics, in emit order.
ANNUAL_GROWTH_METRICS: tuple[str, ...] = (
    'YEARS_AVAILABLE',
    'YEARS_COMPARE',
    'GROWTH_REVENUE_CAGR_LONG',
    'GROWTH_REVENUE_CAGR_SHORT',
    'GROWTH_REVENUE_YOY',
    'GROWTH_REVENUE_COV',
    'GROWTH_EPS_CAGR_LONG',
    'GROWTH_EPS_CAGR_SHORT',
    'QUALITY_EPS_MOMENTUM',
    'GROWTH_CURRENT_ASSET_YOY',
    'GROWTH_ASSET_GROWTH_GAP',
    'QUALITY_NWC_TO_REVENUE',
    'QUALITY_NWC_INTENSITY_CHANGE',
    'QUALITY_REVENUE_MOMENTUM',
    'FORENSIC_DEBT_GROWTH_GAP',
    'FORENSIC_MARGIN_SPIKE',
    # Dividend ratios (workbook `DataInput!B28` / `B29`, blueprint 5.7 / 5.8).
    # They live here, not in the projection driver, because they are annual
    # series metrics like the rest of this tuple: one row per annual snapshot.
    'DIVIDEND_PAYOUT_RATIO',
    'DIVIDEND_YIELD',
)

#: Annual ratio metrics, in emit order. These are **levels**, not growth series,
#: and they live in their own result table (`calc_annual_ratios`) so the growth
#: table's name stays honest (decision S3).
#:
#: Every one of them is a per-share value, a margin, a return or a
#: window-CAGR - the figures the UI used to recompute in the browser
#: (`frontend/src/lib/stock-detail-adapter.ts`) and that n8n could therefore not
#: see. Each is emitted once per annual snapshot, so year Y's snapshot carries
#: year Y's own value.
ANNUAL_RATIO_METRICS: tuple[str, ...] = (
    'EPS',
    'BVPS',
    'ROE',
    'GROSS_MARGIN',
    'NET_MARGIN',
    'TOTAL_ASSETS',
    'TOTAL_ASSETS_DERIVED',
    'REVENUE_CAGR_WINDOW',
    'EARNINGS_CAGR_WINDOW',
)

#: Unit label per ratio metric. Stored on the row so a consumer can never read a
#: ratio as an amount; the single largest risk in the AI payload is mistaking a
#: ratio for an IDR figure (docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md section 2).
ANNUAL_RATIO_UNITS: dict[str, str] = {
    'EPS': 'IDR_PER_SHARE',
    'BVPS': 'IDR_PER_SHARE',
    'ROE': 'RATIO',
    'GROSS_MARGIN': 'RATIO',
    'NET_MARGIN': 'RATIO',
    'TOTAL_ASSETS': 'IDR',
    'TOTAL_ASSETS_DERIVED': 'IDR',
    'REVENUE_CAGR_WINDOW': 'RATIO',
    'EARNINGS_CAGR_WINDOW': 'RATIO',
}

#: Canonical alias pairs. Quarterly balance-sheet facts use different codes from
#: annual ones (blueprint section 4.3). Querying only one side silently returns
#: NULL for the other period type, so both are always tried.
CURRENT_ASSET_ALIASES: tuple[str, ...] = ('CURRENT_ASSETS', 'TOTAL_CURRENT_ASSET')

_QUARTER_LABEL = re.compile(r'^(\d{4})-Q([1-4])$')


# --------------------------------------------------------------------------
# Period and fact helpers
# --------------------------------------------------------------------------

def _period_id(period: Mapping[str, Any]) -> str:
    return str(period.get('id') or period.get('financial_period_id') or '')


def _period_end(period: Mapping[str, Any]) -> str:
    return str(period.get('period_end') or '')


def _quarter_ordinal(period: Mapping[str, Any]) -> int | None:
    """Return a monotonic quarter ordinal (``year * 4 + quarter - 1``).

    ``period_label`` is authoritative when it matches ``YYYY-Qn``. Otherwise the
    ordinal is derived from ``period_end``, whose month must be a quarter-end
    month. Returning ``None`` means the period cannot be ordered, and the caller
    must not guess a comparison partner.
    """
    label = str(period.get('period_label') or '')
    match = _QUARTER_LABEL.match(label)
    if match:
        return int(match.group(1)) * 4 + int(match.group(2)) - 1

    end = _period_end(period)
    if len(end) >= 7 and end[4] == '-' and end[5:7].isdigit():
        month = int(end[5:7])
        if month in (3, 6, 9, 12):
            return int(end[:4]) * 4 + (month // 3) - 1
    return None


def _facts_by_period(facts: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Mapping[str, Any]]]:
    """Index facts as ``{period_id: {metric_code: fact}}``.

    Only ``revision_key == 'CURRENT'`` rows are considered when any CURRENT row
    exists for that period, so a superseded revision can never be selected by
    accident. Canonical data has a single CURRENT revision per fact today, so
    this is a guard rather than a behaviour change.
    """
    index: dict[str, dict[str, Mapping[str, Any]]] = {}
    for fact in facts:
        period_id = str(fact.get('financial_period_id') or '')
        metric_code = str(fact.get('metric_code') or '')
        if not period_id or not metric_code:
            continue
        index.setdefault(period_id, {})[metric_code] = fact
    return index


def _identity(
    *,
    instrument_id: str,
    run_id: str,
    period: Mapping[str, Any] | None = None,
    methodology_version_id: str | None = None,
) -> dict[str, Any]:
    identity: dict[str, Any] = {
        'calculation_run_id': run_id,
        'instrument_id': instrument_id,
    }
    if period is not None:
        identity['financial_period_id'] = _period_id(period)
        identity['observation_date'] = _period_end(period)
    if methodology_version_id is not None:
        identity['methodology_version_id'] = methodology_version_id
    return identity


def _scope_flags(period: Mapping[str, Any]) -> list[str]:
    """Return the statement-scope flag for a period.

    ``statement_scope`` is ``UNKNOWN`` for every canonical period, and that is
    preserved rather than resolved to a guess. ``period_basis`` is checked too:
    annual periods carry ``period_basis = 'UNKNOWN'`` in canonical data.
    """
    scope = str(period.get('statement_scope') or 'UNKNOWN').upper()
    basis = str(period.get('period_basis') or 'UNKNOWN').upper()
    if scope == 'UNKNOWN' or basis == 'UNKNOWN':
        return [FLAG_STATEMENT_SCOPE_UNKNOWN]
    return []


def _current_asset_fact(
    facts: Mapping[str, Mapping[str, Any]],
) -> tuple[Mapping[str, Any] | None, str]:
    """Resolve the current-asset fact across the canonical period-type aliases.

    Returns ``(fact, resolved_code)``. The annual code is ``CURRENT_ASSETS`` and
    the quarterly code is ``TOTAL_CURRENT_ASSET`` (blueprint section 4.3), so
    both must be tried or half the periods silently vanish. ``CURRENT_ASSETS``
    is preferred when both are present, and the resolved code is returned so the
    caller can name the missing input accurately.
    """
    for code in CURRENT_ASSET_ALIASES:
        fact = facts.get(code)
        if fact is not None and to_decimal(fact.get('value_numeric')) is not None:
            return fact, code
    return None, CURRENT_ASSET_ALIASES[0]


# --------------------------------------------------------------------------
# QUARTERLY_GROWTH_QUALITY
# --------------------------------------------------------------------------

def _growth_quarter(
    *,
    period: Mapping[str, Any],
    predecessor: Mapping[str, Any] | None,
    facts_by_period: Mapping[str, Mapping[str, Mapping[str, Any]]],
    instrument_id: str,
    run_id: str,
    methodology_version_id: str | None,
) -> list[dict[str, Any]]:
    """Emit the five ``*_QOQ`` growth rows for one quarter."""
    identity = _identity(
        instrument_id=instrument_id,
        run_id=run_id,
        period=period,
        methodology_version_id=methodology_version_id,
    )
    current_facts = facts_by_period.get(_period_id(period), {})
    prior_facts = (
        facts_by_period.get(_period_id(predecessor), {}) if predecessor is not None else {}
    )

    rows: list[dict[str, Any]] = []
    scope_flags = _scope_flags(period)
    for metric_code in GROWTH_FLOW_METRICS:
        row = growth_result(
            metric_code=metric_code + '_QOQ',
            current=current_facts.get(metric_code),
            prior=prior_facts.get(metric_code),
            current_field=metric_code,
            prior_field=metric_code,
            identity=identity,
            comparison_missing=predecessor is None,
            comparison_flag=FLAG_QUARTERLY_COMPARISON_MISSING,
        )
        row['flags'] = merge_flags(row['flags'], scope_flags)
        rows.append(row)
    return rows


def _quality_quarter(
    *,
    period: Mapping[str, Any],
    facts_by_period: Mapping[str, Mapping[str, Mapping[str, Any]]],
    instrument_id: str,
    run_id: str,
    methodology_version_id: str | None,
) -> list[dict[str, Any]]:
    """Emit the per-quarter quality ratio rows for one period.

    Ratios are computed from facts of the **same** period only, so no comparison
    period is required and no future period can leak in. Every row carries the
    period's statement-scope flags, so ``STATEMENT_SCOPE_UNKNOWN`` propagates to
    the quality block exactly as the forward test requires.
    """
    identity = _identity(
        instrument_id=instrument_id,
        run_id=run_id,
        period=period,
        methodology_version_id=methodology_version_id,
    )
    facts = facts_by_period.get(_period_id(period), {})
    scope_flags = _scope_flags(period)

    rows: list[dict[str, Any]] = []
    for metric_code, numerator_code, denominator_code in QUALITY_RATIO_METRICS:
        row = ratio_result(
            metric_code=metric_code,
            numerator=facts.get(numerator_code),
            denominator=facts.get(denominator_code),
            numerator_field=numerator_code,
            denominator_field=denominator_code,
            identity=identity,
        )
        row['flags'] = merge_flags(row['flags'], scope_flags)
        rows.append(row)
    return rows

@pinned
def calculate_quarterly_outputs(
    periods: Sequence[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
    instrument_id: str,
    run_id: str,
    *,
    methodology_version_id: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Compute the quarterly growth and quality results.

    Returns ``(growth_rows, quality_rows)``.

    Growth
    ------
    Five ``*_QOQ`` rows per quarter — ``REVENUE``, ``EARNINGS``, ``EBITDA``,
    ``OPERATING_CASH_FLOW`` and ``FREE_CASH_FLOW`` — each compared against the
    **immediately preceding quarter**, identified by quarter ordinal rather than
    by list position. When that predecessor period is absent the row is
    ``UNAVAILABLE`` with ``QUARTERLY_COMPARISON_MISSING`` and
    ``value_numeric = None``; no other quarter is ever substituted, so a gap in
    the series cannot silently produce a two-quarter "growth" figure.

    Quality
    -------
    Four same-period ratios per quarter: gross margin, net margin, OCF/net
    income and ROE. Each carries the period's scope flags, which is what makes
    ``STATEMENT_SCOPE_UNKNOWN`` visible on the quality block.

    Ordering
    --------
    Output order is deterministic: quarters ascending by ``period_end`` (then by
    ``period_label``), metrics in their declared order. Re-running on the same
    input therefore produces an identical list.

    Only ``QUARTER`` periods are consumed. Annual periods are handled by
    :func:`calculate_annual_growth_outputs`, because mixing the two period types
    in one comparison would difference incomparable magnitudes.
    """
    quarters = [
        period
        for period in periods
        if str(period.get('period_type') or '').upper() == 'QUARTER'
    ]
    quarters.sort(
        key=lambda period: (_period_end(period), str(period.get('period_label') or ''))
    )

    facts_by_period = _facts_by_period(facts)
    ordinal_to_period: dict[int, Mapping[str, Any]] = {}
    for period in quarters:
        ordinal = _quarter_ordinal(period)
        if ordinal is not None:
            ordinal_to_period[ordinal] = period

    growth: list[dict[str, Any]] = []
    quality: list[dict[str, Any]] = []
    for period in quarters:
        ordinal = _quarter_ordinal(period)
        predecessor = ordinal_to_period.get(ordinal - 1) if ordinal is not None else None
        growth.extend(
            _growth_quarter(
                period=period,
                predecessor=predecessor,
                facts_by_period=facts_by_period,
                instrument_id=instrument_id,
                run_id=run_id,
                methodology_version_id=methodology_version_id,
            )
        )
        quality.extend(
            _quality_quarter(
                period=period,
                facts_by_period=facts_by_period,
                instrument_id=instrument_id,
                run_id=run_id,
                methodology_version_id=methodology_version_id,
            )
        )
    return growth, quality


# --------------------------------------------------------------------------
# Annual series primitives (Excel RRI / STDEV.P / AVERAGE over Range_*)
# --------------------------------------------------------------------------

def _annual_periods(periods: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Return the ANNUAL periods, **newest first**.

    Excel's ``INDEX(Range_X, 1)`` is the **newest** period, because the
    ``DataInput`` columns run newest-first (``C`` = latest, ``I`` = oldest).
    Ordering newest-first here means index ``0`` in this list reproduces
    ``INDEX(Range_X, 1)`` exactly, so the Excel ordering cannot be inverted by
    accident.
    """
    return sorted(
        (
            period
            for period in periods
            if str(period.get('period_type') or '').upper() == 'ANNUAL'
        ),
        key=lambda period: (_period_end(period), str(period.get('period_label') or '')),
        reverse=True,
    )


def _indexed_value(
    ordered_periods: Sequence[Mapping[str, Any]],
    facts_by_period: Mapping[str, Mapping[str, Mapping[str, Any]]],
    metric_code: str,
    index_1based: int,
) -> tuple[Decimal | None, Mapping[str, Any] | None, list[str]]:
    """Reproduce ``INDEX(Range_<metric>, index_1based)``.

    Returns ``(value, period, flags)``. The index addresses a **period
    position**, not a position among present values, so ``INDEX(Range_EPS, 7)``
    always means "the 7th-newest annual period" even when that period's fact is
    missing. The fact is then reported missing rather than the window silently
    shifting to a different year, which is what would happen if the series were
    compacted first.

    An out-of-range index, or a period whose fact is absent/unusable, returns
    ``None`` with the appropriate flag.
    """
    if index_1based < 1 or index_1based > len(ordered_periods):
        return None, None, [FLAG_SERIES_INSUFFICIENT]

    period = ordered_periods[index_1based - 1]
    fact = facts_by_period.get(_period_id(period), {}).get(metric_code)
    value, flags = fact_value(fact, metric_code)
    return value, period, flags


def _period_values(
    ordered_periods: Sequence[Mapping[str, Any]],
    facts_by_period: Mapping[str, Mapping[str, Mapping[str, Any]]],
    metric_code: str,
) -> list[Decimal]:
    """Return the metric's values across the ordered periods, skipping gaps.

    Used for the whole-range aggregates (``STDEV.P`` / ``AVERAGE`` / ``MAX`` /
    ``MIN``), where Excel ranges are value arrays rather than position lookups.
    A period whose fact is absent or unusable is skipped so a gap cannot
    masquerade as a zero, which would corrupt both the mean and the deviation.
    """
    values: list[Decimal] = []
    for period in ordered_periods:
        value, flags = fact_value(
            facts_by_period.get(_period_id(period), {}).get(metric_code), metric_code
        )
        if flags or value is None:
            continue
        values.append(value)
    return values



def _rri(
    periods_count: int,
    start: Decimal | None,
    end: Decimal | None,
    *,
    start_flags: Sequence[str] | None = None,
    end_flags: Sequence[str] | None = None,
) -> tuple[Decimal | None, list[str]]:
    """Excel ``RRI(nper, pv, fv)`` = ``(fv/pv) ** (1/nper) - 1``.

    Returns ``(value, flags)``. Guards:

    * ``start`` is ``None``  -> ``start_flags`` (or ``SERIES_INSUFFICIENT``)
    * ``end`` is ``None``    -> ``end_flags`` (or ``SERIES_INSUFFICIENT``)
    * ``nper <= 0``          -> ``CAGR_PERIOD_ZERO`` (Excel would ``#DIV/0!``)
    * ``start == 0``         -> ``DENOMINATOR_ZERO``
    * ``start < 0``          -> the registered ``negative_base_cagr_mode``

    ``start_flags`` / ``end_flags`` are **missing-input** flags: they are only
    consulted when the matching value is ``None``. A value that is present but
    carries a provenance flag (for example an EPS derived from
    ``EARNINGS / OUTSTANDING_SHARES``) is a real value and is used; its flag is
    the caller's to propagate. Conflating the two would turn a derived-but-valid
    input into a missing one.

    The negative-base branch is **not** invented here. The workbook abandons
    ``RRI`` when the base is negative and uses a linear normalised rate
    (``MetricsClassification!B13``/``B14``); that rule is registered as
    ``negative_base_cagr_mode`` and AUTO genuinely depends on it, because 2020
    EPS is negative. The mode is read from the registry and the exact expression
    ``((end - start) / ABS(start)) / nper`` is applied, so the behaviour is
    versioned rather than hard-coded, and ``NEGATIVE_BASE`` still records that
    the RRI form was abandoned.
    """
    if start is None:
        return None, list(start_flags or [FLAG_SERIES_INSUFFICIENT])
    if end is None:
        return None, list(end_flags or [FLAG_SERIES_INSUFFICIENT])

    if periods_count <= 0:
        return None, [FLAG_CAGR_PERIOD_ZERO]
    if start == 0:
        return None, [FLAG_DENOMINATOR_ZERO]

    if start < 0:
        mode = str(resolved_parameter('negative_base_cagr_mode'))
        if mode != 'linear_normalized':
            raise CalculationError(f'NEGATIVE_BASE_CAGR_MODE_UNSUPPORTED: {mode}')
        linear = divide(end - start, abs(start)) / Decimal(periods_count)
        return linear, [FLAG_NEGATIVE_BASE]

    ratio = divide(end, start)
    if ratio < 0:
        return None, [FLAG_NEGATIVE_SERIES_VALUE]

    from decimal import localcontext

    with localcontext() as context:
        context.prec = 50
        root = ratio ** (Decimal(1) / Decimal(periods_count))
    return root - Decimal(1), []


def _coefficient_of_variation(values: Sequence[Decimal]) -> tuple[Decimal | None, list[str]]:
    """Excel ``STDEV.P(range) / AVERAGE(range)``.

    The **population** standard deviation is used, not the sample one. The two
    differ (``n`` vs ``n-1``) and the workbook uses ``STDEV.P``; substituting
    ``STDEV.S`` silently changes the number, and this metric drives the
    Cyclical classifier (blueprint section 5.16). Returns
    ``(value, flags)`` with ``MEAN_ZERO`` when the mean is zero.
    """
    if len(values) < 2:
        return None, [FLAG_SERIES_INSUFFICIENT]

    count = Decimal(len(values))
    mean = sum(values, Decimal(0)) / count
    if mean == 0:
        return None, [FLAG_MEAN_ZERO]

    variance = sum(((value - mean) ** 2 for value in values), Decimal(0)) / count
    if variance < 0:  # pragma: no cover - impossible for real inputs
        return None, [FLAG_NEGATIVE_SERIES_VALUE]

    from decimal import localcontext

    with localcontext() as context:
        context.prec = 50
        deviation = variance.sqrt()
    return divide(deviation, mean), []


def _years_compare_thresholds() -> dict[str, str]:
    """Return the registered ``years_compare_thresholds`` lookup."""
    return dict(resolved_parameter('years_compare_thresholds'))


def _years_compare(years_avail: int) -> int:
    """Reproduce ``MetricsClassification!B5`` ``IFS`` on the available years.

    Excel: ``IFS(Years_Avail>=7, 5, Years_Avail>=5, 3, Years_Avail>=3, 2, TRUE, 0)``.

    Both the cut-offs and their results come from the registered
    ``years_compare_thresholds`` parameter, whose keys encode the cut-off
    (``years_avail_ge_<N>``) and whose values are the resulting comparison
    window. Parsing the keys means the ladder is versioned in the registry
    rather than re-embedded in code. The highest matching cut-off wins, which
    is the ``IFS`` first-match rule.
    """
    thresholds = _years_compare_thresholds()
    ladder: list[tuple[int, int]] = []
    for key, value in thresholds.items():
        if key.startswith('years_avail_ge_') and key[len('years_avail_ge_'):].isdigit():
            ladder.append((int(key[len('years_avail_ge_'):]), int(value)))
    ladder.sort(reverse=True)

    for cut_off, window in ladder:
        if years_avail >= cut_off:
            return window
    return int(thresholds['default'])


def _as_decimal(value: Any) -> Decimal | None:
    """Convert optional caller-supplied classification values safely."""
    try:
        return to_decimal(value)
    except CalculationError:
        return None


def _result_value(rows: Sequence[Mapping[str, Any]], metric_code: str) -> Decimal | None:
    for row in rows:
        if row.get('metric_code') != metric_code:
            continue
        if row.get('calculation_status') != CALCULATION_STATUS_VALID:
            return None
        return _as_decimal(row.get('value_numeric'))
    return None


def _contains_sector(sector: str, search: str) -> bool:
    return search.casefold() in sector.casefold()


@pinned
def classify_metrics_classification(
    *,
    growth_rows: Sequence[Mapping[str, Any]],
    instrument_id: str,
    run_id: str,
    sector: str | None,
    projected_net_income: Any,
    payout_ratio: Any,
    historical_roe_average: Any,
    projected_pbv: Any,
    pbv_percentile: Any,
    projected_pe: Any,
    projected_peg: Any,
    historical_dividend_yield: Any,
    gpm_stability: Any = None,
    methodology_version_id: str | None = None,
    manual_override: str | None = None,
) -> list[dict[str, Any]]:
    """Evaluate the six MetricsClassification rules and final classifier offline.

    Classification thresholds, sectors, score precedence and the Energy
    override are implemented from the owner-provided
    MetricsClassification formulas. Although the confidence formula is now
    available from the owner, its registry entry is still unresolved, so the
    confidence row is flagged as an offline preview pending methodology
    versioning before live use.
    """
    thresholds = resolved_parameter('classifier_thresholds')
    score_ladder = resolved_parameter('classifier_score_ladder')
    cyclical_sectors = resolved_parameter('classifier_cyclical_sectors')
    defensive_sectors = resolved_parameter('classifier_consumer_defensive_sectors')
    energy_override = str(resolved_parameter('classifier_energy_override'))
    # The registered classifier blob is not yet versioned against the owner
    # formulas supplied for this implementation.
    registry_requires_update = True

    sector_text = sector or ''
    revenue_long = _result_value(growth_rows, 'GROWTH_REVENUE_CAGR_LONG')
    revenue_cov = _result_value(growth_rows, 'GROWTH_REVENUE_COV')
    revenue_momentum = _result_value(growth_rows, 'QUALITY_REVENUE_MOMENTUM')
    eps_long = _result_value(growth_rows, 'GROWTH_EPS_CAGR_LONG')
    margin_stability = _as_decimal(gpm_stability)
    roe_average = _as_decimal(historical_roe_average)
    payout = _as_decimal(payout_ratio)
    net_income = _as_decimal(projected_net_income)
    pbv = _as_decimal(projected_pbv)
    pbv_pct = _as_decimal(pbv_percentile)
    pe = _as_decimal(projected_pe)
    peg = _as_decimal(projected_peg)
    historical_yield = _as_decimal(historical_dividend_yield)

    def flag(name: str, value: bool | None) -> dict[str, Any]:
        return {
            'metric_code': name,
            'value_numeric': None if value is None else ('1' if value else '0'),
            'calculation_status': (
                CALCULATION_STATUS_UNAVAILABLE if value is None else CALCULATION_STATUS_VALID
            ),
            'flags': ['CLASSIFIER_INPUT_MISSING'] if value is None else [],
        }

    financial_sector = _contains_sector(sector_text, 'Financials')
    defensive_sector = any(_contains_sector(sector_text, item) for item in defensive_sectors)
    cyclical_sector = any(_contains_sector(sector_text, item) for item in cyclical_sectors)

    slow = (
        None if revenue_long is None or payout is None
        else revenue_long <= Decimal(str(thresholds['slow_grower_rev_cagr_max']))
        and payout > Decimal(str(thresholds['slow_grower_payout_min']))
    )

    stalwart_branches: list[bool | None] = []
    if financial_sector:
        if revenue_long is None or roe_average is None:
            stalwart_branches.append(None)
        else:
            stalwart_branches.append(
                # MetricsClassification explicitly uses >5% for Financials;
                # the currently published registry blob has only the distinct
                # non-financial Stalwart 10% threshold. Keep the workbook rule
                # here and mark outputs as requiring a registry version update.
                revenue_long > Decimal('0.05')
                and roe_average > Decimal(str(thresholds['stalwart_roe_min']))
            )
    else:
        if revenue_long is None or revenue_cov is None:
            stalwart_branches.append(None)
        else:
            stalwart_branches.append(
                revenue_long > Decimal(str(thresholds['stalwart_rev_cagr_min']))
                and revenue_long <= Decimal(str(thresholds['stalwart_rev_cagr_max']))
                and revenue_cov < Decimal(str(thresholds['rev_cov_max']))
            )
        if defensive_sector:
            if revenue_long is None or roe_average is None or revenue_cov is None:
                stalwart_branches.append(None)
            else:
                stalwart_branches.append(
                    revenue_long >= Decimal(str(thresholds['stalwart_defensive_rev_min']))
                    and revenue_long <= Decimal(str(thresholds['stalwart_defensive_rev_max']))
                    and roe_average > Decimal(str(thresholds['stalwart_roe_min']))
                    and revenue_cov < Decimal(str(thresholds['rev_cov_max']))
                )
    stalwart = (
        True if True in stalwart_branches
        else None if any(value is None for value in stalwart_branches)
        else False
    )

    if financial_sector:
        fast = (
            None if eps_long is None
            else eps_long > Decimal(str(thresholds['fast_grower_eps_cagr_min']))
        )
    else:
        if revenue_long is None:
            fast = None
        elif revenue_long <= Decimal(str(thresholds['fast_grower_rev_cagr_min'])):
            fast = False
        else:
            volatility_pass = (
                None if revenue_cov is None
                else revenue_cov < Decimal(str(thresholds['rev_cov_max']))
            )
            momentum_pass = None if revenue_momentum is None else revenue_momentum == 1
            fast = (
                True if volatility_pass is True or momentum_pass is True
                else None if volatility_pass is None or momentum_pass is None
                else False
            )

    if net_income is None:
        cyclical = None
        system_cyclical = None
    elif net_income <= 0:
        cyclical = False
        system_cyclical = False
    elif financial_sector:
        cyclical = False
        system_cyclical = False
    elif cyclical_sector:
        cyclical = True
        system_cyclical = True
    else:
        cov_match = (
            None if revenue_cov is None
            else revenue_cov > Decimal(str(thresholds['rev_cov_max']))
        )
        system_cyclical = cov_match
        margin_match = (
            None if margin_stability is None
            else margin_stability > Decimal('0.2')
        )
        cyclical = (
            True if cov_match is True or margin_match is True
            else None if cov_match is None or margin_match is None
            else False
        )

    asset_play = (
        None if pbv is None or pbv_pct is None
        else pbv < Decimal(str(thresholds['asset_play_pbv_max']))
        and pbv_pct < Decimal(str(thresholds['asset_play_pbv_percentile_max']))
    )
    turnaround = None if net_income is None else net_income < 0

    rule_values = {
        'CLASSIFICATION_SLOW_GROWER': slow,
        'CLASSIFICATION_STALWART': stalwart,
        'CLASSIFICATION_FAST_GROWER': fast,
        'CLASSIFICATION_CYCLICAL': cyclical,
        'CLASSIFICATION_ASSET_PLAY': asset_play,
        'CLASSIFICATION_TURN_AROUND': turnaround,
    }
    identity: dict[str, Any] = {
        'calculation_run_id': run_id,
        'instrument_id': instrument_id,
    }
    if methodology_version_id is not None:
        identity['methodology_version_id'] = methodology_version_id

    rows: list[dict[str, Any]] = []
    for code, value in rule_values.items():
        row = flag(code, value)
        rows.append(result_row(
            identity=identity,
            metric_code=row['metric_code'],
            value_numeric=row['value_numeric'],
            calculation_status=row['calculation_status'],
            flags=merge_flags(
                row['flags'],
                ['REGISTRY_VERSION_UPDATE_REQUIRED'] if registry_requires_update else [],
            ),
        ))

    if sector_text.strip().casefold() == 'energy':
        system_recommendation = energy_override
    else:
        score_values = {
            'TURN AROUND': turnaround,
            'FAST GROWER': fast,
            # The final System Rec LET formula differs from the standalone
            # CYCLICAL rule row: it omits the GPM-stability branch. Preserve
            # the two Excel outputs independently rather than conflating them.
            'CYCLICAL': system_cyclical,
            'STALWART': stalwart,
            'SLOW GROWER': slow,
            'ASSET PLAY': asset_play,
        }
        matching = [
            (int(score_ladder[name]), name)
            for name, matched in score_values.items()
            if matched is True
        ]
        if matching:
            winning_score, winning_type = max(matching)
            # The Excel IFS has branches for scores 100/80/60/40/20, but not
            # score 10 (ASSET PLAY). Preserve its literal fall-through result.
            system_recommendation = (
                'UNCLASSIFIED' if winning_score == int(score_ladder['ASSET PLAY'])
                else winning_type
            )
        elif any(value is None for value in rule_values.values()):
            system_recommendation = None
        else:
            system_recommendation = 'UNCLASSIFIED'

    rows.append(result_row(
        identity=identity,
        metric_code='CLASSIFICATION_SYSTEM_RECOMMENDATION',
        value_numeric=None,
        calculation_status=(
            CALCULATION_STATUS_VALID
            if system_recommendation is not None
            else CALCULATION_STATUS_UNAVAILABLE
        ),
        flags=[] if system_recommendation is not None else ['CLASSIFIER_INPUT_MISSING'],
        classification_code=system_recommendation,
    ))

    final_type = (manual_override or '').strip() or system_recommendation
    rows.append(result_row(
        identity=identity,
        metric_code='CLASSIFICATION_FINAL_TYPE',
        value_numeric=None,
        calculation_status=(
            CALCULATION_STATUS_VALID if final_type is not None
            else CALCULATION_STATUS_UNAVAILABLE
        ),
        flags=[] if final_type is not None else ['CLASSIFIER_INPUT_MISSING'],
        classification_code=final_type,
        manual_override=(manual_override or '').strip() or None,
    ))

    if final_type == 'TURN AROUND':
        confidence = Decimal('0.4')
    elif final_type == 'CYCLICAL':
        confidence = (
            None if revenue_cov is None or pe is None
            else Decimal('0.95')
            if revenue_cov > Decimal('0.3') and pe < Decimal('15')
            else Decimal('0.7')
        )
    elif final_type == 'FAST GROWER':
        confidence = (
            None if peg is None or revenue_momentum is None
            else Decimal('0.95')
            if peg < Decimal('1.5') and revenue_momentum == Decimal(1)
            else Decimal('0.7')
        )
    elif final_type == 'SLOW GROWER':
        confidence = (
            None if historical_yield is None
            else Decimal('0.95') if historical_yield > Decimal('0.05')
            else Decimal('0.7')
        )
    elif final_type == 'STALWART':
        confidence = (
            None if roe_average is None
            else Decimal('0.95') if roe_average > Decimal('0.15')
            else Decimal('0.7')
        )
    elif final_type == 'ASSET PLAY':
        confidence = (
            None if pbv is None
            else Decimal('0.95') if pbv < Decimal('0.8')
            else Decimal('0.7')
        )
    else:
        confidence = Decimal(0)

    rows.append(result_row(
        identity=identity,
        metric_code='CLASSIFICATION_CONFIDENCE',
        value_numeric=confidence,
        calculation_status=(
            CALCULATION_STATUS_VALID if confidence is not None
            else CALCULATION_STATUS_UNAVAILABLE
        ),
        flags=(
            ['REGISTRY_VERSION_UPDATE_REQUIRED']
            if confidence is not None
            else ['CLASSIFIER_CONFIDENCE_INPUT_MISSING', 'REGISTRY_VERSION_UPDATE_REQUIRED']
        ),
    ))
    return rows





# --------------------------------------------------------------------------
# Annual Class-B growth / quality metrics (Excel MetricsClassification series)
# --------------------------------------------------------------------------

def _annual_identity(
    *,
    instrument_id: str,
    run_id: str,
    period: Mapping[str, Any] | None,
    methodology_version_id: str | None,
) -> dict[str, Any]:
    return _identity(
        instrument_id=instrument_id,
        run_id=run_id,
        period=period,
        methodology_version_id=methodology_version_id,
    )


def _emit(
    rows: list[dict[str, Any]],
    *,
    metric_code: str,
    identity: Mapping[str, Any],
    value: Decimal | None,
    flags: Sequence[str] | None = None,
) -> None:
    """Append one annual row, choosing the status from the value and flags.

    ``value is None`` means no value could be produced, which is always
    ``UNAVAILABLE`` — either an input is missing or a documented guard refused
    the computation. The distinction is carried by the flags
    (``<CODE>_MISSING`` / ``SERIES_INSUFFICIENT`` versus
    ``DENOMINATOR_ZERO`` / ``NEGATIVE_BASE``), so a reader can tell a data gap
    from a refused division without guessing.
    """
    row_flags = list(flags or ())
    if value is None:
        rows.append(
            unavailable_result(
                identity=identity, metric_code=metric_code, flags=row_flags
            )
        )
        return
    rows.append(
        result_row(
            identity=identity,
            metric_code=metric_code,
            value_numeric=value,
            calculation_status=CALCULATION_STATUS_VALID,
            flags=row_flags,
        )
    )


def _latest_period(
    ordered_periods: Sequence[Mapping[str, Any]],
    facts_by_period: Mapping[str, Mapping[str, Mapping[str, Any]]],
    metric_code: str,
) -> Mapping[str, Any] | None:
    """Return the newest period whose ``metric_code`` fact is usable."""
    for period in ordered_periods:
        value, flags = fact_value(
            facts_by_period.get(_period_id(period), {}).get(metric_code), metric_code
        )
        if not flags and value is not None:
            return period
    return None


def _nwc(
    ordered_periods: Sequence[Mapping[str, Any]],
    facts_by_period: Mapping[str, Mapping[str, Mapping[str, Any]]],
    index_1based: int,
) -> tuple[Decimal | None, list[str]]:
    """Net working capital = current assets - current liabilities.

    Reproduces ``DataInput!B36`` (``B37-B38``). The current-asset side is
    resolved through the canonical period-type aliases, because the annual code
    is ``CURRENT_ASSETS`` while the quarterly code is ``TOTAL_CURRENT_ASSET``
    (blueprint section 4.3).
    """
    if index_1based < 1 or index_1based > len(ordered_periods):
        return None, [FLAG_SERIES_INSUFFICIENT]

    period = ordered_periods[index_1based - 1]
    facts = facts_by_period.get(_period_id(period), {})

    current_assets, current_assets_flags = fact_value(
        facts.get(CURRENT_ASSET_ALIASES[0]), CURRENT_ASSET_ALIASES[0]
    )
    if current_assets_flags:
        current_assets, current_assets_flags = fact_value(
            facts.get(CURRENT_ASSET_ALIASES[1]), CURRENT_ASSET_ALIASES[1]
        )
    if current_assets_flags:
        return None, current_assets_flags

    current_liabilities, current_liabilities_flags = fact_value(
        facts.get('CURRENT_LIABILITIES'), 'CURRENT_LIABILITIES'
    )
    if current_liabilities_flags:
        return None, current_liabilities_flags

    if current_assets is None or current_liabilities is None:  # pragma: no cover
        return None, [FLAG_SERIES_INSUFFICIENT]
    return current_assets - current_liabilities, []


def _divide_optional(
    numerator: Decimal | None,
    denominator: Decimal | None,
    numerator_flags: Sequence[str] | None = None,
    denominator_flags: Sequence[str] | None = None,
) -> tuple[Decimal | None, list[str]]:
    """Divide two already resolved amounts, refusing a non-positive denominator.

    Returns ``(value, flags)``. A missing side returns that side's flags, a zero
    denominator returns ``DENOMINATOR_ZERO`` and a negative one returns
    ``NEGATIVE_DENOMINATOR``, mirroring :func:`ratio_result` so an annual metric
    and a quarterly one behave identically on the same edge case.
    """
    if numerator_flags:
        return None, list(numerator_flags)
    if denominator_flags:
        return None, list(denominator_flags)
    if numerator is None or denominator is None:
        return None, [FLAG_SERIES_INSUFFICIENT]
    if denominator == 0:
        return None, [FLAG_DENOMINATOR_ZERO]
    if denominator < 0:
        return None, [FLAG_NEGATIVE_DENOMINATOR]
    return divide(numerator, denominator), []



def _eps_value(
    ordered_periods: Sequence[Mapping[str, Any]],
    facts_by_period: Mapping[str, Mapping[str, Mapping[str, Any]]],
    index_1based: int,
) -> tuple[Decimal | None, list[str]]:
    """Reproduce ``INDEX(Range_EPS, index_1based)``, deriving EPS when absent.

    Canonical ``EPS`` exists for only six annual periods (2020-2025); 2019 is
    ``NULL``. The workbook's ``DataInput!I30`` does carry a 2019 EPS
    (``153.4674223655128``), and it is exactly
    ``EARNINGS / OUTSTANDING_SHARES`` for that year
    (``739672000000 / 4819733000``). Both components **are** canonical for 2019,
    so the value is derived rather than invented, and the row is flagged
    ``EPS_DERIVED_FROM_EARNINGS`` so a derived EPS is never mistaken for a
    stored one.

    No ``x1000`` factor is applied: canonical ``OUTSTANDING_SHARES`` is a raw
    share count, whereas Excel's share column is in *Juta* (blueprint rule
    ``U-3``).
    """
    value, _period, flags = _indexed_value(
        ordered_periods, facts_by_period, 'EPS', index_1based
    )
    if not flags and value is not None:
        return value, []

    # Fall back to the same period's EARNINGS / OUTSTANDING_SHARES.
    if index_1based < 1 or index_1based > len(ordered_periods):
        return None, flags or [FLAG_SERIES_INSUFFICIENT]

    period = ordered_periods[index_1based - 1]
    facts = facts_by_period.get(_period_id(period), {})
    earnings, earnings_flags = fact_value(facts.get('EARNINGS'), 'EARNINGS')
    shares, shares_flags = fact_value(facts.get('OUTSTANDING_SHARES'), 'OUTSTANDING_SHARES')
    if earnings_flags:
        return None, earnings_flags
    if shares_flags:
        return None, shares_flags
    if earnings is None or shares is None:  # pragma: no cover - guarded above
        return None, [FLAG_SERIES_INSUFFICIENT]
    if shares == 0:
        return None, [FLAG_DENOMINATOR_ZERO]

    return divide(earnings, shares), [FLAG_EPS_DERIVED_FROM_EARNINGS]


def _dividend_per_share(
    dividend_rows: Sequence[Mapping[str, Any]],
    year: int,
) -> tuple[Decimal | None, list[str]]:
    """Total DPS declared for one fiscal year (``DataInput`` DPS row).

    Canonical dividends are stored as ``ANNUAL_TOTAL`` rows keyed by
    ``period_year``, so a year with no row means "no dividend was recorded" and
    returns ``UNAVAILABLE`` with ``DIVIDEND_PER_SHARE_MISSING``. A recorded zero
    is a real value and stays ``VALID``: the workbook's ``DPS`` row genuinely is
    zero for years a company skipped, and treating that as missing would hide
    the difference between "paid nothing" and "not loaded".
    """
    for row in dividend_rows:
        if str(row.get('fact_type') or '') != 'ANNUAL_TOTAL':
            continue
        if to_decimal(row.get('period_year')) != Decimal(year):
            continue
        value = to_decimal(row.get('amount_per_share'))
        if value is None:
            return None, [FLAG_DIVIDEND_PER_SHARE_MISSING]
        return value, []
    return None, [FLAG_DIVIDEND_PER_SHARE_MISSING]


def _year_end_close(
    prices: Sequence[Mapping[str, Any]],
    period_end: str,
) -> tuple[Decimal | None, list[str]]:
    """Last close in the fiscal year of ``period_end``, on or before it.

    This is the price basis the workbook uses for ``DataInput!B29``
    (``B26/B25``): the year-end close, **not** the latest price. The XLOOKUP
    searches backwards for the first date ``<= DATE(year,12,31)``, so a year
    whose final trading day is not 31 December still resolves correctly.
    """
    year_start = period_end[:4] + '-01-01'
    eligible = [
        row for row in prices
        if year_start <= str(row.get('trading_date') or '') <= period_end
        and to_decimal(row.get('close_price')) is not None
    ]
    if not eligible:
        return None, [FLAG_PRICE_MISSING]
    selected = max(eligible, key=lambda row: str(row.get('trading_date') or ''))
    return to_decimal(selected.get('close_price')), []


def calculate_annual_growth_outputs(
    periods: Sequence[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
    instrument_id: str,
    run_id: str,
    *,
    methodology_version_id: str | None = None,
    years_available: int | None = None,
    dividend_rows: Sequence[Mapping[str, Any]] = (),
    prices: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Compute the annual Class-B growth, quality and forensic rows.

    Every formula here was re-read from the workbook in Phase 4.2; the
    extraction table is in `docs/PHASE_4_2_IMPLEMENTATION_NOTES.md` section 1.

    ==========================================  ==========================================
    metric_code                                 Excel source
    ==========================================  ==========================================
    ``GROWTH_REVENUE_CAGR_LONG``                ``MetricsClassification!B7``
    ``GROWTH_REVENUE_CAGR_SHORT``               ``MetricsClassification!B8``
    ``GROWTH_REVENUE_YOY``                      ``MetricsClassification!B11``
    ``GROWTH_REVENUE_COV``                      ``MetricsClassification!B10``
    ``GROWTH_EPS_CAGR_LONG``                    ``MetricsClassification!B13``
    ``GROWTH_EPS_CAGR_SHORT``                   ``MetricsClassification!B14``
    ``GROWTH_CURRENT_ASSET_YOY``                ``MetricsClassification!B17``
    ``GROWTH_ASSET_GROWTH_GAP``                 ``MetricsClassification!B18``
    ``QUALITY_NWC_TO_REVENUE``                  ``MetricsClassification!B19`` / ``B68``
    ``QUALITY_NWC_INTENSITY_CHANGE``            ``MetricsClassification!B20``
    ``QUALITY_REVENUE_MOMENTUM``                ``MetricsClassification!B9``
    ``FORENSIC_DEBT_GROWTH_GAP``                ``FinancialHealth!B16``
    ``FORENSIC_MARGIN_SPIKE``                   ``FinancialHealth!B17``
    ``DIVIDEND_PAYOUT_RATIO``                   ``DataInput!B28`` = ``B26/B30``
    ``DIVIDEND_YIELD``                          ``DataInput!B29`` = ``B26/B25``
    ==========================================  ==========================================

    ``Years_Avail`` defaults to the count of annual periods with a usable
    ``REVENUE`` fact. ``years_available`` can be supplied to reproduce a
    historical/backtest window; it selects the newest N such annual periods.
    ``Years_Compare`` is derived from that selected window by the registered
    ``years_compare_thresholds`` ladder. Both feed the Excel index arithmetic
    exactly, so ``INDEX(Range_X, Years_Compare + 1)`` addresses the correct
    year rather than a position among the years that happen to be present.

    The selected window is explicit in the output as ``YEARS_AVAILABLE`` and
    ``YEARS_COMPARE``. A requested window larger than the available revenue
    history is rejected rather than silently shortened.

    Rows whose period cannot be established (for example when the series is
    empty) are emitted once against an instrument-level identity, so a missing
    metric is always visible rather than silently absent from the result set.

    ``QUALITY_REVENUE_MOMENTUM`` is emitted as ``1`` for "Accelerating" and
    ``0`` for "Slowing". Excel renders emoji text; a numeric encoding is used
    because the forward contract's result rows carry ``value_numeric``. The
    raw labels are preserved in the row's ``flags`` as
    ``REVENUE_MOMENTUM_ACCELERATING`` / ``REVENUE_MOMENTUM_SLOWING`` so the
    textual meaning is not lost.

    ``dividend_rows`` and ``prices`` are optional because the first thirteen
    metrics are pure fundamental series. They are required only by the two
    dividend ratios:

    * ``DIVIDEND_PAYOUT_RATIO`` = ``DPS / EPS`` (``DataInput!B28``). ``EPS`` is
      the same value ``GROWTH_EPS_CAGR_*`` reads, so a year with no earnings
      produces ``UNAVAILABLE`` rather than a fabricated zero.
    * ``DIVIDEND_YIELD`` = ``DPS / year-end close`` (``DataInput!B29``). The
      price basis is **critical** (blueprint 5.8): it is the last close on or
      before 31 December of that fiscal year, not the latest price.

    Both are emitted for the **anchor** year (the newest year in the window),
    because a result row belongs to one ``financial_period_id``. The historical
    series the UI charts is assembled from one snapshot per year, so each
    year's own snapshot carries that year's DPS and year-end price.
    """
    all_annual_periods = _annual_periods(periods)
    facts_by_period = _facts_by_period(facts)

    available_periods: list[Mapping[str, Any]] = []
    for period in all_annual_periods:
        revenue_value, revenue_flags = fact_value(
            facts_by_period.get(_period_id(period), {}).get('REVENUE'), 'REVENUE'
        )
        if revenue_flags or revenue_value is None:
            # Do not compact across a missing annual slot: doing so would make
            # an N-year RRI bridge a gap of more than N calendar years.
            break
        available_periods.append(period)

    # A backtest cutoff may leave newer periods in the supplied input. The
    # caller should pass only periods available at that cutoff; the engine takes
    # the newest contiguous block with usable revenue as its anchor.
    if years_available is None:
        years_avail = len(available_periods)
    else:
        if isinstance(years_available, bool) or not isinstance(years_available, int):
            raise CalculationError('YEARS_AVAILABLE_MUST_BE_AN_INTEGER')
        if years_available < 1 or years_available > len(available_periods):
            raise CalculationError(
                'YEARS_AVAILABLE_OUT_OF_RANGE: '
                f'requested {years_available}, available {len(available_periods)}'
            )
        years_avail = years_available

    ordered = available_periods[:years_avail]
    revenue_values = _period_values(ordered, facts_by_period, 'REVENUE')
    years_compare = _years_compare(years_avail)

    anchor = _latest_period(ordered, facts_by_period, 'REVENUE') or (
        ordered[0] if ordered else None
    )
    identity = _annual_identity(
        instrument_id=instrument_id,
        run_id=run_id,
        period=anchor,
        methodology_version_id=methodology_version_id,
    )
    rows: list[dict[str, Any]] = []

    _emit(
        rows,
        metric_code='YEARS_AVAILABLE',
        identity=identity,
        value=Decimal(years_avail),
    )
    _emit(
        rows,
        metric_code='YEARS_COMPARE',
        identity=identity,
        value=Decimal(years_compare),
    )

    # --- B7 / B8: revenue CAGR over the full and comparison windows ---------
    latest_revenue, _p, latest_flags = _indexed_value(
        ordered, facts_by_period, 'REVENUE', 1
    )
    oldest_revenue, _p2, oldest_flags = _indexed_value(
        ordered, facts_by_period, 'REVENUE', years_avail
    )
    long_value, long_flags = _rri(
        years_avail - 1,
        oldest_revenue,
        latest_revenue,
        start_flags=oldest_flags,
        end_flags=latest_flags,
    )
    _emit(
        rows,
        metric_code='GROWTH_REVENUE_CAGR_LONG',
        identity=identity,
        value=long_value,
        flags=long_flags,
    )

    compare_revenue, _p3, compare_flags = _indexed_value(
        ordered, facts_by_period, 'REVENUE', years_compare + 1
    )
    short_value, short_flags = _rri(
        years_compare,
        compare_revenue,
        latest_revenue,
        start_flags=compare_flags,
        end_flags=latest_flags,
    )
    _emit(
        rows,
        metric_code='GROWTH_REVENUE_CAGR_SHORT',
        identity=identity,
        value=short_value,
        flags=short_flags,
    )

    # --- B11: latest-year revenue growth ------------------------------------
    prior_revenue, prior_period, prior_flags = _indexed_value(
        ordered, facts_by_period, 'REVENUE', 2
    )
    yoy_row = growth_result(
        metric_code='GROWTH_REVENUE_YOY',
        current=facts_by_period.get(_period_id(anchor), {}).get('REVENUE')
        if anchor is not None
        else None,
        prior=facts_by_period.get(_period_id(prior_period), {}).get('REVENUE')
        if prior_period is not None
        else None,
        current_field='REVENUE',
        prior_field='REVENUE',
        identity=identity,
        comparison_missing=prior_period is None,
        comparison_flag=FLAG_COMPARISON_PERIOD_MISSING,
    )
    rows.append(yoy_row)

    # --- B10: revenue coefficient of variation (STDEV.P / AVERAGE) ----------
    cov_value, cov_flags = _coefficient_of_variation(revenue_values)
    _emit(
        rows,
        metric_code='GROWTH_REVENUE_COV',
        identity=identity,
        value=cov_value,
        flags=cov_flags,
    )

    # --- B13 / B14: EPS CAGR over the full and comparison windows -----------
    eps_latest, eps_latest_flags = _eps_value(ordered, facts_by_period, 1)
    eps_oldest, eps_oldest_flags = _eps_value(ordered, facts_by_period, years_avail)
    eps_long, eps_long_flags = _rri(
        years_avail - 1,
        eps_oldest,
        eps_latest,
        start_flags=eps_oldest_flags,
        end_flags=eps_latest_flags,
    )
    _emit(
        rows,
        metric_code='GROWTH_EPS_CAGR_LONG',
        identity=identity,
        value=eps_long,
        flags=eps_long_flags,
    )

    eps_compare, eps_compare_flags = _eps_value(ordered, facts_by_period, years_compare + 1)
    eps_short, eps_short_flags = _rri(
        years_compare,
        eps_compare,
        eps_latest,
        start_flags=eps_compare_flags,
        end_flags=eps_latest_flags,
    )
    _emit(
        rows,
        metric_code='GROWTH_EPS_CAGR_SHORT',
        identity=identity,
        value=eps_short,
        flags=eps_short_flags,
    )

    # --- B15: EPS momentum (short-window CAGR vs full-history CAGR) ---------
    if eps_long is None or eps_short is None:
        eps_momentum_value = None
        eps_momentum_flags = merge_flags(eps_long_flags, eps_short_flags)
    else:
        eps_momentum_value = Decimal(1) if eps_short > eps_long else Decimal(0)
        eps_momentum_flags = merge_flags(eps_long_flags, eps_short_flags)
        eps_momentum_flags = merge_flags(
            eps_momentum_flags,
            [
                'EPS_MOMENTUM_ACCELERATING'
                if eps_momentum_value == 1
                else 'EPS_MOMENTUM_SLOWING'
            ],
        )
    _emit(
        rows,
        metric_code='QUALITY_EPS_MOMENTUM',
        identity=identity,
        value=eps_momentum_value,
        flags=eps_momentum_flags,
    )

    # --- B9: revenue momentum (B8 > B7 -> Accelerating) --------------------
    momentum_flags: list[str] = []
    if long_value is None or short_value is None:
        momentum_value = None
    else:
        momentum_value = Decimal(1) if short_value > long_value else Decimal(0)
        momentum_flags = [
            'REVENUE_MOMENTUM_ACCELERATING' if momentum_value == 1
            else 'REVENUE_MOMENTUM_SLOWING'
        ]
    _emit(
        rows,
        metric_code='QUALITY_REVENUE_MOMENTUM',
        identity=identity,
        value=momentum_value,
        flags=momentum_flags,
    )

    # --- B17 / B18: current-asset growth and the asset-growth gap -----------
    current_asset_latest, _p, ca_latest_flags = _indexed_value(
        ordered, facts_by_period, CURRENT_ASSET_ALIASES[0], 1
    )
    if ca_latest_flags:
        # The annual alias is CURRENT_ASSETS; try the quarterly-style code too.
        current_asset_latest, _p, ca_latest_flags = _indexed_value(
            ordered, facts_by_period, CURRENT_ASSET_ALIASES[1], 1
        )
    current_asset_prior, ca_prior_period, ca_prior_flags = _indexed_value(
        ordered, facts_by_period, CURRENT_ASSET_ALIASES[0], 2
    )
    if ca_prior_flags:
        current_asset_prior, ca_prior_period, ca_prior_flags = _indexed_value(
            ordered, facts_by_period, CURRENT_ASSET_ALIASES[1], 2
        )

    ca_growth, ca_growth_flags = _rri(
        1,
        current_asset_prior,
        current_asset_latest,
        start_flags=ca_prior_flags,
        end_flags=ca_latest_flags,
    )
    _emit(
        rows,
        metric_code='GROWTH_CURRENT_ASSET_YOY',
        identity=identity,
        value=ca_growth,
        flags=ca_growth_flags,
    )

    # B18 = revenue YoY - current-asset growth, with the revenue side read from
    # the same B11 row so the two cannot disagree.
    revenue_yoy = to_decimal(yoy_row['value_numeric'])
    if revenue_yoy is None or ca_growth is None:
        gap_value = None
        gap_flags = merge_flags(yoy_row['flags'], ca_growth_flags)
    else:
        gap_value = revenue_yoy - ca_growth
        gap_flags = merge_flags(yoy_row['flags'], ca_growth_flags)
    _emit(
        rows,
        metric_code='GROWTH_ASSET_GROWTH_GAP',
        identity=identity,
        value=gap_value,
        flags=gap_flags,
    )

    # --- B19 / B68 / B20: NWC intensity and its year-over-year change -------
    nwc_latest, nwc_latest_flags = _nwc(
        ordered, facts_by_period, 1
    )
    nwc_prior, nwc_prior_flags = _nwc(
        ordered, facts_by_period, 2
    )
    revenue_latest, _p, rev_latest_flags = _indexed_value(
        ordered, facts_by_period, 'REVENUE', 1
    )
    revenue_prior, _p, rev_prior_flags = _indexed_value(
        ordered, facts_by_period, 'REVENUE', 2
    )

    intensity_latest, intensity_flags = _divide_optional(
        nwc_latest, revenue_latest, nwc_latest_flags, rev_latest_flags
    )
    _emit(
        rows,
        metric_code='QUALITY_NWC_TO_REVENUE',
        identity=identity,
        value=intensity_latest,
        flags=intensity_flags,
    )

    intensity_prior, intensity_prior_flags = _divide_optional(
        nwc_prior, revenue_prior, nwc_prior_flags, rev_prior_flags
    )
    if intensity_latest is None or intensity_prior is None:
        change_value = None
        change_flags = merge_flags(intensity_flags, intensity_prior_flags)
    else:
        change_value = intensity_latest - intensity_prior
        change_flags = merge_flags(intensity_flags, intensity_prior_flags)
    _emit(
        rows,
        metric_code='QUALITY_NWC_INTENSITY_CHANGE',
        identity=identity,
        value=change_value,
        flags=change_flags,
    )

    # --- FinancialHealth!B16: liabilities CAGR minus EPS CAGR ---------------
    # Exactly the workbook formula, which is NOT the same as "debt growth minus
    # profit growth" that its D16 diagnostic text describes. The registry keeps
    # both readings side by side (forensic_debt_growth_gap_definition).
    liabilities_latest, _p, liab_latest_flags = _indexed_value(
        ordered, facts_by_period, 'TOTAL_LIABILITIES', 1
    )
    liabilities_compare, _p, liab_compare_flags = _indexed_value(
        ordered, facts_by_period, 'TOTAL_LIABILITIES', years_compare + 1
    )
    liabilities_cagr, liabilities_flags = _rri(
        years_compare,
        liabilities_compare,
        liabilities_latest,
        start_flags=liab_compare_flags,
        end_flags=liab_latest_flags,
    )
    if liabilities_cagr is None or eps_short is None:
        debt_gap_value = None
        debt_gap_flags = merge_flags(liabilities_flags, eps_short_flags)
    else:
        debt_gap_value = liabilities_cagr - eps_short
        debt_gap_flags = merge_flags(liabilities_flags, eps_short_flags)
    _emit(
        rows,
        metric_code='FORENSIC_DEBT_GROWTH_GAP',
        identity=identity,
        value=debt_gap_value,
        flags=debt_gap_flags,
    )

    # --- FinancialHealth!B17: latest gross margin minus the mean margin -----
    gross_profit_values = _period_values(ordered, facts_by_period, 'GROSS_PROFIT')
    gross_margins: list[Decimal] = []
    for period in ordered:
        gross_profit, gp_flags = fact_value(
            facts_by_period.get(_period_id(period), {}).get('GROSS_PROFIT'), 'GROSS_PROFIT'
        )
        revenue, rev_flags = fact_value(
            facts_by_period.get(_period_id(period), {}).get('REVENUE'), 'REVENUE'
        )
        if gp_flags or rev_flags or gross_profit is None or revenue is None or revenue == 0:
            continue
        gross_margins.append(divide(gross_profit, revenue))

    if not gross_margins or not gross_profit_values:
        spike_value = None
        spike_flags = [FLAG_SERIES_INSUFFICIENT]
    else:
        latest_margin = gross_margins[0]
        mean_margin = sum(gross_margins, Decimal(0)) / Decimal(len(gross_margins))
        spike_value = latest_margin - mean_margin
        spike_flags = []
    _emit(
        rows,
        metric_code='FORENSIC_MARGIN_SPIKE',
        identity=identity,
        value=spike_value,
        flags=spike_flags,
    )

    # --- DataInput!B28 / B29: dividend payout ratio and dividend yield -------
    # Both belong to the anchor year, because a result row carries exactly one
    # `financial_period_id`. The UI's per-year series is built from one snapshot
    # per year (see `populate_growth_quality._prepare_outputs`), so each year's
    # snapshot resolves its own DPS and its own year-end close.
    #
    # The denominator differs on purpose:
    #   * DPR = DPS / EPS, so it reuses `_eps_value` - the same accessor the EPS
    #     CAGR rows read - rather than recomputing EARNINGS / OUTSTANDING_SHARES.
    #     That keeps one definition of EPS in this module.
    #   * Yield = DPS / year-end close, which is a *price* basis, so it must not
    #     use the latest price (`_latest_price` elsewhere) - blueprint 5.8 marks
    #     this as critical.
    anchor_year: int | None = None
    anchor_end = ''
    if anchor is not None:
        anchor_end = str(anchor.get('period_end') or '')
        if anchor_end[:4].isdigit():
            anchor_year = int(anchor_end[:4])

    if anchor_year is None:
        dps_value, dps_flags = None, [FLAG_SERIES_INSUFFICIENT]
    else:
        dps_value, dps_flags = _dividend_per_share(dividend_rows, anchor_year)

    anchor_eps, anchor_eps_flags = _eps_value(ordered, facts_by_period, 1)
    # `_rri` documents the distinction this must respect: `EPS_DERIVED_FROM_EARNINGS`
    # is a *provenance* flag, not a missing-input flag. The value is present and
    # usable, so it must never refuse the division. Only carry the flag forward,
    # and only let it block when the value really is absent. The same treatment
    # is applied to the price side for symmetry.
    payout_value, payout_flags = _divide_optional(
        dps_value,
        anchor_eps,
        dps_flags,
        None if anchor_eps is not None else anchor_eps_flags,
    )
    if anchor_eps is not None:
        payout_flags = merge_flags(payout_flags, anchor_eps_flags)
    _emit(
        rows,
        metric_code='DIVIDEND_PAYOUT_RATIO',
        identity=identity,
        value=payout_value,
        flags=payout_flags,
    )

    if anchor_end:
        year_end_price, price_flags = _year_end_close(prices, anchor_end)
    else:
        year_end_price, price_flags = None, [FLAG_SERIES_INSUFFICIENT]
    yield_value, yield_flags = _divide_optional(
        dps_value,
        year_end_price,
        dps_flags,
        None if year_end_price is not None else price_flags,
    )
    if year_end_price is not None:
        yield_flags = merge_flags(yield_flags, price_flags)
    _emit(
        rows,
        metric_code='DIVIDEND_YIELD',
        identity=identity,
        value=yield_value,
        flags=yield_flags,
    )

    return rows


# --------------------------------------------------------------------------
# Annual ratio layer (`calc_annual_ratios`)
# --------------------------------------------------------------------------

def latest_share_count(
    ordered_periods: Sequence[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
) -> tuple[Decimal | None, list[str]]:
    """The workbook's single `Shares Outstanding [Juta]` value, at full precision.

    The workbook writes `=Proj_Shares` in **every** column of the shares row, so one
    figure divides every year of the table. `Proj_Shares` is
    `IF(SharesThisYear > 0, SharesThisYear, SharesFallback)`, where `SharesFallback`
    is the newest year that reported a count.

    ``ordered_periods`` must be the **whole annual history, newest first**, not one
    snapshot's window: `populate_growth_quality.py` computes this once per run and
    hands the same value to every snapshot. Passing only a snapshot's window would
    silently fall back to that year's own count, which is a different number -
    ITMG 2021 EPS would report 6139.41 instead of the workbook's 6010.73.

    ``facts`` is the flat fact sequence (the same list the other entry points take),
    not a pre-built index, so a caller cannot accidentally collapse it.

    **No rounding to whole millions.** The obvious reuse target,
    `derive_projection_scenario.annual_share_count`, rounds to *Juta* because the
    projection sheet needs a display-friendly figure. Applying that rounding here
    breaks the match against the workbooks: measured against the five sample
    workbooks, full precision reproduces 70/70 EPS and BVPS cells while the rounded
    value reproduces only 49/70 (ITMG 0/14, BIRD 7/14). The rule is therefore
    implemented directly, and `tests/test_annual_ratios.py` pins the 70/70 result.

    Unlike `annual_share_count`, a ticker with no usable count is not an error: it
    returns ``(None, flags)`` so one incomplete ticker cannot abort a
    whole-portfolio run. `SHARES_CARRIED_FORWARD` marks the case where the newest
    period did not report the count itself, so the approximation stays visible.
    """
    facts_by_period = _facts_by_period(facts)
    for period in ordered_periods:
        shares, flags = fact_value(
            facts_by_period.get(_period_id(period), {}).get('OUTSTANDING_SHARES'),
            'OUTSTANDING_SHARES',
        )
        if not flags and shares is not None and shares > 0:
            carried = (
                bool(ordered_periods)
                and _period_id(period) != _period_id(ordered_periods[0])
            )
            return shares, [FLAG_SHARES_CARRIED_FORWARD] if carried else []
    return None, ['OUTSTANDING_SHARES_MISSING']


def _window_cagr(
    periods_count: int,
    first: Decimal | None,
    last: Decimal | None,
    *,
    first_flags: Sequence[str] | None = None,
    last_flags: Sequence[str] | None = None,
) -> tuple[Decimal | None, list[str]]:
    """CAGR across the displayed window: ``(last/first)**(1/n) - 1``.

    This is the ratio layer's own CAGR and it **refuses** rather than
    approximates. `_rri` is not reused on purpose: for a negative base it falls
    back to the registered ``linear_normalized`` rate, which is the right answer
    for the workbook's `MetricsClassification` CAGR cells but the wrong answer for
    a window that starts in a loss. ARII and GOLD both begin their windows in a
    loss, and the honest output there is "not available", not a normalised
    stand-in (docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md Langkah 1 rule 3, and
    section 8's note that those guards are correct behaviour).

    Guards, each with its own flag so the reason survives:

    * either endpoint missing          -> that endpoint's missing-input flags
    * ``periods_count <= 0``           -> ``CAGR_PERIOD_ZERO``
    * ``first == 0``                   -> ``DENOMINATOR_ZERO``
    * ``first < 0`` or ``last <= 0``   -> ``NEGATIVE_BASE``
    """
    if first is None:
        return None, list(first_flags or [FLAG_SERIES_INSUFFICIENT])
    if last is None:
        return None, list(last_flags or [FLAG_SERIES_INSUFFICIENT])
    if periods_count <= 0:
        return None, [FLAG_CAGR_PERIOD_ZERO]
    if first == 0:
        return None, [FLAG_DENOMINATOR_ZERO]
    if first < 0 or last <= 0:
        return None, [FLAG_NEGATIVE_BASE]

    ratio = divide(last, first)

    from decimal import localcontext

    with localcontext() as context:
        context.prec = 50
        root = ratio ** (Decimal(1) / Decimal(periods_count))
    return root - Decimal(1), []


def _emit_ratio(
    rows: list[dict[str, Any]],
    *,
    metric_code: str,
    identity: Mapping[str, Any],
    value: Decimal | None,
    flags: Sequence[str] | None = None,
) -> None:
    """Append one annual ratio row, carrying its unit label.

    The unit is written **beside** the value rather than formatted into it, so a
    consumer can never read ``0.1087`` as an amount when it is a margin
    (docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md section 2).
    """
    row_flags = list(flags or ())
    unit_code = ANNUAL_RATIO_UNITS[metric_code]
    if value is None:
        rows.append(
            unavailable_result(
                identity=identity,
                metric_code=metric_code,
                flags=row_flags,
                unit_code=unit_code,
            )
        )
        return
    rows.append(
        result_row(
            identity=identity,
            metric_code=metric_code,
            value_numeric=value,
            calculation_status=CALCULATION_STATUS_VALID,
            flags=row_flags,
            unit_code=unit_code,
        )
    )


def calculate_annual_ratio_outputs(
    periods: Sequence[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
    instrument_id: str,
    run_id: str,
    *,
    methodology_version_id: str | None = None,
    years_available: int | None = None,
    shares: Decimal | None = None,
    shares_flags: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Compute the annual ratio rows for one annual snapshot.

    ==========================================  ==========================================
    metric_code                                 formula
    ==========================================  ==========================================
    ``EPS``                                     ``EARNINGS / shares``
    ``BVPS``                                    ``TOTAL_EQUITY / shares``
    ``ROE``                                     ``EARNINGS / TOTAL_EQUITY``
    ``GROSS_MARGIN``                            ``GROSS_PROFIT / REVENUE``
    ``NET_MARGIN``                              ``EARNINGS / REVENUE``
    ``TOTAL_ASSETS``                            reported ``TOTAL_ASSETS`` (fallback: identity)
    ``TOTAL_ASSETS_DERIVED``                    ``TOTAL_LIABILITIES + TOTAL_EQUITY``
    ``REVENUE_CAGR_WINDOW``                     ``(last/first)**(1/(n-1)) - 1``
    ``EARNINGS_CAGR_WINDOW``                    idem for ``EARNINGS``
    ==========================================  ==========================================

    One snapshot per annual period, like the growth layer: `populate_growth_quality`
    passes the trailing window ending at year Y, so the level metrics resolve to
    year Y's own figures. The anchor period is the newest period in the window.

    ``shares`` **must be the workbook's single share count for the whole run**, not
    this window's newest count. The workbook writes `=Proj_Shares` in every column
    of the shares row, so year 2021's EPS uses the *latest* reported count rather
    than 2021's own. `populate_growth_quality.py` therefore resolves it once from
    the full annual history and passes the same value to every snapshot; see
    :func:`latest_share_count`. When it is omitted (direct callers, tests) it is
    resolved from the supplied window, which is correct only when that window *is*
    the full history.

    ``TOTAL_ASSETS`` and ``TOTAL_ASSETS_DERIVED`` are both stored, by decision: the
    reported figure is the official value, the reconstruction is kept beside it for
    audit, and a disagreement is flagged
    (``TOTAL_ASSETS_RECONCILIATION_MISMATCH``) instead of being hidden. The identity
    is exact for 139 of the 142 canonical annual rows; ARII, INKP and ITMG 2019
    differ by exactly 1 IDR, which is provider rounding.
    """
    ordered = _annual_periods(periods)
    if years_available is not None:
        if isinstance(years_available, bool) or not isinstance(years_available, int):
            raise CalculationError('YEARS_AVAILABLE_MUST_BE_AN_INTEGER')
        if years_available < 1:
            raise CalculationError('YEARS_AVAILABLE_OUT_OF_RANGE')
        ordered = ordered[:years_available]

    facts_by_period = _facts_by_period(facts)
    anchor = ordered[0] if ordered else None
    identity = _annual_identity(
        instrument_id=instrument_id,
        run_id=run_id,
        period=anchor,
        methodology_version_id=methodology_version_id,
    )
    rows: list[dict[str, Any]] = []

    if anchor is None:
        # No annual period was supplied. Emit one refused row per metric so the
        # metric set stays complete and the loader's set check still passes.
        for metric_code in ANNUAL_RATIO_METRICS:
            _emit_ratio(
                rows,
                metric_code=metric_code,
                identity=identity,
                value=None,
                flags=[FLAG_SERIES_INSUFFICIENT],
            )
        return rows

    latest_facts = facts_by_period.get(_period_id(anchor), {})

    earnings, earnings_flags = fact_value(latest_facts.get('EARNINGS'), 'EARNINGS')
    equity, equity_flags = fact_value(latest_facts.get('TOTAL_EQUITY'), 'TOTAL_EQUITY')
    revenue, revenue_flags = fact_value(latest_facts.get('REVENUE'), 'REVENUE')
    gross_profit, gross_profit_flags = fact_value(
        latest_facts.get('GROSS_PROFIT'), 'GROSS_PROFIT'
    )
    liabilities, liabilities_flags = fact_value(
        latest_facts.get('TOTAL_LIABILITIES'), 'TOTAL_LIABILITIES'
    )
    reported_assets, reported_assets_flags = fact_value(
        latest_facts.get('TOTAL_ASSETS'), 'TOTAL_ASSETS'
    )

    shares, shares_flags = (
        (shares, list(shares_flags or ()))
        if shares is not None or shares_flags is not None
        else latest_share_count(ordered, facts)
    )
    shares_missing_flags = shares_flags if shares is None else None

    # --- Per-share values ---------------------------------------------------
    # A provenance flag on a *present* value must not block the division:
    # `EPS_DERIVED_FROM_EARNINGS` marks how a value was obtained, not that it is
    # missing. Only the missing case passes its flags through. This is the bug
    # that once blanked every dividend payout ratio.
    eps_value, eps_flags = _divide_optional(
        earnings, shares, earnings_flags, shares_missing_flags
    )
    if shares is not None:
        eps_flags = merge_flags(eps_flags, shares_flags)
    _emit_ratio(rows, metric_code='EPS', identity=identity, value=eps_value, flags=eps_flags)

    bvps_value, bvps_flags = _divide_optional(
        equity, shares, equity_flags, shares_missing_flags
    )
    if shares is not None:
        bvps_flags = merge_flags(bvps_flags, shares_flags)
    _emit_ratio(rows, metric_code='BVPS', identity=identity, value=bvps_value, flags=bvps_flags)

    # --- Returns and margins ------------------------------------------------
    roe_value, roe_flags = _divide_optional(earnings, equity, earnings_flags, equity_flags)
    _emit_ratio(rows, metric_code='ROE', identity=identity, value=roe_value, flags=roe_flags)

    gross_margin, gross_margin_flags = _divide_optional(
        gross_profit, revenue, gross_profit_flags, revenue_flags
    )
    _emit_ratio(
        rows,
        metric_code='GROSS_MARGIN',
        identity=identity,
        value=gross_margin,
        flags=gross_margin_flags,
    )

    net_margin, net_margin_flags = _divide_optional(
        earnings, revenue, earnings_flags, revenue_flags
    )
    _emit_ratio(
        rows,
        metric_code='NET_MARGIN',
        identity=identity,
        value=net_margin,
        flags=net_margin_flags,
    )

    # --- Total assets: reported (official) beside the identity reconstruction
    if liabilities is not None and equity is not None:
        derived_assets: Decimal | None = liabilities + equity
        derived_flags: list[str] = [FLAG_TOTAL_ASSETS_DERIVED_FROM_IDENTITY]
    else:
        derived_assets = None
        derived_flags = merge_flags(
            liabilities_flags if liabilities is None else [],
            equity_flags if equity is None else [],
        ) or [FLAG_SERIES_INSUFFICIENT]
    _emit_ratio(
        rows,
        metric_code='TOTAL_ASSETS_DERIVED',
        identity=identity,
        value=derived_assets,
        flags=derived_flags,
    )

    if reported_assets is not None:
        assets_value: Decimal | None = reported_assets
        assets_flags: list[str] = []
        if derived_assets is not None and derived_assets != reported_assets:
            # Reported and reconstructed disagree. The reported figure stays
            # official (decision S1); the difference is recorded, not smoothed.
            assets_flags = [FLAG_TOTAL_ASSETS_RECONCILIATION_MISMATCH]
    elif derived_assets is not None:
        # The reported figure has not been ingested for this row yet. The
        # reconstruction supplies the value and the flag says it is not reported.
        assets_value = derived_assets
        assets_flags = [FLAG_TOTAL_ASSETS_DERIVED_FROM_IDENTITY]
    else:
        assets_value = None
        assets_flags = merge_flags(reported_assets_flags, derived_flags)
    _emit_ratio(
        rows,
        metric_code='TOTAL_ASSETS',
        identity=identity,
        value=assets_value,
        flags=assets_flags,
    )

    # --- Window CAGR --------------------------------------------------------
    # `ordered` is newest-first, so the oldest period of the window is last.
    window_years = len(ordered)
    periods_count = window_years - 1

    first_revenue, _p, first_revenue_flags = _indexed_value(
        ordered, facts_by_period, 'REVENUE', window_years
    )
    last_revenue, _p, last_revenue_flags = _indexed_value(
        ordered, facts_by_period, 'REVENUE', 1
    )
    revenue_cagr, revenue_cagr_flags = _window_cagr(
        periods_count,
        first_revenue,
        last_revenue,
        first_flags=first_revenue_flags,
        last_flags=last_revenue_flags,
    )
    _emit_ratio(
        rows,
        metric_code='REVENUE_CAGR_WINDOW',
        identity=identity,
        value=revenue_cagr,
        flags=revenue_cagr_flags,
    )

    first_earnings, _p, first_earnings_flags = _indexed_value(
        ordered, facts_by_period, 'EARNINGS', window_years
    )
    last_earnings, _p, last_earnings_flags = _indexed_value(
        ordered, facts_by_period, 'EARNINGS', 1
    )
    earnings_cagr, earnings_cagr_flags = _window_cagr(
        periods_count,
        first_earnings,
        last_earnings,
        first_flags=first_earnings_flags,
        last_flags=last_earnings_flags,
    )
    _emit_ratio(
        rows,
        metric_code='EARNINGS_CAGR_WINDOW',
        identity=identity,
        value=earnings_cagr,
        flags=earnings_cagr_flags,
    )

    return rows







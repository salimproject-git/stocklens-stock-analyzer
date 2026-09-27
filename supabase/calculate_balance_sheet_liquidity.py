#!/usr/bin/env python3
"""
calculate_balance_sheet_liquidity.py
====================================

Phase 4.2 - Balance-sheet liquidity and solvency layer.

The forward contract (`Testing/test_calculation_v1.py`) imports exactly one
symbol from this module::

    from supabase.calculate_balance_sheet_liquidity import calculate_balance_outputs

and asserts:

1. ``calculate_balance_outputs`` returns a list of result rows.
2. ``LIQUIDITY_CURRENT_RATIO`` for ``TOTAL_CURRENT_ASSET = 200`` and
   ``CURRENT_LIABILITIES = 100`` is exactly ``'2'``.
3. ``LIQUIDITY_QUICK_RATIO`` is ``UNAVAILABLE`` with ``INVENTORY_MISSING`` when
   the period has no ``INVENTORIES`` fact, even though cash is present.
4. A negative denominator yields ``NEGATIVE_DENOMINATOR``.

Scope discipline
----------------
Only metrics that the workbook, the Phase 4 blueprint, the forward tests or the
existing web-app logic define are implemented. Projection-dependent variants
(for example ``DER_PROJECTED``, which mixes a current liability with a
*projected* equity) are **not** implemented, because the projection engine does
not exist yet (blueprint gap ``G-PROJ``).

Units
-----
Amounts are consumed as stored, in raw IDR. No ``x1000`` scaling is applied:
Excel's multiplier exists only because its share column is denominated in *Juta*
(blueprint rule ``U-3``).

Point-in-time honesty
---------------------
``financial_periods.available_date`` and ``report_date`` are NULL for every
canonical period, so fundamental point-in-time correctness is **not** claimed.
Every row therefore carries ``STATEMENT_SCOPE_UNKNOWN``, which records that the
consolidated-versus-standalone question is unverifiable rather than resolved by
assumption.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Sequence

from calculation_v1_common import (
    CALCULATION_STATUS_UNAVAILABLE,
    FLAG_BANK_SECTOR_EXEMPT,
    FLAG_DENOMINATOR_ZERO,
    FLAG_INTEREST_EXPENSE_NEGATIVE,
    FLAG_INTEREST_EXPENSE_ZERO,
    FLAG_SECTOR_UNKNOWN,
    FLAG_STATEMENT_SCOPE_UNKNOWN,
    CalculationError,
    fact_value,
    merge_flags,
    ratio_result,
    result_row,
    to_decimal,
    unavailable_result,
)

__all__ = [
    'BANK_SECTOR_MARKER',
    'BALANCE_RATIO_METRICS',
    'calculate_balance_outputs',
]

#: Excel's bank test is ``ISNUMBER(SEARCH("Financials", Company_Sector))``
#: (`FinancialHealth!B10`), i.e. a case-insensitive substring match.
BANK_SECTOR_MARKER = 'financials'

#: ``(metric_code, numerator_code, denominator_code)`` for the plain ratios.
BALANCE_RATIO_METRICS: tuple[tuple[str, str, str], ...] = (
    ('LIQUIDITY_CURRENT_RATIO', 'CURRENT_ASSET_ALIAS', 'CURRENT_LIABILITIES'),
    ('LIQUIDITY_DER_ACTUAL', 'TOTAL_LIABILITIES', 'TOTAL_EQUITY'),
)

#: Canonical current-asset alias pair, annual first (blueprint section 4.3).
CURRENT_ASSET_ALIASES: tuple[str, ...] = ('CURRENT_ASSETS', 'TOTAL_CURRENT_ASSET')


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _period_id(period: Mapping[str, Any]) -> str:
    return str(period.get('id') or period.get('financial_period_id') or '')


def _period_end(period: Mapping[str, Any]) -> str:
    return str(period.get('period_end') or '')


def _facts_by_period(
    facts: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Mapping[str, Any]]]:
    index: dict[str, dict[str, Mapping[str, Any]]] = {}
    for fact in facts:
        period_id = str(fact.get('financial_period_id') or '')
        metric_code = str(fact.get('metric_code') or '')
        if not period_id or not metric_code:
            continue
        index.setdefault(period_id, {})[metric_code] = fact
    return index


def _scope_flags(period: Mapping[str, Any]) -> list[str]:
    """Return the statement-scope flag for a period.

    ``statement_scope`` is ``UNKNOWN`` for every canonical period and that is
    preserved, never replaced with a guessed scope.
    """
    scope = str(period.get('statement_scope') or 'UNKNOWN').upper()
    basis = str(period.get('period_basis') or 'UNKNOWN').upper()
    if scope == 'UNKNOWN' or basis == 'UNKNOWN':
        return [FLAG_STATEMENT_SCOPE_UNKNOWN]
    return []


def _identity(
    *,
    instrument_id: str,
    run_id: str,
    period: Mapping[str, Any],
    methodology_version_id: str | None,
) -> dict[str, Any]:
    identity: dict[str, Any] = {
        'calculation_run_id': run_id,
        'instrument_id': instrument_id,
        'financial_period_id': _period_id(period),
        'observation_date': _period_end(period),
    }
    if methodology_version_id is not None:
        identity['methodology_version_id'] = methodology_version_id
    return identity


def _is_bank(sector: str | None) -> tuple[bool, list[str]]:
    """Reproduce ``ISNUMBER(SEARCH("Financials", Company_Sector))``.

    Returns ``(is_bank, flags)``. A bank has no meaningful interest coverage, so
    the workbook short-circuits to ``"N/A (Bank)"``; the engine records
    ``BANK_SECTOR_EXEMPT`` instead of emitting a ratio. An absent sector cannot
    be assumed to be a non-bank, so it is flagged ``SECTOR_UNKNOWN`` and the
    ICR is refused rather than computed on a guess.
    """
    if sector is None or not str(sector).strip():
        return False, [FLAG_SECTOR_UNKNOWN]
    return BANK_SECTOR_MARKER in str(sector).lower(), []


def _current_asset_fact(
    facts: Mapping[str, Mapping[str, Any]],
) -> tuple[Mapping[str, Any] | None, str]:
    """Resolve the current-asset fact across the canonical alias pair.

    Returns ``(fact, resolved_code)``. ``CURRENT_ASSETS`` is the annual code and
    ``TOTAL_CURRENT_ASSET`` is the quarterly one, so both must be tried or half
    the periods silently return NULL (blueprint section 4.3).
    """
    for code in CURRENT_ASSET_ALIASES:
        fact = facts.get(code)
        if fact is not None and to_decimal(fact.get('value_numeric')) is not None:
            return fact, code
    return None, CURRENT_ASSET_ALIASES[0]


def _resolve(
    facts: Mapping[str, Mapping[str, Any]], metric_code: str
) -> tuple[Mapping[str, Any] | None, str]:
    if metric_code == 'CURRENT_ASSET_ALIAS':
        return _current_asset_fact(facts)
    return facts.get(metric_code), metric_code


# --------------------------------------------------------------------------
# BALANCE_SHEET_LIQUIDITY
# --------------------------------------------------------------------------

def calculate_balance_outputs(
    periods: Sequence[Mapping[str, Any]],
    facts: Sequence[Mapping[str, Any]],
    instrument_id: str,
    run_id: str,
    *,
    sector: str | None = None,
    methodology_version_id: str | None = None,
) -> list[dict[str, Any]]:
    """Compute the balance-sheet liquidity and solvency results.

    One row set per period, containing:

    ``LIQUIDITY_CURRENT_RATIO``
        ``current assets / current liabilities``
        (``FinancialHealth!B9``). The current-asset side resolves across the
        canonical ``CURRENT_ASSETS`` / ``TOTAL_CURRENT_ASSET`` alias pair.

    ``LIQUIDITY_QUICK_RATIO``
        ``(current assets - inventories) / current liabilities``. Canonical
        ``INVENTORIES`` exists only for **annual** periods, so a quarterly
        period is ``UNAVAILABLE`` with ``INVENTORY_MISSING``. The forward test
        asserts exactly that, including the case where cash is present: an
        approximate quick ratio using cash instead of inventories is
        deliberately **not** produced, because ``cash`` is not a substitute for
        the current-asset ex-inventory aggregate.

    ``LIQUIDITY_DER_ACTUAL``
        ``total liabilities / total equity`` (``der_actual``). The workbook's
        template variant ``DER_PROJECTED`` mixes a current liability with a
        *projected* equity and is not implemented, because the projection engine
        does not exist (blueprint gap ``G-PROJ``). The blueprint requires the
        two to be separate metric codes precisely so the difference stays
        auditable.

    ``LIQUIDITY_INTEREST_COVERAGE``
        ``(net income - interest expense) / ABS(interest expense)``, exactly the
        workbook's ``FinancialHealth!B10``. The numerator is **net income, not
        EBIT**, which makes the label "interest coverage" misleading; the
        blueprint records that and the engine reproduces the workbook so parity
        is measurable. A bank sector short-circuits with
        ``BANK_SECTOR_EXEMPT``, a zero interest expense with
        ``INTEREST_EXPENSE_ZERO``, and an unknown sector with
        ``SECTOR_UNKNOWN`` rather than being assumed to be a non-bank.

    Every row carries the period's scope flags, so ``STATEMENT_SCOPE_UNKNOWN``
    is always visible.

    Ordering is deterministic: periods ascending by ``period_end``, metrics in
    the order above. Only periods of one type are compared, and no value is
    carried across periods, so no future period can leak into a result.
    """
    ordered = sorted(
        periods,
        key=lambda period: (_period_end(period), str(period.get('period_label') or '')),
    )
    facts_by_period = _facts_by_period(facts)
    is_bank, sector_flags = _is_bank(sector)

    rows: list[dict[str, Any]] = []
    for period in ordered:
        identity = _identity(
            instrument_id=instrument_id,
            run_id=run_id,
            period=period,
            methodology_version_id=methodology_version_id,
        )
        period_facts = facts_by_period.get(_period_id(period), {})
        scope_flags = _scope_flags(period)

        # --- current ratio -------------------------------------------------
        numerator_fact, numerator_code = _resolve(period_facts, 'CURRENT_ASSET_ALIAS')
        current_ratio = ratio_result(
            metric_code='LIQUIDITY_CURRENT_RATIO',
            numerator=numerator_fact,
            denominator=period_facts.get('CURRENT_LIABILITIES'),
            numerator_field=numerator_code,
            denominator_field='CURRENT_LIABILITIES',
            identity=identity,
        )
        current_ratio['flags'] = merge_flags(current_ratio['flags'], scope_flags)
        rows.append(current_ratio)

        # --- quick ratio ---------------------------------------------------
        rows.append(
            _quick_ratio(
                identity=identity,
                facts=period_facts,
                numerator_fact=numerator_fact,
                numerator_code=numerator_code,
                scope_flags=scope_flags,
            )
        )

        # --- DER (actual) --------------------------------------------------
        der = ratio_result(
            metric_code='LIQUIDITY_DER_ACTUAL',
            numerator=period_facts.get('TOTAL_LIABILITIES'),
            denominator=period_facts.get('TOTAL_EQUITY'),
            numerator_field='TOTAL_LIABILITIES',
            denominator_field='TOTAL_EQUITY',
            identity=identity,
        )
        der['flags'] = merge_flags(der['flags'], scope_flags)
        rows.append(der)

        # --- interest coverage ---------------------------------------------
        rows.append(
            _interest_coverage(
                identity=identity,
                facts=period_facts,
                is_bank=is_bank,
                sector_flags=sector_flags,
                scope_flags=scope_flags,
            )
        )
    return rows


def _quick_ratio(
    *,
    identity: Mapping[str, Any],
    facts: Mapping[str, Mapping[str, Any]],
    numerator_fact: Mapping[str, Any] | None,
    numerator_code: str,
    scope_flags: Sequence[str],
) -> dict[str, Any]:
    """``(current assets - inventories) / current liabilities``.

    ``INVENTORIES`` is required, and canonical data has it for **annual periods
    only** (blueprint section 4.3). A quarterly period therefore yields
    ``UNAVAILABLE`` with ``INVENTORY_MISSING`` — the forward test asserts this
    even when cash is present, because cash is not a valid stand-in for the
    current-asset ex-inventory aggregate. No fallback is attempted.
    """
    numerator_value, numerator_flags = fact_value(numerator_fact, numerator_code)
    inventory_value, inventory_flags = fact_value(
        facts.get('INVENTORIES'), 'INVENTORIES'
    )
    if numerator_flags or inventory_flags:
        return unavailable_result(
            identity=identity,
            metric_code='LIQUIDITY_QUICK_RATIO',
            flags=merge_flags(numerator_flags, inventory_flags, scope_flags),
        )

    assert numerator_value is not None and inventory_value is not None
    row = ratio_result(
        metric_code='LIQUIDITY_QUICK_RATIO',
        numerator=None,
        denominator=facts.get('CURRENT_LIABILITIES'),
        numerator_field='QUICK_ASSETS',
        denominator_field='CURRENT_LIABILITIES',
        identity=identity,
        numerator_value=numerator_value - inventory_value,
    )
    row['flags'] = merge_flags(row['flags'], scope_flags)
    return row


def _interest_coverage(
    *,
    identity: Mapping[str, Any],
    facts: Mapping[str, Mapping[str, Any]],
    is_bank: bool,
    sector_flags: Sequence[str],
    scope_flags: Sequence[str],
) -> dict[str, Any]:
    """``(net income - interest expense) / ABS(interest expense)``.

    Reproduces ``FinancialHealth!B10`` exactly, including the fact that the
    numerator is **net income, not EBIT**. The workbook's own label is
    therefore misleading; the blueprint records that and the engine keeps the
    workbook semantics so parity is measurable, rather than silently
    substituting the "better" EBIT formula (blueprint section 5.14 and the
    open decision it raises).

    Short-circuits, in workbook order:

    1. bank sector           -> ``UNAVAILABLE`` + ``BANK_SECTOR_EXEMPT``
    2. interest expense == 0 -> ``UNAVAILABLE`` + ``INTEREST_EXPENSE_ZERO``
    3. unknown sector        -> ``UNAVAILABLE`` + ``SECTOR_UNKNOWN``

    A negative interest expense is impossible for a real expense line, so it is
    treated as unusable rather than being silently absolute-valued.
    """
    if is_bank:
        return unavailable_result(
            identity=identity,
            metric_code='LIQUIDITY_INTEREST_COVERAGE',
            flags=merge_flags([FLAG_BANK_SECTOR_EXEMPT], scope_flags),
        )

    # An absent sector cannot be assumed to be a non-bank: the bank
    # short-circuit is the whole reason this ratio needs a sector at all, so a
    # guessed "not a bank" could emit a meaningless coverage figure for a bank.
    if FLAG_SECTOR_UNKNOWN in sector_flags:
        return unavailable_result(
            identity=identity,
            metric_code='LIQUIDITY_INTEREST_COVERAGE',
            flags=merge_flags(sector_flags, scope_flags),
        )

    net_income, net_income_flags = fact_value(facts.get('EARNINGS'), 'EARNINGS')
    interest, interest_flags = fact_value(
        facts.get('INTEREST_EXPENSE_NON_OPERATING'), 'INTEREST_EXPENSE_NON_OPERATING'
    )
    if net_income_flags or interest_flags:
        return unavailable_result(
            identity=identity,
            metric_code='LIQUIDITY_INTEREST_COVERAGE',
            flags=merge_flags(net_income_flags, interest_flags, scope_flags),
        )

    if interest == 0:
        return unavailable_result(
            identity=identity,
            metric_code='LIQUIDITY_INTEREST_COVERAGE',
            flags=merge_flags([FLAG_INTEREST_EXPENSE_ZERO], scope_flags),
        )
    if interest < 0:
        return unavailable_result(
            identity=identity,
            metric_code='LIQUIDITY_INTEREST_COVERAGE',
            flags=merge_flags([FLAG_INTEREST_EXPENSE_NEGATIVE], scope_flags),
        )

    # The denominator is ABS(interest expense), so it is strictly positive here
    # and the ratio can never be refused for a negative denominator.
    row = ratio_result(
        metric_code='LIQUIDITY_INTEREST_COVERAGE',
        numerator=None,
        denominator=None,
        numerator_field='EARNINGS',
        denominator_field='INTEREST_EXPENSE_NON_OPERATING',
        identity=identity,
        numerator_value=net_income - interest,
        denominator_value=abs(interest),
    )
    row['flags'] = merge_flags(row['flags'], sector_flags, scope_flags)
    return row




#!/usr/bin/env python3
"""
pit_primitives.py
=================

Phase 4.1 - Layer-1 point-in-time (PIT) calculation primitives.

Scope
-----
This module implements **only** reusable, deterministic PIT primitives:

* :func:`edate`              - Excel ``EDATE`` month arithmetic
* :func:`as_of_price`        - last ``Close`` where ``Date <= as_of_date``
* :func:`year_end_price`     - last ``Close`` where ``Date <= YYYY-12-31``
* :func:`avg_volume_3m`      - mean ``Volume`` over ``[EDATE(as_of,-3), as_of]``
* :func:`latest_price_date`  - most recent trading date available

It deliberately does **not** implement valuation, growth, health, or
classification logic. Those belong to later phases.

Authoritative mapping (Phase 4 blueprint section 4.11)
------------------------------------------------------

The workbook resolves a point-in-time price with a backward ``XLOOKUP``::

    LET(ticker, [#This Row Ticker],
        asof,   DATE([#This Row Year], 12, 31),
        IFERROR(XLOOKUP(1,
            (tblPriceHistory_DB[Ticker]=ticker) * (tblPriceHistory_DB[Date]<=asof),
            tblPriceHistory_DB[Close], "", 0, -1), ""))

and the 3-month average volume with::

    LET(asof,      [#This Row Data Available Date],
        startdate, EDATE(asof, -3),
        IFERROR(AVERAGEIFS(tblPriceHistory_DB[Volume],
            tblPriceHistory_DB[Ticker], ticker,
            tblPriceHistory_DB[Date], ">="&startdate,
            tblPriceHistory_DB[Date], "<="&asof), ""))

The primitives below reproduce those two rules exactly.

Rules honoured
--------------

* **PIT-1** A price is always the last close on or before the requested
  as-of date. The globally latest price is *never* substituted.
* **PIT-2** ``year_end_price(year)`` resolves ``as_of = YYYY-12-31`` and takes
  the last close on or before it, so market holidays on 31-Dec are handled.
* **PIT-4** The ``Avg Vol (3M)`` window is inclusive at both ends and is
  averaged over the rows that exist (missing days are not imputed).
* Prices are IDR per share. Volume is share volume. No ``x1000`` factor is
  ever applied here: that multiplier exists in Excel only because Excel's
  share column is denominated in *Juta* (millions), while canonical
  ``OUTSTANDING_SHARES`` is a raw share count.

Workbook defect preserved
-------------------------

``Stock_Database!O`` is *labelled* ``Avg Vol (3M)`` but its formula is
identical to ``Stock_Database!N`` and therefore returns ``Close``. Per the
Phase 4 rule ("do not silently fix the workbook"), this module models the
**documented intended** formula, which is the correct quarterly formula
``Stock_Database_Quarter!O``. The annual defect is recorded in
``docs/PHASE4_CALCULATION_BLUEPRINT.md`` section 2.3.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Sequence

__all__ = [
    'PitPrimitiveError',
    'PricePoint',
    'avg_volume_3m',
    'as_of_price',
    'edate',
    'latest_price_date',
    'normalize_prices',
    'year_end_price',
]


# --------------------------------------------------------------------------
# Value normalisation
# --------------------------------------------------------------------------

def _to_date(value: Any) -> date:
    """Coerce a DB/JSON date value to :class:`datetime.date`."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise PitPrimitiveError('DATE_EMPTY')
        try:
            return date.fromisoformat(text[:10])
        except ValueError as error:
            raise PitPrimitiveError(f'DATE_INVALID: {value!r}') from error
    raise PitPrimitiveError(f'DATE_UNSUPPORTED: {value!r}')


def _to_decimal(value: Any) -> Decimal | None:
    """Coerce a numeric value to :class:`~decimal.Decimal`, or ``None``.

    ``None`` and empty strings are preserved as "no value" rather than being
    coerced to zero (Phase 4 principle P5: missing is not zero).
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise PitPrimitiveError(f'NUMBER_UNSUPPORTED: {value!r}')
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        # Route through repr so a value that arrived via JSON keeps its
        # shortest decimal form rather than the binary expansion.
        return Decimal(repr(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation as error:
            raise PitPrimitiveError(f'NUMBER_INVALID: {value!r}') from error
    raise PitPrimitiveError(f'NUMBER_UNSUPPORTED: {value!r}')


@dataclass(frozen=True)
class PricePoint:
    """One normalised ``prices_daily`` row."""

    trading_date: date
    close_price: Decimal | None
    volume: Decimal | None

    @property
    def has_close(self) -> bool:
        return self.close_price is not None

    @property
    def has_volume(self) -> bool:
        return self.volume is not None


def normalize_prices(rows: Iterable[dict[str, Any]]) -> list[PricePoint]:
    """Normalise raw ``prices_daily`` rows into a sorted :class:`PricePoint` list.

    Rows are sorted by ``trading_date`` ascending. Duplicate trading dates are
    rejected: the canonical table holds one row per instrument per date, so a
    duplicate means the caller passed an unfiltered multi-instrument set.
    """
    points: list[PricePoint] = []
    seen: set[date] = set()
    for row in rows:
        trading_date = _to_date(row.get('trading_date'))
        if trading_date in seen:
            raise PitPrimitiveError(f'DUPLICATE_TRADING_DATE: {trading_date.isoformat()}')
        seen.add(trading_date)
        points.append(
            PricePoint(
                trading_date=trading_date,
                close_price=_to_decimal(row.get('close_price')),
                volume=_to_decimal(row.get('volume')),
            )
        )
    points.sort(key=lambda point: point.trading_date)
    return points



# --------------------------------------------------------------------------
# Excel EDATE
# --------------------------------------------------------------------------

def edate(start: date, months: int) -> date:
    """Reproduce Excel ``EDATE(start_date, months)``.

    Excel shifts the calendar month and **clamps** the day-of-month to the
    last valid day of the target month. For example
    ``EDATE(2026-05-31, -3) == 2026-02-28`` (2026 is not a leap year), while
    ``EDATE(2026-06-30, -3) == 2026-03-30``.

    :mod:`calendar` is used rather than naive day arithmetic so the clamping
    matches Excel for month-end dates.
    """
    if not isinstance(months, int) or isinstance(months, bool):
        raise PitPrimitiveError(f'MONTHS_UNSUPPORTED: {months!r}')

    total = (start.year * 12 + (start.month - 1)) + months
    year, month_index = divmod(total, 12)
    month = month_index + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(start.day, last_day))


# --------------------------------------------------------------------------
# PIT primitives
# --------------------------------------------------------------------------

def _sorted_points(prices: Sequence[PricePoint] | Iterable[dict[str, Any]]) -> list[PricePoint]:
    """Accept either normalised points or raw ``prices_daily`` rows."""
    if isinstance(prices, (list, tuple)) and prices and isinstance(prices[0], PricePoint):
        return list(prices)  # type: ignore[arg-type]
    return normalize_prices(prices)  # type: ignore[arg-type]


def as_of_price(
    prices: Sequence[PricePoint] | Iterable[dict[str, Any]],
    as_of_date: date | str,
) -> Decimal | None:
    """Return the last ``close_price`` with ``trading_date <= as_of_date``.

    Returns ``None`` when no row qualifies. Rows after ``as_of_date`` are
    never considered, so a historical query can never leak a future price.
    Rows whose ``close_price`` is NULL are skipped in favour of the most
    recent row that does carry a close.
    """
    cutoff = _to_date(as_of_date)
    best: Decimal | None = None
    for point in _sorted_points(prices):
        if point.trading_date > cutoff:
            break
        if point.close_price is not None:
            best = point.close_price
    return best


def year_end_price(
    prices: Sequence[PricePoint] | Iterable[dict[str, Any]],
    year: int,
) -> Decimal | None:
    """Return the last ``close_price`` on or before 31-Dec of ``year``.

    This is the ``Stock_Database!N`` rule. Because 31-Dec is a market holiday
    in most years, the result is normally the close of 29-Dec or 30-Dec. A
    naive ``trading_date = YYYY-12-31`` filter would return nothing.
    """
    if not isinstance(year, int) or isinstance(year, bool):
        raise PitPrimitiveError(f'YEAR_UNSUPPORTED: {year!r}')
    return as_of_price(prices, date(year, 12, 31))


def avg_volume_3m(
    prices: Sequence[PricePoint] | Iterable[dict[str, Any]],
    as_of_date: date | str,
) -> Decimal | None:
    """Return the mean ``volume`` over ``[EDATE(as_of, -3), as_of]`` inclusive.

    Reproduces ``Stock_Database_Quarter!O``. The window is a **3 calendar
    month** window, not a 63-trading-day window, and it is **not** adjusted
    for missing days: the mean is taken over the rows that exist.

    Returns ``None`` when the window contains no row carrying a volume.
    """
    cutoff = _to_date(as_of_date)
    start = edate(cutoff, -3)

    total = Decimal(0)
    count = 0
    for point in _sorted_points(prices):
        if point.trading_date < start or point.trading_date > cutoff:
            continue
        if point.volume is None:
            continue
        total += point.volume
        count += 1

    if count == 0:
        return None
    return total / Decimal(count)


def latest_price_date(
    prices: Sequence[PricePoint] | Iterable[dict[str, Any]],
) -> date | None:
    """Return the most recent ``trading_date`` present, or ``None``.

    Provided so callers can report the true data edge **without** accidentally
    using it as a valuation as-of price.
    """
    points = _sorted_points(prices)
    return points[-1].trading_date if points else None


class PitPrimitiveError(RuntimeError):
    """Raised when PIT inputs violate a documented data invariant."""

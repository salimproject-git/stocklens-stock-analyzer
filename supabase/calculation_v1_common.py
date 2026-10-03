#!/usr/bin/env python3
"""
calculation_v1_common.py
========================

Phase 4.1 - Shared primitives for the StockLens calculation engine.

`Testing/test_calculation_v1.py` imports from this module:

    from supabase.calculation_v1_common import (
        CalculationError, SupabaseRest, calculation_contract, canonical_json,
        growth_result, ratio_result, sha256_json,
    )

Phase 4.1 owned the **hashing and transport** half of that contract.
**Phase 4.2** adds the **calculation-domain** half that the forward tests
pin down, and nothing more:

``calculation_contract``  - deterministic run contract (input hash + key).
``growth_result``         - period-over-period growth row.
``ratio_result``          - numerator/denominator ratio row.

Implemented here (Phase 4.1)
----------------------------
``CalculationError``   - error type used across the calculation layer.
``SupabaseRest``       - PostgREST client with secret-safe error messages.
``canonical_json``     - re-exported from `calculation_registry`.
``sha256_json``        - re-exported from `calculation_registry`.

Implemented here (Phase 4.2)
----------------------------
``calculation_contract``, ``growth_result``, ``ratio_result`` plus the
``calculation_status`` and ``flags`` vocabularies they emit. The status set is
fixed by the forward specification (blueprint section 3.5):

    calculation_status in {VALID, NOT_CALCULABLE, UNAVAILABLE}

Flags named by the forward specification are reproduced verbatim. Phase 4.2
adds a small number of *additional* flags for cases the specification does not
name (a present period whose fact is missing, an unknown sector, a bank
exemption). They are listed separately in ``PHASE_4_2_FLAGS`` and documented in
`docs/PHASE_4_2_IMPLEMENTATION_NOTES.md` so the two groups are never confused.

The hashing functions are re-exported rather than re-implemented so that the
Phase 4.1 registry, the migration seed, and this module can never disagree
about what a hash means.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

import requests

from calculation_registry import (
    RegistryError,
    canonical_json,
    idempotency_key,
    input_hash,
    sha256_json,
)

__all__ = [
    'CalculationError',
    'SupabaseRest',
    'canonical_json',
    'calculation_contract',
    'growth_result',
    'idempotency_key',
    'input_hash',
    'pinned',
    'pinned_precision',
    'ratio_result',
    'result_row',
    'sha256_json',
    'unavailable_result',
]


# --------------------------------------------------------------------------
# Result vocabularies
# --------------------------------------------------------------------------
# `calculation_status` is fixed by the forward specification
# (docs/archive/PHASE4_CALCULATION_BLUEPRINT.md section 3.5):
#
#   VALID          the value was computed
#   NOT_CALCULABLE inputs are present but a documented guard refuses the value
#                  (zero denominator, negative denominator, negative base)
#   UNAVAILABLE    an input is missing, so no value can exist at all

CALCULATION_STATUS_VALID = 'VALID'
CALCULATION_STATUS_NOT_CALCULABLE = 'NOT_CALCULABLE'
CALCULATION_STATUS_UNAVAILABLE = 'UNAVAILABLE'

CALCULATION_STATUSES = (
    CALCULATION_STATUS_VALID,
    CALCULATION_STATUS_NOT_CALCULABLE,
    CALCULATION_STATUS_UNAVAILABLE,
)

#: Flags named verbatim by the forward specification.
FLAG_DENOMINATOR_ZERO = 'DENOMINATOR_ZERO'
FLAG_NEGATIVE_BASE = 'NEGATIVE_BASE'
FLAG_NEGATIVE_DENOMINATOR = 'NEGATIVE_DENOMINATOR'
FLAG_QUARTERLY_COMPARISON_MISSING = 'QUARTERLY_COMPARISON_MISSING'
FLAG_STATEMENT_SCOPE_UNKNOWN = 'STATEMENT_SCOPE_UNKNOWN'
FLAG_INSUFFICIENT_ROLLING_WINDOW = 'INSUFFICIENT_ROLLING_WINDOW'
FLAG_MARKET_CAP_MISSING = 'MARKET_CAP_MISSING'
FLAG_PRICE_MISSING = 'PRICE_MISSING'
FLAG_INVENTORY_MISSING = 'INVENTORY_MISSING'
FLAG_TTM_INCOMPLETE = 'TTM_INCOMPLETE'
FLAG_POINT_IN_TIME_UNSAFE = 'POINT_IN_TIME_UNSAFE'
FLAG_DIVIDEND_EVENT_DATE_MISSING = 'DIVIDEND_EVENT_DATE_MISSING'
FLAG_DIVIDEND_PER_SHARE_MISSING = 'DIVIDEND_PER_SHARE_MISSING'

SPECIFICATION_FLAGS = (
    FLAG_DENOMINATOR_ZERO,
    FLAG_NEGATIVE_BASE,
    FLAG_NEGATIVE_DENOMINATOR,
    FLAG_QUARTERLY_COMPARISON_MISSING,
    FLAG_STATEMENT_SCOPE_UNKNOWN,
    FLAG_INSUFFICIENT_ROLLING_WINDOW,
    FLAG_MARKET_CAP_MISSING,
    FLAG_PRICE_MISSING,
    FLAG_INVENTORY_MISSING,
    FLAG_TTM_INCOMPLETE,
    FLAG_POINT_IN_TIME_UNSAFE,
    FLAG_DIVIDEND_EVENT_DATE_MISSING,
)

#: Flags added by Phase 4.2 for cases the forward specification does not name.
#: They are listed separately so the two groups can never be confused, and they
#: are documented in `docs/PHASE_4_2_IMPLEMENTATION_NOTES.md`.
FLAG_COMPARISON_PERIOD_MISSING = 'COMPARISON_PERIOD_MISSING'
FLAG_SECTOR_UNKNOWN = 'SECTOR_UNKNOWN'
FLAG_BANK_SECTOR_EXEMPT = 'BANK_SECTOR_EXEMPT'
FLAG_INTEREST_EXPENSE_ZERO = 'INTEREST_EXPENSE_ZERO'
FLAG_INTEREST_EXPENSE_NEGATIVE = 'INTEREST_EXPENSE_NEGATIVE'
FLAG_CURRENT_ASSETS_ALIAS_RESOLVED = 'CURRENT_ASSETS_ALIAS_RESOLVED'
FLAG_GROSS_PROFIT_DERIVED = 'GROSS_PROFIT_DERIVED'
FLAG_EPS_DERIVED_FROM_EARNINGS = 'EPS_DERIVED_FROM_EARNINGS'
FLAG_PARAMETER_UNRESOLVED = 'PARAMETER_UNRESOLVED'
FLAG_SERIES_INSUFFICIENT = 'SERIES_INSUFFICIENT'
FLAG_CAGR_PERIOD_ZERO = 'CAGR_PERIOD_ZERO'
FLAG_MEAN_ZERO = 'MEAN_ZERO'
FLAG_NEGATIVE_SERIES_VALUE = 'NEGATIVE_SERIES_VALUE'
FLAG_QUICK_ASSET_MISSING = 'QUICK_ASSET_MISSING'

#: Flags for the annual ratio layer (`calculate_annual_ratio_outputs`).
#:
#: These mark *provenance* and *approximation*, never a missing input, with one
#: exception: ``FLAG_TOTAL_ASSETS_RECONCILIATION_MISMATCH`` records that the
#: reported total assets and the balance-sheet identity disagree. The identity
#: is exact for 139 of the 142 canonical annual rows; ARII/INKP/ITMG 2019 differ
#: by exactly 1 IDR, which is provider rounding rather than a data defect. The
#: reported figure stays the official value (decision S1) and the difference is
#: surfaced instead of hidden.
FLAG_SHARES_CARRIED_FORWARD = 'SHARES_CARRIED_FORWARD'
FLAG_TOTAL_ASSETS_DERIVED_FROM_IDENTITY = 'TOTAL_ASSETS_DERIVED_FROM_IDENTITY'
FLAG_TOTAL_ASSETS_RECONCILIATION_MISMATCH = 'TOTAL_ASSETS_RECONCILIATION_MISMATCH'
FLAG_MOS_NOT_APPLICABLE = 'MOS_NOT_APPLICABLE'

PHASE_4_2_FLAGS = (
    FLAG_COMPARISON_PERIOD_MISSING,
    FLAG_SECTOR_UNKNOWN,
    FLAG_BANK_SECTOR_EXEMPT,
    FLAG_INTEREST_EXPENSE_ZERO,
    FLAG_CURRENT_ASSETS_ALIAS_RESOLVED,
    FLAG_GROSS_PROFIT_DERIVED,
    FLAG_EPS_DERIVED_FROM_EARNINGS,
    FLAG_PARAMETER_UNRESOLVED,
    FLAG_SERIES_INSUFFICIENT,
    FLAG_CAGR_PERIOD_ZERO,
    FLAG_MEAN_ZERO,
    FLAG_NEGATIVE_SERIES_VALUE,
    FLAG_QUICK_ASSET_MISSING,
    FLAG_SHARES_CARRIED_FORWARD,
    FLAG_TOTAL_ASSETS_DERIVED_FROM_IDENTITY,
    FLAG_TOTAL_ASSETS_RECONCILIATION_MISMATCH,
    FLAG_MOS_NOT_APPLICABLE,
)

#: Missing-input flag aliases. The forward specification names
#: ``INVENTORY_MISSING`` (singular) for the canonical ``INVENTORIES`` fact, so
#: the flag cannot simply be ``metric_code + '_MISSING'``. Every other
#: canonical metric uses the ``<CODE>_MISSING`` convention.
MISSING_FLAG_ALIASES: dict[str, str] = {
    'INVENTORIES': FLAG_INVENTORY_MISSING,
}


def missing_input_flag(metric_code: str) -> str:
    """Return the missing-input flag for a canonical ``metric_code``."""
    return MISSING_FLAG_ALIASES.get(metric_code, str(metric_code) + '_MISSING')


def merge_flags(*groups: Sequence[str] | None) -> list[str]:
    """Concatenate flag groups, removing duplicates but preserving order."""
    merged: list[str] = []
    for group in groups:
        for flag in group or ():
            if flag not in merged:
                merged.append(flag)
    return merged


# --------------------------------------------------------------------------
# Versioned parameter access (Phase 4.1 registry)
# --------------------------------------------------------------------------

def registry_parameter(parameter_code: str) -> tuple[Any, str]:
    """Return ``(value, resolution_status)`` for a registered parameter.

    The calculation layer must consume versioned parameters rather than
    re-embedding Excel constants in code, so every threshold it needs is looked
    up here. The catalogue import is deferred to call time so this module stays
    importable when only the transport half is needed.

    Raises :class:`CalculationError` for an unknown parameter code: a missing
    parameter is a registry defect, not a value to invent.
    """
    import calculation_parameter_catalogue as catalogue

    row = catalogue.parameter_index().get(parameter_code)
    if row is None:
        raise CalculationError(f'PARAMETER_NOT_REGISTERED: {parameter_code}')
    return row[2], row[4]


def resolved_parameter(parameter_code: str) -> Any:
    """Return a parameter value, refusing to use an unresolved one.

    A parameter whose resolution status is not ``RESOLVED`` must never be
    silently consumed, because that would turn a recorded gap into a guessed
    constant. Callers that can proceed without the value should use
    :func:`registry_parameter` and handle the status themselves.
    """
    from calculation_registry import RESOLUTION_RESOLVED

    value, resolution = registry_parameter(parameter_code)
    if resolution != RESOLUTION_RESOLVED:
        raise CalculationError(
            f'PARAMETER_UNRESOLVED: {parameter_code} ({resolution})'
        )
    return value


class CalculationError(RuntimeError):
    """Raised for calculation-layer configuration and contract failures."""


class SupabaseRest:
    """Minimal PostgREST client for the calculation layer.

    Mirrors the credential and session pattern used by the Phase 2 canonical
    loaders so there is one HTTP convention in the repository.

    Error messages deliberately expose only PostgREST diagnostics (status,
    ``code``, ``message``, ``details``, ``hint``) and never the service key,
    the ``apikey`` header, the ``Authorization`` header, or the request
    payload. ``Testing/test_calculation_v1.py`` asserts exactly that.
    """

    def __init__(self, url: str, key: str) -> None:
        url = (url or '').strip().rstrip('/')
        key = (key or '').strip()
        if not url or not key:
            raise CalculationError('SUPABASE_CONFIGURATION_MISSING')

        self.base_url = url
        self.service_key = key
        self.rest_url = url + '/rest/v1'
        self.session = requests.Session()
        self.session.headers.update(
            {
                'apikey': key,
                'Authorization': 'Bearer ' + key,
                'Content-Type': 'application/json',
            }
        )

    def request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        payload: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Perform a request against ``table`` and return the decoded body.

        On a non-2xx response the PostgREST diagnostics are surfaced without
        leaking credentials or the request payload.
        """
        response = self.session.request(
            method,
            self.rest_url + '/' + table,
            params=params,
            json=payload,
            headers=headers,
            timeout=120,
        )
        if not response.ok:
            raise CalculationError(self._describe_failure(table, response))
        if not response.content:
            return None
        return response.json()

    def get_all(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        """GET ``table`` and require a list response."""
        value = self.request('GET', table, params=params)
        if not isinstance(value, list):
            raise CalculationError(f'{table}: non-list response')
        return value

    @staticmethod
    def _describe_failure(table: str, response: Any) -> str:
        """Build a secret-safe diagnostic string for a failed request."""
        code = message = details = hint = None
        try:
            body = response.json()
            if isinstance(body, dict):
                code = body.get('code')
                message = body.get('message')
                details = body.get('details')
                hint = body.get('hint')
        except Exception:  # noqa: BLE001 - diagnostics are best effort
            pass

        return (
            f'{table}:{getattr(response, "status_code", "?")} '
            f'code={code} message={message} details={details} hint={hint}'
        )


def registry_error_to_calculation_error(error: RegistryError) -> CalculationError:
    """Translate a registry failure into a calculation-layer error."""
    return CalculationError(str(error))


# --------------------------------------------------------------------------
# Numeric handling
# --------------------------------------------------------------------------

#: Working precision for every division in the calculation layer.
#: `decimal` defaults to 28 significant digits, which is enough for the AUTO
#: values but leaves results sensitive to a caller that has widened or narrowed
#: the ambient context. Pinning 34 (IEEE decimal128) inside a ``localcontext``
#: makes every division here reproducible.
DECIMAL_PRECISION = 34

AVAILABILITY_READY = 'READY'

#: `quality_status` values that mean "this fact carries no usable number".
#: The canonical check constraint allows VALID / MISSING / INVALID / ESTIMATED.
#: ESTIMATED is a *present* value and is used as-is; MISSING and INVALID are
#: treated as absent so an unusable number is never silently consumed.
QUALITY_STATUSES_WITHOUT_VALUE = ('MISSING', 'INVALID')

#: Identity keys copied from the caller's identity mapping onto a result row.
RESULT_IDENTITY_KEYS = (
    'calculation_run_id',
    'instrument_id',
    'financial_period_id',
    'observation_date',
    'methodology_version_id',
)


def to_decimal(value: Any) -> Decimal | None:
    """Coerce a canonical numeric value to :class:`~decimal.Decimal`.

    ``None`` and an empty string mean "no value" and return ``None``. Floats go
    through ``repr`` so ``0.1`` becomes ``Decimal('0.1')`` rather than the
    binary expansion. ``NaN`` and ``Infinity`` are rejected instead of being
    propagated silently into a result row.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise CalculationError(f'VALUE_NOT_NUMERIC: {value!r}')
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, float):
        result = Decimal(repr(value))
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            result = Decimal(text)
        except InvalidOperation as error:
            raise CalculationError(f'VALUE_NOT_NUMERIC: {value!r}') from error
    else:
        raise CalculationError(f'VALUE_NOT_NUMERIC: {value!r}')

    if not result.is_finite():
        raise CalculationError(f'VALUE_NOT_FINITE: {value!r}')
    return result


def format_decimal(value: Decimal | None) -> str | None:
    """Return the shortest exact decimal text for ``value``.

    Result values are persisted as decimal **strings** so precision survives
    the JSON round trip, exactly as the parameter registry does. Trailing
    fractional zeros are removed because they carry no information, and the
    exponent form is never emitted (``1E+2`` becomes ``100``), so two equal
    values always render identically. A signed zero is normalised to ``'0'``.
    """
    if value is None:
        return None
    text = format(value, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    if text.startswith('-') and set(text[1:]) <= {'0', '.'}:
        text = text[1:]
    return text or '0'


def divide(numerator: Decimal, denominator: Decimal) -> Decimal:
    """Divide at the pinned precision, independent of the ambient context."""
    with pinned_precision():
        return numerator / denominator


def pinned_precision() -> Any:
    """Return a context manager that pins the decimal working precision.

    Every arithmetic step that touches a high-precision intermediate value must
    run inside this context. ``divide`` pins itself, but a following ``- 1`` or
    ``a - b`` would otherwise fall back to the *ambient* context, so the same
    input could yield different digits for different callers. Pinning every such
    step is what makes the calculation layer reproducible.
    """
    from decimal import localcontext

    return localcontext(prec=DECIMAL_PRECISION)


def pinned(function: Any) -> Any:
    """Decorate a calculation entry point so its whole body is precision-pinned.

    Pinning per-entry-point is stronger than pinning per-operation: a metric that
    chains several subtractions, a division and a comparison cannot have any
    single step silently fall back to the caller's ambient decimal context. The
    wrapper only sets the context, so it never changes a signature or a return
    value, and it keeps working when a body gains another arithmetic step.
    """
    import functools

    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        with pinned_precision():
            return function(*args, **kwargs)

    return wrapper


def fact_value(fact: Mapping[str, Any] | None, field: str) -> tuple[Decimal | None, list[str]]:
    """Read the numeric value of a canonical fact row.

    Returns ``(value, flags)``. The number is read from ``value_numeric``,
    which is the canonical column that holds a fact's amount; ``field`` names
    the input for the returned missing flag and for documentation.

    A missing fact row, a NULL ``value_numeric``, or a fact whose
    ``quality_status`` is ``MISSING`` / ``INVALID`` all mean "no value", and the
    returned flag names the absent input using the canonical ``<CODE>_MISSING``
    convention (with the documented ``INVENTORY_MISSING`` alias for
    ``INVENTORIES``). A value is never substituted or defaulted.

    For a plain mapping that has no ``value_numeric`` key at all — for example a
    pre-flattened ``{field: value}`` dict — ``fact[field]`` is used instead.
    ``value_numeric`` is authoritative whenever the key is present, so a NULL
    canonical value can never fall through to a different key.
    """
    if fact is None:
        return None, [missing_input_flag(field)]
    metric_code = fact.get('metric_code')
    if metric_code is not None and str(metric_code) != field:
        return None, [missing_input_flag(field)]
    if str(fact.get('quality_status') or '').upper() in QUALITY_STATUSES_WITHOUT_VALUE:
        return None, [missing_input_flag(field)]

    if 'value_numeric' in fact:
        value = to_decimal(fact.get('value_numeric'))
    else:
        value = to_decimal(fact.get(field))

    if value is None:
        return None, [missing_input_flag(field)]
    return value, []


def result_row(
    *,
    identity: Mapping[str, Any],
    metric_code: str,
    value_numeric: Decimal | str | None,
    calculation_status: str,
    flags: Sequence[str] | None = None,
    availability_status: str = AVAILABILITY_READY,
    **extra: Any,
) -> dict[str, Any]:
    """Build one calculation result row.

    The identity keys (run, instrument, period, observation date, methodology
    version) are copied from ``identity`` so every result stays traceable back
    to the run and the methodology version that produced it. ``value_numeric``
    is rendered as an exact decimal string.
    """
    if calculation_status not in CALCULATION_STATUSES:
        raise CalculationError(f'CALCULATION_STATUS_UNSUPPORTED: {calculation_status}')

    row: dict[str, Any] = {
        key: identity.get(key) for key in RESULT_IDENTITY_KEYS if key in identity
    }
    row['metric_code'] = metric_code
    row['value_numeric'] = (
        value_numeric if isinstance(value_numeric, str) else format_decimal(value_numeric)
    )
    row['calculation_status'] = calculation_status
    row['flags'] = list(flags or ())
    row['availability_status'] = availability_status

    for key, value in extra.items():
        if key in row:
            raise CalculationError(f'RESULT_ROW_KEY_CONFLICT: {key}')
        row[key] = value
    return row

def unavailable_result(
    *,
    identity: Mapping[str, Any],
    metric_code: str,
    flags: Sequence[str] | None = None,
    availability_status: str = AVAILABILITY_READY,
    **extra: Any,
) -> dict[str, Any]:
    """Build a result row for an input that is missing entirely."""
    return result_row(
        identity=identity,
        metric_code=metric_code,
        value_numeric=None,
        calculation_status=CALCULATION_STATUS_UNAVAILABLE,
        flags=flags,
        availability_status=availability_status,
        **extra,
    )




@pinned
def growth_result(
    *,
    metric_code: str,
    current: Mapping[str, Any] | None,
    prior: Mapping[str, Any] | None,
    current_field: str,
    prior_field: str,
    identity: Mapping[str, Any],
    comparison_missing: bool = False,
    comparison_flag: str = FLAG_QUARTERLY_COMPARISON_MISSING,
    **extra: Any,
) -> dict[str, Any]:
    """Compute ``current / prior - 1`` with explicit failure semantics.

    Semantics — each case is asserted by `Testing/test_calculation_v1.py`
    (``QuarterlyTests.test_growth_boundaries``, lines 79-90):

    =============================================  =================  ================================
    case                                           calculation_status flags
    =============================================  =================  ================================
    ``prior`` period absent (``comparison_missing``)  ``UNAVAILABLE``    ``QUARTERLY_COMPARISON_MISSING``
    ``current`` fact absent, NULL or MISSING       ``UNAVAILABLE``    ``<CURRENT_FIELD>_MISSING``
    ``prior`` fact absent, NULL or MISSING         ``UNAVAILABLE``    ``<PRIOR_FIELD>_MISSING``
    ``prior`` == 0                                 ``NOT_CALCULABLE`` ``DENOMINATOR_ZERO``
    ``prior`` < 0                                  ``NOT_CALCULABLE`` ``NEGATIVE_BASE``
    otherwise                                      ``VALID``          ``[]``
    =============================================  =================  ================================

    A negative base is refused rather than computed. ``current/prior - 1`` with
    ``prior < 0`` flips sign with the magnitude of the base, so the result is
    not interpretable as growth; the forward specification pairs
    ``NEGATIVE_BASE`` with ``NOT_CALCULABLE`` for exactly that reason
    (blueprint section 5.5 and the note at line 738). The workbook's separate
    ``linear_normalized`` escape hatch is a **CAGR** rule recorded in the
    registry as ``negative_base_cagr_mode`` and is deliberately not applied to
    a single-period growth calculation.

    ``value_numeric`` is ``None`` whenever the status is not ``VALID``, so a
    refused growth figure can never be mistaken for a computed one.
    """
    if comparison_missing:
        return unavailable_result(
            identity=identity,
            metric_code=metric_code,
            flags=[comparison_flag],
            **extra,
        )

    current_value, current_flags = fact_value(current, current_field)
    if current_flags:
        return unavailable_result(
            identity=identity,
            metric_code=metric_code,
            flags=current_flags,
            **extra,
        )

    prior_value, prior_flags = fact_value(prior, prior_field)
    if prior_flags:
        return unavailable_result(
            identity=identity,
            metric_code=metric_code,
            flags=prior_flags,
            **extra,
        )

    if current_value is None or prior_value is None:  # pragma: no cover - guarded above
        raise CalculationError('GROWTH_INPUT_UNRESOLVED')

    if prior_value == 0:
        return result_row(
            identity=identity,
            metric_code=metric_code,
            value_numeric=None,
            calculation_status=CALCULATION_STATUS_NOT_CALCULABLE,
            flags=[FLAG_DENOMINATOR_ZERO],
            **extra,
        )
    if prior_value < 0:
        return result_row(
            identity=identity,
            metric_code=metric_code,
            value_numeric=None,
            calculation_status=CALCULATION_STATUS_NOT_CALCULABLE,
            flags=[FLAG_NEGATIVE_BASE],
            **extra,
        )

    with pinned_precision():
        value = divide(current_value, prior_value) - Decimal(1)
    return result_row(
        identity=identity,
        metric_code=metric_code,
        value_numeric=value,
        calculation_status=CALCULATION_STATUS_VALID,
        flags=[],
        **extra,
    )

@pinned
def ratio_result(
    *,
    metric_code: str,
    numerator: Mapping[str, Any] | None,
    denominator: Mapping[str, Any] | None,
    numerator_field: str,
    denominator_field: str,
    identity: Mapping[str, Any],
    numerator_value: Decimal | None = None,
    denominator_value: Decimal | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Compute ``numerator / denominator`` with explicit failure semantics.

    Semantics:

    ==================================  =================  ==========================
    case                                calculation_status flags
    ==================================  =================  ==========================
    numerator absent, NULL or MISSING   ``UNAVAILABLE``    ``<NUMERATOR_FIELD>_MISSING``
    denominator absent, NULL or MISSING ``UNAVAILABLE``    ``<DENOMINATOR_FIELD>_MISSING``
    denominator == 0                    ``NOT_CALCULABLE`` ``DENOMINATOR_ZERO``
    denominator < 0                     ``NOT_CALCULABLE`` ``NEGATIVE_DENOMINATOR``
    otherwise                           ``VALID``          ``[]``
    ==================================  =================  ==========================

    A negative denominator is refused. A ratio with a negative denominator has
    an inverted sign and is not a solvency measure; the forward specification
    names ``NEGATIVE_DENOMINATOR`` for exactly this case
    (`Testing/test_calculation_v1.py` line 132, blueprint section 5.13).
    ``value_numeric`` is ``None`` whenever the status is not ``VALID``, so a
    refused ratio can never be mistaken for a computed one.

    ``numerator_value`` / ``denominator_value`` let a caller supply an already
    resolved amount — for example a derived net working capital, or a value
    produced by an alias lookup across two canonical codes — instead of a fact
    row. A supplied value takes precedence over the fact lookup for that side.
    """
    if numerator_value is None:
        numerator_value, numerator_flags = fact_value(numerator, numerator_field)
        if numerator_flags:
            return unavailable_result(
                identity=identity,
                metric_code=metric_code,
                flags=numerator_flags,
                **extra,
            )

    if denominator_value is None:
        denominator_value, denominator_flags = fact_value(denominator, denominator_field)
        if denominator_flags:
            return unavailable_result(
                identity=identity,
                metric_code=metric_code,
                flags=denominator_flags,
                **extra,
            )

    if numerator_value is None:  # pragma: no cover - guarded above
        return unavailable_result(
            identity=identity,
            metric_code=metric_code,
            flags=[missing_input_flag(numerator_field)],
            **extra,
        )
    if denominator_value is None:  # pragma: no cover - guarded above
        return unavailable_result(
            identity=identity,
            metric_code=metric_code,
            flags=[missing_input_flag(denominator_field)],
            **extra,
        )

    if denominator_value == 0:
        return result_row(
            identity=identity,
            metric_code=metric_code,
            value_numeric=None,
            calculation_status=CALCULATION_STATUS_NOT_CALCULABLE,
            flags=[FLAG_DENOMINATOR_ZERO],
            **extra,
        )
    if denominator_value < 0:
        return result_row(
            identity=identity,
            metric_code=metric_code,
            value_numeric=None,
            calculation_status=CALCULATION_STATUS_NOT_CALCULABLE,
            flags=[FLAG_NEGATIVE_DENOMINATOR],
            **extra,
        )

    value = divide(numerator_value, denominator_value)
    return result_row(
        identity=identity,
        metric_code=metric_code,
        value_numeric=value,
        calculation_status=CALCULATION_STATUS_VALID,
        flags=[],
        **extra,
    )


def calculation_contract(
    *,
    calculation_type: str,
    methodology_version_id: str,
    code_version: str,
    source_cutoff_date: str | None,
    source_ingestion_run_id: str | None,
    scope_type: str,
    scope_id: str,
    input_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the deterministic run contract for one calculation execution.

    Returns the run identity fields, the canonical ``input_hash`` of
    ``input_snapshot`` and the derived ``idempotency_key``. Key order in the
    snapshot never changes either hash, so the same inputs always resolve to
    the same run instead of creating a duplicate.

    ``retry_contract`` (a retry is a *new* run, not a mutation of the previous
    one) lives in ``calculation_v1_runner`` because that module also owns the
    terminal-state rules.
    """
    snapshot = dict(input_snapshot)
    snapshot_hash = input_hash(snapshot)
    return {
        'calculation_type': calculation_type,
        'methodology_version_id': methodology_version_id,
        'code_version': code_version,
        'source_cutoff_date': source_cutoff_date,
        'source_ingestion_run_id': source_ingestion_run_id,
        'scope_type': scope_type,
        'scope_id': scope_id,
        'input_hash': snapshot_hash,
        'idempotency_key': idempotency_key(
            calculation_type=calculation_type,
            methodology_version_id=methodology_version_id,
            code_version=code_version,
            source_cutoff_date=source_cutoff_date,
            source_ingestion_run_id=source_ingestion_run_id,
            scope_type=scope_type,
            scope_id=scope_id,
            input_hash_value=snapshot_hash,
        ),
        'input_snapshot': snapshot,
    }

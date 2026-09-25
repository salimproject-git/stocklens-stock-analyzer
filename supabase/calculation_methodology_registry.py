#!/usr/bin/env python3
"""
calculation_methodology_registry.py
==================================

Phase 4.1 - Methodology registry and seed generation.

Produces the nine methodology seed rows that
``supabase/migrations/0008_calculation_v1_batch.sql`` inserts. The forward test
contract (``Testing/test_calculation_v1.py``) parses those rows out of the
migration text and requires **exactly nine** of them, so the count is a hard
constraint.

The eight test-suite codes
--------------------------
``QUARTERLY_GROWTH_QUALITY``, ``DAILY_LIQUIDITY``,
``BALANCE_SHEET_LIQUIDITY``, ``VALUATION_INPUTS``, ``VALUATION_MULTIPLES``,
``VALUATION_METHOD_PERSISTENCE``, ``CLASSIFICATION_DESCRIPTIVE``,
``AVAILABILITY_REVISION``.

The ninth row: the unresolved valuation-method mapping
-----------------------------------------------------
``Testing/test_run_calculation_v1.py`` requires ``calc_valuation_methods`` to
contain **11** unique method codes and asserts that ``DCF``, ``DDM``,
``GRAHAM`` and ``RESIDUAL_INCOME`` are persisted with
``value_numeric = NULL`` and ``method_status = 'UNAVAILABLE'``.

The workbook, however, computes exactly **five** methods:

1. Peter Lynch Algo IV
2. Type & Sector Weighted IV
3. Mean Reversion PBV IV
4. Dividend Discount Model IV
5. Discounted Earnings Model IV

Those two sets do **not** map one-to-one. ``DDM`` matches the workbook's
Dividend Discount Model IV, and ``DCF`` is *approximately* the workbook's
Discounted Earnings Model, but ``GRAHAM`` and ``RESIDUAL_INCOME`` have no
workbook counterpart at all, and the workbook's Peter Lynch / Type & Sector /
Mean Reversion PBV methods have no test-suite code. A 5-to-11 mapping is
therefore **unresolved**.

Rather than force a false 1:1 mapping, the ninth seed row records the
mismatch explicitly as ``VALUATION_METHOD_MAPPING`` with a non-``RESOLVED``
parameter status. The mapping must be settled by a product decision before
``calc_valuation_methods`` is populated (blueprint open questions Q15 and
Q16).
"""

from __future__ import annotations

from typing import Any

from calculation_parameter_catalogue import (
    METHOD_AVAILABILITY_REVISION,
    METHOD_BALANCE_SHEET_LIQUIDITY,
    METHOD_CLASSIFICATION_DESCRIPTIVE,
    METHOD_DAILY_LIQUIDITY,
    METHOD_QUARTERLY_GROWTH_QUALITY,
    METHOD_VALUATION_INPUTS,
    METHOD_VALUATION_METHOD_PERSISTENCE,
    METHOD_VALUATION_MULTIPLES,
    all_parameters,
)
from calculation_registry import (
    CODE_VERSION,
    INPUT_VOCABULARY_VERSION,
    RESOLUTION_UNRESOLVED_DEFINITION,
)

#: The unresolved Excel-to-test-suite valuation method mapping.
METHOD_VALUATION_METHOD_MAPPING = 'VALUATION_METHOD_MAPPING'

#: Default method version for every seeded methodology.
METHOD_VERSION = '1.0.0'

#: The workbook's five actual valuation methods, by Excel label.
WORKBOOK_VALUATION_METHODS: tuple[str, ...] = (
    'Peter Lynch Algo IV',
    'Type & Sector Weighted IV',
    'Mean Reversion PBV IV',
    'Dividend Discount Model IV',
    'Discounted Earnings Model IV',
)

#: The method codes the forward test suite requires in `calc_valuation_methods`.
TEST_SUITE_VALUATION_METHODS: tuple[str, ...] = (
    'PETER_LYNCH',
    'TYPE_SECTOR_WEIGHTED',
    'MEAN_REVERSION_PBV',
    'DDM',
    'DCF',
    'GRAHAM',
    'RESIDUAL_INCOME',
)

#: Codes the test suite explicitly requires to be persisted as UNAVAILABLE.
TEST_SUITE_UNAVAILABLE_METHODS: tuple[str, ...] = (
    'DCF',
    'DDM',
    'GRAHAM',
    'RESIDUAL_INCOME',
)



def parameters_for_method(method_code: str) -> dict[str, Any]:
    """Collect every catalogue parameter owned by ``method_code``.

    Returns ``{parameter_code: value}``. Only the value is stored in the
    methodology's ``parameter_spec``; units, resolution status and source
    references live in the dedicated registry table so the spec stays compact
    and hash-stable.
    """
    spec: dict[str, Any] = {}
    for code, owner, value, _unit, _resolution, _source, _note in all_parameters():
        if owner == method_code:
            spec[code] = value
    return spec


def _one_line(text: str) -> str:
    """Collapse ``text`` to a single line.

    The test contract matches each seed row with a line-anchored regex, so a
    formula must not contain a newline.
    """
    return ' '.join(text.split())


#: `(method_code, method_name, description, formula_text)`
METHODOLOGY_DEFINITIONS: tuple[tuple[str, str, str, str], ...] = (
    (
        METHOD_QUARTERLY_GROWTH_QUALITY,
        'Quarterly Growth and Quality',
        'Quarter-on-quarter and year-on-year growth plus quality ratios computed from STANDALONE quarterly canonical facts.',
        'current_value / prior_value - 1 with DENOMINATOR_ZERO, NEGATIVE_BASE and QUARTERLY_COMPARISON_MISSING flags',
    ),
    (
        METHOD_DAILY_LIQUIDITY,
        'Daily Liquidity',
        'Rolling daily traded-value and turnover metrics over the configured window, requiring a present market cap.',
        'AVERAGE(volume * close_price) over the trailing 20 trading days, flagging INSUFFICIENT_ROLLING_WINDOW and MARKET_CAP_MISSING',
    ),
    (
        METHOD_BALANCE_SHEET_LIQUIDITY,
        'Balance Sheet Liquidity',
        'Current ratio and quick ratio derived from canonical balance-sheet facts, with explicit missing-inventory handling.',
        'current_assets / current_liabilities and (current_assets - inventories) / current_liabilities',
    ),
    (
        METHOD_VALUATION_INPUTS,
        'Valuation Inputs',
        'Point-in-time price, trailing dividend and forward share-count inputs that valuation multiples consume.',
        'last close_price on or before valuation_date; sum of dividend events inside the trailing window',
    ),
    (
        METHOD_VALUATION_MULTIPLES,
        'Valuation Multiples',
        'Price-to-earnings, price-to-sales and price-to-free-cash-flow multiples computed from valuation inputs.',
        'price_close / per_share_denominator using canonical IDR values with no presentation-unit scaling',
    ),
    (
        METHOD_VALUATION_METHOD_PERSISTENCE,
        'Valuation Method Persistence',
        'Persists one row per valuation method code, deduplicated by method code, keeping unavailable methods explicit.',
        'DISTINCT ON (method_code) ordered so the first snapshot wins',
    ),
    (
        METHOD_CLASSIFICATION_DESCRIPTIVE,
        'Descriptive Classification',
        'Descriptive labels derived from calculation results. No recommendation, buy or sell semantics.',
        'compare aggregated growth and quality results against neutral descriptive bands',
    ),
    (
        METHOD_AVAILABILITY_REVISION,
        'Availability and Revision Audit',
        'Audits period metadata, provenance and revision selection, and reports point-in-time safety.',
        'audit report_date and available_date presence, ingestion provenance resolution, and duplicate revision keys',
    ),
    (
        METHOD_VALUATION_METHOD_MAPPING,
        'Valuation Method Mapping (unresolved)',
        'Records the unresolved mapping between the workbook five valuation methods and the eleven method codes required by the forward test suite.',
        'UNRESOLVED: workbook methods and test-suite method codes are not a one-to-one mapping',
    ),
)


def _method_mapping_spec() -> dict[str, Any]:
    """Build the explicit, unresolved valuation-method mapping spec.

    The workbook computes five methods; the forward test suite requires eleven
    method codes. This spec records both sides plus the known overlaps, so the
    mismatch is machine-readable instead of being silently forced.
    """
    return {
        'resolution_status': RESOLUTION_UNRESOLVED_DEFINITION,
        'workbook_methods': list(WORKBOOK_VALUATION_METHODS),
        'test_suite_method_codes': list(TEST_SUITE_VALUATION_METHODS),
        'test_suite_unavailable_method_codes': list(TEST_SUITE_UNAVAILABLE_METHODS),
        'workbook_method_count': str(len(WORKBOOK_VALUATION_METHODS)),
        'test_suite_method_count_required': '11',
        'test_suite_named_method_codes': list(TEST_SUITE_VALUATION_METHODS),
        'test_suite_named_method_count': str(len(TEST_SUITE_VALUATION_METHODS)),
        'test_suite_enumerated_codes_incomplete': True,
        'confirmed_mapping': {
            'Dividend Discount Model IV': 'DDM',
        },
        'approximate_mapping': {
            'Discounted Earnings Model IV': 'DCF',
        },
        'workbook_methods_without_test_code': [
            'Peter Lynch Algo IV',
            'Type & Sector Weighted IV',
            'Mean Reversion PBV IV',
        ],
        'test_codes_without_workbook_method': ['GRAHAM', 'RESIDUAL_INCOME'],
        'note': (
            'A 5-to-11 mapping is unresolved. The test suite requires 11 unique '
            'method codes but only names 7 of them, so 4 remain unidentified. '
            '`DCF`, `DDM`, `GRAHAM` and `RESIDUAL_INCOME` must be persisted with '
            'value_numeric NULL and method_status UNAVAILABLE until a product '
            'decision settles the mapping. Do not force a false one-to-one '
            'mapping.'
        ),
    }


def methodology_seeds() -> list[dict[str, Any]]:
    """Build the nine methodology seed rows.

    Each row carries ``formula_hash`` (SHA-256 of the raw formula text) and
    ``parameter_hash`` (SHA-256 of the canonical JSON of ``parameter_spec``),
    exactly as the test contract recomputes them.
    """
    from calculation_registry import methodology_hashes

    seeds: list[dict[str, Any]] = []
    for method_code, method_name, description, formula_text in METHODOLOGY_DEFINITIONS:
        formula_text = _one_line(formula_text)
        if method_code == METHOD_VALUATION_METHOD_MAPPING:
            parameter_spec = _method_mapping_spec()
        else:
            parameter_spec = parameters_for_method(method_code)

        formula_hash, parameter_hash = methodology_hashes(formula_text, parameter_spec)
        seeds.append(
            {
                'method_code': method_code,
                'method_version': METHOD_VERSION,
                'method_name': method_name,
                'description': description,
                'formula_text': formula_text,
                'formula_hash': formula_hash,
                'parameter_spec': parameter_spec,
                'parameter_hash': parameter_hash,
                'code_version': CODE_VERSION,
                'input_vocabulary_version': INPUT_VOCABULARY_VERSION,
                'status': 'DRAFT',
            }
        )
    return seeds

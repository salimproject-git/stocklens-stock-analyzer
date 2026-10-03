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


def growth_quality_methodology_seed(
    method_version: str = '1.1.0',
) -> dict[str, Any]:
    """Definisi metodologi `QUARTERLY_GROWTH_QUALITY` versi terbaru.

    Versi `1.0.0` tetap hidup di migrasi `0008` dan tetap dipakai run lama. Baris
    ini adalah versi **berikutnya**, dibuat karena rumusnya berubah:

    * lapisan rasio tahunan baru (`EPS`, `BVPS`, `ROE`, `GROSS_MARGIN`,
      `NET_MARGIN`, `TOTAL_ASSETS`, `TOTAL_ASSETS_DERIVED`, dua CAGR jendela)
      disimpan di `calc_annual_ratios`; dan
    * `EPS`/`BVPS` memakai **satu** jumlah saham untuk seluruh tabel, mengikuti
      `=Proj_Shares` di workbook, bukan jumlah saham tahun berjalan.

    Perubahan kedua mengubah angka tersimpan, jadi ia wajib menjadi versi baru -
    bukan penimpaan `1.0.0` (docs/BACKEND_SINGLE_SOURCE_OF_TRUTH.md §9.2).

    `formula_text` memuat aturan yang menentukan angka, termasuk aturan saham,
    supaya perubahan aturan terlihat di registry dan hasil lama bisa direproduksi.
    """
    from calculation_registry import methodology_hashes

    formula_text = (
        'Annual Class-B growth, quality and forensic metrics over the trailing '
        'annual window, plus the annual ratio layer. Revenue/EPS CAGR use RRI over '
        'the full and comparison windows, falling back to the registered '
        'linear_normalized rate when the base is negative; CoV is STDEV.P/AVERAGE; '
        'DPR = DPS / EPS and Yield = DPS / year-end close. Annual ratios: '
        'EPS = EARNINGS / shares, BVPS = TOTAL_EQUITY / shares, '
        'ROE = EARNINGS / TOTAL_EQUITY, GROSS_MARGIN = GROSS_PROFIT / REVENUE, '
        'NET_MARGIN = EARNINGS / REVENUE, TOTAL_ASSETS_DERIVED = TOTAL_LIABILITIES '
        '+ TOTAL_EQUITY, TOTAL_ASSETS = the reported provider figure, and the two '
        'window CAGRs refuse rather than approximate when an endpoint is '
        'non-positive. shares is the workbook Proj_Shares rule: the newest annual '
        'period reporting a positive OUTSTANDING_SHARES, at full precision, used '
        'unchanged for every year of the table. Every refusal carries its own flag.'
    )
    parameter_spec: dict[str, Any] = {
        'negative_base_cagr_mode': 'linear_normalized',
        'years_compare_thresholds': {
            'years_avail_ge_7': '5', 'years_avail_ge_5': '3',
            'years_avail_ge_3': '2', 'default': '0',
        },
        'payout_trim_historical': '0.2',
        'yield_trim_historical': '0.2',
        'cf_status_ocf_ratio': '0.5',
        'quarterly_yoy_offset_quarters': '3',
        # Aturan saham rasio tahunan, dipakai EPS dan BVPS.
        'annual_ratio_shares_rule': 'latest_reported_positive_count_full_precision',
        'annual_ratio_shares_carried_forward_flag': 'SHARES_CARRIED_FORWARD',
        'annual_ratio_total_assets_rule': 'reported_value_with_identity_reconciliation',
    }

    formula_hash, parameter_hash = methodology_hashes(formula_text, parameter_spec)
    return {
        'method_code': 'QUARTERLY_GROWTH_QUALITY',
        'method_version': method_version,
        'method_name': 'Quarterly Growth and Quality',
        'description': (
            'Quarter-on-quarter and year-on-year growth, annual quality and '
            'forensic metrics, and the annual ratio layer computed from canonical '
            'facts.'
        ),
        'formula_text': formula_text,
        'formula_hash': formula_hash,
        'parameter_spec': parameter_spec,
        'parameter_hash': parameter_hash,
        'code_version': CODE_VERSION,
        'input_vocabulary_version': INPUT_VOCABULARY_VERSION,
        'status': 'DRAFT',
    }


def supplemental_methodology_seeds() -> list[dict[str, Any]]:
    """Methodologies added by later additive migrations.

    The nine Phase 4.1 seeds remain frozen for their migration/test contract.
    New independent methodologies are registered here so the registry checker
    can still verify them without rewriting that historical seed set.
    """
    from calculation_registry import methodology_hashes

    method_code = 'VALUATION_CURRENT'
    formula_text = (
        'Peter Lynch adaptive PER/PBV/liquidation; blended PER/PBV sector-type weights; '
        'quarterly PBV mean minus population standard deviation; Gordon DDM; five-year '
        'discounted earnings; missing inputs fail closed.'
    )
    parameter_spec: dict[str, Any] = {
        'reference_version': '1.0.0',
        'years_compare_thresholds': {
            'years_avail_ge_7': '5', 'years_avail_ge_5': '3',
            'years_avail_ge_3': '2', 'default': '0',
        },
        'target_per_by_type': {
            'SLOW GROWER': {'bottom': '8', 'top': '12'},
            'STALWART': {'bottom': '10', 'top': '16'},
            'STALWART_FINANCIAL': {'bottom': '15', 'top': '25'},
            'FAST GROWER': {
                'bottom': 'growth_rate * 100 * 0.8',
                'top': 'growth_rate * 100 * 1.2',
            },
            'CYCLICAL': {'bottom': '0', 'top': '0'},
            'ASSET PLAY': {'bottom': '0', 'top': '0'},
            'TURN AROUND': {'bottom': '0', 'top': '0'},
            'DEFAULT': {'bottom': '0', 'top': '0'},
        },
        'target_pbv_by_mode': {
            'Conservative_bottom': '0.4', 'Moderate_bottom': '0.5',
            'Aggressive_bottom': '0.7', 'Conservative_top': '0.8',
            'Moderate_top': '1', 'Aggressive_top': '1.2',
        },
        'type_to_valuation_mode': {
            'FAST GROWER': 'Aggressive', 'CYCLICAL': 'Moderate',
            'ASSET PLAY': 'Moderate', 'STALWART': 'Moderate',
            'TURN AROUND': 'Conservative',
            'DEFAULT': 'Conservative',
        },
        'mean_reversion_min_quarters': '3',
        'pe_average_outlier_factor': '0.25',
        'ddm_growth_cap': '0.04',
        'equity_risk_premium_ddm': '0.06',
        'discounted_earnings_growth_cap': '0.15',
        'discounted_earnings_per_cap': '25',
        'discounted_earnings_horizon_years': '5',
        'discounted_earnings_discount_premium': '0.04',
        'quarterly_shares_policy': 'latest_annual_share_count_as_approximation',
        'risk_free_rate': 'UNRESOLVED_SOURCE',
    }
    formula_hash, parameter_hash = methodology_hashes(formula_text, parameter_spec)
    return [{
        'method_code': method_code,
        'method_version': '1.0.0',
        'method_name': 'Current Stock Valuation',
        'description': (
            'Five workbook current-valuation methods using a selected active projection scenario, '
            'explicit stock type, history windows and versioned reference tables.'
        ),
        'formula_text': formula_text,
        'formula_hash': formula_hash,
        'parameter_spec': parameter_spec,
        'parameter_hash': parameter_hash,
        'code_version': 'stocklens-valuation-v1',
        'input_vocabulary_version': INPUT_VOCABULARY_VERSION,
        'status': 'DRAFT',
    }]

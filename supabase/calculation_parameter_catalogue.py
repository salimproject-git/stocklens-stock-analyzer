#!/usr/bin/env python3
"""
calculation_parameter_catalogue.py
=================================

Phase 4.1 - Canonical parameter catalogue.

Every constant that the Phase 4 blueprint (section 13.4) found **embedded
inside Excel formulas** is lifted here into a single, reviewable, versioned
catalogue. Nothing in the calculation engine should hard-code these values
again.

Precision contract
------------------
Values are stored as **exact decimal strings** (for example ``'0.0633'``),
never as JSON numbers. This preserves precision, keeps binary-float artefacts
out of the registry, and makes ``sha256_json`` stable across a JSON round
trip.

Units contract
--------------
Every parameter carries an explicit ``unit``. Units observed in this
catalogue:

``ratio``
    A plain decimal fraction (``0.35`` means 35%).
``multiple``
    A valuation multiple in "x" (PER, PBV).
``count``
    A whole number of items (years, quarters, points).
``integer_score``
    A score or penalty in points.
``IDR``
    An absolute rupiah amount.
``bn_IDR``
    Billions of rupiah, matching Excel's misleadingly labelled ``(M Rp)``.
``text_enum``
    A string selector.
``expression``
    A documented rule that is not a single scalar and must be evaluated in
    code (for example ``growth * 100 * 1.2``).

Resolution contract
-------------------
A parameter that the blueprint could not resolve is **not guessed**. It is
recorded with a non-``RESOLVED`` status and a note explaining exactly what is
missing, so the gap stays visible and queryable.

* ``RESOLVED``                 - value is known and safe to use.
* ``UNRESOLVED_SOURCE``        - no canonical/external data source exists yet.
* ``MISSING_INPUT``            - the required column/field is absent.
* ``UNRESOLVED_DEFINITION``    - the rule itself is undecided.
* ``BROKEN_REFERENCE``         - the workbook reference is ``#REF!``.
"""

from __future__ import annotations

from typing import Any

from calculation_registry import (
    RESOLUTION_BROKEN_REFERENCE,
    RESOLUTION_MISSING_INPUT,
    RESOLUTION_RESOLVED,
    RESOLUTION_UNRESOLVED_DEFINITION,
    RESOLUTION_UNRESOLVED_SOURCE,
)

# --------------------------------------------------------------------------
# Owner methodology codes (must exist in METHODOLOGY_SEEDS)
# --------------------------------------------------------------------------

METHOD_QUARTERLY_GROWTH_QUALITY = 'QUARTERLY_GROWTH_QUALITY'
METHOD_DAILY_LIQUIDITY = 'DAILY_LIQUIDITY'
METHOD_BALANCE_SHEET_LIQUIDITY = 'BALANCE_SHEET_LIQUIDITY'
METHOD_VALUATION_INPUTS = 'VALUATION_INPUTS'
METHOD_VALUATION_MULTIPLES = 'VALUATION_MULTIPLES'
METHOD_VALUATION_METHOD_PERSISTENCE = 'VALUATION_METHOD_PERSISTENCE'
METHOD_CLASSIFICATION_DESCRIPTIVE = 'CLASSIFICATION_DESCRIPTIVE'
METHOD_AVAILABILITY_REVISION = 'AVAILABILITY_REVISION'

# Phase 4.1 additions: parameter groups whose Excel owner has no test-suite
# methodology code of its own. They are registered so their parameters have a
# versioned home rather than living in code.
METHOD_REFERENCE_WEIGHTS = 'REFERENCE_WEIGHTS'
METHOD_HEALTH_SCORE = 'HEALTH_SCORE'
METHOD_FORENSIC_FLAGS = 'FORENSIC_FLAGS'
METHOD_BUSINESS_QUALITY = 'BUSINESS_QUALITY'
METHOD_STOCK_TYPE_CLASSIFIER = 'STOCK_TYPE_CLASSIFIER'
METHOD_STRATEGIC_TARGETS = 'STRATEGIC_TARGETS'
METHOD_PROJECTION_ENGINE = 'PROJECTION_ENGINE'
METHOD_MARKET_MOOD = 'MARKET_MOOD'
METHOD_BACKTEST_ENGINE = 'BACKTEST_ENGINE'

# --------------------------------------------------------------------------
# Reference tables (Excel `Reference` sheet)
# --------------------------------------------------------------------------

#: `Reference!B5:C16` - `Method_Weights_Sector`
SECTOR_WEIGHTS: tuple[tuple[str, str, str], ...] = (
    ('Basic Materials', '2', '2'),
    ('Consumer Cyclicals', '3', '1'),
    ('Consumer Non-Cyclicals', '3', '2'),
    ('Energy', '1', '2'),
    ('Financials', '1', '3'),
    ('Healthcare', '3', '1'),
    ('Industrials', '2', '2'),
    ('Infrastructures', '1', '2'),
    ('Properties & Real Estate', '1', '3'),
    ('Technology', '3', '1'),
    ('Transportation & Logistic', '2', '2'),
    ('Utilities', '1', '3'),
)

#: `Reference!B22:C26` - `Method_Weights_Type`
TYPE_WEIGHTS: tuple[tuple[str, str, str], ...] = (
    ('Asset Play', '0', '3'),
    ('Cyclical', '0', '10'),
    ('Fast Grower', '3', '0'),
    ('Slow Grower', '2', '3'),
    ('Stalwart', '3', '2'),
    ('Turn around', '0', '3'),
)

#: `Reference!B32:C37` - `StockType_Threshold`. `Min ICR` is absent from the
#: workbook, so it is not invented here; see the `health_default_min_icr`
#: parameter, which records the workbook's silent `IFERROR(...,3)` fallback.
TYPE_THRESHOLDS: tuple[tuple[str, str, str], ...] = (
    ('Slow Grower', '0.5', '1.5'),
    ('Stalwart', '0.8', '1.3'),
    ('Fast Grower', '1', '1.2'),
    ('Cyclical', '0.3', '2'),
    ('Turn around', '0.5', '1.5'),
    ('Asset Play', '0.4', '1.5'),
)


# --------------------------------------------------------------------------
# Parameter definitions
# --------------------------------------------------------------------------
# Each entry is:
#   (parameter_code, owner_method, value, unit, resolution, source_reference, note)
#
# `value` is an exact decimal string for scalars, or a JSON-able structure for
# grouped parameters. `source_reference` records exactly where the value came
# from so the registry stays auditable.

PARAMETERS: tuple[tuple[str, str, Any, str, str, str, str], ...] = (
    # ---------------- Valuation: discount-rate / DDM assumptions ----------
    (
        'risk_free_rate',
        METHOD_VALUATION_INPUTS,
        '0.0633',
        'ratio',
        RESOLUTION_UNRESOLVED_SOURCE,
        'DataInput!B11',
        'Excel hard-codes 0.0633 as the 10Y SBN yield. No canonical or Sectors '
        'source exists, so this is an explicit configuration gap, not a value '
        'the engine may invent. Blocks DDM IV and Discounted Earnings IV.',
    ),
    (
        'equity_risk_premium_ddm',
        METHOD_VALUATION_INPUTS,
        '0.06',
        'ratio',
        RESOLUTION_RESOLVED,
        'ValuationCurrent!B28 (WACC = Param_RiskFreeRate + 0.06)',
        'Add-on used as the DDM WACC premium over the risk-free rate.',
    ),
    (
        'ddm_growth_cap',
        METHOD_VALUATION_INPUTS,
        '0.04',
        'ratio',
        RESOLUTION_RESOLVED,
        'ValuationCurrent!B28 MIN(0.04, MAX(0, G_Long))',
        'Upper bound on the sustainable growth rate used by the DDM.',
    ),
    (
        'discounted_earnings_discount_premium',
        METHOD_VALUATION_INPUTS,
        '0.04',
        'ratio',
        RESOLUTION_RESOLVED,
        'ValuationCurrent!B29 (Disc_Rate = RiskFree + 0.04)',
        'Add-on over the risk-free rate used as the discounted-earnings '
        'discount rate.',
    ),
    (
        'discounted_earnings_growth_cap',
        METHOD_VALUATION_INPUTS,
        '0.15',
        'ratio',
        RESOLUTION_RESOLVED,
        'ValuationCurrent!B29 MIN(0.15, MAX(0, GrowthRaw))',
        'Upper bound on the growth rate used by the discounted-earnings model.',
    ),
    (
        'discounted_earnings_per_cap',
        METHOD_VALUATION_INPUTS,
        '25',
        'multiple',
        RESOLUTION_RESOLVED,
        'ValuationCurrent!B29 MIN(PE_Hist, 25)',
        'Cap applied to the historical PER when re-rating forward earnings.',
    ),
    (
        'discounted_earnings_horizon_years',
        METHOD_VALUATION_INPUTS,
        '5',
        'count',
        RESOLUTION_RESOLVED,
        'ValuationCurrent!B29 ((1+g)^5, /(1+disc)^5)',
        'Compounding and discounting horizon for the discounted-earnings model.',
    ),
    (
        'discounted_earnings_fallback_growth',
        METHOD_VALUATION_INPUTS,
        '0.05',
        'ratio',
        RESOLUTION_RESOLVED,
        'ValuationCurrent!B29 IFERROR(Metric_Rev_CAGR_Long, 0.05)',
        'Silent fallback used when the revenue CAGR is unavailable. The engine '
        'must emit an UNAVAILABLE flag rather than applying this silently; the '
        'value is registered so the divergence stays explicit.',
    ),
    (
        'discounted_earnings_fallback_per',
        METHOD_VALUATION_INPUTS,
        '15',
        'multiple',
        RESOLUTION_RESOLVED,
        'ValuationCurrent!B29 IFERROR(Metric_PE_Avg_Long, 15)',
        'Silent fallback PER. Same flagging rule as the growth fallback.',
    ),

    # ---------------- Peter Lynch target multiples (in-formula) -----------
    (
        'target_per_by_type',
        METHOD_VALUATION_MULTIPLES,
        {
            'CYCLICAL': '0',
            'ASSET PLAY': '0',
            'TURN AROUND': '0',
            'STALWART_FINANCIAL': '25',
            'SLOW GROWER': '12',
            'STALWART': '16',
            'FAST GROWER': 'growth_rate * 100 * 1.2',
            'DEFAULT': '0',
        },
        'multiple',
        RESOLUTION_RESOLVED,
        'ValuationCurrent!B4 and B5 Target_PER IFS',
        'Fair PER by stock type. FAST GROWER is an expression, not a scalar.',
    ),
    (
        'target_pbv_by_mode',
        METHOD_VALUATION_MULTIPLES,
        {
            'Conservative_bottom': '0.4',
            'Moderate_bottom': '0.5',
            'Aggressive_bottom': '0.7',
            'Conservative_top': '0.8',
            'Moderate_top': '1',
            'Aggressive_top': '1.2',
        },
        'multiple',
        RESOLUTION_RESOLVED,
        'ValuationCurrent!B7 and B8 Target_PBV IFS',
        'Target PBV split into bottom (asset/liquidation) and top (cyclical).',
    ),
    (
        'type_to_valuation_mode',
        METHOD_VALUATION_MULTIPLES,
        {
            'FAST GROWER': 'Aggressive',
            'CYCLICAL': 'Moderate',
            'ASSET PLAY': 'Moderate',
            'STALWART': 'Moderate',
            'DEFAULT': 'Conservative',
        },
        'text_enum',
        RESOLUTION_RESOLVED,
        'ValuationCurrent!B7 and B8 Final_Mode IFS',
        'Maps stock type to the valuation aggressiveness mode.',
    ),
    (
        'mean_reversion_min_quarters',
        METHOD_VALUATION_MULTIPLES,
        '3',
        'count',
        RESOLUTION_RESOLVED,
        'ValuationCurrent!B27 IF(COUNT(Valid_PBV) < 3, 0, ...)',
        'Minimum valid quarterly PBV observations before the method returns a '
        'value instead of zero.',
    ),
    (
        'pe_average_outlier_factor',
        METHOD_VALUATION_MULTIPLES,
        '0.25',
        'ratio',
        RESOLUTION_RESOLVED,
        'MetricsClassification!B36 (Range_EPS > AVERAGE(Range_EPS)*0.25)',
        'Hard-coded outlier filter for the historical PER average. This is a '
        'heuristic, not a statistical test.',
    ),
)

#: Historical-aggregation and projection parameters.
PARAMETERS_AGGREGATION: tuple[tuple[str, str, Any, str, str, str, str], ...] = (
    (
        'payout_trim_projection',
        METHOD_PROJECTION_ENGINE,
        '0.4',
        'ratio',
        RESOLUTION_RESOLVED,
        'DataInputProyeksi!B6 TRIMMEAN(Range_DPR, 0.4)',
        'Trim fraction used to derive the projected payout ratio.',
    ),
    (
        'payout_trim_historical',
        METHOD_QUARTERLY_GROWTH_QUALITY,
        '0.2',
        'ratio',
        RESOLUTION_RESOLVED,
        'MetricsClassification!B34 TRIMMEAN(..., 0.2)',
        'Trim fraction for the historical payout average.',
    ),
    (
        'yield_trim_historical',
        METHOD_QUARTERLY_GROWTH_QUALITY,
        '0.2',
        'ratio',
        RESOLUTION_RESOLVED,
        'MetricsClassification!B32 TRIMMEAN(..., 0.2)',
        'Trim fraction for the historical dividend-yield average.',
    ),
    (
        'years_compare_thresholds',
        METHOD_QUARTERLY_GROWTH_QUALITY,
        {
            'years_avail_ge_7': '5',
            'years_avail_ge_5': '3',
            'years_avail_ge_3': '2',
            'default': '0',
        },
        'count',
        RESOLUTION_RESOLVED,
        'MetricsClassification!B5 IFS',
        'Comparison-window length derived from the number of available years.',
    ),
    (
        'negative_base_cagr_mode',
        METHOD_QUARTERLY_GROWTH_QUALITY,
        'linear_normalized',
        'text_enum',
        RESOLUTION_RESOLVED,
        'MetricsClassification!B13/B14 IF(StartVal<0, ((End-Start)/ABS(Start))/Period, RRI(...))',
        'When the base value is negative the workbook abandons RRI and uses a '
        'linear normalised rate. AUTO depends on this branch (2020 EPS < 0).',
    ),
    (
        'quarterly_yoy_offset_quarters',
        METHOD_QUARTERLY_GROWTH_QUALITY,
        '3',
        'count',
        RESOLUTION_RESOLVED,
        'DataInputProyeksi!B47-B52 offset = 3',
        'The YoY thesis validator starts three quarters back from the latest '
        'audited quarter, so four quarters are displayed.',
    ),
    (
        'cf_status_ocf_ratio',
        METHOD_QUARTERLY_GROWTH_QUALITY,
        '0.5',
        'ratio',
        RESOLUTION_RESOLVED,
        'MetricsClassification!B69 IF(Proj_OCF < 0.5*Proj_Net_Income, ...)',
        'OCF/NI bar below which the cash-flow status warns of low cash.',
    ),
    (
        'projection_annualisation_factors',
        METHOD_PROJECTION_ENGINE,
        {
            'Q1': 'x4',
            'Q2': 'x2',
            'Q3': 'x(12/9)',
            'Q4': 'sum_of_four_quarters',
        },
        'expression',
        RESOLUTION_RESOLVED,
        'DataInputProyeksi!F12-F16 IFS ladder',
        'Deterministic annualisation of the latest audited quarter YTD flows.',
    ),
)

#: Health-score parameters.
PARAMETERS_HEALTH: tuple[tuple[str, str, Any, str, str, str, str], ...] = (
    (
        'health_component_points',
        METHOD_HEALTH_SCORE,
        {'der': '20', 'current_ratio': '20', 'icr': '20', 'ocf': '20', 'safety': '20'},
        'integer_score',
        RESOLUTION_RESOLVED,
        'FinancialHealth!B26 component scores',
        'Five 20-point components; the maximum score is 100.',
    ),
    (
        'health_bank_max_der',
        METHOD_HEALTH_SCORE,
        '15',
        'multiple',
        RESOLUTION_RESOLVED,
        'FinancialHealth!B26 IFS(IsBank, 15, ...)',
        'Sector override: banks are exempt from the normal DER limit.',
    ),
    (
        'health_property_max_der',
        METHOD_HEALTH_SCORE,
        '2',
        'multiple',
        RESOLUTION_RESOLVED,
        'FinancialHealth!B26 IFS(..., IsProp, 2, ...)',
        'Sector override for Properties.',
    ),
    (
        'health_default_max_der',
        METHOD_HEALTH_SCORE,
        '1',
        'multiple',
        RESOLUTION_RESOLVED,
        'FinancialHealth!B26 IFERROR(XLOOKUP(...), 1)',
        'Fallback DER limit when the stock type is unknown.',
    ),
    (
        'health_default_min_current_ratio',
        METHOD_HEALTH_SCORE,
        '1',
        'multiple',
        RESOLUTION_RESOLVED,
        'FinancialHealth!B26 IFERROR(XLOOKUP(...), 1)',
        'Fallback current-ratio limit when the stock type is unknown.',
    ),
    (
        'health_default_min_icr',
        METHOD_HEALTH_SCORE,
        '3',
        'multiple',
        RESOLUTION_UNRESOLVED_DEFINITION,
        'FinancialHealth!B26 IFERROR(XLOOKUP(Type, Ref_Type_List_Health, Ref_Type_MinICR), 3)',
        'The workbook references a `Min ICR` column that DOES NOT EXIST in '
        '`Reference`. The ICR component therefore always passes via the '
        'IFERROR fallback of 3. The per-type ICR thresholds are unresolved and '
        'must not be invented.',
    ),
    (
        'health_bank_icr_exempt',
        METHOD_HEALTH_SCORE,
        True,
        'text_enum',
        RESOLUTION_RESOLVED,
        'FinancialHealth!B26 OR(IsBank, InterestExp=0) -> 20',
        'Banks and zero-interest companies receive the full ICR component.',
    ),
    (
        'health_bank_ocf_points',
        METHOD_HEALTH_SCORE,
        '10',
        'integer_score',
        RESOLUTION_RESOLVED,
        'FinancialHealth!B26 IFS(B11>0, 20, IsBank, 10, TRUE, 0)',
        'Banks receive half OCF points because the CFO test does not apply.',
    ),
    (
        'health_ocf_ratio_threshold_cyclical',
        METHOD_HEALTH_SCORE,
        '0.6',
        'ratio',
        RESOLUTION_RESOLVED,
        'FinancialHealth!B26 Threshold = IF(IsCyclical, 0.6, 0.8)',
        'Cyclicals are held to a lower OCF/NI bar.',
    ),
    (
        'health_ocf_ratio_threshold_default',
        METHOD_HEALTH_SCORE,
        '0.8',
        'ratio',
        RESOLUTION_RESOLVED,
        'FinancialHealth!B26 Threshold = IF(IsCyclical, 0.6, 0.8)',
        'Default OCF/NI bar.',
    ),
    (
        'health_ocf_penalty_severe',
        METHOD_HEALTH_SCORE,
        '-40',
        'integer_score',
        RESOLUTION_RESOLVED,
        'FinancialHealth!B26 IF(OCF_Ratio < 0.4, -40, -20)',
        'Penalty when OCF/NI falls below 0.4.',
    ),
    (
        'health_ocf_penalty_moderate',
        METHOD_HEALTH_SCORE,
        '-20',
        'integer_score',
        RESOLUTION_RESOLVED,
        'FinancialHealth!B26 IF(OCF_Ratio < 0.4, -40, -20)',
        'Penalty when OCF/NI is below the type threshold but at or above 0.4.',
    ),
    (
        'health_ocf_penalty_severe_ratio',
        METHOD_HEALTH_SCORE,
        '0.4',
        'ratio',
        RESOLUTION_RESOLVED,
        'FinancialHealth!B26 IF(OCF_Ratio < 0.4, ...)',
        'Boundary between the severe and moderate OCF penalties.',
    ),
    (
        'health_safety_points',
        METHOD_HEALTH_SCORE,
        {'OK': '20', 'WARNING': '10', 'FAIL': '0'},
        'integer_score',
        RESOLUTION_RESOLVED,
        'FinancialHealth!B26 IF(B23="OK", 20, IF(B23="WARNING", 10, 0))',
        'Clearance-status contribution to the health score.',
    ),
    (
        'health_score_floor',
        METHOD_HEALTH_SCORE,
        '0',
        'integer_score',
        RESOLUTION_RESOLVED,
        'FinancialHealth!B26 MAX(0, ...)',
        'The weighted sum is floored at zero.',
    ),
    (
        'health_rating_bands',
        METHOD_HEALTH_SCORE,
        {'perfect_min': '85', 'healthy_min': '70', 'moderate_min': '50'},
        'integer_score',
        RESOLUTION_RESOLVED,
        'FinancialHealth!B27 rating IF ladder',
        'Score bands for the risk rating. A FAIL clearance overrides to TOXIC.',
    ),
    (
        'health_clearance_ocf_ratio',
        METHOD_HEALTH_SCORE,
        '0.8',
        'ratio',
        RESOLUTION_RESOLVED,
        'FinancialHealth!B18 OCF >= NetIncome * 0.8',
        'OCF/NI bar that marks the cash-quality check as Strong.',
    ),
)


#: Forensic-flag parameters.
PARAMETERS_FORENSIC: tuple[tuple[str, str, Any, str, str, str, str], ...] = (
    (
        'forensic_asset_growth_gap_bands',
        METHOD_FORENSIC_FLAGS,
        {'severe_below': '-0.1', 'warning_below': '-0.05', 'good_above': '0.05'},
        'ratio',
        RESOLUTION_RESOLVED,
        'FinancialHealth!D14 band ladder',
        'A negative gap means revenue is growing faster than current assets '
        '(healthy). The sign convention is easy to invert accidentally.',
    ),
    (
        'forensic_nwc_intensity_change_bands',
        METHOD_FORENSIC_FLAGS,
        {'warning_above': '0.05', 'monitor_above': '0.02', 'improving_below': '0'},
        'ratio',
        RESOLUTION_RESOLVED,
        'FinancialHealth!D15 band ladder',
        'The workbook labels this metric [ppt] but stores a ratio; the ratio '
        'is authoritative (unit label defect preserved, not fixed).',
    ),
    (
        'forensic_debt_growth_gap_threshold',
        METHOD_FORENSIC_FLAGS,
        '0.05',
        'ratio',
        RESOLUTION_UNRESOLVED_DEFINITION,
        'FinancialHealth!B16 / D16 text only',
        'Only the diagnostic text was extractable. The numeric formula for B16 '
        '(debt growth minus profit growth) must be re-read from the workbook '
        'before implementation (blueprint open question Q18).',
    ),
    (
        'forensic_margin_spike_threshold',
        METHOD_FORENSIC_FLAGS,
        '0.1',
        'ratio',
        RESOLUTION_UNRESOLVED_DEFINITION,
        'FinancialHealth!B17 / D17 text only',
        'Only the diagnostic text was extractable. The numeric formula for B17 '
        '(margin spike) must be re-read (blueprint open question Q18).',
    ),
)

#: Business-quality (moat) parameters.
PARAMETERS_QUALITY: tuple[tuple[str, str, Any, str, str, str, str], ...] = (
    (
        'quality_npm_bands',
        METHOD_BUSINESS_QUALITY,
        {'strong_above': '0.15', 'moderate_above': '0.08'},
        'ratio',
        RESOLUTION_RESOLVED,
        'SUMMARY!B57 IFS',
        'Net-profit-margin bands for the Brand Power component.',
    ),
    (
        'quality_market_cap_bands',
        METHOD_BUSINESS_QUALITY,
        {'strong_above': '10000', 'moderate_above': '2000'},
        'bn_IDR',
        RESOLUTION_RESOLVED,
        'SUMMARY!B57 IFS (DataInput!B14)',
        'Market-cap bands in billions of IDR for the Brand Power component.',
    ),
    (
        'quality_roe_threshold',
        METHOD_BUSINESS_QUALITY,
        '0.15',
        'ratio',
        RESOLUTION_RESOLVED,
        'SUMMARY!B57 Metric_ROE_Avg > 0.15',
        'ROE bar that alone awards the maximum Brand Power score.',
    ),
    (
        'quality_gcg_yield_thresholds',
        METHOD_BUSINESS_QUALITY,
        {'royal_above': '0.03', 'routine_above': '0'},
        'ratio',
        RESOLUTION_RESOLVED,
        'SUMMARY!B58 IF(Metric_Yield_Hist > 0.03, 2, ...)',
        'Historical-yield bands for the GCG and Dividend component.',
    ),
    (
        'quality_liquidity_tier_scores',
        METHOD_BUSINESS_QUALITY,
        {
            'Super Blue Chip (>200 M)': '2',
            'Blue Chip (50 - 200 M)': '1.5',
            'Second Liner (10 - 50 M)': '1',
            'default': '0',
        },
        'integer_score',
        RESOLUTION_RESOLVED,
        'SUMMARY!B59 liquidity-tier contribution',
        'Third component of the total quality score.',
    ),
    (
        'quality_multiplier_bands',
        METHOD_BUSINESS_QUALITY,
        {
            'premium_min': '5',
            'standard_min': '3',
            'premium': '1.2',
            'standard': '1',
            'low': '0.7',
        },
        'multiple',
        RESOLUTION_RESOLVED,
        'SUMMARY!C59 and B74',
        'Quality score maps to a target multiplier. A 0.1 error here moves the '
        'displayed final target by roughly 14 percent.',
    ),
)

#: Stock-type classifier parameters.
PARAMETERS_CLASSIFIER: tuple[tuple[str, str, Any, str, str, str, str], ...] = (
    (
        'classifier_thresholds',
        METHOD_STOCK_TYPE_CLASSIFIER,
        {
            'slow_grower_rev_cagr_max': '0.08',
            'slow_grower_payout_min': '0.2',
            'stalwart_rev_cagr_min': '0.1',
            'stalwart_rev_cagr_max': '0.2',
            'stalwart_roe_min': '0.12',
            'stalwart_defensive_rev_min': '0.05',
            'stalwart_defensive_rev_max': '0.15',
            'rev_cov_max': '0.35',
            'fast_grower_eps_cagr_min': '0.15',
            'fast_grower_rev_cagr_min': '0.2',
            'asset_play_pbv_max': '0.8',
            'asset_play_pbv_percentile_max': '0.2',
        },
        'ratio',
        RESOLUTION_RESOLVED,
        'MetricsClassification!B80 rule set',
        'All thresholds used by the six stock-type rules.',
    ),
    (
        'classifier_score_ladder',
        METHOD_STOCK_TYPE_CLASSIFIER,
        {
            'TURN AROUND': '100',
            'FAST GROWER': '80',
            'CYCLICAL': '60',
            'STALWART': '40',
            'SLOW GROWER': '20',
            'ASSET PLAY': '10',
        },
        'integer_score',
        RESOLUTION_RESOLVED,
        'MetricsClassification!B80 score ladder',
        'Highest matching score wins, so TURN AROUND beats FAST GROWER '
        'regardless of magnitude.',
    ),
    (
        'classifier_energy_override',
        METHOD_STOCK_TYPE_CLASSIFIER,
        'CYCLICAL',
        'text_enum',
        RESOLUTION_RESOLVED,
        'MetricsClassification!B80 IFS(Company_Sector="Energy","CYCLICAL", ...)',
        'Energy always resolves to CYCLICAL, short-circuiting all scoring.',
    ),
    (
        'classifier_cyclical_sectors',
        METHOD_STOCK_TYPE_CLASSIFIER,
        [
            'Energy',
            'Basic Materials',
            'Transportation & Logistic',
            'Properties & Real Estate',
            'Consumer Discretionary',
            'Industrials',
            'Consumer Cyclicals',
        ],
        'text_enum',
        RESOLUTION_RESOLVED,
        'MetricsClassification!B80 IsCyclicalSector',
        'Sector membership for the Cyclical rule.',
    ),
    (
        'classifier_consumer_defensive_sectors',
        METHOD_STOCK_TYPE_CLASSIFIER,
        ['Consumer Non-Cyclicals', 'Utilities', 'Healthcare'],
        'text_enum',
        RESOLUTION_RESOLVED,
        'MetricsClassification!B80 IsConsumerDefensive',
        'Sector membership for the defensive Stalwart branch.',
    ),
    (
        'classifier_confidence_level',
        METHOD_STOCK_TYPE_CLASSIFIER,
        None,
        'ratio',
        RESOLUTION_UNRESOLVED_DEFINITION,
        'MetricsClassification!B83',
        'The confidence-level LET block was only partially extractable. The '
        'displayed AUTO value is 0.7, but the rule is not reproduced here '
        '(blueprint open question Q17).',
    ),
)

#: Strategic target / action-panel parameters.
PARAMETERS_STRATEGIC: tuple[tuple[str, str, Any, str, str, str, str], ...] = (
    (
        'mood_target_multipliers',
        METHOD_STRATEGIC_TARGETS,
        {'BEARISH (Winter)': '0.8', 'NEUTRAL (Spring)': '0.9', 'BULLISH (Summer)': '1'},
        'multiple',
        RESOLUTION_RESOLVED,
        'SUMMARY!B73 IFS',
        'Multiplier applied to the intrinsic-value baseline by market mood.',
    ),
    (
        'mood_default_multiplier',
        METHOD_STRATEGIC_TARGETS,
        '0.9',
        'multiple',
        RESOLUTION_RESOLVED,
        'SUMMARY!B73 IFS(..., TRUE, B72*0.9)',
        'Fallback multiplier when the mood is unrecognised.',
    ),
    (
        'ideal_price_discount',
        METHOD_STRATEGIC_TARGETS,
        '0.7',
        'multiple',
        RESOLUTION_RESOLVED,
        'SUMMARY!B80 (=B72*0.7)',
        'Ideal Price is the intrinsic-value baseline discounted by 30 percent. '
        'It does not depend on Market Mood, so it is replicable without it.',
    ),
    (
        'mos_entry_threshold_workbook',
        METHOD_STRATEGIC_TARGETS,
        '0.35',
        'ratio',
        RESOLUTION_UNRESOLVED_DEFINITION,
        'SUMMARY!C48 ("butuh 35%")',
        'The workbook states a 35 percent MoS entry threshold. The frontend '
        '`backtestMethodology` uses 30 percent. Both are live; the conflict is '
        'unresolved (blueprint open question Q9). Registered, not chosen.',
    ),
    (
        'mos_entry_threshold_frontend',
        METHOD_STRATEGIC_TARGETS,
        '0.3',
        'ratio',
        RESOLUTION_UNRESOLVED_DEFINITION,
        'frontend/src/lib/analysis/backtest.ts classification.mosMainThreshold',
        'Conflicting live threshold. Recorded so the registry shows both sides '
        'of the conflict rather than silently picking one.',
    ),
    (
        'iv_consensus_min_methods',
        METHOD_STRATEGIC_TARGETS,
        '3',
        'count',
        RESOLUTION_RESOLVED,
        'frontend/src/lib/analysis/backtest.ts methodUndervaluedMinimum',
        'Frontend threshold for an UNDERVALUED consensus. Note the workbook '
        'instead divides by the count of VALID methods (open question Q11).',
    ),
    (
        'iv_consensus_denominator_mode',
        METHOD_STRATEGIC_TARGETS,
        'valid_methods',
        'text_enum',
        RESOLUTION_UNRESOLVED_DEFINITION,
        'SUMMARY!B19 (valid denominator) vs backtest.ts (total denominator)',
        'The workbook excludes N/A and error methods from the denominator; the '
        'frontend uses the total. For AUTO both give 5, but they diverge when a '
        'method is skipped (blueprint open question Q11).',
    ),
)

#: Market-mood inputs. These are manual workbook cells with no data source.
PARAMETERS_MARKET_MOOD: tuple[tuple[str, str, Any, str, str, str, str], ...] = (
    (
        'market_mood_ihsg_vs_ma200',
        METHOD_MARKET_MOOD,
        None,
        'text_enum',
        RESOLUTION_UNRESOLVED_SOURCE,
        'SUMMARY!B63 (manual literal "Bearish")',
        'Requires an IHSG index series with a 200-day moving average. Not in '
        'Sectors and not in canonical PostgreSQL.',
    ),
    (
        'market_mood_foreign_flow',
        METHOD_MARKET_MOOD,
        None,
        'text_enum',
        RESOLUTION_UNRESOLVED_SOURCE,
        'SUMMARY!B64 (manual literal "Outflow")',
        'Requires market-wide foreign net buy/sell flow. No source available.',
    ),
    (
        'market_mood_bi_rate',
        METHOD_MARKET_MOOD,
        None,
        'text_enum',
        RESOLUTION_UNRESOLVED_SOURCE,
        'SUMMARY!B65 (manual literal "BI Rate Turun/Tetap")',
        'Requires the Bank Indonesia policy rate and CPI. No source available.',
    ),
    (
        'market_mood_bands',
        METHOD_MARKET_MOOD,
        {'bearish_max_score': '1', 'neutral_score': '2', 'bullish_score': '3'},
        'integer_score',
        RESOLUTION_RESOLVED,
        'SUMMARY!B66 IFS',
        'Vote-count bands. The band rule is known; the votes are not.',
    ),
)

#: Backtest engine parameters (frontend `backtestMethodology`).
PARAMETERS_BACKTEST: tuple[tuple[str, str, Any, str, str, str, str], ...] = (
    (
        'backtest_horizons_months',
        METHOD_BACKTEST_ENGINE,
        ['3', '6', '9', '12'],
        'count',
        RESOLUTION_RESOLVED,
        'frontend/src/lib/analysis/backtest.ts horizonsMonths',
        'Observation horizons for historical evidence.',
    ),
    (
        'backtest_observation_months',
        METHOD_BACKTEST_ENGINE,
        '12',
        'count',
        RESOLUTION_RESOLVED,
        'frontend/src/lib/analysis/backtest.ts observationMonths',
        'Maximum observation window after the analysis date.',
    ),
    (
        'backtest_thresholds_undervalued',
        METHOD_BACKTEST_ENGINE,
        {'upside': '0.2', 'downside': '-0.15'},
        'ratio',
        RESOLUTION_RESOLVED,
        'frontend/src/lib/analysis/backtest.ts undervalued',
        'WIN and RISK thresholds applied to an undervalued case.',
    ),
    (
        'backtest_thresholds_overvalued_or_mixed',
        METHOD_BACKTEST_ENGINE,
        {'upside': '0.15', 'downside': '-0.1'},
        'ratio',
        RESOLUTION_RESOLVED,
        'frontend/src/lib/analysis/backtest.ts overvaluedOrMixed',
        'Thresholds applied to an overvalued or mixed case.',
    ),
    (
        'backtest_generation_rule',
        METHOD_BACKTEST_ENGINE,
        None,
        'expression',
        RESOLUTION_UNRESOLVED_DEFINITION,
        'Backtest_Result sheet contains 0 formula cells',
        'The workbook backtest sheet holds static pasted values with no '
        'generation rule, so the Excel case set cannot be reproduced. The '
        'frontend engine is a separate implementation with different '
        'parameters (blueprint open question Q22).',
    ),
)

#: Fundamental point-in-time configuration gaps.
PARAMETERS_PIT_GAPS: tuple[tuple[str, str, Any, str, str, str, str], ...] = (
    (
        'fundamental_available_date',
        METHOD_AVAILABILITY_REVISION,
        None,
        'text_enum',
        RESOLUTION_MISSING_INPUT,
        'financial_periods.available_date',
        'NULL for all 33 canonical periods. Fundamental point-in-time safety '
        'cannot be enforced until this is populated. Do NOT substitute an '
        'ingestion timestamp: the blueprint forbids it and the test contract '
        'expects a POINT_IN_TIME_UNSAFE flag instead.',
    ),
    (
        'fundamental_report_date',
        METHOD_AVAILABILITY_REVISION,
        None,
        'text_enum',
        RESOLUTION_MISSING_INPUT,
        'financial_periods.report_date',
        'NULL for all 33 canonical periods.',
    ),
    (
        'fundamental_statement_scope',
        METHOD_AVAILABILITY_REVISION,
        None,
        'text_enum',
        RESOLUTION_MISSING_INPUT,
        'financial_periods.statement_scope',
        'UNKNOWN for all 33 canonical periods, so consolidated versus '
        'standalone cannot be verified. The test contract expects a '
        'STATEMENT_SCOPE_UNKNOWN flag.',
    ),
    (
        'quarterly_shares_outstanding',
        METHOD_BALANCE_SHEET_LIQUIDITY,
        None,
        'count',
        RESOLUTION_MISSING_INPUT,
        'financial_facts.OUTSTANDING_SHARES (QUARTER)',
        'OUTSTANDING_SHARES exists only for 7 ANNUAL periods. Mean-Reversion '
        'PBV IV matched Excel exactly only with period-correct quarterly '
        'shares. Blueprint gap G-SHARES-Q, open question Q1.',
    ),
    (
        'price_point_in_time',
        METHOD_VALUATION_INPUTS,
        'last_close_on_or_before_as_of_date',
        'expression',
        RESOLUTION_RESOLVED,
        'prices_daily.trading_date / close_price',
        'Price PIT IS reliable: prices_daily is 100 percent populated and the '
        'seven verified year-end values reconcile exactly.',
    ),
)

#: Every parameter group, in registration order.
PARAMETER_GROUPS: tuple[tuple[str, tuple[tuple[str, str, Any, str, str, str, str], ...]], ...] = (
    ('core_valuation', PARAMETERS),
    ('aggregation_projection', PARAMETERS_AGGREGATION),
    ('health_score', PARAMETERS_HEALTH),
    ('forensic', PARAMETERS_FORENSIC),
    ('business_quality', PARAMETERS_QUALITY),
    ('stock_type_classifier', PARAMETERS_CLASSIFIER),
    ('strategic_targets', PARAMETERS_STRATEGIC),
    ('market_mood', PARAMETERS_MARKET_MOOD),
    ('backtest', PARAMETERS_BACKTEST),
    ('point_in_time_gaps', PARAMETERS_PIT_GAPS),
)


def all_parameters() -> list[tuple[str, str, Any, str, str, str, str]]:
    """Return every parameter definition as one flat list.

    Includes the expanded ``Reference`` lookup tables. Resolution happens at
    call time, so the reference-table group defined further down the module is
    picked up correctly.
    """
    rows: list[tuple[str, str, Any, str, str, str, str]] = []
    for _, group in PARAMETER_GROUPS:
        rows.extend(group)
    rows.extend(PARAMETERS_REFERENCE_TABLES)
    return rows


def parameter_index() -> dict[str, tuple[str, str, Any, str, str, str, str]]:
    """Return ``{parameter_code: definition}``.

    Raises :class:`ValueError` if a parameter code is registered twice, so a
    duplicated code cannot silently shadow another value.
    """
    index: dict[str, tuple[str, str, Any, str, str, str, str]] = {}
    for row in all_parameters():
        code = row[0]
        if code in index:
            raise ValueError(f'DUPLICATE_PARAMETER_CODE: {code}')
        index[code] = row
    return index


def unresolved_parameters() -> list[tuple[str, str, Any, str, str, str, str]]:
    """Return every parameter whose resolution status is not ``RESOLVED``."""
    return [row for row in all_parameters() if row[4] != RESOLUTION_RESOLVED]


# --------------------------------------------------------------------------
# Reference-table expansion
# --------------------------------------------------------------------------

def _expand_reference_tables() -> list[tuple[str, str, Any, str, str, str, str]]:
    """Turn the Excel ``Reference`` tables into one parameter per row.

    Each lookup table becomes a per-key parameter so a weight can be versioned
    and audited individually instead of being buried in one opaque blob.
    """
    rows: list[tuple[str, str, Any, str, str, str, str]] = []

    for sector, weight_pe, weight_pbv in SECTOR_WEIGHTS:
        rows.append(
            (
                'sector_weight:' + sector,
                METHOD_REFERENCE_WEIGHTS,
                {'W_PE': weight_pe, 'W_PBV': weight_pbv},
                'integer_score',
                RESOLUTION_RESOLVED,
                'Reference!B5:C16 (Method_Weights_Sector)',
                f'Sector method weights for {sector}.',
            )
        )

    for stock_type, weight_pe, weight_pbv in TYPE_WEIGHTS:
        rows.append(
            (
                'type_weight:' + stock_type,
                METHOD_REFERENCE_WEIGHTS,
                {'W_PE': weight_pe, 'W_PBV': weight_pbv},
                'integer_score',
                RESOLUTION_RESOLVED,
                'Reference!B22:C26 (Method_Weights_Type)',
                f'Stock-type method weights for {stock_type}.',
            )
        )

    for stock_type, max_der, min_cr in TYPE_THRESHOLDS:
        rows.append(
            (
                'type_threshold:' + stock_type,
                METHOD_REFERENCE_WEIGHTS,
                {'max_der': max_der, 'min_cr': min_cr, 'min_icr': None},
                'multiple',
                RESOLUTION_RESOLVED,
                'Reference!B32:C37 (StockType_Threshold)',
                f'DER/CR thresholds for {stock_type}. `min_icr` is null because '
                'the workbook references a Min ICR column that does not exist.',
            )
        )

    return rows


PARAMETERS_REFERENCE_TABLES: tuple[tuple[str, str, Any, str, str, str, str], ...] = tuple(
    _expand_reference_tables()
)


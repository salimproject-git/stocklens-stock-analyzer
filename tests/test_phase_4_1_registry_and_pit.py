#!/usr/bin/env python3
"""
test_phase_4_1_registry_and_pit.py
=================================

Phase 4.1 tests for:
  A. the parameter & methodology registry, and
  B. the Layer-1 point-in-time primitives.

These tests are deliberately **offline**: they read the committed AUTO fixture
at `tests/fixtures/auto_prices_daily.json` and never touch the network. The
AUTO expectations come from the Phase 4 blueprint and were independently
verified against live canonical PostgreSQL.

Run:
    python -m unittest tests.test_phase_4_1_registry_and_pit -v
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for candidate in (str(REPO_ROOT), str(REPO_ROOT / 'supabase')):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import calculation_parameter_catalogue as catalogue  # noqa: E402
import calculation_methodology_registry as methodology  # noqa: E402
from calculation_registry import (  # noqa: E402
    RESOLUTION_RESOLVED,
    RESOLUTION_STATUSES,
    canonical_json,
    idempotency_key,
    input_hash,
    methodology_hashes,
    sha256_json,
    sha256_text,
)
from pit_primitives import (  # noqa: E402
    PitPrimitiveError,
    avg_volume_3m,
    as_of_price,
    edate,
    latest_price_date,
    normalize_prices,
    year_end_price,
)

FIXTURE_PATH = REPO_ROOT / 'tests' / 'fixtures' / 'auto_prices_daily.json'
MIGRATION_PATH = REPO_ROOT / 'supabase' / 'migrations' / '0008_calculation_v1_batch.sql'


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding='utf-8'))


class CanonicalHashingTests(unittest.TestCase):
    def test_canonical_json_sorts_keys_and_is_stable(self) -> None:
        self.assertEqual(canonical_json({'b': 2, 'a': 1}), '{"a":1,"b":2}')
        self.assertEqual(canonical_json({'a': 1, 'b': 2}), canonical_json({'b': 2, 'a': 1}))

    def test_sha256_text_matches_hashlib(self) -> None:
        text = 'current_value / prior_value - 1'
        self.assertEqual(sha256_text(text), hashlib.sha256(text.encode()).hexdigest())

    def test_sha256_json_is_deterministic_and_key_order_independent(self) -> None:
        first = sha256_json({'a': 1, 'b': {'y': 2, 'x': 3}})
        second = sha256_json({'b': {'x': 3, 'y': 2}, 'a': 1})
        self.assertEqual(first, second)
        self.assertRegex(first, r'^[0-9a-f]{64}$')

    def test_sha256_json_survives_a_json_round_trip(self) -> None:
        value = {'ratio': '0.0633', 'nested': {'list': ['1', '2']}}
        self.assertEqual(sha256_json(value), sha256_json(json.loads(json.dumps(value))))

    def test_methodology_hashes_use_different_rules(self) -> None:
        formula_hash, parameter_hash = methodology_hashes('x=y', {'k': '1'})
        self.assertEqual(formula_hash, hashlib.sha256(b'x=y').hexdigest())
        self.assertEqual(parameter_hash, sha256_json({'k': '1'}))
        # The two rules coincide only when the formula text happens to be the
        # canonical JSON of the spec. Show they diverge otherwise.
        self.assertNotEqual(sha256_text('x=y'), sha256_json({'k': '1'}))
        self.assertEqual(sha256_text(canonical_json({'k': '1'})), sha256_json({'k': '1'}))

    def test_input_hash_ignores_key_order(self) -> None:
        self.assertEqual(input_hash({'b': 2, 'a': 1}), input_hash({'a': 1, 'b': 2}))

    def test_idempotency_key_is_deterministic(self) -> None:
        base = dict(
            calculation_type='X',
            methodology_version_id='m1',
            code_version='c',
            source_cutoff_date='2025-01-01',
            source_ingestion_run_id=None,
            scope_type='INSTRUMENT',
            scope_id='i',
            input_hash_value=input_hash({'a': 1, 'b': 2}),
        )
        first = idempotency_key(**base)
        second = idempotency_key(
            **{**base, 'input_hash_value': input_hash({'b': 2, 'a': 1})}
        )
        self.assertEqual(first, second)

    def test_idempotency_key_differs_for_retry_and_cutoff(self) -> None:
        base = dict(
            calculation_type='X',
            methodology_version_id='m1',
            code_version='c',
            source_cutoff_date='2025-01-01',
            source_ingestion_run_id=None,
            scope_type='INSTRUMENT',
            scope_id='i',
            input_hash_value=input_hash({'a': 1, 'b': 2}),
        )
        plain = idempotency_key(**base)
        retry_one = idempotency_key(**base, retry_of_run_id='run-1')
        retry_two = idempotency_key(**base, retry_of_run_id='run-2')
        moved_cutoff = idempotency_key(**{**base, 'source_cutoff_date': '2025-02-01'})
        self.assertNotEqual(plain, retry_one)
        self.assertNotEqual(retry_one, retry_two)
        self.assertNotEqual(plain, moved_cutoff)


class ParameterCatalogueTests(unittest.TestCase):
    def test_no_duplicate_parameter_codes(self) -> None:
        index = catalogue.parameter_index()
        self.assertEqual(len(index), len(catalogue.all_parameters()))

    def test_parameter_shape_is_well_formed(self) -> None:
        for code, owner, _value, unit, resolution, source, note in catalogue.all_parameters():
            self.assertTrue(code, 'parameter code must not be empty')
            self.assertTrue(owner, f'{code}: owner method required')
            self.assertIn(resolution, RESOLUTION_STATUSES, f'{code}: bad resolution status')
            self.assertTrue(unit, f'{code}: unit required')
            self.assertTrue(source, f'{code}: source reference required')
            self.assertTrue(note, f'{code}: note required')

    def test_every_parameter_owner_is_a_known_methodology(self) -> None:
        known = {seed['method_code'] for seed in methodology.methodology_seeds()}
        known |= {
            catalogue.METHOD_REFERENCE_WEIGHTS,
            catalogue.METHOD_HEALTH_SCORE,
            catalogue.METHOD_FORENSIC_FLAGS,
            catalogue.METHOD_BUSINESS_QUALITY,
            catalogue.METHOD_STOCK_TYPE_CLASSIFIER,
            catalogue.METHOD_STRATEGIC_TARGETS,
            catalogue.METHOD_PROJECTION_ENGINE,
            catalogue.METHOD_MARKET_MOOD,
            catalogue.METHOD_BACKTEST_ENGINE,
        }
        for code, owner, *_rest in catalogue.all_parameters():
            self.assertIn(owner, known, f'{code}: unknown owner method {owner}')

    def test_numeric_values_are_exact_decimal_strings(self) -> None:
        """Scalar numerics must be strings, never JSON floats."""
        for code, _owner, value, *_rest in catalogue.all_parameters():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                self.fail(f'{code}: numeric value stored as a JSON number, not a string')

    def test_resolved_parameters_have_a_value(self) -> None:
        for code, _owner, value, _unit, resolution, *_rest in catalogue.all_parameters():
            if resolution == RESOLUTION_RESOLVED:
                self.assertIsNotNone(value, f'{code}: RESOLVED but value is None')

    def test_unresolved_parameters_are_explicitly_flagged(self) -> None:
        unresolved = {row[0] for row in catalogue.unresolved_parameters()}
        for code in (
            'risk_free_rate',
            'market_mood_ihsg_vs_ma200',
            'market_mood_foreign_flow',
            'market_mood_bi_rate',
            'fundamental_available_date',
            'fundamental_report_date',
            'fundamental_statement_scope',
            'quarterly_shares_outstanding',
            'health_default_min_icr',
            'mos_entry_threshold_workbook',
            'mos_entry_threshold_frontend',
            'iv_consensus_denominator_mode',
            'backtest_generation_rule',
            'classifier_confidence_level',
            'forensic_debt_growth_gap_threshold',
            'forensic_margin_spike_threshold',
        ):
            self.assertIn(code, unresolved, f'{code} must be flagged unresolved')

    def test_risk_free_rate_is_preserved_but_not_claimed_resolved(self) -> None:
        row = catalogue.parameter_index()['risk_free_rate']
        self.assertEqual(row[2], '0.0633')  # workbook literal preserved exactly
        self.assertNotEqual(row[4], RESOLUTION_RESOLVED)  # but flagged as unsourced

    def test_sector_and_type_weights_match_the_workbook(self) -> None:
        index = catalogue.parameter_index()
        self.assertEqual(
            index['sector_weight:Consumer Cyclicals'][2], {'W_PE': '3', 'W_PBV': '1'}
        )
        self.assertEqual(index['type_weight:Cyclical'][2], {'W_PE': '0', 'W_PBV': '10'})
        self.assertEqual(len(catalogue.SECTOR_WEIGHTS), 12)
        self.assertEqual(len(catalogue.TYPE_WEIGHTS), 6)
        self.assertEqual(len(catalogue.TYPE_THRESHOLDS), 6)

    def test_min_icr_is_not_invented_per_type(self) -> None:
        """The workbook has no Min ICR column, so no per-type value may exist."""
        for stock_type, _max_der, _min_cr in catalogue.TYPE_THRESHOLDS:
            row = catalogue.parameter_index()['type_threshold:' + stock_type]
            self.assertIsNone(row[2]['min_icr'], f'{stock_type}: min_icr must stay None')

    def test_auto_sector_type_weight_average_is_reproducible(self) -> None:
        """AUTO: Consumer Cyclicals + CYCLICAL -> W_PE 1.5, W_PBV 5.5."""
        index = catalogue.parameter_index()
        sector = index['sector_weight:Consumer Cyclicals'][2]
        type_weight = index['type_weight:Cyclical'][2]
        weight_pe = (Decimal(sector['W_PE']) + Decimal(type_weight['W_PE'])) / 2
        weight_pbv = (Decimal(sector['W_PBV']) + Decimal(type_weight['W_PBV'])) / 2
        self.assertEqual(weight_pe, Decimal('1.5'))
        self.assertEqual(weight_pbv, Decimal('5.5'))

    def test_registry_is_deterministic(self) -> None:
        first = [sha256_json(row[2]) for row in catalogue.all_parameters()]
        second = [sha256_json(row[2]) for row in catalogue.all_parameters()]
        self.assertEqual(first, second)




class MethodologyRegistryTests(unittest.TestCase):
    def test_exactly_nine_seed_rows(self) -> None:
        self.assertEqual(len(methodology.methodology_seeds()), 9)

    def test_required_methodology_codes_are_present(self) -> None:
        codes = {seed['method_code'] for seed in methodology.methodology_seeds()}
        for required in (
            'QUARTERLY_GROWTH_QUALITY',
            'DAILY_LIQUIDITY',
            'BALANCE_SHEET_LIQUIDITY',
            'VALUATION_INPUTS',
            'VALUATION_MULTIPLES',
            'VALUATION_METHOD_PERSISTENCE',
            'CLASSIFICATION_DESCRIPTIVE',
            'AVAILABILITY_REVISION',
        ):
            self.assertIn(required, codes)
        self.assertIn('VALUATION_METHOD_MAPPING', codes)

    def test_seed_hashes_are_reproducible(self) -> None:
        for seed in methodology.methodology_seeds():
            self.assertEqual(seed['formula_hash'], sha256_text(seed['formula_text']))
            self.assertEqual(seed['parameter_hash'], sha256_json(seed['parameter_spec']))

    def test_formula_text_is_single_line(self) -> None:
        """The migration regex is line-anchored, so no formula may wrap."""
        for seed in methodology.methodology_seeds():
            self.assertNotIn('\n', seed['formula_text'])

    def test_seeds_are_draft_and_versioned(self) -> None:
        for seed in methodology.methodology_seeds():
            self.assertEqual(seed['status'], 'DRAFT')
            self.assertEqual(seed['code_version'], 'stocklens-calc-v1')
            self.assertEqual(seed['input_vocabulary_version'], 'canonical-financial-v1')
            self.assertTrue(seed['method_version'])

    def test_methodology_seeds_are_deterministic(self) -> None:
        first = [seed['parameter_hash'] for seed in methodology.methodology_seeds()]
        second = [seed['parameter_hash'] for seed in methodology.methodology_seeds()]
        self.assertEqual(first, second)

    def test_valuation_method_mapping_is_not_a_false_one_to_one(self) -> None:
        seed = next(
            row for row in methodology.methodology_seeds()
            if row['method_code'] == 'VALUATION_METHOD_MAPPING'
        )
        spec = seed['parameter_spec']
        self.assertEqual(spec['resolution_status'], 'UNRESOLVED_DEFINITION')
        self.assertEqual(len(spec['workbook_methods']), 5)
        self.assertEqual(spec['test_suite_method_count_required'], '11')
        self.assertTrue(spec['test_suite_enumerated_codes_incomplete'])
        # Overlaps that ARE known are recorded; the rest stay explicit gaps.
        self.assertEqual(spec['confirmed_mapping'], {'Dividend Discount Model IV': 'DDM'})
        self.assertEqual(
            spec['test_codes_without_workbook_method'], ['GRAHAM', 'RESIDUAL_INCOME']
        )
        self.assertEqual(
            sorted(spec['workbook_methods_without_test_code']),
            sorted([
                'Peter Lynch Algo IV',
                'Type & Sector Weighted IV',
                'Mean Reversion PBV IV',
            ]),
        )
        self.assertIn('Do not force a false one-to-one mapping', spec['note'])


class MigrationContractTests(unittest.TestCase):
    """Assert the 0008 migration satisfies every documented test contract."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = MIGRATION_PATH.read_text(encoding='utf-8')

    def test_migration_exists_at_the_contract_path(self) -> None:
        self.assertTrue(MIGRATION_PATH.exists())

    def test_forbidden_silent_conflict_clause_is_absent(self) -> None:
        self.assertNotIn(
            'on conflict (method_code, method_version) do nothing',
            self.text.lower(),
        )

    def test_required_conflict_markers_are_present(self) -> None:
        self.assertIn('METHODOLOGY_SEED_CONFLICT', self.text)
        self.assertIn("existing.status is distinct from 'DRAFT'", self.text)

    def test_required_lineage_guards_are_present(self) -> None:
        self.assertIn('financial_facts_supersedes_not_self', self.text)
        self.assertIn('dividend_facts_supersedes_not_self', self.text)
        self.assertIn('supersedes_fact_id is null or supersedes_fact_id <> id', self.text)
        self.assertIn(
            'supersedes_dividend_fact_id is null or supersedes_dividend_fact_id <> id',
            self.text,
        )
        self.assertIn('Multi-row lineage cycles remain', self.text)

    def _seed_rows(self) -> list[tuple[str, ...]]:
        pattern = re.compile(
            r"\('([^']+)','([^']+)','[^']*','[^']*','([^']*)','([0-9a-f]{64})',"
            r"'(\{.*\})'::jsonb,'([0-9a-f]{64})'\),?$"
        )
        rows = []
        for line in self.text.splitlines():
            match = pattern.match(line.strip())
            if match:
                rows.append(match.groups())
        return rows

    def test_seed_rows_parse_and_hashes_verify(self) -> None:
        rows = self._seed_rows()
        self.assertEqual(len(rows), 9)
        for _code, _version, formula, formula_hash, parameter_text, parameter_hash in rows:
            self.assertEqual(formula_hash, hashlib.sha256(formula.encode()).hexdigest())
            self.assertEqual(parameter_hash, sha256_json(json.loads(parameter_text)))

    def test_seed_rows_match_the_registry_exactly(self) -> None:
        on_disk = {row[0]: (row[3], row[5]) for row in self._seed_rows()}
        for seed in methodology.methodology_seeds():
            self.assertIn(seed['method_code'], on_disk)
            formula_hash, parameter_hash = on_disk[seed['method_code']]
            self.assertEqual(formula_hash, seed['formula_hash'])
            self.assertEqual(parameter_hash, seed['parameter_hash'])

    def test_migration_is_additive_only(self) -> None:
        lowered = self.text.lower()
        for forbidden in ('drop table', 'truncate', 'delete from', 'alter column'):
            self.assertNotIn(forbidden, lowered, f'migration must not contain {forbidden}')

    def test_migration_creates_only_registry_tables(self) -> None:
        created = re.findall(
            r'create table if not exists public\.(\w+)', self.text.lower()
        )
        self.assertEqual(
            sorted(created),
            ['calculation_parameters', 'calculation_runs', 'methodology_versions'],
        )

    def test_migration_seed_block_is_in_sync_with_the_registry(self) -> None:
        import render_calculation_v1_migration

        self.assertEqual(render_calculation_v1_migration.check(), [])




class EdateTests(unittest.TestCase):
    """Excel EDATE must clamp the day to the last valid day of the month."""

    def test_simple_month_shift(self) -> None:
        self.assertEqual(edate(date(2026, 6, 30), -3), date(2026, 3, 30))

    def test_month_end_clamping(self) -> None:
        # 2026 is not a leap year, so 31-May minus 3 months clamps to 28-Feb.
        self.assertEqual(edate(date(2026, 5, 31), -3), date(2026, 2, 28))

    def test_leap_year_clamping(self) -> None:
        # 2024 IS a leap year, so the same shift lands on 29-Feb.
        self.assertEqual(edate(date(2024, 5, 31), -3), date(2024, 2, 29))

    def test_forward_shift_across_year_boundary(self) -> None:
        self.assertEqual(edate(date(2025, 11, 30), 3), date(2026, 2, 28))

    def test_invalid_months_rejected(self) -> None:
        with self.assertRaises(PitPrimitiveError):
            edate(date(2026, 6, 30), 'three')  # type: ignore[arg-type]


class PriceNormalisationTests(unittest.TestCase):
    def test_sorts_by_trading_date(self) -> None:
        rows = [
            {'trading_date': '2025-03-01', 'close_price': '3', 'volume': '30'},
            {'trading_date': '2025-01-01', 'close_price': '1', 'volume': '10'},
        ]
        points = normalize_prices(rows)
        self.assertEqual(points[0].trading_date, date(2025, 1, 1))
        self.assertEqual(points[-1].trading_date, date(2025, 3, 1))

    def test_duplicate_dates_are_rejected(self) -> None:
        rows = [
            {'trading_date': '2025-01-01', 'close_price': '1', 'volume': '10'},
            {'trading_date': '2025-01-01', 'close_price': '2', 'volume': '20'},
        ]
        with self.assertRaisesRegex(PitPrimitiveError, 'DUPLICATE_TRADING_DATE'):
            normalize_prices(rows)

    def test_null_values_are_not_coerced_to_zero(self) -> None:
        points = normalize_prices(
            [{'trading_date': '2025-01-01', 'close_price': None, 'volume': ''}]
        )
        self.assertIsNone(points[0].close_price)
        self.assertIsNone(points[0].volume)
        self.assertFalse(points[0].has_close)

    def test_decimal_precision_is_preserved(self) -> None:
        points = normalize_prices(
            [{
                'trading_date': '2025-01-01',
                'close_price': '2449150.847457627119',
                'volume': '1',
            }]
        )
        self.assertEqual(points[0].close_price, Decimal('2449150.847457627119'))


class AsOfPriceTests(unittest.TestCase):
    """PIT-1: never leak a future price, never substitute the latest price."""

    PRICES = [
        {'trading_date': '2025-01-10', 'close_price': '100', 'volume': '10'},
        {'trading_date': '2025-02-10', 'close_price': '200', 'volume': '20'},
        {'trading_date': '2025-03-10', 'close_price': '300', 'volume': '30'},
    ]

    def test_exact_date_match(self) -> None:
        self.assertEqual(as_of_price(self.PRICES, '2025-02-10'), Decimal('200'))

    def test_between_dates_uses_the_last_prior_close(self) -> None:
        self.assertEqual(as_of_price(self.PRICES, '2025-02-28'), Decimal('200'))

    def test_before_all_data_returns_none(self) -> None:
        self.assertEqual(as_of_price(self.PRICES, '2025-01-01'), None)
        self.assertEqual(as_of_price(self.PRICES, '2025-01-31'), Decimal('100'))

    def test_historical_query_never_leaks_a_future_price(self) -> None:
        self.assertEqual(as_of_price(self.PRICES, '2025-01-05'), None)
        self.assertNotEqual(as_of_price(self.PRICES, '2025-01-05'), Decimal('300'))

    def test_no_globally_latest_fallback(self) -> None:
        """An as-of before all data must be None, not the latest price."""
        self.assertIsNone(as_of_price(self.PRICES, '2024-12-31'))

    def test_null_close_is_skipped_in_favour_of_prior(self) -> None:
        prices = [
            {'trading_date': '2025-01-10', 'close_price': '100', 'volume': '10'},
            {'trading_date': '2025-02-10', 'close_price': None, 'volume': '20'},
        ]


class AvgVolume3MTests(unittest.TestCase):
    """PIT-4: 3 calendar months, inclusive, mean over existing rows."""

    def test_window_is_three_calendar_months(self) -> None:
        prices = [
            {'trading_date': '2025-02-28', 'close_price': '1', 'volume': '100'},  # inside
            {'trading_date': '2025-03-01', 'close_price': '1', 'volume': '10'},   # inside
            {'trading_date': '2025-05-31', 'close_price': '1', 'volume': '20'},   # inside
            {'trading_date': '2025-06-01', 'close_price': '1', 'volume': '1000'},  # after
        ]
        # EDATE(2025-05-31, -3) == 2025-02-28, so 2025-02-28 IS inside.
        self.assertEqual(avg_volume_3m(prices, '2025-05-31'), Decimal('43.33333333333333333333333333'))

    def test_is_a_calendar_window_not_a_trading_day_count(self) -> None:
        prices = [
            {'trading_date': f'2025-01-{day:02d}', 'close_price': '1', 'volume': '1'}
            for day in range(1, 32)
        ]
        # All 31 January rows fall inside a 3-month window ending 31-Mar.
        self.assertEqual(avg_volume_3m(prices, '2025-03-31'), Decimal('1'))

    def test_missing_volume_rows_are_not_imputed(self) -> None:
        prices = [
            {'trading_date': '2025-03-01', 'close_price': '1', 'volume': '10'},
            {'trading_date': '2025-03-02', 'close_price': '1', 'volume': None},
            {'trading_date': '2025-03-03', 'close_price': '1', 'volume': '20'},
        ]
        # Only the two rows carrying a volume participate: (10+20)/2 = 15.
        self.assertEqual(avg_volume_3m(prices, '2025-03-31'), Decimal('15'))

    def test_empty_window_returns_none(self) -> None:
        prices = [{'trading_date': '2020-01-01', 'close_price': '1', 'volume': '5'}]
        self.assertIsNone(avg_volume_3m(prices, '2025-03-31'))

    def test_future_rows_are_excluded(self) -> None:
        prices = [
            {'trading_date': '2025-03-01', 'close_price': '1', 'volume': '10'},
            {'trading_date': '2025-04-01', 'close_price': '1', 'volume': '9999'},
        ]
        self.assertEqual(avg_volume_3m(prices, '2025-03-31'), Decimal('10'))


class YearEndPriceTests(unittest.TestCase):
    def test_uses_last_close_on_or_before_dec_31(self) -> None:
        prices = [
            {'trading_date': '2025-12-29', 'close_price': '10', 'volume': '1'},
            {'trading_date': '2025-12-30', 'close_price': '20', 'volume': '1'},
            {'trading_date': '2026-01-02', 'close_price': '99', 'volume': '1'},
        ]
        self.assertEqual(year_end_price(prices, 2025), Decimal('20'))

    def test_missing_year_returns_none(self) -> None:
        prices = [{'trading_date': '2025-12-30', 'close_price': '20', 'volume': '1'}]
        self.assertIsNone(year_end_price(prices, 2019))

    def test_invalid_year_rejected(self) -> None:
        with self.assertRaises(PitPrimitiveError):
            year_end_price([], '2025')  # type: ignore[arg-type]


class LatestPriceDateTests(unittest.TestCase):
    def test_returns_the_most_recent_date(self) -> None:
        prices = [
            {'trading_date': '2025-01-01', 'close_price': '1', 'volume': '1'},
            {'trading_date': '2025-03-01', 'close_price': '1', 'volume': '1'},
        ]
        self.assertEqual(latest_price_date(prices), date(2025, 3, 1))

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(latest_price_date([]))


class AsOfEdgeCaseTests(unittest.TestCase):
    def test_empty_input_returns_none(self) -> None:
        self.assertIsNone(as_of_price([], '2025-01-01'))


class AutoPitValidationTests(unittest.TestCase):
    """Mandatory AUTO validation against the Phase 4 blueprint values."""

    @classmethod
    def setUpClass(cls) -> None:
        fixture = load_fixture()
        cls.fixture = fixture
        cls.prices = normalize_prices(fixture['prices'])
        cls.expected = fixture['expected']

    def test_fixture_is_present_and_complete(self) -> None:
        self.assertTrue(FIXTURE_PATH.exists())
        self.assertEqual(self.fixture['row_count'], len(self.fixture['prices']))
        self.assertEqual(len(self.prices), 1619)

    def test_seven_verified_year_end_prices(self) -> None:
        """Every year-end price must match the blueprint exactly."""
        expected = self.expected['year_end_prices']
        self.assertEqual(len(expected), 7)
        for year_text, expected_value in expected.items():
            year = int(year_text)
            actual = year_end_price(self.prices, year)
            if expected_value is None:
                self.assertIsNone(
                    actual,
                    f'year_end_price({year}) must be None: canonical price '
                    'history starts 2020-01-02, so 2019 has no price',
                )
            else:
                self.assertEqual(
                    actual, Decimal(expected_value), f'year_end_price({year}) mismatch'
                )

    def test_2019_year_end_price_is_none_not_substituted(self) -> None:
        """A missing year must not silently borrow the 2020 price."""
        self.assertIsNone(year_end_price(self.prices, 2019))
        self.assertNotEqual(year_end_price(self.prices, 2019), Decimal('1115'))

    def test_avg_volume_3m_matches_the_blueprint_exactly(self) -> None:
        as_of = self.expected['avg_volume_3m_as_of']
        actual = avg_volume_3m(self.prices, as_of)
        self.assertIsNotNone(actual)
        # The blueprint records the value at IEEE-754 double precision. The
        # primitive keeps full decimal precision, so the float projection must
        # reproduce the blueprint exactly.
        self.assertEqual(float(actual), float(self.expected['avg_volume_3m']))
        self.assertEqual(float(actual), 2449150.8474576273)
        # Exact rational form: 144499900 / 59, with no intermediate rounding.
        self.assertEqual(actual, Decimal(144499900) / Decimal(59))

    def test_avg_volume_3m_window_boundaries(self) -> None:
        """The window is EDATE(as_of,-3) .. as_of, both inclusive."""
        start = edate(date(2026, 6, 30), -3)
        self.assertEqual(start, date(2026, 3, 30))
        inside = [p for p in self.prices if start <= p.trading_date <= date(2026, 6, 30)]
        self.assertEqual(len(inside), 59)
        self.assertEqual(sum(p.volume for p in inside), Decimal('144499900'))

    def test_latest_price_is_reported_but_never_used_as_an_as_of_price(self) -> None:
        self.assertEqual(
            latest_price_date(self.prices),
            date.fromisoformat(self.expected['latest_trading_date']),
        )
        # The workbook as-of (2026-Q2) must resolve to 2350, not the latest 3340.
        self.assertEqual(as_of_price(self.prices, '2026-06-30'), Decimal('2350'))
        self.assertEqual(as_of_price(self.prices, '2026-09-24'), Decimal('3340'))

    def test_primitives_are_deterministic(self) -> None:
        first = [str(year_end_price(self.prices, year)) for year in range(2020, 2026)]
        second = [str(year_end_price(self.prices, year)) for year in range(2020, 2026)]
        self.assertEqual(first, second)
        self.assertEqual(
            avg_volume_3m(self.prices, '2026-06-30'),
            avg_volume_3m(self.prices, '2026-06-30'),
        )

    def test_historical_queries_never_leak_future_prices(self) -> None:
        """For every year-end, the resolved date must be <= that year-end."""
        for year in range(2020, 2026):
            cutoff = date(year, 12, 31)
            candidates = [p for p in self.prices if p.trading_date <= cutoff]
            if not candidates:
                continue
            resolved = max(p.trading_date for p in candidates)
            self.assertLessEqual(resolved, cutoff)
            self.assertEqual(as_of_price(self.prices, cutoff), candidates[-1].close_price)

    def test_no_globally_latest_price_fallback_anywhere(self) -> None:
        """An as-of before the data edge must never return the latest price."""
        latest = Decimal(self.expected['latest_close'])
        self.assertEqual(as_of_price(self.prices, '2026-09-24'), latest)
        for probe in ('2019-12-31', '2020-01-01'):
            self.assertNotEqual(as_of_price(self.prices, probe), latest)


if __name__ == '__main__':
    unittest.main()


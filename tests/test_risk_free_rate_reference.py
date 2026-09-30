"""Offline contract checks for the risk-free-rate reference table and resolver.

The table is the explicit home for the workbook's `DataInput!B11` rate. These
checks pin the migration's safety invariants and the resolver's selection rules
without touching a live database.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'supabase'))

from calculation_v1_common import CalculationError  # noqa: E402
from calculate_valuation import (  # noqa: E402
    REFERENCE_RATE_CODE,
    resolve_risk_free_rate,
)
from valuation_engine import REFERENCE_VERSION  # noqa: E402


MIGRATION = ROOT / 'supabase' / 'migrations' / '0020_risk_free_rate_reference.sql'


class FakeDb:
    """Minimal stand-in for ``SupabaseRest`` returning canned reference rows."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.requests: list[dict[str, str]] = []

    def get_all(self, table: str, params: dict[str, str]) -> list[dict[str, object]]:
        assert table == 'risk_free_rate_reference', table
        self.requests.append(params)
        return list(self.rows)


def workbook_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        'rate': '0.0633',
        'observation_date': None,
        'source_kind': 'WORKBOOK_CONSTANT',
        'source_name': 'Excel workbook DataInput!B11',
        'source_reference': 'DataInput!B11',
        'is_default': True,
    }
    row.update(overrides)
    return row


class RiskFreeRateReferenceMigrationTests(unittest.TestCase):
    """Contract checks for `0020_risk_free_rate_reference.sql`."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = MIGRATION.read_text(encoding='utf-8')
        cls.lower = cls.sql.lower()

    def test_migration_is_transactional(self) -> None:
        self.assertRegex(self.lower, r'(?m)^begin;')
        self.assertRegex(self.lower, r'(?m)^commit;')

    def test_table_is_versioned_dated_and_provenance_bound(self) -> None:
        for column in (
            'reference_version text not null',
            'rate_code text not null',
            'observation_date date',
            'source_kind text not null',
            'source_name text not null',
            'source_reference text not null',
            'is_default boolean not null',
        ):
            self.assertIn(column, self.lower)
        self.assertIn("source_kind in ('workbook_constant', 'market_observation')", self.lower)

    def test_workbook_constant_is_seeded_exactly_once_as_default(self) -> None:
        self.assertIn("('1.0.0', 'sbn_10y_yield', null, 0.0633", self.lower)
        self.assertIn('workbook_constant', self.lower)
        self.assertIn('is_default', self.lower)
        # The workbook literal must be preserved exactly, not rounded.
        self.assertNotIn('0.0634', self.lower)

    def test_reference_table_stays_private_to_service_role(self) -> None:
        self.assertIn(
            'revoke all on table public.risk_free_rate_reference from public, anon, authenticated;',
            self.lower,
        )
        self.assertIn(
            'grant select, insert, update on table public.risk_free_rate_reference to service_role;',
            self.lower,
        )
        self.assertIn('enable row level security', self.lower)

    def test_migration_verifies_invariants_before_commit(self) -> None:
        self.assertIn('risk_free_rate_reference_default_row_invalid', self.lower)
        self.assertIn('risk_free_rate_reference_workbook_value_drift', self.lower)
        self.assertIn('risk_free_rate_reference_must_stay_private', self.lower)
        self.assertLess(self.lower.index('do $verify$'), self.lower.rindex('commit;'))


class ResolveRiskFreeRateTests(unittest.TestCase):
    """Resolver behaviour: newest dated observation wins, else the default row."""

    def test_workbook_constant_is_used_when_no_dated_observation_exists(self) -> None:
        db = FakeDb([workbook_row()])
        rate, source = resolve_risk_free_rate(db)
        self.assertEqual(rate, '0.0633')
        self.assertIn('WORKBOOK_CONSTANT', source)
        self.assertIn('DataInput!B11', source)
        self.assertIn('no observation date recorded', source)

    def test_dated_market_observation_supersedes_the_workbook_constant(self) -> None:
        db = FakeDb([
            workbook_row(),
            {
                'rate': '0.0588',
                'observation_date': '2026-09-25',
                'source_kind': 'MARKET_OBSERVATION',
                'source_name': 'Named market source',
                'source_reference': 'SBN 10Y close 2026-09-25',
                'is_default': False,
            },
        ])
        rate, source = resolve_risk_free_rate(db)
        self.assertEqual(rate, '0.0588')
        self.assertIn('MARKET_OBSERVATION', source)
        self.assertIn('2026-09-25', source)

    def test_query_is_scoped_to_the_active_reference_version_and_rate_code(self) -> None:
        db = FakeDb([workbook_row()])
        resolve_risk_free_rate(db)
        params = db.requests[0]
        self.assertEqual(params['reference_version'], 'eq.' + REFERENCE_VERSION)
        self.assertEqual(params['rate_code'], 'eq.' + REFERENCE_RATE_CODE)
        self.assertEqual(params['order'], 'observation_date.desc.nullslast')

    def test_missing_reference_row_is_a_hard_error(self) -> None:
        with self.assertRaises(CalculationError) as context:
            resolve_risk_free_rate(FakeDb([]))
        self.assertIn('RISK_FREE_RATE_REFERENCE_MISSING', str(context.exception))

    def test_ambiguous_default_rows_are_refused(self) -> None:
        with self.assertRaises(CalculationError) as context:
            resolve_risk_free_rate(FakeDb([workbook_row(), workbook_row()]))
        self.assertIn('RISK_FREE_RATE_REFERENCE_DEFAULT_ROW_INVALID', str(context.exception))

    def test_non_positive_rate_is_refused_instead_of_used(self) -> None:
        with self.assertRaises(CalculationError) as context:
            resolve_risk_free_rate(FakeDb([workbook_row(rate='0')]))
        self.assertIn('RISK_FREE_RATE_REFERENCE_VALUE_INVALID', str(context.exception))

    def test_resolver_never_invents_a_rate_without_a_reference_table(self) -> None:
        # The catalogue still flags risk_free_rate as unresolved, so the only
        # sanctioned path to a rate is this explicit reference lookup.
        with self.assertRaises(CalculationError):
            resolve_risk_free_rate(FakeDb([]))


if __name__ == '__main__':
    unittest.main()

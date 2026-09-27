"""Offline checks for the staged D-08 instrument-master rollout."""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for candidate in (str(ROOT), str(ROOT / 'supabase')):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import cleanup_test_artifacts as cleanup  # noqa: E402
import load_identity_to_supabase as identity  # noqa: E402

MIGRATION = ROOT / 'supabase' / 'migrations' / '0010_instrument_company_information.sql'
BACKFILL = ROOT / 'supabase' / 'backfills' / '0010_instrument_company_information_backfill.sql'
VERSIONED_BACKFILL = ROOT / 'supabase' / 'migrations' / '0011_backfill_instrument_company_information.sql'
CLEANUP_MIGRATION = ROOT / 'supabase' / 'migrations' / '0012_cleanup_legacy_company_information.sql'


class FakeIdentityDb:
    """Small in-memory REST fake; it cannot access a network or database."""

    def __init__(self, *, instruments=None, companies=None, legacy_company_fk=True):
        self.instruments = list(instruments or [])
        self.companies = list(companies or [])
        self.legacy_company_fk = legacy_company_fk
        self.inserted = []
        self.patched = []
        self.read_tables = []
        self.schema_checks = []

    def has_column(self, table: str, column: str) -> bool:
        self.schema_checks.append((table, column))
        if (table, column) != ('instruments', 'company_id'):
            raise AssertionError(f'Unexpected schema check: {table}.{column}')
        return self.legacy_company_fk

    def get(self, table: str, params: dict[str, str]):
        self.read_tables.append(table)
        if table == 'instruments':
            return [row.copy() for row in self.instruments if row['ticker'] == params['ticker'][3:]]
        if table == 'companies':
            provider_identity = params.get('provider_identity')
            company_id = params.get('id')
            return [
                row.copy()
                for row in self.companies
                if (provider_identity is None or row['provider_identity'] == provider_identity[3:])
                and (company_id is None or row['id'] == company_id[3:])
            ]
        raise AssertionError(f'Unexpected table read: {table}')

    def insert(self, table: str, row: dict):
        self.inserted.append((table, row.copy()))
        if table == 'companies':
            stored = {'id': 'company-new', **row}
            self.companies.append(stored)
            return stored.copy()
        if table == 'instruments':
            stored = {'id': 'instrument-new', **row}
            self.instruments.append(stored)
            return stored.copy()
        raise AssertionError(f'Unexpected table insert: {table}')

    def patch(self, table: str, row_id: str, values: dict):
        self.patched.append((table, row_id, values.copy()))
        if table != 'instruments':
            raise AssertionError(f'Unexpected table patch: {table}')
        row = next(row for row in self.instruments if row['id'] == row_id)
        row.update(values)
        return row.copy()


def instrument_row(**overrides):
    row = {
        'id': 'instrument-stable-id',
        'company_id': 'legacy-company-id',
        'exchange_code': 'IDX',
        'ticker': 'AUTO',
        'provider_symbol': 'AUTO.JK',
        'currency_code': 'IDR',
        'company_name': 'Astra Otoparts Tbk',
        'sector_name': 'Consumer Cyclicals',
        'subsector_name': 'Automobiles & Components',
    }
    row.update(overrides)
    return row


def legacy_company():
    return {
        'id': 'legacy-company-id',
        'provider_identity': 'AUTO.JK',
        'legal_name': 'Astra Otoparts Tbk',
    }


class CompanyInformationMigrationTests(unittest.TestCase):
    def test_cleanup_migration_is_separate_guarded_and_never_uses_cascade(self) -> None:
        sql = CLEANUP_MIGRATION.read_text(encoding='utf-8').lower()

        self.assertTrue(sql.startswith('-- 0012_cleanup_legacy_company_information.sql'))
        self.assertIn('do not apply without explicit owner', sql)
        self.assertIn('begin;', sql)
        self.assertIn('commit;', sql)
        self.assertIn('instruments_company_id_fkey', sql)
        self.assertIn('drop column company_id', sql)
        self.assertIn('drop table public.instrument_sector_classifications', sql)
        self.assertIn('drop table public.sectors', sql)
        self.assertIn('drop table public.companies', sql)
        self.assertIn('d08_cleanup_unexpected_foreign_key', sql)
        self.assertIn('d08_cleanup_unexpected_view', sql)
        self.assertIn('d08_cleanup_unexpected_routine', sql)
        self.assertIn('d08_cleanup_unexpected_trigger', sql)
        self.assertNotRegex(sql, r'\bdrop\s+(table|column|constraint)[^;]*\bcascade\b')
        self.assertNotRegex(sql, r'(?im)^\s*(grant|revoke|create\s+policy)\b')

    def test_versioned_backfill_is_guarded_and_preserves_identity_and_permissions(self) -> None:
        sql = VERSIONED_BACKFILL.read_text(encoding='utf-8').lower()

        self.assertTrue(sql.startswith('-- 0011_backfill_instrument_company_information.sql'))
        self.assertIn('begin;', sql)
        self.assertIn('commit;', sql)
        self.assertIn('lock table public.instruments', sql)
        self.assertIn('d08_backfill_company_name_missing', sql)
        self.assertIn('d08_backfill_ambiguous', sql)
        self.assertIn('d08_backfill_company_name_conflict', sql)
        self.assertIn('d08_backfill_sector_conflict', sql)
        self.assertIn('d08_backfill_verification_failed', sql)
        self.assertRegex(sql, r'\bcompany_name\b')
        self.assertIn('sector_name', sql)
        self.assertIn('subsector_name', sql)
        self.assertNotRegex(sql, r'(?im)^\s*drop\s+')
        self.assertNotRegex(sql, r'(?im)^\s*(grant|revoke|create\s+policy|alter\s+table\s+public\.instruments\s+disable\s+row\s+level\s+security)\b')

        update_sql = sql.split('update public.instruments as target', 1)[1].split('\n  from', 1)[0]
        self.assertNotRegex(update_sql, r'(?i)\bid\s*=')
        self.assertNotRegex(update_sql, r'(?i)\bcompany_id\s*=')
        self.assertNotRegex(update_sql, r'(?i)\b(ticker|exchange_code|provider_symbol)\s*=')

    def test_migration_is_additive_and_backfills_from_legacy_relations(self) -> None:
        sql = MIGRATION.read_text(encoding='utf-8').lower()
        backfill = BACKFILL.read_text(encoding='utf-8').lower()
        backfill_executable = re.sub(r'/\*.*?\*/|--[^\n]*', '', backfill, flags=re.DOTALL)

        self.assertIn('add column if not exists company_name text', sql)
        self.assertIn('add column if not exists sector_name text', sql)
        self.assertIn('add column if not exists subsector_name text', sql)
        self.assertNotIn('update public.', sql)
        self.assertNotIn('delete from', sql)
        self.assertNotIn('drop table', sql)
        self.assertNotIn('drop column', sql)
        self.assertNotIn('grant ', sql)
        self.assertNotIn('create policy', sql)
        self.assertNotIn('set not null', sql)
        self.assertIn('legacy companies/sectors/classification', sql)

        self.assertIn('c.legal_name as company_name', backfill)
        self.assertIn('join public.sectors as s on s.id = isc.sector_id', backfill)
        self.assertIn("s.taxonomy = 'sectors_app'", backfill)
        self.assertIn('isc.effective_from <= current_date', backfill)
        self.assertIn('isc.effective_to > current_date', backfill)
        self.assertIn('update public.instruments as target', backfill)
        self.assertNotIn('update public.instruments as target', backfill_executable)
        self.assertIn('d08_backfill_ambiguous', backfill)
        self.assertIn('d08_backfill_sector_conflict', backfill)
        self.assertNotIn('delete from', backfill_executable)
        self.assertNotIn('update public.', backfill_executable)
        self.assertNotIn('drop table', backfill_executable)
        self.assertNotIn('grant ', backfill_executable)
        self.assertNotIn('create policy', backfill_executable)

    def test_cleanup_script_protects_both_legacy_identity_tables(self) -> None:
        self.assertTrue({
            'companies',
            'instruments',
            'sectors',
            'instrument_sector_classifications',
        }.issubset(set(cleanup.CANONICAL_TABLES)))

    def test_backfill_plan_is_not_wrapped_in_implicit_commit(self) -> None:
        sql = BACKFILL.read_text(encoding='utf-8').lower()
        self.assertNotRegex(sql, r'(?m)^\s*(begin|commit|rollback)\s*;')
        self.assertIn('owner approves', sql)
        executable = re.sub(r'/\*.*?\*/|--[^\n]*', '', sql, flags=re.DOTALL)
        self.assertNotRegex(executable, r'\b(update|insert|delete|drop|alter)\s+')
        self.assertIn('select i.id as instrument_id', executable)

    def test_backfill_mapping_copies_only_observed_legacy_values(self) -> None:
        raw = json.loads((ROOT / 'Data' / 'Raw' / 'AUTO' / 'company_report_info.json').read_text(encoding='utf-8'))
        legacy_company = {
            'id': 'legacy-company-id',
            'provider_identity': 'AUTO.JK',
            'legal_name': 'Astra Otoparts Tbk',
        }
        legacy_sector = {
            'id': 'legacy-sector-id',
            'taxonomy': 'SECTORS_APP',
            'sector_name': 'Consumer Cyclicals',
            'subsector_name': 'Automobiles & Components',
        }
        classification = {
            'instrument_id': 'instrument-stable-id',
            'sector_id': 'legacy-sector-id',
            'effective_from': None,
            'effective_to': None,
        }

        overview = raw['overview']
        mapped_from_legacy = {
            'company_name': legacy_company['legal_name'],
            'sector_name': legacy_sector['sector_name'],
            'subsector_name': legacy_sector['subsector_name'],
        }

        self.assertEqual(mapped_from_legacy['company_name'], raw['company_name'])
        self.assertEqual(mapped_from_legacy['sector_name'], overview['sector'])
        self.assertEqual(mapped_from_legacy['subsector_name'], overview['sub_sector'])
        self.assertEqual(classification['instrument_id'], 'instrument-stable-id')
        self.assertIsNone(classification['effective_from'])
        self.assertIsNone(classification['effective_to'])

    def test_schema_does_not_touch_financial_or_price_foreign_keys(self) -> None:
        financials = json.loads((ROOT / 'tests' / 'fixtures' / 'auto_financials.json').read_text(encoding='utf-8'))
        prices = json.loads((ROOT / 'tests' / 'fixtures' / 'auto_prices_daily.json').read_text(encoding='utf-8'))
        instrument_id = '1ca51ed2-22c1-4f15-806a-013acc98fc8e'
        instrument_links = [
            {'instrument_id': instrument_id, 'period_end': period['period_end']}
            for period in financials['periods']
        ] + [
            {'instrument_id': instrument_id, 'trading_date': price['trading_date']}
            for price in prices['prices']
        ]
        self.assertEqual(len(financials['periods']), 33)
        self.assertEqual(len(financials['facts']), 1213)
        self.assertEqual(len(prices['prices']), 1619)

        schema_sql = MIGRATION.read_text(encoding='utf-8').lower()
        base_schema = (ROOT / 'supabase' / 'migrations' / '0001_stocklens_mvp.sql').read_text(encoding='utf-8').lower()
        normalized_base_schema = ' '.join(base_schema.split())
        self.assertRegex(
            normalized_base_schema,
            r'create table if not exists public\.financial_periods \(.*?instrument_id uuid not null references public\.instruments\(id\) on delete cascade',
        )
        self.assertRegex(
            normalized_base_schema,
            r'create table if not exists public\.prices_daily \(.*?instrument_id uuid not null references public\.instruments\(id\) on delete cascade',
        )
        self.assertNotRegex(schema_sql, r'(?m)^\s*alter\s+table\s+public\.(financial_periods|financial_facts|prices_daily)')
        self.assertEqual({row['instrument_id'] for row in instrument_links}, {instrument_id})
        self.assertEqual(sum('period_end' in row for row in instrument_links), 33)
        self.assertIn('where target.id = master_values.instrument_id', BACKFILL.read_text(encoding='utf-8').lower())

    def test_existing_identity_uses_instrument_master_without_legacy_lookup(self) -> None:
        db = FakeIdentityDb(
            instruments=[instrument_row()],
            companies=[legacy_company()],
        )
        values = {
            'provider_identity': 'AUTO.JK',
            'legal_name': 'Astra Otoparts Tbk',
            'company_name': 'Astra Otoparts Tbk',
            'provider_symbol': 'AUTO.JK',
            'sector_name': 'Consumer Cyclicals',
            'subsector_name': 'Automobiles & Components',
        }

        instrument_id, notes = identity.load_identity(db, 'AUTO', values)

        self.assertEqual(instrument_id, 'instrument-stable-id')
        self.assertEqual(db.read_tables[0], 'instruments')
        self.assertNotIn('companies', db.read_tables)
        self.assertNotIn('sectors', db.read_tables)
        self.assertNotIn('instrument_sector_classifications', db.read_tables)
        self.assertEqual(db.inserted, [])
        self.assertEqual(db.patched, [])
        self.assertIn('instrument_master=SKIP', notes)
        self.assertEqual(db.schema_checks, [('instruments', 'company_id')])

    def test_existing_identity_fails_if_required_legacy_company_fk_is_missing(self) -> None:
        db = FakeIdentityDb(instruments=[instrument_row(company_id=None)])
        values = {
            'provider_identity': 'AUTO.JK',
            'legal_name': 'Astra Otoparts Tbk',
            'company_name': 'Astra Otoparts Tbk',
            'provider_symbol': 'AUTO.JK',
            'sector_name': 'Consumer Cyclicals',
            'subsector_name': 'Automobiles & Components',
        }

        with self.assertRaisesRegex(RuntimeError, 'INSTRUMENT_COMPANY_FK_MISSING'):
            identity.load_identity(db, 'AUTO', values)

        self.assertNotIn('companies', db.read_tables)
        self.assertEqual(db.patched, [])
        self.assertEqual(db.inserted, [])

    def test_existing_instrument_only_fills_missing_master_fields(self) -> None:
        db = FakeIdentityDb(
            instruments=[instrument_row(company_name=None, sector_name=None, subsector_name=None)],
            companies=[legacy_company()],
        )
        values = {
            'provider_identity': 'AUTO.JK',
            'legal_name': 'Astra Otoparts Tbk',
            'company_name': 'Astra Otoparts Tbk',
            'provider_symbol': 'AUTO.JK',
            'sector_name': 'Consumer Cyclicals',
            'subsector_name': 'Automobiles & Components',
        }

        instrument_id, notes = identity.load_identity(db, 'AUTO', values)

        self.assertEqual(instrument_id, 'instrument-stable-id')
        self.assertEqual(len(db.patched), 1)
        self.assertEqual(db.patched[0][1], 'instrument-stable-id')
        self.assertEqual(db.patched[0][2], {
            'company_name': 'Astra Otoparts Tbk',
            'sector_name': 'Consumer Cyclicals',
            'subsector_name': 'Automobiles & Components',
        })
        self.assertFalse(any(table in {'sectors', 'instrument_sector_classifications'} for table, _ in db.inserted))
        self.assertIn('instrument_master=PATCH_MISSING_FIELDS', notes)

    def test_new_instrument_after_legacy_fk_cleanup_uses_master_only(self) -> None:
        db = FakeIdentityDb(legacy_company_fk=False)
        values = {
            'provider_identity': 'AUTO.JK',
            'legal_name': 'Astra Otoparts Tbk',
            'company_name': 'Astra Otoparts Tbk',
            'provider_symbol': 'AUTO.JK',
            'sector_name': 'Consumer Cyclicals',
            'subsector_name': 'Automobiles & Components',
        }

        instrument_id, notes = identity.load_identity(db, 'AUTO', values)

        self.assertEqual(instrument_id, 'instrument-new')
        self.assertEqual([table for table, _ in db.inserted], ['instruments'])
        instrument_insert = db.inserted[0][1]
        self.assertNotIn('company_id', instrument_insert)
        self.assertEqual(instrument_insert['company_name'], 'Astra Otoparts Tbk')
        self.assertNotIn('companies', db.read_tables)
        self.assertIn('legacy_company=NOT_REQUIRED(company_id column absent)', notes)

    def test_conflicting_existing_master_value_is_not_overwritten(self) -> None:
        db = FakeIdentityDb(
            instruments=[instrument_row(sector_name='Existing reviewed value')],
            companies=[legacy_company()],
        )
        values = {
            'provider_identity': 'AUTO.JK',
            'legal_name': 'Astra Otoparts Tbk',
            'company_name': 'Astra Otoparts Tbk',
            'provider_symbol': 'AUTO.JK',
            'sector_name': 'Consumer Cyclicals',
            'subsector_name': 'Automobiles & Components',
        }

        with self.assertRaisesRegex(RuntimeError, 'INSTRUMENT_MASTER_VALUE_CONFLICT'):
            identity.load_identity(db, 'AUTO', values)

        self.assertEqual(db.instruments[0]['sector_name'], 'Existing reviewed value')
        self.assertEqual(db.patched, [])

    def test_new_instrument_gets_master_fields_and_does_not_write_sector_lookup(self) -> None:
        db = FakeIdentityDb()
        values = {
            'provider_identity': 'AUTO.JK',
            'legal_name': 'Astra Otoparts Tbk',
            'company_name': 'Astra Otoparts Tbk',
            'provider_symbol': 'AUTO.JK',
            'sector_name': 'Consumer Cyclicals',
            'subsector_name': 'Automobiles & Components',
        }

        instrument_id, _ = identity.load_identity(db, 'AUTO', values)

        self.assertEqual(instrument_id, 'instrument-new')
        instrument_insert = next(row for table, row in db.inserted if table == 'instruments')
        self.assertEqual(instrument_insert['company_name'], 'Astra Otoparts Tbk')
        self.assertEqual(instrument_insert['sector_name'], 'Consumer Cyclicals')
        self.assertEqual(instrument_insert['subsector_name'], 'Automobiles & Components')
        self.assertFalse(any(table in {'sectors', 'instrument_sector_classifications'} for table, _ in db.inserted))

    def test_existing_instrument_primary_key_and_fk_model_are_preserved(self) -> None:
        financial_fixture = json.loads(
            (ROOT / 'tests' / 'fixtures' / 'auto_financials.json').read_text(encoding='utf-8')
        )
        price_fixture = json.loads(
            (ROOT / 'tests' / 'fixtures' / 'auto_prices_daily.json').read_text(encoding='utf-8')
        )
        instrument_id = '1ca51ed2-22c1-4f15-806a-013acc98fc8e'
        period_instrument_links = [instrument_id for _ in financial_fixture['periods']]
        price_records = price_fixture['prices']
        price_instrument_links = [instrument_id for _ in price_records]
        self.assertEqual(len(financial_fixture['periods']), 33)
        self.assertEqual(len(period_instrument_links), 33)
        self.assertEqual(len(price_records), 1619)
        self.assertEqual(set(period_instrument_links), {instrument_id})
        self.assertEqual(set(price_instrument_links), {instrument_id})
        self.assertTrue(all('trading_date' in row for row in price_records))
        backfill_sql = BACKFILL.read_text(encoding='utf-8').lower()

        sql = MIGRATION.read_text(encoding='utf-8').lower()
        self.assertNotIn('drop constraint', sql)
        self.assertNotIn('drop column', sql)
        set_clause = backfill_sql.split('update public.instruments as target', 1)[1].split('from master_values', 1)[0]
        self.assertNotIn('id =', set_clause)
        self.assertNotIn('company_id =', set_clause)


if __name__ == '__main__':
    unittest.main()
"""Loaders must accept the sector shapes the provider actually emits.

Three defects are locked down here, all found by ingesting a bank (BRIS) and a
newer listing (CMRY) for the first time:

1. `load_annual_financials_to_supabase` required balance-sheet fields a bank
   does not report (`inventories`, `current_assets`, `capital_expenditure`,
   `non_current_liabilities`), so BRIS failed with
   `ANNUAL_SOURCE_MISSING_FIELD`.
2. `load_quarterly_financials_to_supabase` compared the raw key set for exact
   equality, so BRIS failed because a bank reports
   `realized_capital_goods_investment` instead of `capital_expenditure`.
3. `load_daily_prices_to_supabase` reported a successful load of zero rows when
   every raw window was an empty array, and `ingest_raw_history` never fetched
   the real history because those empty windows counted as "already downloaded".
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (str(ROOT), str(ROOT / 'supabase')):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import ingest_raw_history as ingest  # noqa: E402
import load_annual_financials_to_supabase as annual  # noqa: E402
import load_daily_prices_to_supabase as daily  # noqa: E402
import load_quarterly_financials_to_supabase as quarterly  # noqa: E402

RAW_AUTO = ROOT / 'Data' / 'Raw' / 'AUTO'


def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


class AnnualSectorShapeTests(unittest.TestCase):
    def test_bank_shaped_payload_loads_with_missing_facts(self) -> None:
        payload = load_json(RAW_AUTO / 'company_report_annual.json')
        rows = payload['financials']['historical_financials']
        for row in rows:
            for field in annual.SECTOR_DEPENDENT_SOURCE_FIELDS:
                row.pop(field, None)

        validated, _ = annual.validate_source(payload, 'AUTO')

        plans = annual.make_fact_plans(validated)
        current_assets = [p for p in plans if p['source_field'] == 'current_assets']
        self.assertEqual(len(current_assets), len(validated))
        self.assertTrue(all(p['value_numeric'] is None for p in current_assets))
        self.assertTrue(all(p['quality_status'] == 'MISSING' for p in current_assets))
        # Fields the provider always reports are still required.
        self.assertTrue(all(p['quality_status'] == 'VALID' for p in plans if p['source_field'] == 'revenue'))

    def test_absent_required_field_still_fails(self) -> None:
        payload = load_json(RAW_AUTO / 'company_report_annual.json')
        payload['financials']['historical_financials'][0].pop('revenue')

        with self.assertRaisesRegex(annual.LoaderError, 'ANNUAL_SOURCE_MISSING_FIELD'):
            annual.validate_source(payload, 'AUTO')

    def test_sector_dependent_fields_are_disjoint_from_required(self) -> None:
        required = set(annual.REQUIRED_SOURCE_FIELDS)
        sector = set(annual.SECTOR_DEPENDENT_SOURCE_FIELDS)
        self.assertEqual(required & sector, set())
        self.assertEqual(
            annual.RAW_MONETARY_FIELDS,
            annual.REQUIRED_SOURCE_FIELDS + annual.SECTOR_DEPENDENT_SOURCE_FIELDS,
        )
        self.assertEqual(
            sector,
            {'inventories', 'current_assets', 'capital_expenditure', 'non_current_liabilities'},
        )


class QuarterlySectorShapeTests(unittest.TestCase):
    def _payload(self):
        return load_json(RAW_AUTO / 'quarterly' / '2024-12-31.json')

    def _date_index(self):
        return quarterly.load_date_index(ROOT / 'Data' / 'Raw', 'AUTO')

    def test_bank_capex_alias_is_tolerated(self) -> None:
        payload = self._payload()
        payload[0].pop('capital_expenditure')
        payload[0]['realized_capital_goods_investment'] = 123

        validated = quarterly.validate_quarterly_record(
            payload, '2024-12-31.json', 'AUTO', '2024-12-31', self._date_index(),
        )

        self.assertNotIn('capital_expenditure', validated)
        self.assertEqual(validated['realized_capital_goods_investment'], 123)

    def test_other_field_mismatch_still_fails(self) -> None:
        payload = self._payload()
        payload[0].pop('revenue')

        with self.assertRaisesRegex(quarterly.LoaderError, 'QUARTERLY_FIELD_MISMATCH'):
            quarterly.validate_quarterly_record(
                payload, '2024-12-31.json', 'AUTO', '2024-12-31', self._date_index(),
            )

    def test_unexpected_extra_field_still_fails(self) -> None:
        payload = self._payload()
        payload[0]['brand_new_provider_field'] = 1

        with self.assertRaisesRegex(quarterly.LoaderError, 'QUARTERLY_FIELD_MISMATCH'):
            quarterly.validate_quarterly_record(
                payload, '2024-12-31.json', 'AUTO', '2024-12-31', self._date_index(),
            )


class _FakeSource:
    """Minimal RawStorageSource stand-in for the daily loader."""

    def __init__(self, payloads: dict[str, object]) -> None:
        self.payloads = payloads

    def names(self, category: str, suffix: str = '.json') -> list[str]:
        return sorted(self.payloads)

    def read(self, category: str, name: str) -> bytes:
        return json.dumps(self.payloads[name]).encode('utf-8')

    def storage_path(self, category: str, name: str) -> str:
        return f'sectors/FAKE/{category}/{name}'


class DailyEmptyWindowTests(unittest.TestCase):
    def test_all_empty_windows_fail_instead_of_reporting_zero_rows(self) -> None:
        source = _FakeSource({
            '2020-01-01_2020-03-30.json': [],
            '2020-03-31_2020-06-28.json': [],
        })

        with self.assertRaisesRegex(RuntimeError, 'NO_DAILY_PRICE_RECORDS'):
            daily.collect_daily_from_storage(source, 'FAKE')

    def test_one_populated_window_is_enough(self) -> None:
        record = {
            'symbol': 'FAKE.JK', 'date': '2020-04-01', 'open': 1, 'high': 1,
            'low': 1, 'close': 1, 'volume': 1, 'market_cap': 1,
        }
        source = _FakeSource({
            '2020-01-01_2020-03-30.json': [],
            '2020-03-31_2020-06-28.json': [record],
        })

        rows, file_count, checksums = daily.collect_daily_from_storage(source, 'FAKE')

        self.assertEqual(list(rows), ['2020-04-01'])
        self.assertEqual(file_count, 2)
        self.assertEqual(len(checksums), 2)


class _FakeStorage:
    """Storage stand-in exposing daily window payloads."""

    def __init__(self, payloads: dict[str, object]) -> None:
        self.payloads = payloads

    def list_page(self, bucket: str, prefix: str, offset: int):
        entries = [
            {'name': name.split('/')[-1], 'id': 'obj-' + name}
            for name in sorted(self.payloads)
            if name.startswith(prefix)
        ]
        return entries[offset:offset + ingest.PAGE_LIMIT]

    def object_info(self, bucket: str, path: str):
        return {'id': 'obj'} if path in self.payloads else None

    def download(self, bucket: str, path: str) -> bytes:
        return json.dumps(self.payloads[path]).encode('utf-8')


class DailyWindowPlanningTests(unittest.TestCase):
    def test_empty_legacy_windows_do_not_suppress_the_default_range(self) -> None:
        storage = _FakeStorage({
            'sectors/FAKE/daily/2020-01-01_2020-03-30.json': [],
            'sectors/FAKE/daily/2020-03-31_2020-06-28.json': [],
        })
        with tempfile.TemporaryDirectory() as temp:
            names = ingest.daily_window_names(
                'FAKE', Path(temp), storage, include_default_range=True
            )

        # The default 90-day tiling from DEFAULT_MIN_DATE to today, not just the
        # two empty windows. The first default window happens to carry the same
        # name as the first legacy empty window - the tiling is identical.
        self.assertEqual(names, sorted(ingest._default_daily_windows()))
        self.assertGreater(len(names), 2)

    def test_real_windows_are_kept_and_no_default_range_is_added(self) -> None:
        record = {
            'symbol': 'FAKE.JK', 'date': '2020-04-01', 'open': 1, 'high': 1,
            'low': 1, 'close': 1, 'volume': 1, 'market_cap': 1,
        }
        storage = _FakeStorage({'sectors/FAKE/daily/2020-03-31_2020-06-28.json': [record]})
        with tempfile.TemporaryDirectory() as temp:
            names = ingest.daily_window_names(
                'FAKE', Path(temp), storage, include_default_range=True
            )

        self.assertEqual(names, ['2020-03-31_2020-06-28.json'])


class IngestExitStatusTests(unittest.TestCase):
    def test_failed_fetches_fail_the_step(self) -> None:
        # `STEP OK: ingest-raw` was printed while 24 of 28 daily windows had been
        # rejected by the API, so the next step failed far from the real cause.
        source = (ROOT / 'supabase' / 'ingest_raw_history.py').read_text(encoding='utf-8')
        self.assertIn('RAW_INGEST_INCOMPLETE', source)
        self.assertIn('if counters.failed:', source)


if __name__ == '__main__':
    unittest.main()

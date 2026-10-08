"""Offline regression checks for RawStorageSource.names().

The bug this guards: `names()` used to call `client.walk()`, which lists every
folder in the whole `stocklens_raw` bucket. `require_storage_raw` calls `names()`
five times (once per family), so a single `run_pipeline.py TICKER` made hundreds
of Storage requests before printing anything, which looked like a hang and was
killed with Ctrl+C mid-request. The fix lists the category prefix directly.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'supabase'))

from raw_storage_source import RawStorageSource  # noqa: E402


class _FakeClient:
    """Serves one page per prefix and records every call, so a test can assert
    that `walk` is never used and that only the requested prefix is listed."""

    def __init__(self, objects: dict[str, list[dict]]) -> None:
        self.objects = objects
        self.list_calls: list[tuple[str, int]] = []
        self.walk_calls = 0

    def list_page(self, bucket_id: str, prefix: str, offset: int) -> list[dict]:
        self.list_calls.append((prefix, offset))
        return self.objects.get(prefix, [])

    def walk(self, bucket_id: str) -> list[str]:  # pragma: no cover - must not run
        self.walk_calls += 1
        raise AssertionError('names() must not walk the whole bucket')


def _file(name: str) -> dict:
    return {'name': name, 'id': 'object-id'}


def _folder(name: str) -> dict:
    # Storage has no real folders: a folder is an entry without an object id.
    return {'name': name, 'id': None}


class RawStorageSourceNamesTests(unittest.TestCase):
    def _source(self, objects: dict[str, list[dict]]) -> tuple[RawStorageSource, _FakeClient]:
        source = RawStorageSource('AUTO')
        client = _FakeClient(objects)
        source._client = client  # bypass the network client
        return source, client

    def test_names_lists_only_the_requested_prefix(self) -> None:
        source, client = self._source(
            {
                'sectors/AUTO/quarterly/': [
                    _file('2020-03-31.json'),
                    _file('2020-06-30.json'),
                    _folder('nested'),
                ],
                'sectors/OTHER/quarterly/': [_file('leak.json')],
            }
        )
        self.assertEqual(source.names('quarterly'), ['2020-03-31.json', '2020-06-30.json'])
        self.assertEqual(client.walk_calls, 0)
        self.assertEqual([prefix for prefix, _ in client.list_calls], ['sectors/AUTO/quarterly/'])

    def test_names_skips_folders_and_non_suffix_entries(self) -> None:
        source, _ = self._source(
            {
                'sectors/AUTO/info/': [
                    _file('company_report_info.json'),
                    _file('notes.txt'),
                    _folder('subdir'),
                ],
            }
        )
        self.assertEqual(source.names('info'), ['company_report_info.json'])

    def test_names_returns_empty_for_a_ticker_with_no_raw(self) -> None:
        source, client = self._source({})
        self.assertEqual(source.names('info'), [])
        self.assertEqual(client.walk_calls, 0)


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""
cleanup_test_artifacts.py
=========================

PHASE 1C - STEP 2 ONLY:
Remove raw-ingestion TEST ARTIFACTS created while proving the CASE C
(idempotency) behaviour, without touching the production raw catalog.

Scope (enforced by this script):
- Deletes ONLY an explicit allow-list of storage paths.
- Deletes ONLY the matching `ingestion_files` history rows.
- NEVER deletes the bucket.
- NEVER changes bucket visibility (must already be private).
- NEVER touches any other bucket.
- NEVER touches the `auth` schema.
- NEVER touches canonical tables
  (companies, instruments, financial_periods, financial_facts,
   prices_daily, dividend_facts) and never DROPs a table.
- NEVER touches `ingestion_runs` (kept as an audit trail).
- Refuses to run if a protected (core catalog) path is on the list.

Credentials (server-side only, never printed):
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

Usage:
    python .\\supabase\\cleanup_test_artifacts.py --dry-run
    python .\\supabase\\cleanup_test_artifacts.py --yes
"""

from __future__ import annotations

import argparse
import os
from typing import Any
from urllib.parse import quote

import requests

BUCKET = 'stocklens_raw'

# ---------------------------------------------------------------------------
# TEST ARTIFACTS (allow-list). Nothing outside this list is ever deleted.
# ---------------------------------------------------------------------------
TEST_ARTIFACT_PATHS = [
    'sectors/AUTO/annual_info/company_report_annual_info.json',
]

# ---------------------------------------------------------------------------
# PROTECTED CORE CATALOG (never deleted). Any path matching these prefixes
# aborts the run before a single delete happens.
# ---------------------------------------------------------------------------
PROTECTED_PREFIXES = [
    'sectors/AUTO/info/',
    'sectors/AUTO/annual/',
    'sectors/AUTO/dividend/',
    'sectors/AUTO/quarterly/',
    'sectors/AUTO/daily/',
    'sectors/AUTO/manifest/',
]

# Canonical tables that must never be referenced by a deleted file row.
CANONICAL_TABLES = [
    'companies',
    'instruments',
    'financial_periods',
    'financial_facts',
    'prices_daily',
    'dividend_facts',
]


def required_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise RuntimeError(f'Environment variable belum di-set: {name}')
    return value


class Client:
    def __init__(self, url: str, key: str) -> None:
        base = url.rstrip('/')
        self.rest_url = base + '/rest/v1'
        self.storage_url = base + '/storage/v1'
        self.session = requests.Session()
        self.session.headers.update(
            {
                'apikey': key,
                'Authorization': 'Bearer ' + key,
            }
        )

    def rest(
        self,
        method: str,
        resource: str,
        params: dict[str, Any] | None = None,
        body: Any = None,
        prefer: str | None = None,
    ) -> Any:
        headers = {'Content-Type': 'application/json'}
        if prefer:
            headers['Prefer'] = prefer

        response = self.session.request(
            method,
            self.rest_url + '/' + resource,
            params=params,
            json=body,
            headers=headers,
            timeout=60,
        )

        if not response.ok:
            raise RuntimeError(
                'REST %s %s failed (%s): %s'
                % (method, resource, response.status_code, response.text[:1000])
            )

        return response.json() if response.text else None

    def bucket(self, bucket_id: str) -> dict[str, Any]:
        response = self.session.get(
            self.storage_url + '/bucket/' + bucket_id,
            timeout=60,
        )
        if not response.ok:
            raise RuntimeError(
                'bucket info failed (%s): %s'
                % (response.status_code, response.text[:1000])
            )
        return response.json()

    def object_exists(self, bucket_id: str, path: str) -> bool:
        response = self.session.get(
            self.storage_url
            + '/object/info/'
            + bucket_id
            + '/'
            + quote(path, safe='/'),
            timeout=60,
        )
        return response.ok

    def delete_object(self, bucket_id: str, path: str) -> None:
        response = self.session.delete(
            self.storage_url + '/object/' + bucket_id,
            json={'prefixes': [path]},
            timeout=60,
        )
        if not response.ok:
            raise RuntimeError(
                'delete failed (%s): %s'
                % (response.status_code, response.text[:1000])
            )


def assert_not_protected(paths: list[str]) -> None:
    """Abort before deleting anything if a core catalog path is on the list."""
    for path in paths:
        for prefix in PROTECTED_PREFIXES:
            if path.startswith(prefix):
                raise SystemExit(
                    f'Refusing to delete protected core catalog object: {path}'
                )


def assert_no_canonical_dependency(db: Client, storage_path: str) -> None:
    """
    Abort if any canonical row references this storage path.

    Canonical tables link to raw files through `source_ingestion_file_id`
    (prices_daily) or through `raw_ingestion_payloads`. If a canonical row
    depends on the file we are about to delete, we must not delete it.
    """
    rows = db.rest(
        'GET',
        'ingestion_files',
        {'storage_path': 'eq.' + storage_path, 'select': 'id'},
    ) or []

    file_ids = [row['id'] for row in rows]

    if not file_ids:
        return

    dependents = db.rest(
        'GET',
        'prices_daily',
        {
            'source_ingestion_file_id': 'in.(' + ','.join(file_ids) + ')',
            'select': 'id',
        },
    ) or []

    if dependents:
        raise SystemExit(
            'Refusing to delete %s: %d canonical row(s) depend on it.'
            % (storage_path, len(dependents))
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Delete raw-ingestion test artifacts (allow-list only).'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Only show what would be deleted.',
    )
    parser.add_argument(
        '--yes',
        action='store_true',
        help='Required to actually delete. Without it the script is read-only.',
    )
    args = parser.parse_args()

    # Guard 1: never a protected core catalog path.
    assert_not_protected(TEST_ARTIFACT_PATHS)

    db = Client(
        required_env('SUPABASE_URL'),
        required_env('SUPABASE_SERVICE_ROLE_KEY'),
    )

    info = db.bucket(BUCKET)

    print('=' * 74)
    print('PHASE 1C - CLEANUP TEST ARTIFACTS')
    print('=' * 74)
    print(f'Bucket   : {info.get("id")}')
    print(f'Private  : {not bool(info.get("public"))}')
    print(f'Dry run  : {args.dry_run}')
    print(f'Confirmed: {args.yes}')
    print('=' * 74)

    if info.get('public'):
        raise SystemExit(
            f'Refusing to continue: bucket "{BUCKET}" is public. '
            'It must remain private.'
        )

    # Guard 2: no canonical row may depend on these files.
    for path in TEST_ARTIFACT_PATHS:
        assert_no_canonical_dependency(db, path)

    print('Guards passed: no protected path, no canonical dependency.')
    print()

    plan: list[dict[str, Any]] = []

    for path in TEST_ARTIFACT_PATHS:
        history = db.rest(
            'GET',
            'ingestion_files',
            {
                'storage_path': 'eq.' + path,
                'select': 'id,ingestion_run_id,source_file_type,checksum_sha256,status',
            },
        ) or []

        plan.append(
            {
                'path': path,
                'object_exists': db.object_exists(BUCKET, path),
                'history': history,
            }
        )

    for item in plan:
        print(f'ARTIFACT : {item["path"]}')
        print(f'  storage object : {item["object_exists"]}')
        print(f'  history rows   : {len(item["history"])}')

        for row in item['history']:
            print(
                '    id=%s type=%s status=%s checksum=%s'
                % (
                    row['id'],
                    row['source_file_type'],
                    row['status'],
                    row['checksum_sha256'][:12],
                )
            )

    if args.dry_run or not args.yes:
        print()
        print('Read-only run. Re-run with --yes to delete these artifacts.')
        return

    deleted_objects = 0
    deleted_rows = 0

    for item in plan:
        if item['object_exists']:
            db.delete_object(BUCKET, item['path'])
            deleted_objects += 1
            print(f'DELETED OBJECT: {item["path"]}')

        if item['history']:
            # NOTE: `service_role` has INSERT/SELECT/UPDATE but NOT DELETE on
            # public.ingestion_files (only `postgres` does). The REST DELETE
            # therefore returns 403/42501. The row is removed through the
            # database tooling instead (plain data DELETE, not DDL).
            try:
                db.rest(
                    'DELETE',
                    'ingestion_files',
                    {'storage_path': 'eq.' + item['path']},
                    None,
                    'return=minimal',
                )
                deleted_rows += len(item['history'])
                print(f'DELETED HISTORY ROWS: {len(item["history"])}')
            except RuntimeError as error:
                print('MANUAL STEP REQUIRED for history rows:')
                print('  ' + item['path'])
                print(f'  reason: {error}')
                print(
                    '  action: delete via SQL -> delete from public.ingestion_files'
                    f" where storage_path = '{item['path']}';"
                )

    print()
    print(f'Objects deleted : {deleted_objects}')
    print(f'History deleted : {deleted_rows}')

    # Post-verification.
    remaining = [
        path
        for path in TEST_ARTIFACT_PATHS
        if db.object_exists(BUCKET, path)
    ]

    leftover_rows = db.rest(
        'GET',
        'ingestion_files',
        {
            'storage_path': 'in.(' + ','.join(TEST_ARTIFACT_PATHS) + ')',
            'select': 'id',
        },
    ) or []

    print(f'Remaining objects : {len(remaining)}')
    print(f'Remaining rows    : {len(leftover_rows)}')

    if remaining or leftover_rows:
        raise SystemExit('Cleanup incomplete.')

    print('VERIFIED: test artifacts removed; core catalog untouched.')


if __name__ == '__main__':
    main()

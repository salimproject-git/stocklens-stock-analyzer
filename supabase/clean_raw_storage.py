#!/usr/bin/env python3
"""
clean_raw_storage.py
====================

STEP 2 ONLY:
Delete every object currently inside the private `stocklens_raw` bucket.

Safety rules (enforced by this script):
- NEVER deletes the bucket itself.
- NEVER changes bucket visibility; the bucket must already be private.
- NEVER touches any other bucket.
- NEVER touches the `auth` schema.
- NEVER touches canonical PostgreSQL tables.

The Storage API is used instead of raw SQL so the object store and the
`storage.objects` metadata stay consistent (no orphaned files).

Credentials (server-side only):
    Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY as environment variables.

PowerShell:
    $env:SUPABASE_URL='https://YOUR_PROJECT_REF.supabase.co'
    $env:SUPABASE_SERVICE_ROLE_KEY='YOUR_SERVICE_ROLE_KEY'

Usage:
    python .\\supabase\\clean_raw_storage.py --dry-run
    python .\\supabase\\clean_raw_storage.py --yes
"""

from __future__ import annotations

import argparse
import os
from typing import Any

import requests

BUCKET = 'stocklens_raw'

# Storage list endpoint page size.
PAGE_LIMIT = 1000

# Storage bulk delete accepts up to 1000 prefixes per request.
DELETE_BATCH = 100


def required_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise RuntimeError(f'Environment variable belum di-set: {name}')
    return value


class StorageClient:
    def __init__(self, url: str, key: str) -> None:
        self.storage_url = url.rstrip('/') + '/storage/v1'
        self.session = requests.Session()
        self.session.headers.update(
            {
                'apikey': key,
                'Authorization': 'Bearer ' + key,
            }
        )

    def _handle(self, response: requests.Response, action: str) -> Any:
        if not response.ok:
            raise RuntimeError(
                '%s failed (%s): %s'
                % (action, response.status_code, response.text[:1000])
            )
        return response.json() if response.text else None

    def bucket(self, bucket_id: str) -> dict[str, Any]:
        response = self.session.get(
            self.storage_url + '/bucket/' + bucket_id,
            timeout=60,
        )
        return self._handle(response, 'bucket info')

    def list_page(
        self,
        bucket_id: str,
        prefix: str,
        offset: int,
    ) -> list[dict[str, Any]]:
        response = self.session.post(
            self.storage_url + '/object/list/' + bucket_id,
            json={
                'prefix': prefix,
                'limit': PAGE_LIMIT,
                'offset': offset,
                'sortBy': {'column': 'name', 'order': 'asc'},
            },
            timeout=60,
        )
        return self._handle(response, 'list') or []

    def walk(self, bucket_id: str) -> list[str]:
        """Return every object key (files only, not folders) in the bucket."""
        objects: list[str] = []
        pending = ['']

        while pending:
            prefix = pending.pop()

            offset = 0
            while True:
                page = self.list_page(bucket_id, prefix, offset)

                for entry in page:
                    name = entry.get('name')
                    if not name:
                        continue

                    full = f'{prefix}/{name}' if prefix else name

                    # Storage has no real folders: a folder is an entry
                    # without an object id.
                    if entry.get('id') is None:
                        pending.append(full)
                    else:
                        objects.append(full)

                if len(page) < PAGE_LIMIT:
                    break

                offset += PAGE_LIMIT

        return sorted(objects)

    def delete_objects(self, bucket_id: str, paths: list[str]) -> None:
        for start in range(0, len(paths), DELETE_BATCH):
            chunk = paths[start:start + DELETE_BATCH]
            response = self.session.delete(
                self.storage_url + '/object/' + bucket_id,
                json={'prefixes': chunk},
                timeout=120,
            )
            self._handle(response, 'delete')


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Delete every object in a private Supabase Storage bucket.'
    )
    parser.add_argument(
        '--bucket',
        default=BUCKET,
        help=f'Bucket to clean (default: {BUCKET})',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Only list what would be deleted.',
    )
    parser.add_argument(
        '--yes',
        action='store_true',
        help='Required to actually delete. Without it the script is read-only.',
    )
    args = parser.parse_args()

    bucket_id = args.bucket

    # Guard: this script is scoped to the raw ingestion bucket only.
    if bucket_id != BUCKET:
        raise SystemExit(
            f'Refusing to clean bucket "{bucket_id}". '
            f'This script is scoped to "{BUCKET}".'
        )

    db = StorageClient(
        required_env('SUPABASE_URL'),
        required_env('SUPABASE_SERVICE_ROLE_KEY'),
    )

    info = db.bucket(bucket_id)

    print('=' * 72)
    print('CLEAN RAW STORAGE - STEP 2')
    print('=' * 72)
    print(f'Bucket   : {info.get("id")}')
    print(f'Private  : {not bool(info.get("public"))}')
    print(f'Mime     : {info.get("allowed_mime_types")}')
    print(f'Dry run  : {args.dry_run}')
    print(f'Confirmed: {args.yes}')
    print('=' * 72)

    if info.get('public'):
        raise SystemExit(
            f'Refusing to continue: bucket "{bucket_id}" is public. '
            'It must remain private.'
        )

    objects = db.walk(bucket_id)

    print(f'Object count BEFORE : {len(objects)}')

    for path in objects[:10]:
        print(f'  - {path}')

    if len(objects) > 10:
        print(f'  ... and {len(objects) - 10} more')

    if not objects:
        print('Nothing to delete. Object count is already 0.')
        return

    if args.dry_run or not args.yes:
        print()
        print('Read-only run. Re-run with --yes to delete these objects.')
        return

    db.delete_objects(bucket_id, objects)

    remaining = db.walk(bucket_id)

    print()
    print(f'Deleted             : {len(objects)}')
    print(f'Object count AFTER  : {len(remaining)}')

    if remaining:
        raise SystemExit('Cleanup incomplete; objects remain.')

    print('VERIFIED: bucket is empty.')


if __name__ == '__main__':
    main()


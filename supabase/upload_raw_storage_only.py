#!/usr/bin/env python3
"""
upload_raw_storage_only.py
==========================

STEP 3 ONLY (raw ingestion proof):
Upload local `Data\\Raw\\{TICKER}` JSON files into the private
`stocklens_raw` Storage bucket.

This uploader is Storage-only by design:
- NEVER writes to PostgreSQL (no `ingestion_runs`, no `ingestion_files`,
  no canonical tables).
- NEVER creates canonical records and never converts anything.
- Uploads the local file bytes AS-IS (no transformation, no re-serialisation).
- NEVER deletes objects and NEVER overwrites an existing object.
- NEVER changes bucket visibility; the bucket must already be private.
- Refuses to run against any bucket other than `stocklens_raw`.

Storage path convention is imported from the canonical uploader so later
steps see exactly the same paths:

    sectors/{TICKER}/{category}/{file}

Credentials (server-side only):
    Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY as environment variables.

PowerShell:
    $env:SUPABASE_URL='https://YOUR_PROJECT_REF.supabase.co'
    $env:SUPABASE_SERVICE_ROLE_KEY='YOUR_SERVICE_ROLE_KEY'

Usage:
    python .\\supabase\\upload_raw_storage_only.py AUTO --dry-run
    python .\\supabase\\upload_raw_storage_only.py AUTO --yes
    python .\\supabase\\upload_raw_storage_only.py AUTO --yes --verify
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from upload_raw_to_supabase_storage import (
    BUCKET,
    DEFAULT_RAW_ROOT,
    discover_files,
)

# Storage list endpoint page size.
PAGE_LIMIT = 1000


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

    def object_info(self, bucket_id: str, path: str) -> dict[str, Any] | None:
        """Return object metadata, or None when the object does not exist."""
        response = self.session.get(
            self.storage_url
            + '/object/info/'
            + bucket_id
            + '/'
            + quote(path, safe='/'),
            timeout=60,
        )

        if response.ok:
            return response.json()

        try:
            payload = response.json()
        except ValueError:
            payload = {}

        if payload.get('code') == 'NoSuchBucket':
            raise RuntimeError('Storage bucket missing: ' + bucket_id)

        if response.status_code in {401, 403}:
            raise RuntimeError(
                'Storage permission/authentication failure (%s): %s'
                % (response.status_code, response.text[:1000])
            )

        if response.status_code == 404 or payload.get('code') == 'NoSuchKey':
            return None

        raise RuntimeError(
            'Storage info failed (%s): %s'
            % (response.status_code, response.text[:1000])
        )

    def upload(self, bucket_id: str, path: str, content: bytes) -> None:
        response = self.session.post(
            self.storage_url
            + '/object/'
            + bucket_id
            + '/'
            + quote(path, safe='/'),
            headers={
                'Content-Type': 'application/json',
                'x-upsert': 'false',
            },
            data=content,
            timeout=120,
        )
        self._handle(response, 'upload')

    def download(self, bucket_id: str, path: str) -> bytes:
        response = self.session.get(
            self.storage_url
            + '/object/'
            + bucket_id
            + '/'
            + quote(path, safe='/'),
            timeout=120,
        )
        if not response.ok:
            raise RuntimeError(
                'download failed (%s): %s'
                % (response.status_code, response.text[:1000])
            )
        return response.content

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Upload local Data/Raw JSON to private Storage only (no PostgreSQL).'
    )
    parser.add_argument('ticker', help='IDX ticker, e.g. AUTO')
    parser.add_argument(
        '--raw-root',
        default=str(DEFAULT_RAW_ROOT),
        help=f'Raw data root (default: {DEFAULT_RAW_ROOT})',
    )
    parser.add_argument(
        '--bucket',
        default=BUCKET,
        help=f'Bucket to upload to (default: {BUCKET})',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Only list what would be uploaded.',
    )
    parser.add_argument(
        '--yes',
        action='store_true',
        help='Required to actually upload. Without it the script is read-only.',
    )
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Download every object back and compare its SHA-256 checksum.',
    )
    args = parser.parse_args()

    bucket_id = args.bucket

    # Guard: this script is scoped to the raw ingestion bucket only.
    if bucket_id != BUCKET:
        raise SystemExit(
            f'Refusing to upload to bucket "{bucket_id}". '
            f'This script is scoped to "{BUCKET}".'
        )

    ticker = args.ticker.upper().replace('.JK', '')

    items = discover_files(Path(args.raw_root), ticker)

    db = StorageClient(
        required_env('SUPABASE_URL'),
        required_env('SUPABASE_SERVICE_ROLE_KEY'),
    )

    info = db.bucket(bucket_id)

    print('=' * 72)
    print('UPLOAD RAW -> SUPABASE STORAGE (STORAGE-ONLY, STEP 3)')
    print('=' * 72)
    print(f'Ticker   : {ticker}')
    print(f'Raw root : {args.raw_root}')
    print(f'Bucket   : {info.get("id")}')
    print(f'Private  : {not bool(info.get("public"))}')
    print(f'Dry run  : {args.dry_run}')
    print(f'Confirmed: {args.yes}')
    print('=' * 72)

    if info.get('public'):
        raise SystemExit(
            f'Refusing to continue: bucket "{bucket_id}" is public. '
            'It must remain private.'
        )

    before = db.walk(bucket_id)

    print(f'Object count BEFORE : {len(before)}')
    print()
    print(f'Local JSON files    : {len(items)}')

    for item in items:
        print(
            '  %-9s %-12s %8d bytes  %s'
            % (
                item['source_file_type'],
                item['checksum'][:12],
                len(item['content']),
                item['storage_path'],
            )
        )

    if args.dry_run or not args.yes:
        print()
        print('Read-only run. Re-run with --yes to upload these objects.')
        return

    counts = {'UPLOAD': 0, 'SKIP': 0}

    print()

    for item in items:
        existing = db.object_info(bucket_id, item['storage_path'])

        if existing is not None:
            counts['SKIP'] += 1
            print('SKIP (exists, not overwritten): ' + item['storage_path'])
            continue

        db.upload(bucket_id, item['storage_path'], item['content'])
        counts['UPLOAD'] += 1
        print('UPLOAD: ' + item['storage_path'])

    after = db.walk(bucket_id)

    print()
    print(f'Uploaded            : {counts["UPLOAD"]}')
    print(f'Skipped             : {counts["SKIP"]}')
    print(f'Object count AFTER  : {len(after)}')

    expected = len(before) + counts['UPLOAD']

    if len(after) != expected:
        raise SystemExit(
            f'Storage verification failed: expected {expected} objects, '
            f'found {len(after)}.'
        )

    print('VERIFIED: object count matches upload result.')

    if args.verify:
        print()
        print('Checksum verification (download back + SHA-256 compare):')

        mismatched = 0

        for item in items:
            downloaded = db.download(bucket_id, item['storage_path'])
            remote_checksum = hashlib.sha256(downloaded).hexdigest()

            if remote_checksum != item['checksum']:
                mismatched += 1
                print('  MISMATCH: ' + item['storage_path'])
            else:
                print(
                    '  OK  %s  %s'
                    % (remote_checksum[:12], item['storage_path'])
                )

        if mismatched:
            raise SystemExit(
                f'Checksum verification failed for {mismatched} object(s).'
            )

        print('VERIFIED: every stored object matches its local SHA-256.')


if __name__ == '__main__':
    main()

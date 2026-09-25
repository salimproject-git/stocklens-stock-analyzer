#!/usr/bin/env python3
"""
raw_storage_source.py
=====================

Shared Storage-first raw source for the Phase 2 canonical loaders.

Source of truth:
    Supabase Storage bucket `stocklens_raw`
    object layout: sectors/{TICKER}/{category}/{name}

Local disk is never the pipeline source; `--source local` exists only for
debugging/verification.

No transformation happens here: bytes are returned exactly as stored.
"""

from __future__ import annotations

import os
from typing import Any

from upload_raw_storage_only import StorageClient

BUCKET = 'stocklens_raw'


def required_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise RuntimeError(f'Environment variable belum di-set: {name}')
    return value


class RawStorageSource:
    """Read-only view over the private raw bucket for one ticker."""

    def __init__(self, ticker: str, bucket: str = BUCKET) -> None:
        self.ticker = ticker.upper().replace('.JK', '')
        self.bucket = bucket
        self._client: StorageClient | None = None

    @property
    def client(self) -> StorageClient:
        if self._client is None:
            self._client = StorageClient(
                required_env('SUPABASE_URL'),
                required_env('SUPABASE_SERVICE_ROLE_KEY'),
            )
        return self._client

    def storage_path(self, category: str, name: str) -> str:
        return f'sectors/{self.ticker}/{category}/{name}'

    def names(self, category: str, suffix: str = '.json') -> list[str]:
        """Sorted object names directly under sectors/{ticker}/{category}/."""
        prefix = f'sectors/{self.ticker}/{category}/'
        names = []
        for path in self.client.walk(self.bucket):
            if not path.startswith(prefix):
                continue
            remainder = path[len(prefix):]
            if '/' in remainder:
                continue
            if suffix and not remainder.endswith(suffix):
                continue
            names.append(remainder)
        return sorted(names)

    def exists(self, category: str, name: str) -> bool:
        return self.client.object_info(self.bucket, self.storage_path(category, name)) is not None

    def read(self, category: str, name: str) -> bytes:
        storage_path = self.storage_path(category, name)
        if not self.exists(category, name):
            raise RuntimeError(f'RAW_SOURCE_NOT_FOUND: {self.bucket}/{storage_path}')
        return self.client.download(self.bucket, storage_path)

    def info(self, category: str, name: str) -> dict[str, Any]:
        return self.client.object_info(self.bucket, self.storage_path(category, name))


class ProvenanceIndex:
    """
    Resolve `ingestion_files` rows by storage path.

    Phase 1B registered one `ingestion_runs` row per raw file, so a single
    run_id cannot cover a whole family (e.g. 27 quarterly files / 29 daily
    windows). Provenance is therefore keyed by storage_path, and every row is
    validated for status + checksum before it is trusted.

    Rows are looked up through the Supabase REST API using the same
    service-role credentials as the loaders.
    """

    def __init__(self, url: str, key: str, bucket: str = BUCKET) -> None:
        import requests

        self.bucket = bucket
        self.rest_url = url.rstrip('/') + '/rest/v1'
        self.session = requests.Session()
        self.session.headers.update(
            {
                'apikey': key,
                'Authorization': 'Bearer ' + key,
                'Content-Type': 'application/json',
            }
        )
        self._rows: dict[str, dict[str, Any]] | None = None

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._rows is not None:
            return self._rows

        rows: list[dict[str, Any]] = []
        offset = 0
        page_size = 1000

        while True:
            response = self.session.get(
                self.rest_url + '/ingestion_files',
                params={
                    'storage_bucket': 'eq.' + self.bucket,
                    'select': 'id,storage_path,checksum_sha256,status',
                    'limit': str(page_size),
                    'offset': str(offset),
                },
                timeout=60,
            )
            if not response.ok:
                raise RuntimeError(
                    'PROVENANCE_QUERY_FAILED (%s): %s'
                    % (response.status_code, response.text[:1000])
                )
            page = response.json()
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size

        by_path: dict[str, dict[str, Any]] = {}
        for row in rows:
            by_path.setdefault(row['storage_path'], row)
        self._rows = by_path
        return by_path

    def resolve(self, storage_path: str, checksum: str) -> str:
        """Return ingestion_files.id, verifying status and checksum."""
        row = self._load().get(storage_path)
        if row is None:
            raise RuntimeError('PROVENANCE_NOT_FOUND: ' + storage_path)
        if row.get('status') not in {'UPLOADED', 'SKIPPED'}:
            raise RuntimeError(
                'PROVENANCE_NOT_READY: %s status=%s' % (storage_path, row.get('status'))
            )
        if row.get('checksum_sha256') != checksum:
            raise RuntimeError('PROVENANCE_CHECKSUM_CONFLICT: ' + storage_path)
        return row['id']

    def resolve_many(self, checksums: dict[str, str]) -> dict[str, str]:
        """Map {storage_path: checksum} -> {storage_path: ingestion_files.id}."""
        return {
            storage_path: self.resolve(storage_path, checksum)
            for storage_path, checksum in checksums.items()
        }

#!/usr/bin/env python3
"""
seed_calculation_registry.py
============================

Phase 4.1 - Seeds and verifies the parameter & methodology registry.

Reads the catalogue in `calculation_parameter_catalogue.py` and the
methodology definitions in `calculation_methodology_registry.py`, then writes
them into `public.calculation_parameters` and `public.methodology_versions`
through the Supabase REST API, using the same service-role credential pattern
as the Phase 2 canonical loaders.

Behaviour
---------
* `--dry-run` (default) prints what would be written and performs no HTTP
  request.
* `--write` upserts both registries.
* `--check` reads the registry back and compares it against the catalogue,
  reporting drift.

Safety rules
------------
1.  An existing `methodology_versions` row whose status is **not** `DRAFT` is
    never overwritten. It is reported as `METHODOLOGY_SEED_CONFLICT` and the
    run fails, so a published methodology cannot be silently rewritten.
2.  Canonical data tables are never touched. Only the two registry tables are
    written.
3.  Parameters are stored with their exact decimal string value, so precision
    survives the round trip.

Usage
-----
    python supabase/seed_calculation_registry.py --dry-run
    python supabase/seed_calculation_registry.py --write
    python supabase/seed_calculation_registry.py --check
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import requests

from calculation_methodology_registry import METHOD_VERSION, methodology_seeds
from calculation_parameter_catalogue import all_parameters
from calculation_registry import RegistryError, canonical_json, sha256_json

#: Bumped when the registry content shape changes.
PARAMETER_VERSION = '1.0.0'

METHODOLOGY_TABLE = 'methodology_versions'
PARAMETER_TABLE = 'calculation_parameters'


def required_env(name: str) -> str:
    """Return a required environment variable, or raise."""
    value = os.getenv(name, '').strip()
    if not value:
        raise RegistryError(f'SUPABASE_CONFIGURATION_MISSING: {name}')
    return value


class SupabaseRest:
    """Minimal PostgREST client for the registry tables."""

    def __init__(self, url: str, key: str) -> None:
        url = url.strip().rstrip('/')
        key = key.strip()
        if not url or not key:
            raise RegistryError('SUPABASE_CONFIGURATION_MISSING')
        self.base_url = url + '/rest/v1'
        self.session = requests.Session()
        self.session.headers.update(
            {
                'apikey': key,
                'Authorization': 'Bearer ' + key,
                'Content-Type': 'application/json',
            }
        )

    def get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        response = self.session.get(self.base_url + '/' + table, params=params, timeout=60)
        if not response.ok:
            raise RegistryError(
                f'{table}:{response.status_code} {response.text[:500]}'
            )
        value = response.json()
        if not isinstance(value, list):
            raise RegistryError(f'{table}: non-list response')
        return value

    def upsert(self, table: str, rows: list[dict[str, Any]], on_conflict: str) -> list[dict[str, Any]]:
        response = self.session.post(
            self.base_url + '/' + table,
            params={'on_conflict': on_conflict, 'select': '*'},
            json=rows,
            headers={'Prefer': 'resolution=merge-duplicates,return=representation'},
            timeout=120,
        )
        if not response.ok:
            raise RegistryError(
                f'{table}:{response.status_code} {response.text[:1000]}'
            )
        value = response.json()
        return value if isinstance(value, list) else []


def parameter_rows() -> list[dict[str, Any]]:
    """Build the `calculation_parameters` rows from the catalogue."""
    rows: list[dict[str, Any]] = []
    for code, owner, value, unit, resolution, source, note in all_parameters():
        rows.append(
            {
                'parameter_code': code,
                'parameter_version': PARAMETER_VERSION,
                'owner_method_code': owner,
                'parameter_value': value,
                'unit': unit,
                'resolution_status': resolution,
                'source_reference': source,
                'note': note,
                'value_hash': sha256_json(value),
            }
        )
    return rows


def methodology_rows() -> list[dict[str, Any]]:
    """Build the `methodology_versions` rows from the methodology registry."""
    rows: list[dict[str, Any]] = []
    for seed in methodology_seeds():
        rows.append(
            {
                'method_code': seed['method_code'],
                'method_version': seed['method_version'],
                'method_name': seed['method_name'],
                'description': seed['description'],
                'formula_text': seed['formula_text'],
                'formula_hash': seed['formula_hash'],
                'parameter_spec': seed['parameter_spec'],
                'parameter_hash': seed['parameter_hash'],
                'code_version': seed['code_version'],
                'input_vocabulary_version': seed['input_vocabulary_version'],
                'status': seed['status'],
            }
        )
    return rows



def assert_no_methodology_conflict(
    db: SupabaseRest, rows: list[dict[str, Any]]
) -> list[str]:
    """Fail if any existing methodology row is not DRAFT and differs.

    Returns a list of conflict descriptions. An empty list means it is safe to
    seed. A PUBLISHED or RETIRED row is never overwritten.
    """
    existing = db.get(
        METHODOLOGY_TABLE,
        {
            'select': 'method_code,method_version,formula_hash,parameter_hash,status',
            'limit': '200',
        },
    )
    by_key = {(row['method_code'], row['method_version']): row for row in existing}

    conflicts: list[str] = []
    for row in rows:
        key = (row['method_code'], row['method_version'])
        current = by_key.get(key)
        if current is None:
            continue
        same_content = (
            current.get('formula_hash') == row['formula_hash']
            and current.get('parameter_hash') == row['parameter_hash']
        )
        if current.get('status') != 'DRAFT' and not same_content:
            conflicts.append(
                'METHODOLOGY_SEED_CONFLICT: %s %s is %s with different content'
                % (key[0], key[1], current.get('status'))
            )
    return conflicts


def verify_registry(db: SupabaseRest) -> list[str]:
    """Compare the stored registry against the catalogue.

    Returns a list of drift problems; an empty list means the registry matches.
    """
    problems: list[str] = []

    stored_methods = db.get(
        METHODOLOGY_TABLE,
        {
            'select': 'method_code,method_version,formula_hash,parameter_hash,status',
            'limit': '200',
        },
    )
    expected_methods = {
        (row['method_code'], row['method_version']): row for row in methodology_rows()
    }
    stored_method_index = {
        (row['method_code'], row['method_version']): row for row in stored_methods
    }

    for key, expected in expected_methods.items():
        current = stored_method_index.get(key)
        if current is None:
            problems.append('METHODOLOGY_MISSING: %s %s' % key)
            continue
        if current.get('formula_hash') != expected['formula_hash']:
            problems.append('METHODOLOGY_FORMULA_HASH_DRIFT: %s %s' % key)
        if current.get('parameter_hash') != expected['parameter_hash']:
            problems.append('METHODOLOGY_PARAMETER_HASH_DRIFT: %s %s' % key)

    for key in stored_method_index:
        if key not in expected_methods:
            problems.append('METHODOLOGY_UNEXPECTED: %s %s' % key)

    stored_params = db.get(
        PARAMETER_TABLE,
        {
            'select': 'parameter_code,parameter_version,resolution_status,value_hash',
            'limit': '500',
        },
    )
    stored_param_index = {
        (row['parameter_code'], row['parameter_version']): row for row in stored_params
    }
    expected_params = {
        (row['parameter_code'], row['parameter_version']): row for row in parameter_rows()
    }

    for key, expected in expected_params.items():
        current = stored_param_index.get(key)
        if current is None:
            problems.append('PARAMETER_MISSING: %s %s' % key)
            continue
        if current.get('value_hash') != expected['value_hash']:
            problems.append('PARAMETER_VALUE_DRIFT: %s %s' % key)
        if current.get('resolution_status') != expected['resolution_status']:
            problems.append('PARAMETER_RESOLUTION_DRIFT: %s %s' % key)

    for key in stored_param_index:
        if key not in expected_params:
            problems.append('PARAMETER_UNEXPECTED: %s %s' % key)

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Seed the StockLens calculation registry')
    parser.add_argument('--write', action='store_true', help='write the registry')
    parser.add_argument('--check', action='store_true', help='verify the stored registry')
    parser.add_argument('--dry-run', action='store_true', help='print without writing')
    args = parser.parse_args(argv)

    methods = methodology_rows()
    parameters = parameter_rows()

    if args.dry_run or not (args.write or args.check):
        print(f'parameters   : {len(parameters)}')
        print(f'methodologies: {len(methods)}')
        unresolved = [row for row in parameters if row['resolution_status'] != 'RESOLVED']
        print(f'unresolved   : {len(unresolved)}')
        for row in unresolved:
            print('  - %s [%s]' % (row['parameter_code'], row['resolution_status']))
        print('dry run: no HTTP request performed')
        return 0

    db = SupabaseRest(required_env('SUPABASE_URL'), required_env('SUPABASE_SERVICE_ROLE_KEY'))

    if args.check:
        problems = verify_registry(db)
        for problem in problems:
            print(problem)
        print('registry check: %s' % ('DRIFT' if problems else 'OK'))
        return 1 if problems else 0

    conflicts = assert_no_methodology_conflict(db, methods)
    if conflicts:
        for conflict in conflicts:
            print(conflict)
        return 1

    written_methods = db.upsert(METHODOLOGY_TABLE, methods, 'method_code,method_version')
    written_parameters = db.upsert(
        PARAMETER_TABLE, parameters, 'parameter_code,parameter_version'
    )
    print(f'methodologies written: {len(written_methods)}')
    print(f'parameters written   : {len(written_parameters)}')

    problems = verify_registry(db)
    for problem in problems:
        print(problem)
    print('post-write verification: %s' % ('DRIFT' if problems else 'OK'))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""
calculation_registry.py
=======================

Phase 4.1 - Parameter & methodology registry primitives.

This module owns the **canonical hashing contract** used by the Phase 4
calculation engine. `Testing/test_calculation_v1.py` imports
`canonical_json` and `sha256_json` from `supabase.calculation_v1_common`;
that module must re-export the two functions defined here so that there is
exactly one implementation.

Design decisions
----------------

1.  **Numeric values are stored as decimal strings.**
    Every parameter value is carried as its exact decimal text (for example
    ``"0.0633"``) instead of a JSON number. This preserves precision exactly,
    keeps the registry free of binary-float artefacts, and makes
    :func:`sha256_json` trivially stable across a JSON round trip.

2.  **Hashing is canonical, not "pretty".**
    :func:`canonical_json` sorts keys and removes insignificant whitespace.
    :func:`sha256_json` hashes the UTF-8 bytes of that canonical form.
    ``formula_hash`` uses a different rule: it hashes the raw formula text
    exactly as written (:func:`sha256_text`), because the test contract
    recomputes it with ``hashlib.sha256(formula.encode()).hexdigest()``.

3.  **Determinism.**
    Both helpers are pure functions of their argument. Re-running the seeder
    against unchanged catalogue data produces identical hashes, so the
    registry is reproducible.

Only the standard library is required.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# --------------------------------------------------------------------------
# Registry vocabulary (fixed by the Phase 4 test contract)
# --------------------------------------------------------------------------

#: Methodology lifecycle statuses. ``DRAFT`` is the only status the seeder
#: treats as safely re-seedable; anything else is a conflict.
METHODOLOGY_STATUSES = ('DRAFT', 'PUBLISHED', 'RETIRED')

#: Statuses the orchestrator may execute (see the forward test suite).
EXECUTABLE_METHODOLOGY_STATUSES = ('DRAFT', 'PUBLISHED')

#: Version of the calculation code that produced a result row.
CODE_VERSION = 'stocklens-calc-v1'

#: Version of the canonical financial input vocabulary.
INPUT_VOCABULARY_VERSION = 'canonical-financial-v1'

#: Resolution states for a parameter specification. These make an
#: unresolved value an explicit, queryable state instead of a guess.
RESOLUTION_RESOLVED = 'RESOLVED'
RESOLUTION_UNRESOLVED_SOURCE = 'UNRESOLVED_SOURCE'
RESOLUTION_MISSING_INPUT = 'MISSING_INPUT'
RESOLUTION_UNRESOLVED_DEFINITION = 'UNRESOLVED_DEFINITION'
RESOLUTION_BROKEN_REFERENCE = 'BROKEN_REFERENCE'

RESOLUTION_STATUSES = (
    RESOLUTION_RESOLVED,
    RESOLUTION_UNRESOLVED_SOURCE,
    RESOLUTION_MISSING_INPUT,
    RESOLUTION_UNRESOLVED_DEFINITION,
    RESOLUTION_BROKEN_REFERENCE,
)

#: Statuses that mean "the engine must not silently use a fallback value".
UNRESOLVED_STATUSES = (
    RESOLUTION_UNRESOLVED_SOURCE,
    RESOLUTION_MISSING_INPUT,
    RESOLUTION_UNRESOLVED_DEFINITION,
    RESOLUTION_BROKEN_REFERENCE,
)


class RegistryError(RuntimeError):
    """Raised when a registry contract is violated."""


# --------------------------------------------------------------------------
# Canonical hashing
# --------------------------------------------------------------------------

def canonical_json(value: Any) -> str:
    """Return the canonical JSON text of ``value``.

    Keys are sorted, separators are compact, and non-ASCII characters are
    preserved. The result is byte-stable for any JSON-representable value
    that survives a ``json.dumps`` / ``json.loads`` round trip.
    """
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def sha256_text(text: str) -> str:
    """SHA-256 hex digest of ``text`` encoded as UTF-8.

    Used for ``formula_hash``: the test contract recomputes it with
    ``hashlib.sha256(formula.encode()).hexdigest()``.
    """
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def sha256_json(value: Any) -> str:
    """SHA-256 hex digest of the canonical JSON form of ``value``.

    Used for ``parameter_hash``. Deterministic and JSON-round-trip stable.
    """
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()




# --------------------------------------------------------------------------
# Input hash / idempotency key contract
# --------------------------------------------------------------------------

def input_hash(input_snapshot: dict[str, Any]) -> str:
    """Deterministic input hash for a calculation run.

    The forward test contract requires that key order in the snapshot does
    not change the hash (``{'b': 2, 'a': 1}`` and ``{'a': 1, 'b': 2}`` hash
    identically), which :func:`canonical_json` guarantees.
    """
    return sha256_json(input_snapshot)


def idempotency_key(
    *,
    calculation_type: str,
    methodology_version_id: str,
    code_version: str,
    source_cutoff_date: str | None,
    source_ingestion_run_id: str | None,
    scope_type: str,
    scope_id: str,
    input_hash_value: str,
    retry_of_run_id: str | None = None,
) -> str:
    """Deterministic idempotency key for one calculation run.

    Identical inputs plus identical methodology produce an identical key. A
    retry appends ``retry_of_run_id``, so a retry is a *new* run rather than
    a mutation of the previous one.
    """
    return sha256_json(
        {
            'calculation_type': calculation_type,
            'methodology_version_id': methodology_version_id,
            'code_version': code_version,
            'source_cutoff_date': source_cutoff_date,
            'source_ingestion_run_id': source_ingestion_run_id,
            'scope_type': scope_type,
            'scope_id': scope_id,
            'input_hash': input_hash_value,
            'retry_of_run_id': retry_of_run_id,
        }
    )

def methodology_hashes(formula_text: str, parameter_spec: dict[str, Any]) -> tuple[str, str]:
    """Return ``(formula_hash, parameter_hash)`` for a methodology seed row."""
    return sha256_text(formula_text), sha256_json(parameter_spec)

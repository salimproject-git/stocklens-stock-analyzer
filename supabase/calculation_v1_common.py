#!/usr/bin/env python3
"""
calculation_v1_common.py
========================

Phase 4.1 - Shared primitives for the StockLens calculation engine.

`Testing/test_calculation_v1.py` imports from this module:

    from supabase.calculation_v1_common import (
        CalculationError, SupabaseRest, calculation_contract, canonical_json,
        growth_result, ratio_result, sha256_json,
    )

Phase 4.1 owns the **hashing and transport** half of that contract. The
**calculation-domain** half (`calculation_contract`, `growth_result`,
`ratio_result`) belongs to the later calculation phases and is deliberately
NOT implemented here. Defining those functions now, before their inputs and
status semantics are settled, would be exactly the kind of silent invention
Phase 4.1 is meant to avoid.

Implemented here (Phase 4.1)
----------------------------
``CalculationError``   - error type used across the calculation layer.
``SupabaseRest``       - PostgREST client with secret-safe error messages.
``canonical_json``     - re-exported from `calculation_registry`.
``sha256_json``        - re-exported from `calculation_registry`.

Deferred (Phase 4.2+)
---------------------
``calculation_contract``, ``growth_result``, ``ratio_result``.
See `PHASE_4_1_IMPLEMENTATION_NOTES.md` for the deferral rationale.

The hashing functions are re-exported rather than re-implemented so that the
Phase 4.1 registry, the migration seed, and this module can never disagree
about what a hash means.
"""

from __future__ import annotations

from typing import Any

import requests

from calculation_registry import (
    RegistryError,
    canonical_json,
    sha256_json,
)

__all__ = [
    'CalculationError',
    'SupabaseRest',
    'canonical_json',
    'sha256_json',
]


class CalculationError(RuntimeError):
    """Raised for calculation-layer configuration and contract failures."""


class SupabaseRest:
    """Minimal PostgREST client for the calculation layer.

    Mirrors the credential and session pattern used by the Phase 2 canonical
    loaders so there is one HTTP convention in the repository.

    Error messages deliberately expose only PostgREST diagnostics (status,
    ``code``, ``message``, ``details``, ``hint``) and never the service key,
    the ``apikey`` header, the ``Authorization`` header, or the request
    payload. ``Testing/test_calculation_v1.py`` asserts exactly that.
    """

    def __init__(self, url: str, key: str) -> None:
        url = (url or '').strip().rstrip('/')
        key = (key or '').strip()
        if not url or not key:
            raise CalculationError('SUPABASE_CONFIGURATION_MISSING')

        self.base_url = url
        self.service_key = key
        self.rest_url = url + '/rest/v1'
        self.session = requests.Session()
        self.session.headers.update(
            {
                'apikey': key,
                'Authorization': 'Bearer ' + key,
                'Content-Type': 'application/json',
            }
        )

    def request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        payload: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Perform a request against ``table`` and return the decoded body.

        On a non-2xx response the PostgREST diagnostics are surfaced without
        leaking credentials or the request payload.
        """
        response = self.session.request(
            method,
            self.rest_url + '/' + table,
            params=params,
            json=payload,
            headers=headers,
            timeout=120,
        )
        if not response.ok:
            raise CalculationError(self._describe_failure(table, response))
        if not response.content:
            return None
        return response.json()

    def get_all(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        """GET ``table`` and require a list response."""
        value = self.request('GET', table, params=params)
        if not isinstance(value, list):
            raise CalculationError(f'{table}: non-list response')
        return value

    @staticmethod
    def _describe_failure(table: str, response: Any) -> str:
        """Build a secret-safe diagnostic string for a failed request."""
        code = message = details = hint = None
        try:
            body = response.json()
            if isinstance(body, dict):
                code = body.get('code')
                message = body.get('message')
                details = body.get('details')
                hint = body.get('hint')
        except Exception:  # noqa: BLE001 - diagnostics are best effort
            pass

        return (
            f'{table}:{getattr(response, "status_code", "?")} '
            f'code={code} message={message} details={details} hint={hint}'
        )


def registry_error_to_calculation_error(error: RegistryError) -> CalculationError:
    """Translate a registry failure into a calculation-layer error."""
    return CalculationError(str(error))

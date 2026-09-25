#!/usr/bin/env python3
"""
emit_calculation_v1_seed_sql.py
===============================

Phase 4.1 helper: renders the nine methodology seed rows as the exact SQL
``VALUES`` lines that ``supabase/migrations/0008_calculation_v1_batch.sql``
must contain.

Why a helper exists
-------------------
``Testing/test_calculation_v1.py`` parses the migration text with a
line-anchored regex::

    \\('([^']+)','([^']+)','[^']*','[^']*','([^']*)','([0-9a-f]{64})','(\\{.*\\})'::jsonb,'([0-9a-f]{64})'\\),?$

It then re-derives ``formula_hash`` and ``parameter_hash`` from the captured
groups and asserts equality. Hand-writing those hashes is error-prone, so they
are generated from the registry and pasted into the migration.

The generated lines are also re-verified by ``verify_calculation_v1_seed.py``
and by the Phase 4.1 test module, so a drift between the registry and the
migration fails loudly.

Usage
-----
    python supabase/emit_calculation_v1_seed_sql.py
"""

from __future__ import annotations

import json

from calculation_methodology_registry import methodology_seeds


def sql_literal(text: str) -> str:
    """Return ``text`` escaped for a single-quoted SQL literal."""
    return text.replace("'", "''")


def render_seed_line(seed: dict[str, object]) -> str:
    """Render one seed row as a single-line SQL ``VALUES`` tuple."""
    parameter_json = json.dumps(
        seed['parameter_spec'], sort_keys=True, separators=(',', ':'), ensure_ascii=False
    )
    return (
        f"('{sql_literal(str(seed['method_code']))}',"
        f"'{sql_literal(str(seed['method_version']))}',"
        f"'{sql_literal(str(seed['method_name']))}',"
        f"'{sql_literal(str(seed['description']))}',"
        f"'{sql_literal(str(seed['formula_text']))}',"
        f"'{seed['formula_hash']}',"
        f"'{sql_literal(parameter_json)}'::jsonb,"
        f"'{seed['parameter_hash']}')"
    )


def render_seed_block() -> str:
    """Render every seed row as a comma-terminated block."""
    lines = [render_seed_line(seed) + ',' for seed in methodology_seeds()]
    return '\n'.join(lines)


if __name__ == '__main__':
    print(render_seed_block())

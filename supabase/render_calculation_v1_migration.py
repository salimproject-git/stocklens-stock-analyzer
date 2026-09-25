#!/usr/bin/env python3
"""
render_calculation_v1_migration.py
==================================

Phase 4.1 - Renders the generated seed block of
``supabase/migrations/0008_calculation_v1_batch.sql`` from the registry.

Why this exists
---------------
The forward test contract parses the migration text with a line-anchored regex
and recomputes both hashes from the captured groups. Hand-maintaining those
hashes is how drift happens, so the seed block is **generated** and the
migration is treated as a build artefact for that one region.

Workflow
--------
1. Edit `calculation_parameter_catalogue.py` and/or
   `calculation_methodology_registry.py`.
2. Run this renderer (``--write``) to refresh the block.
3. Run ``--check`` (also used by the Phase 4.1 test module) to prove the file
   on disk matches the registry.

Usage
-----
    python supabase/render_calculation_v1_migration.py --check
    python supabase/render_calculation_v1_migration.py --write
"""

from __future__ import annotations

import sys
from pathlib import Path

from emit_calculation_v1_seed_sql import render_seed_block

BEGIN_MARKER = '-- BEGIN GENERATED SEED'
END_MARKER = '-- END GENERATED SEED'

MIGRATION_PATH = Path(__file__).resolve().parent / 'migrations' / '0008_calculation_v1_batch.sql'


class RenderError(RuntimeError):
    """Raised when the migration cannot be rendered or does not match."""


def split_migration(text: str) -> tuple[str, str, str]:
    """Return ``(before, generated_block, after)`` around the seed markers."""
    if BEGIN_MARKER not in text or END_MARKER not in text:
        raise RenderError('SEED_MARKERS_MISSING')

    begin = text.index(BEGIN_MARKER)
    end = text.index(END_MARKER)

    before = text[: begin + len(BEGIN_MARKER)]
    block = text[begin + len(BEGIN_MARKER) : end]
    after = text[end:]
    return before, block, after


def expected_block() -> str:
    """Return the seed block exactly as it should appear on disk."""
    return '\n' + render_seed_block() + '\n'


def render(text: str) -> str:
    """Return ``text`` with the generated seed block refreshed."""
    before, _block, after = split_migration(text)
    return before + expected_block() + after


def check(path: Path = MIGRATION_PATH) -> list[str]:
    """Return a list of drift problems. An empty list means the file is in sync."""
    text = path.read_text(encoding='utf-8')
    _before, block, _after = split_migration(text)
    if block == expected_block():
        return []
    return [
        'SEED_BLOCK_DRIFT: the generated seed block on disk differs from the '
        'registry. Run `python supabase/render_calculation_v1_migration.py --write`.'
    ]


def write(path: Path = MIGRATION_PATH) -> None:
    """Rewrite the migration with a freshly rendered seed block."""
    text = path.read_text(encoding='utf-8')
    path.write_text(render(text), encoding='utf-8', newline='\n')


def main(argv: list[str]) -> int:
    if '--write' in argv:
        write()
        print('rendered: ' + str(MIGRATION_PATH))
        return 0
    if '--check' in argv:
        problems = check()
        for problem in problems:
            print(problem)
        return 1 if problems else 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))

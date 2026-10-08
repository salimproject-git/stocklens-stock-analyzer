#!/usr/bin/env python3
"""Run the whole per-ticker pipeline with one command.

Replaces the long hand-typed sequence in ``docs/SUPABASE_MANUAL_RUNBOOK.md``:

    python run_pipeline.py SIDO

Every step is the *existing* script, invoked as a subprocess, so there is one
implementation of each step and the runbook stays accurate. What this adds is
sequencing, automatic discovery of the ids the runbook asks you to copy by hand,
and a single place that reports what succeeded.

Steps
-----
1. ``ingest_raw_history.py --symbol TICKER --apply``
   Uploads local raw JSON to Storage and records ``ingestion_runs`` provenance.
2. Resolve ``ingestion_run_id`` per request family from the database
   (``ingestion_runs`` + ``ingestion_files``) instead of copying it out of the
   terminal output. This is the manual step the runbook warns about most.
3. ``load_identity_to_supabase.py`` (needs the ``info`` run id)
4. ``load_annual_financials_to_supabase.py``
5. ``load_quarterly_financials_to_supabase.py``
6. ``load_dividend_to_supabase.py``
7. ``load_daily_prices_to_supabase.py``
8. ``populate_growth_quality.py --apply``
9. ``derive_projection_scenario.py --apply``
10. ``populate_metrics_classification.py --apply``
11. ``calculate_valuation.py --risk-free-from-reference --apply``
    No ``--stock-type``: the classifier from step 10 supplies it.
12. ``run_backtest.py --ticker TICKER --apply``
    Reads the canonical financial periods and prices the earlier steps just
    refreshed, and writes only ``calc_backtest_cases`` / ``calc_backtest_methods``
    - never ``calc_valuation_*``. Running it last therefore cannot change a
    valuation result; it only fills the Backtest tab and the market card's Win
    Rate. It is the final step of ``--mode rebuild`` and ``--mode fundamental``;
    ``--mode daily`` deliberately excludes it (see docs/PIPELINE_OPERATIONS_SCHEDULE.md).

Flags
-----
``--from-step``  resume after a failure without redoing earlier steps.
``--only``       run a single step by name.
``--skip-raw``   start at identity, for a ticker already ingested.
``--dry-run``    print the commands without executing them.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

SUPABASE_DIR = Path(__file__).resolve().parent / 'supabase'
REPO_ROOT = SUPABASE_DIR.parent
if str(SUPABASE_DIR) not in sys.path:
    sys.path.insert(0, str(SUPABASE_DIR))

from calculation_v1_common import (  # noqa: E402
    CalculationError,
    SupabaseRest,
)
from derive_classifier_inputs import load_env_file  # noqa: E402

#: Request families whose ``ingestion_files`` row is needed by a loader.
REQUIRED_RUN_FAMILIES: dict[str, str] = {
    'info': 'load_identity_to_supabase.py',
    'annual': 'load_annual_financials_to_supabase.py',
    'quarterly': 'load_quarterly_financials_to_supabase.py',
    'dividend': 'load_dividend_to_supabase.py',
    'daily': 'load_daily_prices_to_supabase.py',
}

#: Ordered pipeline. ``needs_run_id`` selects the ingestion family to resolve.
#: Paths are relative to the repository root, which is the subprocess cwd.
STEPS: tuple[dict[str, Any], ...] = (
    {
        # Uploads whatever local raw JSON is missing from Storage. This is what
        # makes a ticker whose files were already downloaded loadable *without*
        # the Sectors API: `ingest-raw` below then finds the bytes in Storage and
        # registers provenance from them (its CASE B) instead of re-fetching
        # (its CASE C). It never overwrites an existing object, so it is safe to
        # re-run and a no-op once Storage is complete.
        'name': 'upload-raw',
        'args': ['supabase/upload_raw_storage_only.py', '{ticker}', '--yes'],
        'needs_run_id': None,
    },
    {
        # No API call when `upload-raw` already placed every file: each target
        # resolves to SKIP_ALREADY_INGESTED or REPAIRED_FROM_EXISTING_STORAGE.
        # An API call only happens for a target absent from both Storage and
        # local disk, which is exactly the "brand new data" case.
        'name': 'ingest-raw',
        'args': ['supabase/ingest_raw_history.py', '--symbol', '{ticker}', '--apply'],
        'needs_run_id': None,
    },
    {
        'name': 'load-identity',
        'args': [
            'supabase/load_identity_to_supabase.py', '{ticker}',
            '--ingestion-run-id', '{run_id:info}',
        ],
        'needs_run_id': 'info',
    },
    {
        'name': 'load-annual',
        'args': ['supabase/load_annual_financials_to_supabase.py', '{ticker}'],
        'needs_run_id': None,
    },
    {
        'name': 'load-quarterly',
        'args': ['supabase/load_quarterly_financials_to_supabase.py', '{ticker}'],
        'needs_run_id': None,
    },
    {
        'name': 'load-dividend',
        'args': ['supabase/load_dividend_to_supabase.py', '{ticker}'],
        'needs_run_id': None,
    },
    {
        'name': 'load-prices',
        'args': ['supabase/load_daily_prices_to_supabase.py', '{ticker}'],
        'needs_run_id': None,
    },
    {
        'name': 'growth-quality',
        'args': ['supabase/populate_growth_quality.py', '--ticker', '{ticker}', '--apply'],
        'needs_run_id': None,
    },
    {
        'name': 'projection',
        'args': ['supabase/derive_projection_scenario.py', '{ticker}', '--apply'],
        'needs_run_id': None,
    },
    {
        'name': 'classification',
        'args': [
            'supabase/populate_metrics_classification.py', '--ticker', '{ticker}', '--apply',
        ],
        'needs_run_id': None,
    },
    {
        'name': 'valuation',
        'args': [
            'supabase/calculate_valuation.py',
            '--ticker', '{ticker}',
            '--risk-free-from-reference',
            '--frequency-snapshot',
            '--apply',
        ],
        'needs_run_id': None,
    },
    {
        # Fase 1 backtest: daftar kasus + metrik harga. Tidak menulis ke
        # `calc_valuation_*` dan tidak menghitung verdict - keduanya fase 2/3.
        # Diletakkan setelah valuation karena fase 2 nanti memakai hasil
        # valuation sebagai input, sehingga urutannya sudah benar begitu
        # ditambahkan tanpa memindahkan step ini.
        'name': 'backtest',
        'args': ['supabase/run_backtest.py', '--ticker', '{ticker}', '--apply'],
        'needs_run_id': None,
    },
)

STEP_NAMES: tuple[str, ...] = tuple(str(step['name']) for step in STEPS)
PIPELINE_STEP_CHOICES = STEP_NAMES + ('daily-status', 'projection-reuse')

PIPELINE_MODE_STEPS: dict[str, tuple[str, ...]] = {
    # Rebuild reads existing raw objects from Storage via the canonical loaders.
    # It must never run the API-capable ingest step as an implicit fallback.
    #
    # `backtest` is last on purpose: it reads the canonical `financial_periods`
    # and `prices_daily` that the loaders above just refreshed, and writes only
    # to `calc_backtest_cases`/`calc_backtest_methods`. It never touches
    # `calc_valuation_*`, so running it after `valuation`/`daily-status` cannot
    # change a valuation result - it only fills the Backtest tab and the market
    # card's Win Rate from the data those steps already produced.
    'rebuild': (
        'load-identity', 'load-annual', 'load-quarterly', 'load-dividend',
        'load-prices', 'growth-quality', 'projection-reuse', 'classification',
        'valuation', 'daily-status', 'backtest',
    ),
    'fundamental': (
        'load-identity', 'load-annual', 'load-quarterly', 'load-dividend', 'load-prices',
        'growth-quality', 'projection', 'classification', 'valuation', 'daily-status',
        'backtest',
    ),
    # `daily` stays deliberately narrow: docs/PIPELINE_OPERATIONS_SCHEDULE.md §4
    # and docs/VALUATION_FREQUENCY_ARCHITECTURE.md both require that a routine
    # daily-price update never triggers the backtest. Add it to `daily` only if
    # that scheduling rule is intentionally revised.
    'daily': ('load-prices', 'daily-status'),
    # Standalone re-run: recompute the backtest without reloading any raw family.
    'backtest': ('backtest',),
}

MODE_EXTRA_STEPS: dict[str, dict[str, Any]] = {
    'projection-reuse': {
        'name': 'projection-reuse',
        'args': [
            'supabase/derive_projection_scenario.py', '{ticker}', '--apply',
            '--reuse-equivalent-active',
        ],
        'needs_run_id': None,
    },
    'daily-status': {
        'name': 'daily-status',
        'args': ['supabase/calculate_daily_valuation.py', '--ticker', '{ticker}', '--apply'],
        'needs_run_id': None,
    },
}


def check_local_raw(ticker: str) -> list[str]:
    """Return the raw JSON files present locally for ``ticker``.

    Used to fail fast with an actionable message. Without this, a ticker whose
    raw was never downloaded produces a traceback from deep inside
    ``discover_files``, which reads like a code defect rather than missing input.
    """
    root = REPO_ROOT / 'Data' / 'Raw' / ticker
    if not root.is_dir():
        return []
    return sorted(str(path.relative_to(root)) for path in root.rglob('*.json'))


def require_local_raw(ticker: str) -> None:
    """Report whether the ticker has local raw, and what that means.

    ``upload_raw_storage_only.py`` is Storage-only by design and cannot fetch.
    Running it for a ticker with no local files is therefore pointless, not
    fatal: ``ingest_raw_history.py`` will fetch that ticker from the API instead
    (its CASE C). This prints which path will be taken so the choice is visible.
    """
    files = check_local_raw(ticker)
    if files:
        print(f'Local raw files: {len(files)} (will be uploaded, then reconciled)')
        return
    print(
        'Local raw files: 0 -> no upload step needed.\n'
        '  This ticker has never been downloaded, so the raw step will fetch it '
        'from the Sectors API\n'
        '  (requires SECTORS_API_KEY). To download it locally first instead:\n'
        f'    python .\\scripts\\data_pipeline\\01_download_sectors.py {ticker} --task all'
    )


def require_storage_raw(ticker: str) -> None:
    """Fail closed unless all existing raw Storage families have registered files.

    Prints a progress line before the checks so the operator sees the pipeline is
    alive: for a ticker whose raw is missing, the only output used to be the
    error, which looked like a hang while the Storage requests were in flight.
    """
    from raw_storage_source import BUCKET, RawStorageSource

    print(f'Checking Storage raw families for {ticker} (bucket={BUCKET}) ...', flush=True)
    source = RawStorageSource(ticker)
    families = {
        'info': ('company_report_info.json',),
        'annual': ('company_report_annual.json',),
        'dividend': ('company_report_dividend.json',),
        'quarterly': ('quarterly_financial_dates.json',),
        'daily': (),
    }
    missing: list[str] = []
    for family, required_names in families.items():
        names = source.names(family)
        if not names:
            missing.append(family)
            continue
        for name in required_names:
            if name not in names:
                missing.append(f'{family}/{name}')
    if missing:
        raise CalculationError(
            'STORAGE_RAW_PREFLIGHT_FAILED (no API fallback): '
            + ', '.join(missing)
            + f'; bucket={BUCKET}; ticker={ticker}'
            + '\n  The canonical loaders read raw from Storage and never call the '
            'Sectors API as a fallback.'
            + '\n  Fetch the raw into Storage first (needs SECTORS_API_KEY), then '
            're-run this command:'
            + f'\n    python run_pipeline.py {ticker} --only ingest-raw'
            + f'\n    python run_pipeline.py {ticker}'
        )
    print(f'Storage preflight OK: ticker={ticker}; families={len(families)}; no Sectors API fallback.')


def resolve_ingestion_run_id(db: SupabaseRest, symbol: str, family: str) -> str:
    """Find the newest successful ingestion run that has a ``family`` file.

    The runbook asks the operator to copy this id out of the terminal output.
    Deriving it from ``ingestion_runs`` + ``ingestion_files`` removes that
    copy-paste step and the class of mistake that comes with it.

    ``ingestion_runs.status`` uses ``SUCCESS``; ``calculation_runs.status`` uses
    ``SUCCEEDED``. They are different vocabularies and both are asserted by
    check constraints, so neither may be assumed.

    A file row counts as registered whether its status is ``UPLOADED`` (bytes
    were sent by this run) or ``SKIPPED`` (the bytes were already in Storage and
    provenance was registered from them, which is what ``ingest_raw_history``
    CASE B does). Only ``FAILED`` is excluded. Accepting just ``UPLOADED`` would
    silently miss every ticker whose raw was uploaded separately.
    """
    runs = db.get_all('ingestion_runs', {
        'symbol': 'eq.' + symbol,
        'status': 'eq.SUCCESS',
        'select': 'id,started_at',
        'order': 'started_at.desc',
    })
    for run in runs:
        files = db.get_all('ingestion_files', {
            'ingestion_run_id': 'eq.' + str(run['id']),
            'source_file_type': 'eq.' + family,
            'select': 'id,status',
        })
        if any(str(row.get('status')) in ('UPLOADED', 'SKIPPED') for row in files):
            return str(run['id'])
    raise CalculationError(f'INGESTION_RUN_NOT_FOUND: symbol={symbol} family={family}')


def render_command(step: dict[str, Any], ticker: str, run_ids: dict[str, str]) -> list[str]:
    """Substitute the placeholders in a step's argument list."""
    rendered: list[str] = []
    for token in step['args']:
        if token == '{ticker}':
            rendered.append(ticker)
        elif token.startswith('{run_id:'):
            family = token[len('{run_id:'):-1]
            try:
                rendered.append(run_ids[family])
            except KeyError:
                raise CalculationError(
                    f'INGESTION_RUN_ID_UNRESOLVED: family={family}'
                ) from None
        else:
            rendered.append(token)
    return rendered


def run_step(command: Sequence[str], *, dry_run: bool) -> int:
    """Execute one step, streaming its output.

    Output is streamed rather than captured so a long loader stays visible and
    its own progress reporting is preserved.
    """
    printable = ' '.join(command)
    print(f'\n>>> {printable}', flush=True)
    if dry_run:
        return 0
    completed = subprocess.run(
        [sys.executable, *command],
        cwd=str(REPO_ROOT),
        env=os.environ.copy(),
    )
    return completed.returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Run the per-ticker StockLens pipeline end to end.'
    )
    parser.add_argument('ticker', help='IDX ticker, e.g. SIDO')
    parser.add_argument(
        '--mode', choices=tuple(PIPELINE_MODE_STEPS), default='rebuild',
        help=(
            'Pipeline frequency: rebuild or fundamental (both end with backtest), '
            'daily (prices + daily status only), or backtest (backtest alone).'
        ),
    )
    parser.add_argument(
        '--only',
        choices=PIPELINE_STEP_CHOICES,
        help='Run a single step by name.',
    )
    parser.add_argument(
        '--from-step',
        choices=PIPELINE_STEP_CHOICES,
        help='Start at this step, skipping earlier ones (resume after a failure).',
    )
    parser.add_argument(
        '--skip-raw',
        action='store_true',
        help='Skip both raw steps (upload-raw, ingest-raw); for a ticker already in Storage.',
    )
    parser.add_argument(
        '--offline',
        action='store_true',
        help=(
            'Alias for --skip-raw. Use when raw is already in Storage and you do '
            'not want the Sectors API touched at all.'
        ),
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print the commands without running them.',
    )
    args = parser.parse_args(argv)

    ticker = args.ticker.strip().upper().replace('.JK', '')
    load_env_file(REPO_ROOT / '.env')

    if args.only:
        selected = [step for step in STEPS if step['name'] == args.only]
        if args.only in MODE_EXTRA_STEPS:
            selected.append(MODE_EXTRA_STEPS[args.only])
    else:
        names = PIPELINE_MODE_STEPS[args.mode]
        selected = [
            next((step for step in STEPS if step['name'] == name), MODE_EXTRA_STEPS.get(name))
            for name in names
        ]
        selected = [step for step in selected if step is not None]
        if args.skip_raw or args.offline:
            selected = [
                step for step in selected
                if step['name'] not in ('upload-raw', 'ingest-raw')
            ]
        if args.from_step:
            start = next(
                index for index, step in enumerate(selected)
                if step['name'] == args.from_step
            )
            selected = selected[start:]

    # Storage preflight only when a step that READS raw from Storage is about to
    # run. `--only ingest-raw` / `--only upload-raw` are the steps that *populate*
    # Storage, so they must never be blocked by the check that Storage is
    # already populated - that would make fetching a new ticker impossible.
    storage_reader_steps = {
        'load-identity', 'load-annual', 'load-quarterly', 'load-dividend', 'load-prices',
    }
    if any(step['name'] in storage_reader_steps for step in selected) and not args.dry_run:
        require_storage_raw(ticker)

    # Decide the raw path before announcing the step list, so what is printed is
    # what actually runs.
    raw_steps = {'upload-raw', 'ingest-raw'}
    if any(step['name'] in raw_steps for step in selected):
        require_local_raw(ticker)
        if not check_local_raw(ticker):
            # Nothing local to upload; let `ingest-raw` fetch from the API.
            selected = [step for step in selected if step['name'] != 'upload-raw']
        if not selected:
            raise CalculationError('NO_STEPS_SELECTED')

    print(f'Ticker: {ticker}')
    print(f'Steps : {", ".join(str(step["name"]) for step in selected)}')

    db: SupabaseRest | None = None
    run_ids: dict[str, str] = {}
    for step in selected:
        family = step.get('needs_run_id')
        if family and family not in run_ids:
            if db is None:
                db = SupabaseRest(
                    os.getenv('SUPABASE_URL', ''),
                    os.getenv('SUPABASE_SERVICE_ROLE_KEY', ''),
                )
            run_ids[family] = resolve_ingestion_run_id(db, ticker, str(family))
            print(f'Resolved {family} ingestion_run_id: {run_ids[family]}')

        command = render_command(step, ticker, run_ids)
        exit_code = run_step(command, dry_run=args.dry_run)
        if exit_code != 0:
            print(f'\nSTEP FAILED: {step["name"]} (exit {exit_code})')
            print(f'Resume with: python run_pipeline.py {ticker} --from-step {step["name"]}')
            return exit_code
        print(f'STEP OK: {step["name"]}')

    print(f'\nPipeline complete for {ticker}.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

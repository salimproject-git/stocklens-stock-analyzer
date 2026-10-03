#!/usr/bin/env python3
"""Persist daily valuation comparisons without running the intrinsic engine."""

from __future__ import annotations

import os
import sys
from pathlib import Path

SUPABASE_DIR = Path(__file__).resolve().parent
if str(SUPABASE_DIR) not in sys.path:
    sys.path.insert(0, str(SUPABASE_DIR))

from calculate_valuation import (  # noqa: E402
    REPO_ROOT,
    calculate_and_store_daily_status,
    load_env_file,
)
from calculation_v1_common import CalculationError, SupabaseRest  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ticker', required=True, help='IDX ticker, e.g. AUTO')
    parser.add_argument('--apply', action='store_true', help='Persist daily status (default is read-only dry-run).')
    args = parser.parse_args(argv)
    ticker = args.ticker.strip().upper().removesuffix('.JK')
    load_env_file(REPO_ROOT / '.env')
    db = SupabaseRest(os.getenv('SUPABASE_URL', ''), os.getenv('SUPABASE_SERVICE_ROLE_KEY', ''))
    if not args.apply:
        raise CalculationError('DAILY_STATUS_DRY_RUN_REQUIRES_APPLY_FOR_LIVE_READ')
    run_id = calculate_and_store_daily_status(db, ticker)
    print(f'Daily valuation status persisted: ticker={ticker}; run_id={run_id}')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except CalculationError as error:
        print(f'FAILED: {error}', file=sys.stderr)
        raise SystemExit(1) from error
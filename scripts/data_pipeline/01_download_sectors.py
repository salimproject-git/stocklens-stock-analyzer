#!/usr/bin/env python3
"""
01_download_sectors.py
======================

STEP 1 ONLY:
Download Sectors.app data AS-IS and store raw responses locally.

NO Excel mapping happens here.
NO conversion to template columns happens here.

Run one task at a time:
    python .\\scripts\\data_pipeline\\01_download_sectors.py ERAA --task info
    python .\\scripts\\data_pipeline\\01_download_sectors.py ERAA --task annual
    python .\\scripts\\data_pipeline\\01_download_sectors.py ERAA --task dividend
    python .\\scripts\\data_pipeline\\01_download_sectors.py ERAA --task quarterly-dates
    python .\\scripts\\data_pipeline\\01_download_sectors.py ERAA --task quarterly
    python .\\scripts\\data_pipeline\\01_download_sectors.py ERAA --task daily

Or run everything in sequence:
    python .\\scripts\\data_pipeline\\01_download_sectors.py ERAA --task all

Daily first-run logic:
    - start from today's date
    - move backwards in max 90-day windows
    - save every non-empty API response AS-IS
    - stop when:
        * data reaches MIN_DATE, OR
        * API returns an empty window twice consecutively
          (one empty window is treated as a possible gap)
    - if existing local data is reached, stop historical crawl there

Daily subsequent run:
    - detect latest local daily date
    - download only newer dates up to today
    - still use max 90-day windows

API key:
    Set SECTORS_API_KEY as an environment variable.

PowerShell:
    $env:SECTORS_API_KEY="YOUR_API_KEY"

CMD:
    set SECTORS_API_KEY=YOUR_API_KEY
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests


# ============================================================
# CONFIG
# ============================================================

BASE_URL = "https://api.sectors.app/v2"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = PROJECT_ROOT / "Data" / "Raw"

# User wants daily history starting from 2020.
DEFAULT_MIN_DATE = "2020-01-01"

# Sectors daily API: max 90 calendar days per request.
MAX_WINDOW_DAYS = 90

# Small pause between API requests.
SLEEP_SECONDS = 0.5

# Only request the sections needed by the current workbook.
# Each requested Company Report section costs 1 API credit.
COMPANY_REPORT_SECTION_MAP = {
    "info": ["overview"],
    "annual": ["financials"],
    "dividend": ["dividend"],
}


# ============================================================
# BASIC HELPERS
# ============================================================

def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def today_date() -> date:
    return date.today()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)

    temp_path = path.with_suffix(path.suffix + ".tmp")

    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )

    temp_path.replace(path)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def sleep_between_calls() -> None:
    if SLEEP_SECONDS > 0:
        time.sleep(SLEEP_SECONDS)


def get_api_key() -> str:
    api_key = os.getenv("SECTORS_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError(
            "SECTORS_API_KEY belum di-set.\n\n"
            "PowerShell:\n"
            '$env:SECTORS_API_KEY="YOUR_API_KEY"\n\n'
            "CMD:\n"
            "set SECTORS_API_KEY=YOUR_API_KEY"
        )

    return api_key


# ============================================================
# PATHS
# ============================================================

def ticker_root(data_root: Path, symbol: str) -> Path:
    return data_root / symbol.upper()


def manifest_path(data_root: Path, symbol: str) -> Path:
    return ticker_root(data_root, symbol) / "manifest.json"


def company_report_path(
    data_root: Path,
    symbol: str,
    task: str,
) -> Path:
    return ticker_root(data_root, symbol) / f"company_report_{task}.json"


def quarterly_dates_path(
    data_root: Path,
    symbol: str,
) -> Path:
    return ticker_root(data_root, symbol) / "quarterly_financial_dates.json"


def quarterly_dir(
    data_root: Path,
    symbol: str,
) -> Path:
    return ticker_root(data_root, symbol) / "quarterly"


def daily_dir(
    data_root: Path,
    symbol: str,
) -> Path:
    return ticker_root(data_root, symbol) / "daily"


# ============================================================
# MANIFEST
# ============================================================

def load_manifest(
    data_root: Path,
    symbol: str,
) -> dict[str, Any]:
    path = manifest_path(data_root, symbol)

    if not path.exists():
        return {
            "symbol": symbol.upper(),
            "collector_version": "1.1",
            "updated_at": None,
            "sources": {},
        }

    return read_json(path)


def save_manifest(
    data_root: Path,
    symbol: str,
    manifest: dict[str, Any],
) -> None:
    manifest["symbol"] = symbol.upper()
    manifest["collector_version"] = "1.1"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")

    write_json(
        manifest_path(data_root, symbol),
        manifest,
    )


# ============================================================
# HTTP CLIENT
# ============================================================

class SectorsClient:
    def __init__(self, api_key: str) -> None:
        self.session = requests.Session()

        self.session.headers.update(
            {
                "Authorization": api_key,
                "Accept": "application/json",
                "User-Agent": "StockAnalyzer-SectorsCollector/1.1",
            }
        )

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        max_retries: int = 4,
    ) -> Any:
        """
        GET with automatic retry/backoff for HTTP 429.

        Backoff:
            retry #1 -> 5 sec
            retry #2 -> 10 sec
            retry #3 -> 20 sec
            retry #4 -> 40 sec

        Other HTTP errors are raised immediately.
        """
        url = f"{BASE_URL}{endpoint}"

        retry_delays = [5, 10, 20, 40]
        attempt = 0

        while True:
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=60,
                )
            except requests.exceptions.RequestException as error:
                print("\n--- REQUEST ERROR ---")
                print(f"URL      : {url}")
                print(f"Error    : {error}")
                print("---------------------\n")
                raise

            if response.status_code == 429:
                if attempt >= max_retries:
                    print("\n--- API RATE LIMIT ---")
                    print(f"URL      : {response.url}")
                    print("Retry    : exhausted")
                    print("Action   : stopping this task")
                    print("----------------------\n")
                    response.raise_for_status()

                delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                attempt += 1

                print(
                    f"\n    RATE LIMIT (429). "
                    f"Waiting {delay}s before retry "
                    f"{attempt}/{max_retries}..."
                )

                time.sleep(delay)
                continue

            if not response.ok:
                print("\n--- API ERROR ---")
                print(f"URL      : {response.url}")
                print(f"HTTP     : {response.status_code}")
                print(f"Response : {response.text[:3000]}")
                print("-----------------\n")

            response.raise_for_status()
            return response.json()


# ============================================================
# COMPANY REPORT
# ============================================================

def download_company_report_section(
    client: SectorsClient,
    symbol: str,
    data_root: Path,
    task: str,
    force: bool,
    manifest: dict[str, Any],
) -> None:
    sections = COMPANY_REPORT_SECTION_MAP[task]

    path = company_report_path(
        data_root,
        symbol,
        task,
    )

    label = {
        "info": "Company Information",
        "annual": "Annual Financials",
        "dividend": "Dividend",
    }[task]

    print(f"[{label}]")

    if path.exists() and not force:
        print(f"    SKIP - {path.name} sudah ada")

        manifest.setdefault("sources", {})[task] = {
            "status": "cached",
            "file": str(path),
            "sections": sections,
        }

        return

    print(
        f"    GET Company Report "
        f"(sections={','.join(sections)})..."
    )

    data = client.get(
        f"/company/report/{symbol.upper()}/",
        params={
            "sections": ",".join(sections),
        },
    )

    # IMPORTANT:
    # Save the API response AS-IS.
    write_json(path, data)

    print("    OK")

    manifest.setdefault("sources", {})[task] = {
        "status": "ok",
        "file": str(path),
        "sections": sections,
    }

    sleep_between_calls()


# ============================================================
# QUARTERLY DATES
# ============================================================

def download_quarterly_dates(
    client: SectorsClient,
    symbol: str,
    data_root: Path,
    force: bool,
    manifest: dict[str, Any],
) -> Any:
    path = quarterly_dates_path(
        data_root,
        symbol,
    )

    print("[Quarterly Financial Dates]")

    if path.exists() and not force:
        print("    SKIP - quarterly_financial_dates.json sudah ada")

        data = read_json(path)

        manifest.setdefault("sources", {})["quarterly_dates"] = {
            "status": "cached",
            "file": str(path),
        }

        return data

    print("    GET quarterly financial dates...")

    data = client.get(
        f"/company/get_quarterly_financial_dates/{symbol.upper()}/"
    )

    # IMPORTANT:
    # Save API response AS-IS.
    write_json(path, data)

    print("    OK")

    manifest.setdefault("sources", {})["quarterly_dates"] = {
        "status": "ok",
        "file": str(path),
    }

    sleep_between_calls()

    return data


def extract_quarterly_report_dates(
    raw_data: Any,
) -> list[str]:
    """
    Read report_date values from the Quarterly Financial Dates response.

    The collector accepts a few common shapes because the date endpoint
    response format may be represented as:
        ["2026-06-30", ...]
    or
        [{"date": "2026-06-30"}, ...]
    or
        {"dates": ["2026-06-30", ...]}
    or similar.

    This function ONLY reads the raw response.
    It does NOT modify the saved raw JSON.
    """
    found: set[str] = set()

    preferred_keys = {
        "report_date",
        "date",
        "reportDate",
    }

    def visit(value: Any, key_hint: str | None = None) -> None:
        if isinstance(value, str):
            try:
                parsed = parse_date(value)
            except ValueError:
                return

            normalized = parsed.isoformat()

            # If inside a known date field, accept it immediately.
            if key_hint in preferred_keys:
                found.add(normalized)

            # Also accept plain YYYY-MM-DD strings in list responses.
            elif value == normalized:
                found.add(normalized)

        elif isinstance(value, list):
            for item in value:
                visit(item, None)

        elif isinstance(value, dict):
            for key, item in value.items():
                visit(item, str(key))

    visit(raw_data)

    return sorted(found, reverse=True)


# ============================================================
# QUARTERLY FINANCIALS
# ============================================================

def quarterly_file_path(
    data_root: Path,
    symbol: str,
    report_date: str,
) -> Path:
    return quarterly_dir(
        data_root,
        symbol,
    ) / f"{report_date}.json"


def download_quarterly_financials(
    client: SectorsClient,
    symbol: str,
    data_root: Path,
    force: bool,
    manifest: dict[str, Any],
) -> None:
    print("[Quarterly Financials]")

    dates_path = quarterly_dates_path(
        data_root,
        symbol,
    )

    # IMPORTANT:
    # Quarterly financials never call the dates endpoint implicitly.
    # User runs --task quarterly-dates first.
    if not dates_path.exists():
        print(
            "    STOP - quarterly_financial_dates.json belum ada."
        )
        print(
            "    Jalankan dulu:"
        )
        print(
            f"    python 01_download_sectors.py {symbol} "
            "--task quarterly-dates"
        )
        return

    raw_dates = read_json(dates_path)

    report_dates = extract_quarterly_report_dates(
        raw_dates
    )

    if not report_dates:
        raise RuntimeError(
            "Tidak menemukan report_date YYYY-MM-DD "
            "di quarterly_financial_dates.json."
        )

    print(
        f"    Total report dates tersedia: "
        f"{len(report_dates)}"
    )

    ensure_dir(
        quarterly_dir(
            data_root,
            symbol,
        )
    )

    quarterly_manifest = (
        manifest
        .setdefault("sources", {})
        .setdefault("quarterly", {})
    )

    total = len(report_dates)

    for index, report_date in enumerate(
        report_dates,
        start=1,
    ):
        output_path = quarterly_file_path(
            data_root,
            symbol,
            report_date,
        )

        if output_path.exists() and not force:
            print(
                f"    [{index:02d}/{total:02d}] "
                f"{report_date} -> SKIP"
            )

            quarterly_manifest[report_date] = {
                "status": "cached",
                "file": str(output_path),
            }

            continue

        print(
            f"    [{index:02d}/{total:02d}] "
            f"{report_date} -> GET...",
            end=" ",
        )

        # Valid report_date comes from the official dates endpoint.
        data = client.get(
            f"/financials/quarterly/{symbol.upper()}/",
            params={
                "report_date": report_date,
                "approx": "true",
            },
        )

        # IMPORTANT:
        # Save API response AS-IS.
        write_json(
            output_path,
            data,
        )

        print("OK")

        quarterly_manifest[report_date] = {
            "status": "ok",
            "file": str(output_path),
        }

        sleep_between_calls()


# ============================================================
# DAILY PRICE
# ============================================================

def create_date_windows(
    start_date: date,
    end_date: date,
) -> list[tuple[date, date]]:
    if start_date > end_date:
        return []

    windows: list[tuple[date, date]] = []

    current_date = start_date

    while current_date <= end_date:
        window_end = min(
            current_date + timedelta(days=MAX_WINDOW_DAYS - 1),
            end_date,
        )

        windows.append(
            (
                current_date,
                window_end,
            )
        )

        current_date = window_end + timedelta(days=1)

    return windows


def daily_window_path(
    data_root: Path,
    symbol: str,
    window_start: date,
    window_end: date,
) -> Path:
    filename = (
        f"{window_start.isoformat()}"
        f"_{window_end.isoformat()}.json"
    )

    return daily_dir(
        data_root,
        symbol,
    ) / filename


def extract_dates_from_daily_response(
    data: Any,
) -> list[date]:
    dates: list[date] = []

    if not isinstance(data, list):
        return dates

    for record in data:
        if not isinstance(record, dict):
            continue

        raw_date = record.get("date")

        if not raw_date:
            continue

        try:
            dates.append(
                parse_date(str(raw_date))
            )
        except ValueError:
            continue

    return dates


def scan_local_daily_dates(
    data_root: Path,
    symbol: str,
) -> tuple[date | None, date | None, int]:
    """
    Return:
        earliest local date
        latest local date
        total raw records seen
    """
    folder = daily_dir(
        data_root,
        symbol,
    )

    if not folder.exists():
        return None, None, 0

    earliest: date | None = None
    latest: date | None = None
    total_records = 0

    for path in sorted(folder.glob("*.json")):
        try:
            data = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue

        for record_date in extract_dates_from_daily_response(data):
            total_records += 1

            if earliest is None or record_date < earliest:
                earliest = record_date

            if latest is None or record_date > latest:
                latest = record_date

    return earliest, latest, total_records


def fetch_daily_window(
    client: SectorsClient,
    symbol: str,
    window_start: date,
    window_end: date,
) -> Any:
    return client.get(
        f"/daily/{symbol.upper()}/",
        params={
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
        },
    )


def daily_first_run_backward(
    client: SectorsClient,
    symbol: str,
    data_root: Path,
    min_date: date,
    force: bool,
    manifest: dict[str, Any],
) -> None:
    """
    First-run historical discovery:
        today -> backwards

    Stop conditions:
        1. earliest fetched date <= min_date
        2. two consecutive empty windows
        3. existing local historical date is reached
    """
    ensure_dir(
        daily_dir(
            data_root,
            symbol,
        )
    )

    today = today_date()

    # If there is already local daily data, use its earliest date
    # as the overlap boundary.
    local_earliest, local_latest, local_count = scan_local_daily_dates(
        data_root,
        symbol,
    )

    if local_count:
        print(
            f"    Local earliest date : "
            f"{local_earliest}"
        )
        print(
            f"    Local latest date   : "
            f"{local_latest}"
        )
        print(
            f"    Local raw records   : "
            f"{local_count}"
        )

    current_end = today
    empty_streak = 0

    saved_windows = 0

    while current_end >= min_date:
        current_start = max(
            min_date,
            current_end - timedelta(days=MAX_WINDOW_DAYS - 1),
        )

        output_path = daily_window_path(
            data_root,
            symbol,
            current_start,
            current_end,
        )

        # If exact window exists, do not re-hit it.
        if output_path.exists() and not force:
            print(
                f"    {current_start} -> {current_end} "
                f"-> SKIP (window sudah ada)"
            )

            try:
                existing_data = read_json(output_path)
            except (OSError, json.JSONDecodeError):
                existing_data = []

            dates = extract_dates_from_daily_response(
                existing_data
            )

            if dates:
                earliest_in_window = min(dates)

                if earliest_in_window <= min_date:
                    print(
                        f"    Reached MIN_DATE via local window: "
                        f"{earliest_in_window}"
                    )
                    break

                if (
                    local_earliest is not None
                    and earliest_in_window <= local_earliest
                ):
                    print(
                        "    Reached existing local history. STOP."
                    )
                    break

            current_end = current_start - timedelta(days=1)
            continue

        print(
            f"    GET {current_start} -> {current_end}...",
            end=" ",
        )

        data = fetch_daily_window(
            client,
            symbol,
            current_start,
            current_end,
        )

        response_dates = extract_dates_from_daily_response(
            data
        )

        if not response_dates:
            print("EMPTY")

            empty_streak += 1

            if empty_streak >= 2:
                print(
                    "    2 consecutive empty windows. "
                    "Assume history boundary. STOP."
                )
                break

        else:
            empty_streak = 0

            write_json(
                output_path,
                data,
            )

            earliest_in_window = min(response_dates)
            latest_in_window = max(response_dates)

            print(
                f"OK ({len(response_dates)} records; "
                f"{earliest_in_window} -> {latest_in_window})"
            )

            saved_windows += 1

            manifest.setdefault("sources", {}).setdefault(
                "daily",
                {},
            )[
                f"{current_start.isoformat()}_{current_end.isoformat()}"
            ] = {
                "status": "ok",
                "file": str(output_path),
                "records": len(response_dates),
                "first_record_date": earliest_in_window.isoformat(),
                "last_record_date": latest_in_window.isoformat(),
            }

            # If API returned data overlapping existing local history,
            # stop at the boundary. This is the user's requested logic.
            if (
                local_earliest is not None
                and earliest_in_window <= local_earliest
            ):
                print(
                    f"    Existing local date reached "
                    f"({local_earliest}). STOP."
                )
                break

            # If we already reached requested minimum, stop.
            if earliest_in_window <= min_date:
                print(
                    f"    Reached MIN_DATE "
                    f"({min_date}). STOP."
                )
                break

            sleep_between_calls()

        current_end = current_start - timedelta(days=1)

    print(
        f"    Backward crawl selesai. "
        f"Windows baru disimpan: {saved_windows}"
    )


def daily_incremental_forward(
    client: SectorsClient,
    symbol: str,
    data_root: Path,
    force: bool,
    manifest: dict[str, Any],
) -> None:
    """
    Existing local history:
        latest local date -> today

    Only fetch data after the latest local date.
    """
    local_earliest, local_latest, local_count = scan_local_daily_dates(
        data_root,
        symbol,
    )

    if local_latest is None:
        return

    today = today_date()

    if local_latest >= today:
        print(
            f"    Daily sudah up to date sampai "
            f"{local_latest}."
        )
        return

    start_date = local_latest + timedelta(days=1)

    print(
        f"    Existing latest date : {local_latest}"
    )
    print(
        f"    Incremental range    : "
        f"{start_date} -> {today}"
    )

    windows = create_date_windows(
        start_date,
        today,
    )

    for index, (window_start, window_end) in enumerate(
        windows,
        start=1,
    ):
        output_path = daily_window_path(
            data_root,
            symbol,
            window_start,
            window_end,
        )

        if output_path.exists() and not force:
            print(
                f"    [{index:02d}/{len(windows):02d}] "
                f"{window_start} -> {window_end} "
                f"-> SKIP"
            )
            continue

        print(
            f"    [{index:02d}/{len(windows):02d}] "
            f"{window_start} -> {window_end} -> GET...",
            end=" ",
        )

        data = fetch_daily_window(
            client,
            symbol,
            window_start,
            window_end,
        )

        response_dates = extract_dates_from_daily_response(
            data
        )

        if not response_dates:
            print("EMPTY")
        else:
            write_json(
                output_path,
                data,
            )

            earliest_in_window = min(response_dates)
            latest_in_window = max(response_dates)

            print(
                f"OK ({len(response_dates)} records; "
                f"{earliest_in_window} -> {latest_in_window})"
            )

        sleep_between_calls()


def download_daily_prices(
    client: SectorsClient,
    symbol: str,
    data_root: Path,
    min_date: date,
    force: bool,
    manifest: dict[str, Any],
) -> None:
    print("[Daily Prices]")

    ensure_dir(
        daily_dir(
            data_root,
            symbol,
        )
    )

    local_earliest, local_latest, local_count = scan_local_daily_dates(
        data_root,
        symbol,
    )

    if local_count == 0:
        print(
            f"    No local daily data. "
            f"Historical crawl from MAX -> {min_date}"
        )

        daily_first_run_backward(
            client,
            symbol,
            data_root,
            min_date,
            force,
            manifest,
        )

    else:
        # User requested max->min discovery for the initial population.
        # Once local data exists, incremental update should be forward.
        daily_incremental_forward(
            client,
            symbol,
            data_root,
            force,
            manifest,
        )


# ============================================================
# TASK DISPATCH
# ============================================================

def run_task(
    task: str,
    client: SectorsClient,
    symbol: str,
    data_root: Path,
    min_date: date,
    force: bool,
    manifest: dict[str, Any],
) -> None:

    if task == "info":
        download_company_report_section(
            client,
            symbol,
            data_root,
            "info",
            force,
            manifest,
        )

    elif task == "annual":
        download_company_report_section(
            client,
            symbol,
            data_root,
            "annual",
            force,
            manifest,
        )

    elif task == "dividend":
        download_company_report_section(
            client,
            symbol,
            data_root,
            "dividend",
            force,
            manifest,
        )

    elif task == "quarterly-dates":
        download_quarterly_dates(
            client,
            symbol,
            data_root,
            force,
            manifest,
        )

    elif task == "quarterly":
        download_quarterly_financials(
            client,
            symbol,
            data_root,
            force,
            manifest,
        )

    elif task == "daily":
        download_daily_prices(
            client,
            symbol,
            data_root,
            min_date,
            force,
            manifest,
        )

    else:
        raise ValueError(f"Unknown task: {task}")


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sectors.app RAW Collector - Step 1",
    )

    parser.add_argument(
        "symbol",
        help="IDX ticker, e.g. ERAA",
    )

    parser.add_argument(
        "--task",
        required=True,
        choices=[
            "info",
            "annual",
            "dividend",
            "quarterly-dates",
            "quarterly",
            "daily",
            "all",
        ],
        help="Run one task only, or all tasks in sequence.",
    )

    parser.add_argument(
        "--start-date",
        default=DEFAULT_MIN_DATE,
        help=f"Minimum daily history date (default: {DEFAULT_MIN_DATE})",
    )

    parser.add_argument(
        "--data-root",
        default=str(DEFAULT_DATA_ROOT),
        help=f"Raw data root (default: {DEFAULT_DATA_ROOT})",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Redownload existing raw files for the selected task.",
    )

    args = parser.parse_args()

    symbol = args.symbol.upper().replace(".JK", "")
    data_root = Path(args.data_root)

    min_date = parse_date(args.start_date)

    api_key = get_api_key()
    client = SectorsClient(api_key)

    ensure_dir(
        ticker_root(
            data_root,
            symbol,
        )
    )

    manifest = load_manifest(
        data_root,
        symbol,
    )

    print("=" * 72)
    print("SECTORS.APP RAW COLLECTOR - STEP 1")
    print("=" * 72)
    print(f"Ticker    : {symbol}")
    print(f"Task      : {args.task}")
    print(f"Data root : {data_root}")
    print(f"Min date  : {min_date}")
    print(f"Force     : {args.force}")
    print("=" * 72)

    if args.task == "all":
        # Intentionally sequential so each stage can be inspected.
        tasks = [
            "info",
            "annual",
            "dividend",
            "quarterly-dates",
            "quarterly",
            "daily",
        ]

        for task in tasks:
            print("\n" + "-" * 72)
            print(f"RUN TASK: {task}")
            print("-" * 72)

            run_task(
                task,
                client,
                symbol,
                data_root,
                min_date,
                args.force,
                manifest,
            )

            save_manifest(
                data_root,
                symbol,
                manifest,
            )

    else:
        run_task(
            args.task,
            client,
            symbol,
            data_root,
            min_date,
            args.force,
            manifest,
        )

        save_manifest(
            data_root,
            symbol,
            manifest,
        )

    print("\n" + "=" * 72)
    print("TASK SELESAI")
    print(f"RAW DATA : {ticker_root(data_root, symbol)}")
    print("=" * 72)


if __name__ == "__main__":
    main()
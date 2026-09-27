"""
02_convert_sectors_raw.py
STEP 2 - Convert Sectors.app RAW JSON into the legacy template shape.

Important:
- READ ONLY from Data/Raw/{TICKER}
- DOES NOT modify the Excel workbook
- DOES NOT call the Sectors API
- Produces CSV + JSON audit files under Data\\Converted\\{TICKER}
- Keeps source values raw enough to audit, while applying only the agreed
  template unit conversions and sign convention.

Run from the project root:
    D:\\Stock Analyzer

Examples:
    python .\\scripts\\data_pipeline\\02_convert_sectors_raw.py
        -> Process ALL valid tickers in Data\\Raw

    python .\\scripts\\data_pipeline\\02_convert_sectors_raw.py ERAA
        -> Process ERAA only

    python .\\scripts\\data_pipeline\\02_convert_sectors_raw.py ERAA ARII IPOL
        -> Process selected tickers

Outputs per ticker:
    Data\\Converted\\TICKER\\
        Stock_Information.csv
        Stock_Database.csv
        Stock_Database_Quarter.csv
        Price_History.csv
        Conversion_Audit.csv
        conversion_manifest.json
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


# ============================================================================
# CONFIG
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_ROOT = PROJECT_ROOT / "Data" / "Raw"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "Data" / "Converted"


# ============================================================================
# OUTPUT HEADERS
# ============================================================================

ANNUAL_HEADERS = [
    "Ticker",
    "Year",
    "Revenue (M Rp)",
    "HPP COGS (M Rp)",
    "Interest Expenses (M Rp)",
    "Net Income (M Rp)",
    "OCF (M Rp)",
    "DPS (Rp)",
    "Current Assets (M Rp)",
    "Current Liabilities (M Rp)",
    "Total Liabilities (M Rp)",
    "Total Equity (M Rp)",
    "Shares (Juta)",
    "Stock Price (Rp)",
    "Avg Vol (3M)",
]

QUARTER_HEADERS = [
    "Ticker",
    "Data Available Date",
    "Year",
    "Quarter",
    "Revenue (M Rp)",
    "HPP COGS (M Rp)",
    "Interest Expenses (M Rp)",
    "Net Income (M Rp)",
    "OCF (M Rp)",
    "Current Assets (M Rp)",
    "Current Liabilities (M Rp)",
    "Total Liabilities (M Rp)",
    "Total Equity (M Rp)",
    "Shares (Juta)",
    "Avg Vol (3M)",
    "Stock Price (Rp)",
]

INFO_HEADERS = [
    "Ticker",
    "Company Name",
    "Sector",
    "Subsector",
]

PRICE_HEADERS = [
    "Ticker",
    "Date",
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "Market Cap",
]

AUDIT_HEADERS = [
    "Ticker",
    "Dataset",
    "Period",
    "Target Field",
    "Source Field",
    "Source Value",
    "Converted Value",
    "Rule",
    "Status",
    "Note",
]


# ============================================================================
# GENERIC HELPERS
# ============================================================================

def load_json(path: Path) -> Any:
    """
    Load JSON file using UTF-8 encoding.
    """
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def first_not_none(*values: Any) -> Any:
    """
    Return the first value that is not None.
    """
    for value in values:
        if value is not None:
            return value
    return None


def to_m_rp(value: Any) -> Optional[float]:
    """
    Convert Rupiah absolute value into Million Rp.

    Example:
        1,000,000,000 Rp -> 1,000 M Rp
    """
    if value is None:
        return None

    return float(value) / 1_000_000_000.0


def to_million_shares(value: Any) -> Optional[float]:
    """
    Convert number of shares into million shares.

    Example:
        2,502,100,000 shares -> 2,502.1 Juta
    """
    if value is None:
        return None

    return float(value) / 1_000_000.0


def negative_abs_m_rp(value: Any) -> Optional[float]:
    """
    Convert source value into negative Million Rp.

    Used for:
        HPP / COGS

    Regardless of source sign, output is always negative.

    Example:
        3,000,000,000 -> -3,000
        -3,000,000,000 -> -3,000
    """
    if value is None:
        return None

    return -abs(float(value) / 1_000_000_000.0)


def write_csv(
    path: Path,
    headers: List[str],
    rows: Iterable[Dict[str, Any]],
) -> None:
    """
    Write rows to CSV using UTF-8 BOM so Excel opens it nicely.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=headers,
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    h: row.get(h)
                    for h in headers
                }
            )


# ============================================================================
# AUDIT
# ============================================================================

def add_audit(
    audits: List[Dict[str, Any]],
    ticker: str,
    dataset: str,
    period: Any,
    target_field: str,
    source_field: str,
    source_value: Any,
    converted_value: Any,
    rule: str,
    status: str = "OK",
    note: str = "",
) -> None:
    """
    Add one conversion audit record.
    """

    audits.append(
        {
            "Ticker": ticker,
            "Dataset": dataset,
            "Period": period,
            "Target Field": target_field,
            "Source Field": source_field,
            "Source Value": source_value,
            "Converted Value": converted_value,
            "Rule": rule,
            "Status": status,
            "Note": note,
        }
    )


# ============================================================================
# ANNUAL DATA
# ============================================================================

def load_annual(raw_dir: Path) -> List[Dict[str, Any]]:
    """
    Load annual financial data.
    """

    path = raw_dir / "company_report_annual.json"

    data = load_json(path)

    financials = data.get("financials", {})

    hist = financials.get(
        "historical_financials",
        [],
    )

    return sorted(
        hist,
        key=lambda x: int(x.get("year", 0)),
    )


# ============================================================================
# DIVIDEND
# ============================================================================

def load_dividends(raw_dir: Path) -> Dict[str, Any]:
    """
    Load dividend data if available.
    """

    path = raw_dir / "company_report_dividend.json"

    if not path.exists():
        return {}

    data = load_json(path)

    return data.get(
        "dividend",
        {},
    ) or {}


def dividend_by_year(
    dividend_data: Dict[str, Any],
) -> Dict[int, Optional[float]]:
    """
    Convert dividend history into:

        {
            2024: 91,
            2025: 120,
            ...
        }
    """

    result: Dict[int, Optional[float]] = {}

    historical = (
        dividend_data.get("historical_dividends")
        or {}
    )

    for year_text, payload in historical.items():

        try:
            year = int(year_text)
        except (
            TypeError,
            ValueError,
        ):
            continue

        total = None

        if isinstance(payload, dict):
            total = payload.get(
                "total_dividend"
            )

        result[year] = total

    return result


# ============================================================================
# COMPANY INFORMATION
# ============================================================================

def load_info(raw_dir: Path) -> Dict[str, Any]:
    """
    Load company identity information.
    """

    data = load_json(
        raw_dir / "company_report_info.json"
    )

    overview = (
        data.get("overview", {})
        or {}
    )

    return {
        "Ticker": (
            data.get("symbol", "")
            .replace(".JK", "")
        ),
        "Company Name": data.get(
            "company_name"
        ),
        "Sector": overview.get(
            "sector"
        ),
        "Subsector": overview.get(
            "sub_sector"
        ),
    }


# ============================================================================
# QUARTER DATES
# ============================================================================

def load_quarter_dates(
    raw_dir: Path,
) -> Dict[tuple[int, str], str]:
    """
    Load official quarterly report dates.

    Expected format:

        {
            "2025": [
                ["2025-03-31", "q1"],
                ["2025-06-30", "q2"]
            ]
        }
    """

    path = raw_dir / "quarterly_financial_dates.json"

    if not path.exists():
        return {}

    data = load_json(path)

    result: Dict[
        tuple[int, str],
        str
    ] = {}

    for year_text, entries in data.items():

        year = int(year_text)

        for entry in entries:

            if (
                not isinstance(entry, list)
                or len(entry) < 2
            ):
                continue

            report_date = entry[0]

            quarter = str(
                entry[1]
            ).lower()

            result[
                (year, quarter)
            ] = report_date

    return result


# ============================================================================
# QUARTERLY FINANCIALS
# ============================================================================

def load_quarters(
    raw_dir: Path,
) -> List[Dict[str, Any]]:
    """
    Load all quarterly JSON files.
    """

    qdir = raw_dir / "quarterly"

    if not qdir.exists():
        return []

    rows: List[
        Dict[str, Any]
    ] = []

    for path in sorted(
        qdir.glob("*.json")
    ):

        try:
            payload = load_json(path)

        except json.JSONDecodeError:
            continue

        # Current Sectors response is normally
        # a list containing one object.
        if isinstance(payload, list):

            items = payload

        elif isinstance(payload, dict):

            items = (
                payload.get("data")
                or payload.get("financials")
                or [payload]
            )

        else:

            items = []

        for item in items:

            if isinstance(item, dict):

                row = dict(item)

                row["_report_date"] = (
                    path.stem
                )

                rows.append(row)

    rows.sort(
        key=lambda x: str(
            x.get("_report_date", "")
        )
    )

    return rows


def quarter_from_date(
    report_date: str,
) -> str:
    """
    Convert report date to quarter.
    """

    month = int(
        report_date[5:7]
    )

    if month == 3:
        return "q1"

    if month == 6:
        return "q2"

    if month == 9:
        return "q3"

    if month == 12:
        return "q4"

    return ""


# ============================================================================
# DAILY PRICE DATA
# ============================================================================

def annual_price_rows(
    raw_dir: Path,
    ticker: str,
) -> List[Dict[str, Any]]:
    """
    Create annual price summary from daily data.

    Stock Price:
        Last daily close available in the year.

    Avg Vol (3M):
        Currently simple mean of all daily volume
        records available in that calendar year.

    This is kept as the original audit placeholder.
    """

    daily_dir = raw_dir / "daily"

    records: List[
        Dict[str, Any]
    ] = []

    for path in sorted(
        daily_dir.glob("*.json")
    ):

        payload = load_json(path)

        if isinstance(payload, list):

            items = payload

        elif isinstance(payload, dict):

            items = (
                payload.get("data")
                or []
            )

        else:

            items = []

        for item in items:

            if not isinstance(item, dict):
                continue

            row = dict(item)

            if row.get("date"):
                records.append(row)

    # Deduplicate by date.
    by_date: Dict[
        str,
        Dict[str, Any]
    ] = {}

    for r in records:

        by_date[
            str(r["date"])
        ] = r

    yearly: Dict[
        int,
        List[Dict[str, Any]]
    ] = {}

    for d_text, r in by_date.items():

        try:
            year = int(
                str(d_text)[:4]
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

        yearly.setdefault(
            year,
            []
        ).append(r)

    result = []

    for year in sorted(yearly):

        items = sorted(
            yearly[year],
            key=lambda x: str(
                x.get("date")
            )
        )

        last = (
            items[-1]
            if items
            else {}
        )

        volumes = [
            x.get("volume")
            for x in items
            if isinstance(
                x.get("volume"),
                (int, float),
            )
        ]

        avg_vol = (
            sum(volumes) / len(volumes)
            if volumes
            else None
        )

        result.append(
            {
                "Ticker": ticker,
                "Year": year,
                "Stock Price (Rp)": last.get(
                    "close"
                ),
                "Avg Vol (3M)": avg_vol,
            }
        )

    return result


def raw_price_history(
    raw_dir: Path,
    ticker: str,
) -> List[Dict[str, Any]]:
    """
    Convert daily raw price records into
    Price_History.csv.
    """

    daily_dir = raw_dir / "daily"

    records: Dict[
        str,
        Dict[str, Any]
    ] = {}

    for path in sorted(
        daily_dir.glob("*.json")
    ):

        payload = load_json(path)

        if isinstance(payload, list):

            items = payload

        elif isinstance(payload, dict):

            items = (
                payload.get("data")
                or []
            )

        else:

            items = []

        for item in items:

            if (
                not isinstance(
                    item,
                    dict,
                )
                or not item.get("date")
            ):
                continue

            d = str(
                item["date"]
            )

            records[d] = {
                "Ticker": ticker,
                "Date": d,
                "Open": item.get(
                    "open"
                ),
                "High": item.get(
                    "high"
                ),
                "Low": item.get(
                    "low"
                ),
                "Close": item.get(
                    "close"
                ),
                "Volume": item.get(
                    "volume"
                ),
                "Market Cap": item.get(
                    "market_cap"
                ),
            }

    return [
        records[d]
        for d in sorted(records)
    ]


# ============================================================================
# VALID RAW TICKER DETECTION
# ============================================================================

def is_valid_raw_ticker_folder(
    folder: Path,
) -> bool:
    """
    Check whether a folder looks like a valid
    Sectors.app RAW ticker folder.

    We require the same core files that
    convert_ticker() requires.
    """

    required_files = [
        "company_report_info.json",
        "company_report_annual.json",
        "quarterly_financial_dates.json",
    ]

    return (
        folder.is_dir()
        and all(
            (folder / filename).exists()
            for filename in required_files
        )
    )


def discover_all_tickers(
    raw_root: Path,
) -> List[str]:
    """
    Discover all valid ticker folders
    under Data\\Raw.
    """

    if not raw_root.exists():

        raise FileNotFoundError(
            f"RAW root tidak ditemukan: "
            f"{raw_root}"
        )

    tickers = []

    for folder in raw_root.iterdir():

        if not folder.is_dir():
            continue

        if is_valid_raw_ticker_folder(
            folder
        ):
            tickers.append(
                folder.name.upper()
            )

    return sorted(tickers)


# ============================================================================
# MAIN CONVERSION
# ============================================================================

def convert_ticker(
    ticker: str,
    raw_root: Path,
    output_root: Path,
) -> Dict[str, Any]:
    """
    Convert one ticker from RAW -> Converted.
    """

    ticker = (
        ticker
        .upper()
        .replace(".JK", "")
    )

    raw_dir = (
        raw_root / ticker
    )

    out_dir = (
        output_root / ticker
    )

    out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ------------------------------------------------------------------------
    # Validate required RAW files
    # ------------------------------------------------------------------------

    required = [
        raw_dir
        / "company_report_info.json",

        raw_dir
        / "company_report_annual.json",

        raw_dir
        / "quarterly_financial_dates.json",
    ]

    missing = [
        str(p)
        for p in required
        if not p.exists()
    ]

    if missing:

        raise FileNotFoundError(
            f"{ticker}: RAW incomplete. "
            f"Missing: "
            + "; ".join(missing)
        )

    # ------------------------------------------------------------------------
    # Audit container
    # ------------------------------------------------------------------------

    audits: List[
        Dict[str, Any]
    ] = []

    # ------------------------------------------------------------------------
    # Company info
    # ------------------------------------------------------------------------

    info = load_info(
        raw_dir
    )

    write_csv(
        out_dir
        / "Stock_Information.csv",
        INFO_HEADERS,
        [info],
    )

    # ------------------------------------------------------------------------
    # Dividends
    # ------------------------------------------------------------------------

    dividends = dividend_by_year(
        load_dividends(raw_dir)
    )

    # ------------------------------------------------------------------------
    # Annual financials
    # ------------------------------------------------------------------------

    annual_raw = load_annual(
        raw_dir
    )

    yearly_prices = {
        r["Year"]: r
        for r in annual_price_rows(
            raw_dir,
            ticker,
        )
    }

    annual_rows: List[
        Dict[str, Any]
    ] = []

    for r in annual_raw:

        year = int(
            r["year"]
        )

        dps = dividends.get(
            year
        )

        row = {
            "Ticker": ticker,
            "Year": year,

            "Revenue (M Rp)":
                to_m_rp(
                    r.get("revenue")
                ),

            "HPP COGS (M Rp)":
                negative_abs_m_rp(
                    r.get(
                        "cost_of_revenue"
                    )
                ),

            "Interest Expenses (M Rp)":
                to_m_rp(
                    r.get(
                        "interest_expense_non_operating"
                    )
                ),

            "Net Income (M Rp)":
                to_m_rp(
                    r.get("earnings")
                ),

            "OCF (M Rp)":
                to_m_rp(
                    r.get(
                        "operating_cash_flow"
                    )
                ),

            "DPS (Rp)": dps,

            "Current Assets (M Rp)":
                to_m_rp(
                    r.get(
                        "current_assets"
                    )
                ),

            "Current Liabilities (M Rp)":
                to_m_rp(
                    r.get(
                        "current_liabilities"
                    )
                ),

            "Total Liabilities (M Rp)":
                to_m_rp(
                    r.get(
                        "total_liabilities"
                    )
                ),

            "Total Equity (M Rp)":
                to_m_rp(
                    r.get(
                        "total_equity"
                    )
                ),

            "Shares (Juta)":
                to_million_shares(
                    r.get(
                        "outstanding_shares"
                    )
                ),

            "Stock Price (Rp)":
                yearly_prices.get(
                    year,
                    {},
                ).get(
                    "Stock Price (Rp)"
                ),

            "Avg Vol (3M)":
                yearly_prices.get(
                    year,
                    {},
                ).get(
                    "Avg Vol (3M)"
                ),
        }

        annual_rows.append(
            row
        )

        # --------------------------------------------------------------------
        # Audit annual fields
        # --------------------------------------------------------------------

        add_audit(
            audits,
            ticker,
            "annual",
            year,
            "Revenue (M Rp)",
            "revenue",
            r.get("revenue"),
            row["Revenue (M Rp)"],
            "source / 1e9",
        )

        add_audit(
            audits,
            ticker,
            "annual",
            year,
            "HPP COGS (M Rp)",
            "cost_of_revenue",
            r.get(
                "cost_of_revenue"
            ),
            row[
                "HPP COGS (M Rp)"
            ],
            "-ABS(source / 1e9)",
        )

        add_audit(
            audits,
            ticker,
            "annual",
            year,
            "Interest Expenses (M Rp)",
            "interest_expense_non_operating",
            r.get(
                "interest_expense_non_operating"
            ),
            row[
                "Interest Expenses (M Rp)"
            ],
            "source / 1e9",
        )

        add_audit(
            audits,
            ticker,
            "annual",
            year,
            "Net Income (M Rp)",
            "earnings",
            r.get("earnings"),
            row[
                "Net Income (M Rp)"
            ],
            "source / 1e9",
        )

        add_audit(
            audits,
            ticker,
            "annual",
            year,
            "OCF (M Rp)",
            "operating_cash_flow",
            r.get(
                "operating_cash_flow"
            ),
            row["OCF (M Rp)"],
            "source / 1e9",
        )

        add_audit(
            audits,
            ticker,
            "annual",
            year,
            "DPS (Rp)",
            "historical_dividends",
            dps,
            dps,
            "annual dividend total; null stays null",
        )

        add_audit(
            audits,
            ticker,
            "annual",
            year,
            "Shares (Juta)",
            "outstanding_shares",
            r.get(
                "outstanding_shares"
            ),
            row[
                "Shares (Juta)"
            ],
            "source / 1e6",
        )

    # ------------------------------------------------------------------------
    # Write annual CSV
    # ------------------------------------------------------------------------

    write_csv(
        out_dir
        / "Stock_Database.csv",
        ANNUAL_HEADERS,
        annual_rows,
    )

    # ------------------------------------------------------------------------
    # Quarterly
    # ------------------------------------------------------------------------

    quarter_dates = load_quarter_dates(
        raw_dir
    )

    quarter_raw = load_quarters(
        raw_dir
    )

    quarter_rows: List[
        Dict[str, Any]
    ] = []

    for r in quarter_raw:

        report_date = str(
            r.get(
                "_report_date"
            )
        )

        year = int(
            report_date[:4]
        )

        quarter = quarter_from_date(
            report_date
        )

        # Prefer official quarter date list.
        data_available = (
            quarter_dates.get(
                (
                    year,
                    quarter,
                ),
                report_date,
            )
        )

        row = {
            "Ticker": ticker,

            "Data Available Date":
                data_available,

            "Year": year,

            "Quarter": quarter,

            "Revenue (M Rp)":
                to_m_rp(
                    r.get("revenue")
                ),

            "HPP COGS (M Rp)":
                negative_abs_m_rp(
                    r.get(
                        "cost_of_revenue"
                    )
                ),

            "Interest Expenses (M Rp)":
                to_m_rp(
                    r.get(
                        "interest_expense_non_operating"
                    )
                ),

            "Net Income (M Rp)":
                to_m_rp(
                    r.get("earnings")
                ),

            "OCF (M Rp)":
                to_m_rp(
                    r.get(
                        "operating_cash_flow"
                    )
                ),

            "Current Assets (M Rp)":
                to_m_rp(
                    r.get(
                        "total_current_asset"
                    )
                ),

            "Current Liabilities (M Rp)":
                to_m_rp(
                    r.get(
                        "current_liabilities"
                    )
                ),

            "Total Liabilities (M Rp)":
                to_m_rp(
                    r.get(
                        "total_liabilities"
                    )
                ),

            "Total Equity (M Rp)":
                to_m_rp(
                    r.get(
                        "total_equity"
                    )
                ),

            "Shares (Juta)":
                to_million_shares(
                    r.get(
                        "outstanding_shares"
                    )
                ),

            "Avg Vol (3M)": None,

            "Stock Price (Rp)": None,
        }

        quarter_rows.append(
            row
        )

        # --------------------------------------------------------------------
        # Audit quarterly fields
        # --------------------------------------------------------------------

        audit_fields = [
            (
                "Revenue (M Rp)",
                "revenue",
                r.get("revenue"),
                row[
                    "Revenue (M Rp)"
                ],
                "source / 1e9",
            ),

            (
                "HPP COGS (M Rp)",
                "cost_of_revenue",
                r.get(
                    "cost_of_revenue"
                ),
                row[
                    "HPP COGS (M Rp)"
                ],
                "-ABS(source / 1e9)",
            ),

            (
                "Interest Expenses (M Rp)",
                "interest_expense_non_operating",
                r.get(
                    "interest_expense_non_operating"
                ),
                row[
                    "Interest Expenses (M Rp)"
                ],
                "source / 1e9",
            ),

            (
                "Net Income (M Rp)",
                "earnings",
                r.get("earnings"),
                row[
                    "Net Income (M Rp)"
                ],
                "source / 1e9",
            ),

            (
                "OCF (M Rp)",
                "operating_cash_flow",
                r.get(
                    "operating_cash_flow"
                ),
                row["OCF (M Rp)"],
                "source / 1e9",
            ),

            (
                "Current Assets (M Rp)",
                "total_current_asset",
                r.get(
                    "total_current_asset"
                ),
                row[
                    "Current Assets (M Rp)"
                ],
                "source / 1e9",
            ),

            (
                "Current Liabilities (M Rp)",
                "current_liabilities",
                r.get(
                    "current_liabilities"
                ),
                row[
                    "Current Liabilities (M Rp)"
                ],
                "source / 1e9",
            ),

            (
                "Total Liabilities (M Rp)",
                "total_liabilities",
                r.get(
                    "total_liabilities"
                ),
                row[
                    "Total Liabilities (M Rp)"
                ],
                "source / 1e9",
            ),

            (
                "Total Equity (M Rp)",
                "total_equity",
                r.get(
                    "total_equity"
                ),
                row[
                    "Total Equity (M Rp)"
                ],
                "source / 1e9",
            ),

            (
                "Shares (Juta)",
                "outstanding_shares",
                r.get(
                    "outstanding_shares"
                ),
                row[
                    "Shares (Juta)"
                ],
                "source / 1e6",
            ),
        ]

        for (
            target,
            source,
            value,
            converted,
            rule,
        ) in audit_fields:

            add_audit(
                audits,
                ticker,
                "quarter",
                report_date,
                target,
                source,
                value,
                converted,
                rule,
            )

    # ------------------------------------------------------------------------
    # Write quarterly CSV
    # ------------------------------------------------------------------------

    write_csv(
        out_dir
        / "Stock_Database_Quarter.csv",
        QUARTER_HEADERS,
        quarter_rows,
    )

    # ------------------------------------------------------------------------
    # Price history
    # ------------------------------------------------------------------------

    price_rows = raw_price_history(
        raw_dir,
        ticker,
    )

    write_csv(
        out_dir
        / "Price_History.csv",
        PRICE_HEADERS,
        price_rows,
    )

    # ------------------------------------------------------------------------
    # Conversion audit
    # ------------------------------------------------------------------------

    write_csv(
        out_dir
        / "Conversion_Audit.csv",
        AUDIT_HEADERS,
        audits,
    )

    # ------------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------------

    manifest = {
        "ticker": ticker,

        "raw_root": str(
            raw_dir
        ),

        "output_root": str(
            out_dir
        ),

        "converted_at":
            datetime_now_iso(),

        "status": "ok",

        "counts": {
            "annual_rows":
                len(annual_rows),

            "quarter_rows":
                len(quarter_rows),

            "price_rows":
                len(price_rows),

            "audit_rows":
                len(audits),
        },

        "notes": [
            (
                "This Step 2 output does not "
                "write into the Excel workbook."
            ),

            (
                "Annual stock price uses the "
                "last daily close present in "
                "each calendar year."
            ),

            (
                "Annual Avg Vol (3M) is currently "
                "a simple mean of all daily volume "
                "records available in that calendar "
                "year; this is an audit placeholder "
                "and will be aligned to the legacy "
                "formula logic before workbook "
                "write-back."
            ),

            (
                "Quarterly price and Avg Vol are "
                "left blank here; the Excel engine "
                "can continue to calculate them later."
            ),

            (
                "Null source values remain null."
            ),
        ],
    }

    with (
        out_dir
        / "conversion_manifest.json"
    ).open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            manifest,
            f,
            ensure_ascii=False,
            indent=2,
        )

    return manifest


# ============================================================================
# DATE / TIME
# ============================================================================

def datetime_now_iso() -> str:
    """
    Return current date in ISO format.

    Example:
        2026-09-12
    """

    return date.today().isoformat()


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Convert Sectors.app RAW JSON "
            "into legacy template-shaped CSVs."
        )
    )

    # ------------------------------------------------------------------------
    # Ticker argument
    #
    # nargs="*" means:
    #
    #   python script.py
    #       -> ALL tickers
    #
    #   python script.py BIRD
    #       -> BIRD only
    #
    #   python script.py BIRD ERAA TLKM
    #       -> selected tickers
    # ------------------------------------------------------------------------

    parser.add_argument(
        "tickers",
        nargs="*",
        help=(
            "Ticker(s), e.g. ERAA ARII IPOL. "
            "Jika kosong, semua folder ticker "
            "valid di RAW akan diproses."
        ),
    )

    parser.add_argument(
        "--raw-root",
        type=Path,
        default=DEFAULT_RAW_ROOT,
        help=(
            f"RAW root "
            f"(default: {DEFAULT_RAW_ROOT})"
        ),
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help=(
            f"Output root "
            f"(default: {DEFAULT_OUTPUT_ROOT})"
        ),
    )

    args = parser.parse_args()

    print("=" * 72)
    print(
        "SECTORS.APP RAW CONVERTER - STEP 2"
    )
    print("=" * 72)

    print(
        f"RAW root    : {args.raw_root}"
    )

    print(
        f"Output root : {args.output_root}"
    )

    print()

    # =========================================================================
    # DETERMINE TICKERS
    # =========================================================================

    if args.tickers:

        # User explicitly provided tickers.
        tickers = [
            t.upper().replace(
                ".JK",
                "",
            )
            for t in args.tickers
        ]

        # Remove duplicates while keeping sorted order.
        tickers = sorted(
            set(tickers)
        )

        print(
            f"MODE        : SELECTED TICKERS"
        )

    else:

        # No ticker argument.
        # Automatically discover all valid ticker folders.
        tickers = discover_all_tickers(
            args.raw_root
        )

        print(
            f"MODE        : ALL TICKERS"
        )

    print(
        f"TICKER COUNT: {len(tickers)}"
    )

    print()

    # =========================================================================
    # NO TICKER FOUND
    # =========================================================================

    if not tickers:

        print(
            "Tidak ada ticker RAW yang valid ditemukan."
        )

        print(
            f"Check folder: {args.raw_root}"
        )

        return

    # =========================================================================
    # PROCESS
    # =========================================================================

    success_tickers: List[str] = []
    failed_tickers: List[str] = []

    for index, ticker in enumerate(
        tickers,
        start=1,
    ):

        print("-" * 72)

        print(
            f"[{index}/{len(tickers)}] "
            f"CONVERT: {ticker}"
        )

        print("-" * 72)

        try:

            manifest = convert_ticker(
                ticker,
                args.raw_root,
                args.output_root,
            )

            print("OK")

            print(
                f"  Annual     : "
                f"{manifest['counts']['annual_rows']} rows"
            )

            print(
                f"  Quarterly  : "
                f"{manifest['counts']['quarter_rows']} rows"
            )

            print(
                f"  Price Hist : "
                f"{manifest['counts']['price_rows']} rows"
            )

            print(
                f"  Audit      : "
                f"{manifest['counts']['audit_rows']} rows"
            )

            print(
                f"  Output     : "
                f"{manifest['output_root']}"
            )

            success_tickers.append(
                ticker
            )

        except Exception as exc:

            print(
                f"ERROR: {exc}"
            )

            failed_tickers.append(
                ticker
            )

    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================

    print()
    print("=" * 72)
    print(
        "STEP 2 SELESAI"
    )
    print("=" * 72)

    print(
        f"Total ticker : {len(tickers)}"
    )

    print(
        f"Berhasil     : {len(success_tickers)}"
    )

    print(
        f"Error        : {len(failed_tickers)}"
    )

    print()

    if success_tickers:

        print(
            "BERHASIL:"
        )

        print(
            "  "
            + ", ".join(
                success_tickers
            )
        )

        print()

    if failed_tickers:

        print(
            "ERROR:"
        )

        print(
            "  "
            + ", ".join(
                failed_tickers
            )
        )

        print()

    print(
        "Tidak ada file Excel yang diubah."
    )


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    main()
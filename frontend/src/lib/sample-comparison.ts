/**
 * Compare the documented AUTO workbook sample against the database values.
 *
 * Purpose: give a reader a side-by-side view of "what the workbook says" versus
 * "what the table says", so a divergence is visible instead of hidden behind a
 * single rendered number.
 *
 * The sample is transcribed from docs/reference/Template_Sample_data.md and
 * docs/reference/EXCEL_POSTGRES_VALIDATION.md. It is AUTO-specific, so a
 * comparison is only meaningful on AUTO's page; other tickers get an
 * explanation rather than a misleading mixed-ticker table.
 */

import type { FinancialPeriod, StockResearchData } from "@/lib/stock-data";
import {
  SAMPLE_ANNUAL,
  SAMPLE_PROJECTION,
  SAMPLE_QUARTERLY,
  SAMPLE_RISK_FREE,
  SAMPLE_VALUATION,
  type WorkbookSampleValue,
} from "@/data/workbook-sample-auto";

const BILLION = 1_000_000_000;
const MILLION = 1_000_000;

/** The only ticker whose workbook sample is documented. */
export const SAMPLE_TICKER = "AUTO";

export type SampleComparisonStatus = "MATCH" | "MISMATCH" | "DB_MISSING" | "NOT_EXPOSED";

export type SampleComparisonRow = {
  group: string;
  metric: string;
  period: string;
  sampleDisplay: string;
  dbDisplay: string;
  status: SampleComparisonStatus;
  source: string;
};

export type SampleComparison = {
  /** False when the ticker has no documented workbook sample. */
  available: boolean;
  rows: SampleComparisonRow[];
  matchCount: number;
  mismatchCount: number;
  missingCount: number;
  notExposedCount: number;
  note: string;
};

function findPeriod(
  data: StockResearchData,
  label: string,
  type: "ANNUAL" | "QUARTER",
): FinancialPeriod | undefined {
  return data.financialPeriods.find((p) => p.periodLabel === label && p.periodType === type);
}

function fact(period: FinancialPeriod | undefined, code: string): number | null {
  return period?.facts.find((f) => f.metricCode === code)?.value ?? null;
}

/** Per-share value = amount / shares, or null when either input is missing. */
function perShare(amount: number | null, shares: number | null): number | null {
  if (amount == null || shares == null || shares <= 0) return null;
  return amount / shares;
}

function display(value: number | null, unit: WorkbookSampleValue["unit"]): string {
  if (value == null || !Number.isFinite(value)) return "Belum Tersedia";
  const n = (digits: number) => value.toFixed(digits).replace(".", ",");
  switch (unit) {
    case "IDR_BILLION":
      return `${n(2)} B`;
    case "IDR_PER_SHARE":
      return `Rp${n(2)}`;
    case "SHARES_MILLION":
      return `${n(1)} jt`;
    case "PERCENT":
      return `${n(2)}%`;
    case "MULTIPLE":
      return `${n(2)}x`;
    default:
      return n(2);
  }
}

/** Latest stored close at or before `cutoff`, or null when none exists. */
function lastCloseOnOrBefore(data: StockResearchData, cutoff: string): number | null {
  const candidates = data.prices
    .filter((p) => p.closePrice != null && p.tradingDate <= cutoff)
    .sort((a, b) => a.tradingDate.localeCompare(b.tradingDate));
  return candidates.at(-1)?.closePrice ?? null;
}

/**
 * Resolve the database value for one sample row, expressed in the SAME unit as
 * the sample so the two columns are directly comparable.
 */
function resolveDbValue(sample: WorkbookSampleValue, data: StockResearchData): number | null {
  const annual = findPeriod(data, sample.period, "ANNUAL");
  const quarter = findPeriod(data, sample.period, "QUARTER");

  // A projection period ("2026 (Proyeksi)") is not a reported period, so it must
  // be resolved from the stored projection scenario instead of a statement fact.
  // Without this guard the statement switch below would return null for it and
  // the row would be mislabelled as missing from the table.
  if (!annual && !quarter) {
    return resolveDerivedValue(sample, data);
  }

  const annualBillion = (code: string): number | null => {
    const value = fact(annual, code);
    return value == null ? null : value / BILLION;
  };
  const quarterBillion = (code: string): number | null => {
    const value = fact(quarter, code);
    return value == null ? null : value / BILLION;
  };

  switch (sample.metric) {
    case "Revenue":
      return annual ? annualBillion("REVENUE") : quarterBillion("REVENUE");
    case "COGS (magnitude)": {
      // The workbook shows COGS negative; the sample records its magnitude.
      const value = annual ? fact(annual, "COST_OF_REVENUE") : fact(quarter, "COST_OF_REVENUE");
      return value == null ? null : Math.abs(value) / BILLION;
    }
    case "Interest Expense": {
      const value = annual
        ? fact(annual, "INTEREST_EXPENSE_NON_OPERATING")
        : fact(quarter, "INTEREST_EXPENSE_NON_OPERATING");
      return value == null ? null : value / BILLION;
    }
    case "Net Income":
      return annual ? annualBillion("EARNINGS") : quarterBillion("EARNINGS");
    case "Operating Cash Flow":
      return annual ? annualBillion("OPERATING_CASH_FLOW") : quarterBillion("OPERATING_CASH_FLOW");
    case "Gross Profit":
      return annualBillion("GROSS_PROFIT");
    case "Current Assets": {
      // Annual periods use CURRENT_ASSETS, quarters use TOTAL_CURRENT_ASSET.
      const value = annual ? fact(annual, "CURRENT_ASSETS") : fact(quarter, "TOTAL_CURRENT_ASSET");
      return value == null ? null : value / BILLION;
    }
    case "Current Liabilities":
      return annual ? annualBillion("CURRENT_LIABILITIES") : quarterBillion("CURRENT_LIABILITIES");
    case "Total Liabilities":
      return annual ? annualBillion("TOTAL_LIABILITIES") : quarterBillion("TOTAL_LIABILITIES");
    case "Total Equity":
      return annual ? annualBillion("TOTAL_EQUITY") : quarterBillion("TOTAL_EQUITY");
    case "Shares Outstanding": {
      const value = fact(annual, "OUTSTANDING_SHARES");
      return value == null ? null : value / MILLION;
    }
    case "EPS":
      return perShare(fact(annual, "EARNINGS"), fact(annual, "OUTSTANDING_SHARES"));
    case "BVPS":
      return perShare(fact(annual, "TOTAL_EQUITY"), fact(annual, "OUTSTANDING_SHARES"));
    case "Closing Price (year-end)":
      return lastCloseOnOrBefore(data, `${sample.period}-12-31`);
    case "DPS": {
      const year = Number(sample.period);
      const match = data.dividends.find((d) => d.periodYear === year);
      return match?.amountPerShare ?? null;
    }
    default:
      break;
  }

  return resolveDerivedValue(sample, data);
}

/** Valuation results, projection scenario values, and the reference rate. */
function resolveDerivedValue(sample: WorkbookSampleValue, data: StockResearchData): number | null {
  // These keys are the *sample workbook* metric names from
  // `data/workbook-sample-auto.ts`, not UI labels, so they stay literal: the
  // mapping is "workbook wording -> stored method_code".
  const valuationMethod: Record<string, string> = {
    "Peter Lynch (Main Rule)": "PETER_LYNCH",
    "Type & Sector Weighted": "TYPE_SECTOR_WEIGHTED",
    "Mean Reversion PBV": "MEAN_REVERSION_PBV",
    "Dividend Discount Model": "DDM",
    "Discounted Earnings": "DISCOUNTED_EARNINGS",
  };
  const methodCode = valuationMethod[sample.metric];
  if (methodCode) {
    const method = data.valuationMethods.find((m) => m.methodCode === methodCode);
    return method?.intrinsicValue ?? null;
  }

  if (sample.metric === "Current Price (workbook as-of)") {
    // The workbook's as-of price is a manual 2026-Q2 value; compare it with the
    // stored close at that period end rather than the latest daily close.
    const periodEnd = findPeriod(data, "2026-Q2", "QUARTER")?.periodEnd;
    return periodEnd ? lastCloseOnOrBefore(data, periodEnd) : null;
  }

  const projectionCode: Record<string, string> = {
    Revenue: "REVENUE",
    "COGS (magnitude)": "COST_OF_REVENUE",
    "Interest Expense": "INTEREST_EXPENSE_NON_OPERATING",
    "Net Income": "EARNINGS",
    "Operating Cash Flow": "OPERATING_CASH_FLOW",
    "Potential DPS": "POTENTIAL_DPS",
  };
  const code = projectionCode[sample.metric];
  if (code && data.projection) {
    const entry = data.projection.values.find((v) => v.metricCode === code);
    if (!entry || entry.value == null) return null;
    if (entry.unitCode === "IDR_PER_SHARE") return entry.value;
    return Math.abs(entry.value) / BILLION;
  }

  if (sample.metric === "Avg DPR (7Y)") {
    const dpr = data.projection?.averageDprRatio;
    return dpr == null ? null : dpr * 100;
  }

  // The live rate lives in risk_free_rate_reference, which is service-role only,
  // so the browser cannot read it. Reported as unavailable rather than faking a
  // match against the workbook constant.
  return null;
}

function buildRows(
  samples: WorkbookSampleValue[],
  group: string,
  data: StockResearchData,
): SampleComparisonRow[] {
  return samples.map((sample) => {
    const dbValue = resolveDbValue(sample, data);
    // The live risk-free rate lives in `risk_free_rate_reference`, which is
    // readable only by `service_role`. The browser therefore cannot compare it,
    // and reporting "table empty" would be inaccurate: the value exists, it is
    // simply not exposed. That distinction is stated explicitly.
    const notExposed = sample.metric === "Risk Free Rate (SBN 10Y)";
    const status: SampleComparisonStatus = notExposed
      ? "NOT_EXPOSED"
      : dbValue == null
        ? "DB_MISSING"
        : Math.abs(dbValue - sample.value) <= sample.tolerance
          ? "MATCH"
          : "MISMATCH";
    return {
      group,
      metric: sample.metric,
      period: sample.period,
      sampleDisplay: display(sample.value, sample.unit),
      dbDisplay: notExposed ? "Tidak diekspos ke UI" : display(dbValue, sample.unit),
      status,
      source: sample.source,
    };
  });
}

export function buildSampleComparison(data: StockResearchData): SampleComparison {
  const ticker = data.instrument.ticker.toUpperCase();
  if (ticker !== SAMPLE_TICKER) {
    return {
      available: false,
      rows: [],
      matchCount: 0,
      mismatchCount: 0,
      missingCount: 0,
      notExposedCount: 0,
      note: `Sampel workbook yang terdokumentasi hanya tersedia untuk ${SAMPLE_TICKER}. Buka halaman ${SAMPLE_TICKER} untuk membandingkan sampel dengan isi tabel.`,
    };
  }

  const rows = [
    ...buildRows(SAMPLE_ANNUAL, "Laporan Tahunan (DataInput)", data),
    ...buildRows(SAMPLE_QUARTERLY, "Laporan Kuartalan (DataInputProyeksi)", data),
    ...buildRows(SAMPLE_PROJECTION, "Proyeksi Aktif (skenario tersimpan)", data),
    ...buildRows(SAMPLE_VALUATION, "Hasil Valuasi (SUMMARY)", data),
    ...buildRows(SAMPLE_RISK_FREE, "Risk-Free Rate (tabel acuan)", data),
  ];

  return {
    available: true,
    rows,
    matchCount: rows.filter((r) => r.status === "MATCH").length,
    mismatchCount: rows.filter((r) => r.status === "MISMATCH").length,
    missingCount: rows.filter((r) => r.status === "DB_MISSING").length,
    notExposedCount: rows.filter((r) => r.status === "NOT_EXPOSED").length,
    note:
      "Kolom 'Sampel' adalah angka workbook yang terdokumentasi. Kolom 'Tabel' adalah nilai database yang sudah dinormalkan ke satuan yang sama, sehingga bisa dibandingkan langsung. Catatan satuan: kolom yang di workbook dilabeli 'M Rp' sebenarnya berisi miliar IDR.",
  };
}


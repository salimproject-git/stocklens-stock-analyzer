/**
 * AUTO workbook sample values, transcribed from the documented sample template.
 *
 * Source of truth (not invented here):
 *   docs/reference/Template_Sample_data.md
 *   docs/reference/EXCEL_POSTGRES_VALIDATION.md  (§9 AUTO reconciliation)
 *
 * Unit convention (important): every column the workbook labels "M Rp" actually
 * holds **billions** of IDR. The workbook's own note in
 * EXCEL_POSTGRES_VALIDATION.md §"Unit reality check" states
 * `1 template unit = 1,000,000,000 IDR`, so values below are in billion IDR
 * unless the unit field says otherwise (Rp per share, x, or %).
 *
 * This module is deliberately read-only reference data. It exists so the UI can
 * show "workbook sample vs database table" side by side; nothing here is fed
 * into a calculation.
 */

export type WorkbookSampleValue = {
  metric: string;
  period: string;
  /** Value exactly as documented in the sample template. */
  value: number;
  unit: "IDR_BILLION" | "IDR_PER_SHARE" | "MULTIPLE" | "PERCENT" | "SHARES_MILLION" | "IDR";
  /** Where in the workbook/doc the number comes from. */
  source: string;
  /** Absolute tolerance used when comparing against the database value. */
  tolerance: number;
};

/** Annual financials — `DataInput` sheet, section B/C. */
export const SAMPLE_ANNUAL: WorkbookSampleValue[] = [
  { metric: "Revenue", period: "2025", value: 19906.8, unit: "IDR_BILLION", source: "DataInput B: Revenue 2025", tolerance: 0.05 },
  { metric: "COGS (magnitude)", period: "2025", value: 16540.5, unit: "IDR_BILLION", source: "DataInput B: COGS 2025 (shown negative in workbook)", tolerance: 0.05 },
  { metric: "Interest Expense", period: "2025", value: 43.5, unit: "IDR_BILLION", source: "DataInput B: Interest 2025", tolerance: 0.05 },
  { metric: "Net Income", period: "2025", value: 2205.0, unit: "IDR_BILLION", source: "DataInput B: Net Income 2025", tolerance: 0.05 },
  { metric: "Operating Cash Flow", period: "2025", value: 1944.3, unit: "IDR_BILLION", source: "DataInput B: OCF 2025", tolerance: 0.05 },
  { metric: "Gross Profit", period: "2025", value: 3366.2, unit: "IDR_BILLION", source: "DataInput B: Gross Profit 2025", tolerance: 0.05 },
  { metric: "Current Assets", period: "2025", value: 9974.0, unit: "IDR_BILLION", source: "DataInput C: Current Assets 2025", tolerance: 0.05 },
  { metric: "Current Liabilities", period: "2025", value: 4523.3, unit: "IDR_BILLION", source: "DataInput C: Current Liabilities 2025", tolerance: 0.05 },
  { metric: "Total Liabilities", period: "2025", value: 5651.1, unit: "IDR_BILLION", source: "DataInput C: Total Liabilities 2025", tolerance: 0.05 },
  { metric: "Total Equity", period: "2025", value: 16964.4, unit: "IDR_BILLION", source: "DataInput C: Total Equity 2025", tolerance: 0.05 },
  { metric: "Shares Outstanding", period: "2025", value: 4819.7, unit: "SHARES_MILLION", source: "DataInput C: Shares 2025 (Juta)", tolerance: 0.05 },
  { metric: "EPS", period: "2025", value: 457.5, unit: "IDR_PER_SHARE", source: "DataInput B: EPS 2025", tolerance: 0.05 },
  { metric: "BVPS", period: "2025", value: 3519.8, unit: "IDR_PER_SHARE", source: "DataInput C: BVPS 2025", tolerance: 0.05 },
  { metric: "Closing Price (year-end)", period: "2025", value: 2690, unit: "IDR", source: "DataInput B: Stock Price 2025", tolerance: 0 },
  { metric: "DPS", period: "2025", value: 192, unit: "IDR_PER_SHARE", source: "DataInput B: DPS 2025", tolerance: 0 },
  { metric: "DPS", period: "2024", value: 189, unit: "IDR_PER_SHARE", source: "DataInput B: DPS 2024", tolerance: 0 },
];

/** Quarterly financials — `DataInputProyeksi` sheet, sections B/C. */
export const SAMPLE_QUARTERLY: WorkbookSampleValue[] = [
  { metric: "Revenue", period: "2026-Q2", value: 5596, unit: "IDR_BILLION", source: "DataInputProyeksi B: Revenue Q2", tolerance: 0.5 },
  { metric: "Revenue", period: "2026-Q1", value: 5257, unit: "IDR_BILLION", source: "DataInputProyeksi B: Revenue Q1", tolerance: 0.5 },
  { metric: "COGS (magnitude)", period: "2026-Q2", value: 4750, unit: "IDR_BILLION", source: "DataInputProyeksi B: COGS Q2", tolerance: 0.5 },
  { metric: "Interest Expense", period: "2026-Q2", value: 9, unit: "IDR_BILLION", source: "DataInputProyeksi B: Interest Q2", tolerance: 0.5 },
  { metric: "Interest Expense", period: "2026-Q1", value: 9, unit: "IDR_BILLION", source: "DataInputProyeksi B: Interest Q1", tolerance: 0.5 },
  { metric: "Net Income", period: "2026-Q2", value: 592, unit: "IDR_BILLION", source: "DataInputProyeksi B: Net Income Q2", tolerance: 0.5 },
  { metric: "Net Income", period: "2026-Q1", value: 559, unit: "IDR_BILLION", source: "DataInputProyeksi B: Net Income Q1", tolerance: 0.5 },
  { metric: "Operating Cash Flow", period: "2026-Q2", value: 340, unit: "IDR_BILLION", source: "DataInputProyeksi B: OCF Q2", tolerance: 0.5 },
  { metric: "Operating Cash Flow", period: "2026-Q1", value: 411, unit: "IDR_BILLION", source: "DataInputProyeksi B: OCF Q1", tolerance: 0.5 },
  { metric: "Current Assets", period: "2026-Q2", value: 11056, unit: "IDR_BILLION", source: "DataInputProyeksi C: Current Assets Q2", tolerance: 0.5 },
  { metric: "Current Liabilities", period: "2026-Q2", value: 5459, unit: "IDR_BILLION", source: "DataInputProyeksi C: Current Liabilities Q2", tolerance: 0.5 },
  { metric: "Total Liabilities", period: "2026-Q2", value: 6687, unit: "IDR_BILLION", source: "DataInputProyeksi C: Total Liabilities Q2", tolerance: 0.5 },
  { metric: "Total Equity", period: "2026-Q2", value: 17195, unit: "IDR_BILLION", source: "DataInputProyeksi C: Total Equity Q2", tolerance: 0.5 },
];

/** Workbook current-valuation results — `SUMMARY` + `ValuationCurrent` sheets. */
export const SAMPLE_VALUATION: WorkbookSampleValue[] = [
  { metric: "Peter Lynch (Main Rule)", period: "2026-Q2", value: 3568, unit: "IDR_PER_SHARE", source: "SUMMARY: Peter Lynch IV", tolerance: 1 },
  { metric: "Type & Sector Weighted", period: "2026-Q2", value: 2537, unit: "IDR_PER_SHARE", source: "SUMMARY: Weighted IV", tolerance: 1 },
  { metric: "Mean Reversion PBV", period: "2026-Q2", value: 1740, unit: "IDR_PER_SHARE", source: "SUMMARY: Mean Reversion PBV IV", tolerance: 1 },
  { metric: "Dividend Discount Model", period: "2026-Q2", value: 1418, unit: "IDR_PER_SHARE", source: "SUMMARY: DDM IV", tolerance: 1 },
  { metric: "Discounted Earnings", period: "2026-Q2", value: 2305, unit: "IDR_PER_SHARE", source: "SUMMARY: Discounted Earnings IV", tolerance: 1 },
  { metric: "Current Price (workbook as-of)", period: "2026-Q2", value: 2350, unit: "IDR_PER_SHARE", source: "DataInput B10: manual/as-of price", tolerance: 0 },
];

/** Workbook projection inputs — `DataInputProyeksi` "2026 (Proyeksi)" column. */
export const SAMPLE_PROJECTION: WorkbookSampleValue[] = [
  { metric: "Revenue", period: "2026 (Proyeksi)", value: 21705, unit: "IDR_BILLION", source: "DataInputProyeksi B: Revenue projection", tolerance: 1 },
  { metric: "COGS (magnitude)", period: "2026 (Proyeksi)", value: 18330, unit: "IDR_BILLION", source: "DataInputProyeksi B: COGS projection", tolerance: 1 },
  { metric: "Interest Expense", period: "2026 (Proyeksi)", value: 37, unit: "IDR_BILLION", source: "DataInputProyeksi B: Interest projection", tolerance: 1 },
  { metric: "Net Income", period: "2026 (Proyeksi)", value: 2303, unit: "IDR_BILLION", source: "DataInputProyeksi B: Net Income projection", tolerance: 1 },
  { metric: "Operating Cash Flow", period: "2026 (Proyeksi)", value: 1501, unit: "IDR_BILLION", source: "DataInputProyeksi B: OCF projection", tolerance: 1 },
  { metric: "Potential DPS", period: "2026 (Proyeksi)", value: 114, unit: "IDR_PER_SHARE", source: "DataInputProyeksi B: Potential DPS", tolerance: 1 },
  { metric: "Avg DPR (7Y)", period: "2026 (Proyeksi)", value: 24, unit: "PERCENT", source: "DataInputProyeksi A: Avg DPR (7Y)", tolerance: 1 },
];

/** Risk-free rate — `DataInput!B11`. Mirrors risk_free_rate_reference. */
export const SAMPLE_RISK_FREE: WorkbookSampleValue[] = [
  { metric: "Risk Free Rate (SBN 10Y)", period: "workbook", value: 6.33, unit: "PERCENT", source: "DataInput B11", tolerance: 0 },
];

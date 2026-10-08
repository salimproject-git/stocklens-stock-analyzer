/**
 * Canonical valuation-method registry — the single source of truth for how each
 * stored `method_code` is labelled and ordered in the UI.
 *
 * Why this exists: the research RPC returns methods ordered by `method_code`
 * (alphabetical), so the Valuation table used to reshuffle itself whenever the
 * method set changed. Display order and labels must be a product decision, not a
 * side effect of the SQL `order by`. Everything (table rows, spectrum chart,
 * backtest columns) reads from here so the two can never drift apart.
 *
 * Labels mirror the workbook's valuation breakdown exactly
 * (see `Data/Sample Data/BIRD Quarter 2 2026.txt`, "VALUATION BREAKDOWN").
 */

export type ValuationMethodCode =
  | "PETER_LYNCH"
  | "TYPE_SECTOR_WEIGHTED"
  | "MEAN_REVERSION_PBV"
  | "DDM"
  | "DISCOUNTED_EARNINGS";

/**
 * Display status for one valuation-method row.
 *
 * `SKIPPED` is the workbook's `⚪ N/A (Skip)`: the model produced no value
 * (`IV = 0`, e.g. DDM for a company that has never paid a dividend), so the
 * method is left out of the comparison rather than being called "overvalued".
 * The row stays visible — the reader should see that the method exists and was
 * deliberately skipped, not silently missing.
 *
 * A **negative** IV is not skipped: it is a real (if bleak) estimate and keeps
 * its `OVERVALUED` status. Only its margin of safety is withheld, because the
 * ratio divides by that value.
 */
export type ValuationMethodStatus = "UNDERVALUED" | "OVERVALUED" | "SKIPPED";

/** Fixed display order for every surface that lists valuation methods. */
export const VALUATION_METHOD_ORDER: ValuationMethodCode[] = [
  "PETER_LYNCH",
  "TYPE_SECTOR_WEIGHTED",
  "MEAN_REVERSION_PBV",
  "DDM",
  "DISCOUNTED_EARNINGS",
];

/**
 * Workbook labels for the Valuation table.
 *
 * The workbook's "(Main Rule)" / "(Optional Rule)" qualifiers are intentionally
 * dropped. Which rule is *the* main rule depends on the stock type and is
 * already stated by the "Main" badge on the selected row, so repeating the
 * qualifier inside every label only made the method names harder to scan.
 */
export const VALUATION_METHOD_LABELS: Record<ValuationMethodCode, string> = {
  PETER_LYNCH: "Peter Lynch / Adaptive",
  TYPE_SECTOR_WEIGHTED: "Type & Sector Weighted",
  MEAN_REVERSION_PBV: "Mean Reversion PBV",
  DDM: "Dividend Discount Model",
  DISCOUNTED_EARNINGS: "Discounted Earnings",
};

/** Short, user-facing explanation shown in the Valuation Methods table. */
export const VALUATION_METHOD_DESCRIPTIONS: Record<ValuationMethodCode, string> = {
  PETER_LYNCH: "Asset-based (PEG + growth)",
  TYPE_SECTOR_WEIGHTED: "Blended (sector & type multiple)",
  MEAN_REVERSION_PBV: "Historical asset valuation (PBV)",
  DDM: "Dividend-based (Dividend Discount Model)",
  DISCOUNTED_EARNINGS: "Earnings-based (DCF)",
};

/**
 * Two-line labels for the spectrum chart, where the full workbook label would
 * wrap awkwardly under a 96px column.
 */
export const VALUATION_METHOD_SHORT_LABELS: Record<
  ValuationMethodCode,
  { first: string; second: string }
> = {
  PETER_LYNCH: { first: "Peter Lynch", second: "Adaptive" },
  TYPE_SECTOR_WEIGHTED: { first: "Type & Sector", second: "Weighted" },
  MEAN_REVERSION_PBV: { first: "Mean Reversion", second: "PBV" },
  DDM: { first: "Dividend Discount", second: "Model" },
  DISCOUNTED_EARNINGS: { first: "Discounted Earnings", second: "" },
};

/** Dot colours for the spectrum chart, keyed by method code. */
export const VALUATION_METHOD_COLORS: Record<ValuationMethodCode, string> = {
  PETER_LYNCH: "bg-[#3ecf9d]",
  TYPE_SECTOR_WEIGHTED: "bg-[#42bfd0]",
  MEAN_REVERSION_PBV: "bg-[#c79d51]",
  DDM: "bg-[#d66f65]",
  DISCOUNTED_EARNINGS: "bg-[#78a8c8]",
};

const FALLBACK_COLOR = "bg-[#78a8c8]";

export function isValuationMethodCode(code: string): code is ValuationMethodCode {
  return (VALUATION_METHOD_ORDER as string[]).includes(code);
}

/**
 * Human label for a stored `method_code`. Unknown codes are passed through
 * unchanged so a new method stays visible instead of rendering as blank.
 */
export function valuationMethodLabel(code: string): string {
  return isValuationMethodCode(code) ? VALUATION_METHOD_LABELS[code] : code;
}

export function valuationMethodDescription(code: string): string {
  return isValuationMethodCode(code) ? VALUATION_METHOD_DESCRIPTIONS[code] : code;
}

/** Position in the fixed order; unknown codes sort after every known method. */
export function valuationMethodRank(code: string): number {
  const index = VALUATION_METHOD_ORDER.indexOf(code as ValuationMethodCode);
  return index < 0 ? VALUATION_METHOD_ORDER.length : index;
}

export function valuationMethodShortLabel(code: string): { first: string; second: string } {
  return isValuationMethodCode(code)
    ? VALUATION_METHOD_SHORT_LABELS[code]
    : { first: code, second: "" };
}

export function valuationMethodColor(code: string): string {
  return isValuationMethodCode(code) ? VALUATION_METHOD_COLORS[code] : FALLBACK_COLOR;
}

/**
 * Sort rows into the fixed display order. Sorting is stable, so rows sharing a
 * code (or two unknown codes) keep their incoming relative order.
 */
export function sortValuationMethods<T extends { methodCode: string }>(rows: T[]): T[] {
  return [...rows].sort(
    (left, right) => valuationMethodRank(left.methodCode) - valuationMethodRank(right.methodCode),
  );
}

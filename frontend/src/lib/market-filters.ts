/**
 * Screener facets for the market overview, and the helpers that validate them.
 *
 * Like `market-page-size.ts`, this lives outside `stock-data.ts` because the
 * market overview is a Client Component: `stock-data.ts` is `server-only`, so
 * importing runtime values from it would drag the server Supabase client into
 * the browser bundle and fail the build.
 *
 * The SQL function `get_market_overview_page` (migration 0040) validates every
 * value again on its side. Anything it does not recognise falls back to the
 * default, so a stale client keeps rendering instead of erroring.
 */

export const MARKET_STOCK_TYPE_OPTIONS = [
  "ASSET PLAY",
  "CYCLICAL",
  "FAST GROWER",
  "SLOW GROWER",
  "STALWART",
  "TURN AROUND",
] as const;
export type MarketStockType = (typeof MARKET_STOCK_TYPE_OPTIONS)[number];

/**
 * Sort keys map 1:1 onto a SQL `order by`, so the ranking happens over the whole
 * instrument set rather than only the rows on the current page.
 *
 * `price_asc`/`price_desc` put stocks without a stored close last in both
 * directions: an absent price is not a low price.
 */
export const MARKET_SORT_OPTIONS = [
  { value: "ticker", label: "Ticker (A-Z)" },
  { value: "market_cap_desc", label: "Market Cap (Largest)" },
  // Kept short on purpose: these render inside a fixed-width control, and the
  // longer wording was truncated to "Historical Win Ra...".
  { value: "mos_desc", label: "MoS (Highest)" },
  { value: "win_rate_desc", label: "Win Rate (Highest)" },
  { value: "price_desc", label: "Price (Highest)" },
  { value: "price_asc", label: "Price (Lowest)" },
] as const;
export type MarketSort = (typeof MARKET_SORT_OPTIONS)[number]["value"];

export const DEFAULT_MARKET_SORT: MarketSort = "ticker";

/** Empty string means "no filter" — that is what the "All ..." option sends. */
export type MarketFilterSelection = {
  sector: string;
  stockType: MarketStockType | "";
  sort: MarketSort;
};

export const DEFAULT_MARKET_FILTERS: MarketFilterSelection = {
  sector: "",
  stockType: "",
  sort: DEFAULT_MARKET_SORT,
};

function parseSort(value: unknown): MarketSort {
  const raw = typeof value === "string" ? value : "";
  return (MARKET_SORT_OPTIONS as readonly { value: string }[]).some(
    (option) => option.value === raw,
  )
    ? (raw as MarketSort)
    : DEFAULT_MARKET_SORT;
}

function parseStockType(value: unknown): MarketStockType | "" {
  const raw = typeof value === "string" ? value.trim().toUpperCase() : "";
  return (MARKET_STOCK_TYPE_OPTIONS as readonly string[]).includes(raw)
    ? (raw as MarketStockType)
    : "";
}

/**
 * Sector names come from the database, so this cannot be a fixed list: it only
 * has to reject anything that is obviously not a sector name. The SQL side
 * matches the value against stored rows, so an unknown name simply yields no
 * results rather than an error.
 */
function parseSector(value: unknown): string {
  const raw = typeof value === "string" ? value.trim() : "";
  if (raw === "" || raw.length > 64) return "";
  return /^[\p{L}\p{N} &.'\-]+$/u.test(raw) ? raw : "";
}

/** Coerce untrusted values (e.g. query params) into a valid filter selection. */
export function parseMarketFilters(input: {
  sector?: unknown;
  stockType?: unknown;
  sort?: unknown;
}): MarketFilterSelection {
  return {
    sector: parseSector(input.sector),
    stockType: parseStockType(input.stockType),
    sort: parseSort(input.sort),
  };
}
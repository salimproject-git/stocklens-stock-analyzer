/**
 * Page sizes for the market overview, and the helpers that validate them.
 *
 * This lives in its own module (not in `stock-data.ts`) because the market
 * overview is a Client Component: `stock-data.ts` is `server-only`, so importing
 * runtime values from it would drag the server Supabase client into the browser
 * bundle and fail the build.
 *
 * The list is the single source of truth — the picker renders it and
 * `parseMarketPageSize` accepts only these values. It must stay in sync with the
 * whitelist inside `get_market_overview_page` (migration 0027), which silently
 * falls back to 8 for anything else.
 */

export const MARKET_PAGE_SIZE_OPTIONS = [8, 12, 16, 20] as const;
export type MarketPageSize = (typeof MARKET_PAGE_SIZE_OPTIONS)[number];
export const DEFAULT_MARKET_PAGE_SIZE: MarketPageSize = 8;

/** Coerce an untrusted value (e.g. a `?size=` query param) into a valid page size. */
export function parseMarketPageSize(value: unknown): MarketPageSize {
  const parsed = typeof value === "number" ? value : Number.parseInt(String(value ?? ""), 10);
  return (MARKET_PAGE_SIZE_OPTIONS as readonly number[]).includes(parsed)
    ? (parsed as MarketPageSize)
    : DEFAULT_MARKET_PAGE_SIZE;
}

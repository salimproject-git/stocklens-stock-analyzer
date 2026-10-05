/**
 * Static copy for the Valuation tab's "Why the Methods Differ?" section.
 *
 * This is presentation copy, NOT research data: it explains the three valuation
 * lenses and never changes per ticker, so it deliberately lives in the frontend
 * and is rendered directly. It is intentionally absent from `StockDetail` and
 * from the research RPC payload — nothing here is read from the database.
 *
 * Tags use concise names for this section; the valuation table keeps its
 * canonical method labels independently.
 */

export type ValuationLensCard = {
  title: string;
  text: string;
  tags: string[];
};

export const VALUATION_LENS_CARDS: ValuationLensCard[] = [
  {
    title: "Asset-based",
    text: "Uses book value, assets, or historical multiples such as PBV to estimate value.",
    tags: ["Mean Reversion PBV"],
  },
  {
    title: "Income-based",
    text: "Uses future earnings or dividends, such as Dividend Discount Model and discounted earnings. More sensitive to growth and earnings assumptions.",
    tags: ["Dividend Discount Model", "Discounted Earnings"],
  },
  {
    title: "Blended",
    text: "Combines multiple valuation lenses, adjusted for sector and company type.",
    tags: ["Peter Lynch", "Type & Sector Weighted"],
  },
];

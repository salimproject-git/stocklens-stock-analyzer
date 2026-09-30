import { VALUATION_METHOD_LABELS } from "@/lib/valuation-methods";

/**
 * Static copy for the Valuation tab's "Why the Methods Differ?" section.
 *
 * This is presentation copy, NOT research data: it explains the three valuation
 * lenses and never changes per ticker, so it deliberately lives in the frontend
 * and is rendered directly. It is intentionally absent from `StockDetail` and
 * from the research RPC payload — nothing here is read from the database.
 *
 * Tags reference `VALUATION_METHOD_LABELS` so the wording can never drift from
 * the method names shown in the Valuation table.
 */

export type ValuationLensCard = {
  title: string;
  text: string;
  tags: string[];
};

export const VALUATION_LENS_CARDS: ValuationLensCard[] = [
  {
    title: "Asset-based",
    text:
      "This approach looks at what the company owns to estimate what the stock may be worth. It is useful for companies where assets are an important part of the business, such as banks, commodity companies, and other asset-heavy businesses. Mean Reversion PBV compares the stock's current price with its historical PBV levels to see whether the market is valuing the company below or above its usual range. The idea is simple: when a stock is priced well below its own historical valuation, it may be trading at a level that deserves a closer look.",
    tags: [VALUATION_METHOD_LABELS.MEAN_REVERSION_PBV],
  },
  {
    title: "Income-based",
    text:
      "This approach looks at the money a company can return to shareholders or generate from its business. The Dividend Discount Model focuses on the dividends a company pays and estimates what those future payments may be worth today. The Discounted Earnings Model focuses on future profits and how the company's earnings may grow over time. Because both methods look into the future, their results can change depending on assumptions about growth, interest rates, and the level of risk involved.",
    tags: [VALUATION_METHOD_LABELS.DDM, VALUATION_METHOD_LABELS.DISCOUNTED_EARNINGS],
  },
  {
    title: "Blended",
    text:
      "This approach combines more than one way of looking at a company's value instead of relying on a single measure. Peter Lynch uses different factors depending on the type of company—for example, earnings may matter more for growth companies, while assets may matter more for cyclical or asset-heavy businesses. Weighted IV combines several valuation results and adjusts them based on the company's sector and stock type. The goal is to give a broader view of valuation by looking at the company from several angles rather than relying on just one method.",
    tags: [VALUATION_METHOD_LABELS.PETER_LYNCH, VALUATION_METHOD_LABELS.TYPE_SECTOR_WEIGHTED],
  },
];

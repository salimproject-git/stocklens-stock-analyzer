export type MarketOverviewSignal = "Undervalued" | "Overvalued" | "Mixed" | "Not available";

export type MarketOverviewStock = {
  ticker: string;
  companyName: string;
  sector: string;
  stockType: string;
  currencyCode?: string;
  price: number | null;
  change: number | null;
  changePercent: number | null;
  sparkline: number[];
  verdict: "Undervalued" | "Fairly Valued" | "Overvalued" | "Not available";
  /**
   * Agreement between the two "cheap" rules: the method consensus and the MoS
   * rule. Both cheap -> Undervalued, both expensive -> Overvalued, they
   * disagree -> Mixed, and a rule with no stored verdict -> Not available.
   */
  signal: MarketOverviewSignal;
  recommendationAvailable?: boolean;
  /** Main-method margin of safety, already a percentage (e.g. 35.9). */
  mos: number | null;
  /** How many valid methods call the stock cheap, over how many valid methods. */
  methodUndervalued: number | null;
  methodValid: number | null;
  /** Higher of the two historical win rates, and the cases it is measured over. */
  winRatePercent: number | null;
  winRateCases: number | null;
  evidenceWins: number | null;
  evidenceTotal: number | null;
  updatedAt: string | null;
};
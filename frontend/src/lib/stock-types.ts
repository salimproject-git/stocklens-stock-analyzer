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
  recommendationAvailable?: boolean;
  mos: number | null;
  evidenceWins: number | null;
  evidenceTotal: number | null;
  updatedAt: string | null;
};
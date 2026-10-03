import { notFound } from "next/navigation";
import { StockResearchPage } from "@/components/stock-research/stock-research-page";
import {
  getStockResearchData,
  getStockBacktestData,
  getStockValuationSummary,
} from "@/lib/stock-data";
import { buildStockDetail } from "@/lib/stock-detail-adapter";

export default async function StockPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const resolvedParams = await params;
  // Both reads are independent, so they are issued together rather than
  // serialised. The backtest is optional: a ticker that has never been run
  // simply gets no backtest section instead of failing the whole page.
  const [data, backtest, valuationSummary] = await Promise.all([
    getStockResearchData(resolvedParams.ticker),
    getStockBacktestData(resolvedParams.ticker).catch(() => null),
    getStockValuationSummary(resolvedParams.ticker),
  ]);

  // Unknown ticker must render the not-found state instead of another
  // company's data. Never fall back to a different instrument.
  if (!data) {
    notFound();
  }

  const stock = buildStockDetail(data, backtest, valuationSummary);

  return <StockResearchPage stock={stock} />;
}


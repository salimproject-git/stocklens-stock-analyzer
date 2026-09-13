import { StockResearchPage } from "@/components/stock-research/stock-research-page";

export default async function StockPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const resolvedParams = await params;
  return <StockResearchPage ticker={resolvedParams.ticker} />;
}


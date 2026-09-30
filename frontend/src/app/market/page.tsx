import { MarketOverviewPage } from "@/components/market-overview-page";
import { getMarketOverviewData } from "@/lib/stock-data";
import { parseMarketPageSize } from "@/lib/market-page-size";

type PageProps = {
  searchParams: Promise<{ page?: string | string[]; size?: string | string[] }>;
};

function parsePageParam(value: string | string[] | undefined): number {
  const raw = Array.isArray(value) ? value[0] : value;
  const parsed = Number.parseInt(raw ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

export default async function MarketPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const page = parsePageParam(params.page);
  const pageSize = parseMarketPageSize(params.size);
  const data = await getMarketOverviewData(page, pageSize);

  return (
    <MarketOverviewPage
      initialData={data}
      currentPage={data.currentPage || page}
    />
  );
}


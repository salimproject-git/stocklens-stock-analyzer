import { MarketOverviewPage } from "@/components/market-overview-page";
import { getMarketOverviewData, getMarketSectors } from "@/lib/stock-data";
import { parseMarketPageSize } from "@/lib/market-page-size";
import { parseMarketFilters } from "@/lib/market-filters";

type PageProps = {
  searchParams: Promise<{
    page?: string | string[];
    size?: string | string[];
    sector?: string | string[];
    type?: string | string[];
    sort?: string | string[];
  }>;
};

function firstParam(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function parsePageParam(value: string | string[] | undefined): number {
  const raw = firstParam(value);
  const parsed = Number.parseInt(raw ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

export default async function MarketPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const page = parsePageParam(params.page);
  const pageSize = parseMarketPageSize(params.size);
  const filters = parseMarketFilters({
    sector: firstParam(params.sector),
    stockType: firstParam(params.type),
    sort: firstParam(params.sort),
  });

  // The two reads are independent, so they are issued together. Sector options
  // are only needed to render the filter control; they never gate the data.
  const [data, sectors] = await Promise.all([
    getMarketOverviewData(page, pageSize, filters),
    getMarketSectors(),
  ]);

  return (
    <MarketOverviewPage
      initialData={data}
      currentPage={data.currentPage || page}
      sectors={sectors}
      filters={filters}
    />
  );
}


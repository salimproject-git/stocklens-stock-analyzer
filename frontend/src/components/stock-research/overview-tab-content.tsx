import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { ResearchSummaryCard } from "@/components/stock-research/research-summary-card";
import { CompanyProfileCard } from "@/components/stock-research/company-profile-card";
import { PriceChartCard } from "@/components/stock-research/price-chart-card";
import { CurrentValuationCard } from "@/components/stock-research/current-valuation-card";
import { GrowthSummaryCard } from "@/components/stock-research/growth-summary-card";
import { HistoricalEvidencePreviewCard } from "@/components/stock-research/historical-evidence-preview-card";
import { DividendConsistencyCard } from "@/components/stock-research/dividend-consistency-card";

export function OverviewTabContent({ stock }: { stock: StockDetail }) {
  return (
    <div className="space-y-6">
      {/* Row 1 — Research Summary */}
      <ResearchSummaryCard
        summaryText={stock.researchSummary}
        methodologyUrl={stock.methodologyUrl}
      />

      {/* Row 2 — Company Profile + Price Chart */}
      <div className="grid gap-6 lg:grid-cols-2">
        <CompanyProfileCard profile={stock.companyProfile} />
        <PriceChartCard chartData={stock.priceChart} />
      </div>

      {/* Row 3 — Current Valuation + Historical Evidence */}
      <div className="grid gap-6 lg:grid-cols-2">
        <CurrentValuationCard valuation={stock.currentValuation} />
        <HistoricalEvidencePreviewCard
          evidence={stock.historicalEvidencePreview}
        />
      </div>

      {/* Row 4 — Growth Summary + Dividend Consistency */}
      <div className="grid gap-6 lg:grid-cols-2">
        <GrowthSummaryCard
          growth={stock.growthSummary}
          validator={stock.thesisValidator}
        />

        <DividendConsistencyCard
          dividend={stock.dividendConsistency}
        />
      </div>
    </div>
  );
}
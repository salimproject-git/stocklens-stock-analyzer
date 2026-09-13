import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { CompanyProfileCard } from "./company-profile-card";
import { PriceChartCard } from "./price-chart-card";
import { CurrentValuationCard } from "./current-valuation-card";
import { FinancialHealthCard } from "./financial-health-card";
import { GrowthSummaryCard } from "./growth-summary-card";
import { HistoricalEvidencePreviewCard } from "./historical-evidence-preview-card";
import { ThesisValidatorCard } from "./thesis-validator-card";
import { DividendConsistencyCard } from "./dividend-consistency-card";

export function OverviewTabContent({ stock }: { stock: StockDetail }) {
  return (
    <div className="space-y-6">
      {/* Row 1: Company Profile & Price Chart */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <CompanyProfileCard profile={stock.companyProfile} />
        <PriceChartCard chartData={stock.priceChart} />
      </div>

      {/* Row 2: Current Valuation & Financial Health */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <CurrentValuationCard valuation={stock.currentValuation} />
        <FinancialHealthCard health={stock.financialHealth} />
      </div>

      {/* Row 3: Growth Summary & Historical Evidence Preview */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <GrowthSummaryCard growth={stock.growthSummary} />
        <HistoricalEvidencePreviewCard evidence={stock.historicalEvidencePreview} />
      </div>

      {/* Row 4: Thesis Validator & Dividend Consistency */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <ThesisValidatorCard validator={stock.thesisValidator} />
        <DividendConsistencyCard dividend={stock.dividendConsistency} />
      </div>
    </div>
  );
}


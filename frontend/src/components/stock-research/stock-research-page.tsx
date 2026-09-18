"use client";

import React, { useState } from "react";
import { mockStockDetails } from "@/data/mock-stock-details";
import { Breadcrumb } from "./breadcrumb";
import { StockHeader } from "./stock-header";
import { KeyMetricSummary } from "./key-metric-card";
import { ResearchTabs, ResearchTabKey } from "./research-tabs";
import { OverviewTabContent } from "./overview-tab-content";
import { FinancialsTabContent } from "./financials-tab-content";
import { GrowthTabContent } from "./growth-tab-content";
import { DisclaimerFooter } from "./disclaimer-footer";

export function StockResearchPage({ ticker }: { ticker: string }) {
  const [activeTab, setActiveTab] = useState<ResearchTabKey>("Overview");

  // Fallback to AUTO mock data if ticker not found in mock table
  const stock = mockStockDetails[ticker.toUpperCase()] ?? mockStockDetails.AUTO;

  return (
    <>
      <Breadcrumb ticker={stock.ticker} />
      <StockHeader stock={stock} />
      <KeyMetricSummary stock={stock} />
      <ResearchTabs activeTab={activeTab} onTabChange={setActiveTab} />

      {activeTab === "Overview" ? (
        <OverviewTabContent stock={stock} />
      ) : activeTab === "Financials" ? (
        <FinancialsTabContent stock={stock} />
      ) : activeTab === "Growth" ? (
        <GrowthTabContent stock={stock} />
      ) : (
        <div className="my-12 flex flex-col items-center justify-center rounded-[20px] border border-white/10 bg-[linear-gradient(180deg,_rgba(11,23,37,0.92),_rgba(7,16,28,0.94))] p-16 text-center shadow-lg">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-[#d6a24d]/40 bg-[#f2bb5c]/10 text-[#f2bb5c]">
            <SparklesIcon className="h-6 w-6" />
          </div>
          <h3 className="mt-4 text-xl font-semibold text-white">
            {activeTab} Analysis for {stock.ticker}
          </h3>
          <p className="mt-2 max-w-md text-sm text-[#9aa9bf]">
            The detailed {activeTab.toLowerCase()} models and historical data views for{" "}
            {stock.ticker} will be available in the next module release.
          </p>
        </div>
      )}

      <DisclaimerFooter />
    </>
  );
}

function SparklesIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3L12 3Z" />
    </svg>
  );
}

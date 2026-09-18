import React from "react";

export type ResearchTabKey =
  | "Overview"
  | "Financials"
  | "Growth"
  | "Valuation"
  | "Backtest";

const TABS: ResearchTabKey[] = [
  "Overview",
  "Financials",
  "Growth",
  "Valuation",
  "Backtest",
];

export function ResearchTabs({
  activeTab,
  onTabChange,
}: {
  activeTab: ResearchTabKey;
  onTabChange: (tab: ResearchTabKey) => void;
}) {
  return (
    <nav className="mb-6 flex border-b border-white/10" aria-label="Stock research tabs">
      <div className="flex gap-8">
        {TABS.map((tab) => {
          const isActive = activeTab === tab;
          return (
            <button
              key={tab}
              type="button"
              onClick={() => onTabChange(tab)}
              className={[
                "relative pb-3 text-sm font-semibold transition",
                isActive
                  ? "text-[#f4d18b]"
                  : "text-[#9aa9bf] hover:text-white",
              ].join(" ")}
            >
              {tab}
              {isActive && (
                <span className="absolute inset-x-0 bottom-0 h-0.5 rounded-full bg-[#f2bb5c]" />
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
}


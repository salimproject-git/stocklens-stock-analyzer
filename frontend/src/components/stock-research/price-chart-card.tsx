"use client";

import React, { useState } from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { SectionCard } from "@/components/ui/section-card";
import { formatRupiah } from "@/utils/currency";

const TIMEFRAMES = ["3M", "6M", "9M", "12M"] as const;
type Timeframe = (typeof TIMEFRAMES)[number];

export function PriceChartCard({
  chartData,
}: {
  chartData: StockDetail["priceChart"];
}) {
  const [activeTimeframe, setActiveTimeframe] = useState<Timeframe>("12M");

  const points = chartData.points.slice(-Number.parseInt(activeTimeframe, 10));
  const width = 500;
  const height = 180;
  const values = points.map((p) => p.value);
  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = max - min || 1;

  const svgPoints = points.map((p, idx) => {
    const x = (idx / Math.max(points.length - 1, 1)) * (width - 40) + 20;
    const y = height - ((p.value - min) / range) * (height - 40) - 20;
    return `${x},${y}`;
  });

  const polylineStr = svgPoints.join(" ");
  const lastPoint = svgPoints[svgPoints.length - 1].split(",");
  const lastX = parseFloat(lastPoint[0]);
  const lastY = parseFloat(lastPoint[1]);

  const areaPath = `M 20 ${height} L ${svgPoints.join(" L ")} L ${width - 20} ${height} Z`;

  return (
    <SectionCard
      icon={<TrendingUpIcon className="h-4 w-4" />}
      title="Price Chart"
      actionSlot={
        <div className="flex items-center gap-1 rounded-xl border border-white/10 bg-[#091322]/80 p-1 text-xs">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                type="button"
                onClick={() => setActiveTimeframe(tf)}
                aria-pressed={activeTimeframe === tf}
              className={[
                "rounded-lg px-2.5 py-1 font-semibold transition",
                activeTimeframe === tf
                  ? "bg-[#f2bb5c] text-[#1d170f]"
                  : "text-[#9ba9bd] hover:bg-white/5 hover:text-white",
              ].join(" ")}
            >
              {tf}
            </button>
          ))}
        </div>
      }
    >
      {/* SVG Chart */}
      <div className="relative mt-2 h-[190px] min-w-0 w-full">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          className="block h-full w-full overflow-visible"
          aria-hidden="true"
        >
          <defs>
            <linearGradient id="chart-area-grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3ef0a9" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#3ef0a9" stopOpacity="0" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          <line x1="20" y1="30" x2={width - 20} y2="30" stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" />
          <line x1="20" y1="80" x2={width - 20} y2="80" stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" />
          <line x1="20" y1="130" x2={width - 20} y2="130" stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" />

          {/* Area fill */}
          <path d={areaPath} fill="url(#chart-area-grad)" />

          {/* Line stroke */}
          <polyline
            fill="none"
            points={polylineStr}
            stroke="#3ef0a9"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Endpoint pulsing dot */}
          <circle cx={lastX} cy={lastY} r="5" fill="#3ef0a9" />
          <circle cx={lastX} cy={lastY} r="9" fill="#3ef0a9" opacity="0.3" />
        </svg>

        {/* Floating Endpoint Label */}
        <div
          className="absolute rounded-lg border border-[#1fcf86]/50 bg-[#0d2b22] px-2 py-0.5 text-xs font-bold text-[#3ef0a9] shadow-lg"
          style={{
            right: 0,
            top: `${Math.min(78, Math.max(0, (lastY / height) * 100 - 15))}%`,
          }}
        >
          {formatRupiah(points.at(-1)?.value ?? 0)}
        </div>
      </div>

      {/* X-Axis Month Labels */}
      <div className="mt-2 flex justify-between gap-2 px-2 text-[11px] text-[#7f8c9f]">
        {getAxisPoints(points).map((p) => {
          const [month, year] = p.date.split(" ");
          return (
            <span key={p.date} className="flex min-w-0 flex-col items-center text-center leading-tight">
              <span>{month}</span>
              <span className="mt-0.5">{year}</span>
            </span>
          );
        })}
      </div>

      {/* Bottom Key Stats Bar */}
      <div className="mt-4 grid grid-cols-5 divide-x divide-white/8 rounded-xl border border-white/8 bg-[#07111c]/80 p-3 text-center">
        <div>
          <div className="text-xs font-semibold text-white">
            {formatRupiah(chartData.low52W)}
          </div>
          <div className="mt-0.5 text-[10px] text-[#7f8c9f]">52W Low</div>
        </div>
        <div>
          <div className="text-xs font-semibold text-white">
            {formatRupiah(chartData.high52W)}
          </div>
          <div className="mt-0.5 text-[10px] text-[#7f8c9f]">52W High</div>
        </div>
        <div>
          <div className="text-xs font-semibold text-[#ff5967]">
            {chartData.ytdPercent.toFixed(1).replace(".", ",")}%
          </div>
          <div className="mt-0.5 text-[10px] text-[#7f8c9f]">YTD</div>
        </div>
        <div>
          <div className="text-xs font-semibold text-white">
            {chartData.marketCap}
          </div>
          <div className="mt-0.5 text-[10px] text-[#7f8c9f]">Market Cap</div>
        </div>
        <div>
          <div className="text-xs font-semibold text-white">
            {chartData.peTTM.toFixed(1).replace(".", ",")}x
          </div>
          <div className="mt-0.5 text-[10px] text-[#7f8c9f]">P/E (TTM)</div>
        </div>
      </div>
    </SectionCard>
  );
}

function getAxisPoints(points: { date: string; value: number }[]) {
  const step = Math.max(1, Math.ceil((points.length - 1) / 6));

  return points.filter((_, index) => index % step === 0 || index === points.length - 1);
}

function TrendingUpIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
      <polyline points="17 6 23 6 23 12" />
    </svg>
  );
}


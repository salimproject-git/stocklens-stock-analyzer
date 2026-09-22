import React from "react";
import { StockDetail } from "@/data/mock-stock-details";
import { analyzeHistoricalGrowth } from "@/lib/analysis";

type AnnualTrendCard = NonNullable<StockDetail["financialHistory"]>["annualTrendCards"][number];
type AnnualTable = NonNullable<StockDetail["financialHistory"]>["annualTable"];

const REVENUE_COLOR = "#2563eb";
const NET_INCOME_COLOR = "#16a34a";
const EPS_COLOR = "#7c3aed";

type ChartSeries = {
  id: string;
  label: string;
  unit: string;
  color: string;
  points: { label: string; value: number }[];
};

function parseNumeric(value: string | undefined) {
  if (!value) return Number.NaN;
  const cleaned = value.replace(/[^0-9.,-]/g, "").replace(/\./g, "").replace(",", ".");
  if (!cleaned) return Number.NaN;
  const numeric = Number(cleaned);
  return Number.isNaN(numeric) ? Number.NaN : numeric;
}

function formatTick(value: number) {
  return new Intl.NumberFormat("id-ID", {
    maximumFractionDigits: value >= 100 ? 0 : 2,
  }).format(value);
}

// Projected periods are detected from the period label so reusable components
// never depend on a hardcoded year/quarter.
function isProjectedPeriod(label: string) {
  return /(proyeksi|projeksi|\bproj\b|estimasi|\bestimate\b|\(f\)|\(e\)|\bF\d{2}\b|\bE\d{2}\b)/i.test(
    label,
  );
}

function LineChart({
  primary,
  secondary,
  caption,
}: {
  primary: ChartSeries;
  secondary?: ChartSeries;
  caption: string;
}) {
  const width = 760;
  const height = 260;
  const pad = { top: 26, right: secondary ? 62 : 24, bottom: 34, left: 62 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;

  const axisLabels = primary.points.map((point) => point.label);
  const secondaryValues = new Map(
    (secondary?.points ?? []).map((point) => [point.label, point.value]),
  );

  const scaleMax = (values: number[]) => {
    const max = Math.max(...values, 0);
    return max > 0 ? max * 1.12 : 1;
  };

  const primaryMax = scaleMax(primary.points.map((point) => point.value));
  const secondaryMax = secondary ? scaleMax(secondary.points.map((point) => point.value)) : 1;

  const xFor = (index: number) =>
    axisLabels.length > 1
      ? pad.left + (index / (axisLabels.length - 1)) * plotWidth
      : pad.left + plotWidth / 2;

  const yFor = (value: number, max: number) =>
    pad.top + plotHeight - (value / max) * plotHeight;

  const linePath = (points: { label: string; value: number }[], max: number) => {
    const coordinates = points
      .map((point) => {
        const index = axisLabels.indexOf(point.label);
        return index < 0 ? null : `${xFor(index)},${yFor(point.value, max)}`;
      })
      .filter((entry): entry is string => entry !== null);

    return coordinates.length > 1 ? `M${coordinates.join(" L")}` : "";
  };

  const secondaryPoints = secondary
    ? axisLabels
        .filter((label) => secondaryValues.has(label))
        .map((label) => ({ label, value: secondaryValues.get(label) as number }))
    : [];

  const gridLevels = [0, 1, 2, 3];

  return (
    <figure className="rounded-xl border border-[#e3e8ef] bg-white p-4">
      <figcaption className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-[12px] font-medium text-[#5b6b82]">
        <span className="flex items-center gap-2">
          <span
            className="h-2 w-2 rounded-full"
            style={{ backgroundColor: primary.color }}
            aria-hidden="true"
          />
          {primary.label} · {primary.unit}
        </span>
        {secondary && (
          <span className="flex items-center gap-2">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: secondary.color }}
              aria-hidden="true"
            />
            {secondary.label} · {secondary.unit}
          </span>
        )}
      </figcaption>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-[260px] w-full"
        role="img"
        aria-label={`${primary.label} historical series`}
      >
        {gridLevels.map((level) => {
          const ratio = level / (gridLevels.length - 1);
          const y = pad.top + plotHeight * ratio;

          return (
            <g key={level}>
              <line
                x1={pad.left}
                x2={pad.left + plotWidth}
                y1={y}
                y2={y}
                stroke="#eef2f7"
                strokeWidth="1"
              />
              <text
                x={pad.left - 10}
                y={y + 4}
                textAnchor="end"
                fill="#94a3b8"
                fontSize="11"
              >
                {formatTick(primaryMax * (1 - ratio))}
              </text>
              {secondary && (
                <text
                  x={pad.left + plotWidth + 10}
                  y={y + 4}
                  textAnchor="start"
                  fill="#94a3b8"
                  fontSize="11"
                >
                  {formatTick(secondaryMax * (1 - ratio))}
                </text>
              )}
            </g>
          );
        })}

        {axisLabels.map((label, index) => (
          <text
            key={label}
            x={xFor(index)}
            y={height - 10}
            textAnchor="middle"
            fill="#94a3b8"
            fontSize="11"
          >
            {label}
          </text>
        ))}

        {secondary && secondaryPoints.length > 1 && (
          <path
            d={linePath(secondaryPoints, secondaryMax)}
            fill="none"
            stroke={secondary.color}
            strokeWidth="2"
            strokeLinejoin="round"
          />
        )}

        <path
          d={linePath(primary.points, primaryMax)}
          fill="none"
          stroke={primary.color}
          strokeWidth="2"
          strokeLinejoin="round"
        />

        {[...primary.points, ...secondaryPoints].map((point, index) => {
          const isSecondary = index >= primary.points.length;
          const axisIndex = axisLabels.indexOf(point.label);
          if (axisIndex < 0) return null;

          const color = isSecondary ? secondary?.color : primary.color;
          const max = isSecondary ? secondaryMax : primaryMax;

          return (
            <circle
              key={`${isSecondary ? "secondary" : "primary"}-${point.label}`}
              cx={xFor(axisIndex)}
              cy={yFor(point.value, max)}
              r="3.5"
              fill="#ffffff"
              stroke={color}
              strokeWidth="2"
            >
              <title>{`${point.label}: ${formatTick(point.value)}`}</title>
            </circle>
          );
        })}
      </svg>

      <p className="mt-2 text-[12px] leading-relaxed text-[#7c8aa0]">{caption}</p>
    </figure>
  );
}

function KpiTile({ card }: { card: AnnualTrendCard }) {
  const numeric = parseNumeric(card.cagrValue);
  const tone =
    Number.isNaN(numeric) || numeric === 0
      ? "text-[#0f1e35]"
      : numeric > 0
        ? "text-[#0f8a4f]"
        : "text-[#c0392b]";

  return (
    <div className="rounded-xl border border-[#e3e8ef] bg-white p-5 shadow-[0_1px_2px_rgba(15,30,53,0.03)]">
      <div className="text-[12px] font-medium text-[#5b6b82]">{card.title}</div>
      <div className={`mt-2 text-[26px] font-semibold tracking-[-0.01em] ${tone}`}>
        {card.cagrValue}
      </div>
      <div className="mt-1 text-[12px] font-medium text-[#7c8aa0]">{card.cagrLabel}</div>
      <div className="mt-3 border-t border-[#eef2f7] pt-3 text-[12px] leading-relaxed text-[#7c8aa0]">
        Latest reported: {card.latestValue} {card.unit}
      </div>
    </div>
  );
}

function HistoricalGrowthTable({ table }: { table: AnnualTable }) {
  const latestIndex = table.periods.length - 1;

  return (
    <div className="overflow-x-auto rounded-xl border border-[#e3e8ef] bg-white">
      <table className="w-full min-w-[880px] text-left text-[13px]">
        <thead className="border-b border-[#eef2f7] bg-[#fafbfd] text-[11px] font-semibold uppercase tracking-wide text-[#7c8aa0]">
          <tr>
            <th className="min-w-[220px] px-4 py-3">Metric</th>
            {table.periods.map((period) => (
              <th key={period} className="px-4 py-3 text-right">
                <span className="inline-flex items-center gap-1.5">
                  {period}
                  {isProjectedPeriod(period) && (
                    <span className="rounded-md border border-[#f0d9a8] bg-[#fdf6e7] px-1.5 py-0.5 text-[10px] font-semibold normal-case text-[#a1720f]">
                      Proj
                    </span>
                  )}
                </span>
              </th>
            ))}
            <th className="px-4 py-3 text-right">{table.changeLabel}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#eef2f7]">
          {table.rows.map((row) => {
            const changeNumeric = parseNumeric(row.change);
            const changeTone =
              Number.isNaN(changeNumeric) || changeNumeric === 0
                ? "text-[#5b6b82]"
                : changeNumeric > 0
                  ? "text-[#0f8a4f]"
                  : "text-[#c0392b]";

            return (
              <tr key={row.metric} className="transition hover:bg-[#fafbfd]">
                <td className="px-4 py-3 font-medium text-[#0f1e35]">{row.metric}</td>
                {table.periods.map((period, index) => (
                  <td
                    key={period}
                    className={
                      index === latestIndex
                        ? "px-4 py-3 text-right font-semibold text-[#0f1e35]"
                        : "px-4 py-3 text-right text-[#5b6b82]"
                    }
                  >
                    {row.values[index] ?? "—"}
                  </td>
                ))}
                <td className={`px-4 py-3 text-right font-semibold ${changeTone}`}>
                  {row.change}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function HistoricalGrowthSection({ stock }: { stock: StockDetail }) {
  const history = stock.financialHistory;
  const cards = history?.annualTrendCards ?? [];
  const table = history?.annualTable;

  const toSeries = (id: string, color: string): ChartSeries | undefined => {
    const card = cards.find((entry) => entry.id === id);
    if (!card || card.series.length < 2) return undefined;

    return {
      id: card.id,
      label: card.title,
      unit: card.unit,
      color,
      points: card.series.map((point) => ({ label: point.year, value: point.value })),
    };
  };

  const revenueSeries = toSeries("revenue", REVENUE_COLOR);
  const netIncomeSeries = toSeries("netIncome", NET_INCOME_COLOR);
  const epsSeries = toSeries("eps", EPS_COLOR);

  const insights = table ? analyzeHistoricalGrowth(cards, table).insights : [];

  return (
    <div className="space-y-5">
      {cards.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {cards.map((card) => (
            <KpiTile key={card.id} card={card} />
          ))}
        </div>
      ) : (
        <p className="rounded-xl border border-dashed border-[#dfe5ee] bg-[#fbfcfe] p-5 text-[13px] text-[#7c8aa0]">
          Historical growth measures are not available for this ticker yet.
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {revenueSeries && (
          <LineChart
            primary={revenueSeries}
            secondary={netIncomeSeries}
            caption={
              netIncomeSeries
                ? `Revenue (left axis) and net income (right axis) across the available annual periods, both reported in ${revenueSeries.unit}.`
                : `Revenue across the available annual periods, reported in ${revenueSeries.unit}.`
            }
          />
        )}

        {epsSeries && (
          <LineChart
            primary={epsSeries}
            caption={`Earnings per share across the available annual periods, reported in ${epsSeries.unit}.`}
          />
        )}
      </div>

      {table ? (
        <HistoricalGrowthTable table={table} />
      ) : (
        <p className="rounded-xl border border-dashed border-[#dfe5ee] bg-[#fbfcfe] p-5 text-[13px] text-[#7c8aa0]">
          Historical financial series are not available for this ticker yet.
        </p>
      )}

      {insights.length > 0 && (
        <div className="rounded-xl border border-[#e3e8ef] bg-[#fbfcfe] p-5">
          <h4 className="text-[13px] font-semibold text-[#0f1e35]">
            Growth observations
          </h4>
          <ul className="mt-3 space-y-2">
            {insights.map((insight) => (
              <li
                key={insight}
                className="flex gap-3 text-[13px] leading-relaxed text-[#5b6b82]"
              >
                <span
                  className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#2563eb]"
                  aria-hidden="true"
                />
                {insight}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

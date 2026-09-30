import React from "react";
import { UnavailableBadge } from "@/components/ui/unavailable-badge";

/**
 * Placeholder frame for a chart whose data is not in the database yet.
 *
 * Charts used to disappear entirely when their series were empty, which hid
 * whole sections of the research page and made the missing data invisible. This
 * keeps the chart frame (title, axes area, legend slot) on screen and labels the
 * gap honestly, so each chart can be filled in one at a time.
 */
export function ChartEmptyState({
  title,
  subtitle,
  hint,
  height = 220,
  className = "",
}: {
  title?: string;
  subtitle?: string;
  hint?: string;
  height?: number;
  className?: string;
}) {
  return (
    <div
      className={[
        "flex min-w-0 flex-col rounded-lg border border-white/[0.09] bg-[#081523]/75 p-4",
        className,
      ].join(" ")}
    >
      {title && <div className="text-sm font-semibold text-white">{title}</div>}
      {subtitle && <div className="mt-1 text-[11px] text-[#8e9db3]">{subtitle}</div>}

      <div
        className="mt-3 flex flex-col items-center justify-center gap-2.5 rounded-lg border border-dashed border-white/[0.14] bg-[#07111c]/60 px-4 py-6 text-center"
        style={{ minHeight: height }}
      >
        <UnavailableBadge label="No data yet" />
        <p className="max-w-md text-[11px] leading-relaxed text-[#8e9bb0]">
          {hint ??
            "This chart cannot be drawn yet because its data is not stored in the database. The chart frame stays on screen so it can be filled in step by step."}
        </p>
      </div>
    </div>
  );
}

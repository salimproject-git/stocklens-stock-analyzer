import React from "react";

/**
 * Badge for illustrative/sample data that is intentionally not backed by the
 * database yet (for example the backtest demo dataset). It exists so demo
 * numbers can never be mistaken for stored research results.
 */
export function DemoDataBadge({
  label = "Sample data · Demo",
  className = "",
}: {
  label?: string;
  className?: string;
}) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1.5 rounded-md border border-[#d6a24d]/45 bg-[#2b2212]/70 px-2 py-1 text-xs font-medium text-[#f4d18b]",
        className,
      ].join(" ")}
      title="This figure is sample data for the demo, not yet stored in the database"
    >
      <svg
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        className="h-3 w-3"
        aria-hidden="true"
      >
        <path d="M8 1.5 14.5 13H1.5L8 1.5Z" />
        <path d="M8 6v3M8 11h.01" />
      </svg>
      {label}
    </span>
  );
}

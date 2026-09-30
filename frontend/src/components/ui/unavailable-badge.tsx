import React from "react";

/**
 * Standard badge to indicate data is not yet available in the database.
 * Used consistently across the app for missing/incomplete data.
 */
export function UnavailableBadge({
  label = "Not available",
  className = "",
}: {
  label?: string;
  className?: string;
}) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1.5 rounded-md border border-[#8f9db1]/30 bg-[#1a2332]/60 px-2 py-1 text-xs font-medium text-[#9aa9bf]",
        className,
      ].join(" ")}
      title="This data is not available in the database yet"
    >
      <svg
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        className="h-3 w-3"
        aria-hidden="true"
      >
        <circle cx="8" cy="8" r="6" />
        <path d="M8 5v3M8 11h.01" />
      </svg>
      {label}
    </span>
  );
}

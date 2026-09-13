import React from "react";

type BadgeTone =
  | "undervalued"
  | "fairly-valued"
  | "overvalued"
  | "healthy"
  | "positive"
  | "stable"
  | "cukup"
  | "caution";

export function StatusBadge({
  tone = "positive",
  children,
  className = "",
}: {
  tone?: BadgeTone;
  children: React.ReactNode;
  className?: string;
}) {
  const toneClasses: Record<BadgeTone, string> = {
    undervalued: "border-[#1fcf86]/40 bg-[#0d2b22] text-[#3ef0a9]",
    healthy: "border-[#1fcf86]/40 bg-[#0d2b22] text-[#3ef0a9]",
    positive: "border-[#1fcf86]/40 bg-[#0d2b22] text-[#3ef0a9]",
    "fairly-valued": "border-[#c79d51]/40 bg-[#2f2717] text-[#f1c56d]",
    stable: "border-[#c79d51]/40 bg-[#2f2717] text-[#f1c56d]",
    cukup: "border-[#d9a23c]/40 bg-[#2b2212] text-[#eab308]",
    caution: "border-[#ff4b5f]/35 bg-[#32161e] text-[#ff5f73]",
    overvalued: "border-[#ff4b5f]/35 bg-[#32161e] text-[#ff5f73]",
  };

  return (
    <span
      className={[
        "inline-flex items-center rounded-lg border px-2.5 py-1 text-xs font-semibold tracking-wide transition",
        toneClasses[tone] ?? toneClasses.positive,
        className,
      ].join(" ")}
    >
      {children}
    </span>
  );
}


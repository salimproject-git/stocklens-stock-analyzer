import React from "react";

export function ResearchSection({
  title,
  subtitle,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={[
        "relative overflow-hidden rounded-2xl border border-[#e3e8ef] bg-white p-6 shadow-[0_1px_2px_rgba(15,30,53,0.04),0_14px_34px_rgba(15,30,53,0.06)]",
        className,
      ].join(" ")}
    >
      <span className="absolute inset-y-0 left-0 w-1 bg-[#2563eb]/70" aria-hidden="true" />

      <header className="mb-5 border-b border-[#eef2f7] pb-4 pl-2">
        <h3 className="text-[17px] font-semibold tracking-[-0.01em] text-[#0f1e35]">
          {title}
        </h3>
        {subtitle && (
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[#5b6b82]">
            {subtitle}
          </p>
        )}
      </header>

      <div className="pl-2">{children}</div>
    </section>
  );
}

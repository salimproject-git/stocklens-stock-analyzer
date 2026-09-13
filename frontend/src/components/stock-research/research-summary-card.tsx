import React from "react";

export function ResearchSummaryCard({
  summaryText,
  methodologyUrl = "#",
}: {
  summaryText: string;
  methodologyUrl?: string;
}) {
  return (
    <section className="mb-6 flex flex-col items-start justify-between gap-4 rounded-[20px] border border-white/10 bg-[linear-gradient(180deg,_rgba(11,23,37,0.95),_rgba(7,16,28,0.97))] p-5 shadow-md md:flex-row md:items-center">
      <div className="flex items-start gap-4">
        <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[#3892d0]/40 bg-[#3892d0]/12 text-[#59b3f4]">
          <FileTextIcon className="h-5 w-5" />
        </span>
        <div>
          <h2 className="text-base font-semibold text-white">Research Summary</h2>
          <p className="mt-1 max-w-4xl text-sm leading-relaxed text-[#b6c2d4]">
            {summaryText}
          </p>
        </div>
      </div>
      <a
        href={methodologyUrl}
        className="shrink-0 flex items-center gap-1.5 text-sm font-semibold text-[#f2bb5c] transition hover:text-[#ffd68a]"
      >
        <span>View Methodology</span>
        <ArrowRightIcon className="h-4 w-4" />
      </a>
    </section>
  );
}

function FileTextIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  );
}

function ArrowRightIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <line x1="5" y1="12" x2="19" y2="12" />
      <polyline points="12 5 19 12 12 19" />
    </svg>
  );
}


"use client";

import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { BeginnerSignalSummary } from "@/lib/analysis";

/**
 * Beginner-facing Backtest pieces (docs/BACKTEST_BEGINNER_CONCEPT.md):
 *   * `BacktestReportCard` — the "report card, not a forecast" banner for the tab header;
 *   * `SignalParagraph` — the plain-language summary paragraph shown under each signal card;
 *   * `BacktestVerdictGlossary` — a "What each verdict means" button that opens a popup.
 *
 * Nothing here computes a new number: it only re-words results the tab already has.
 */

function formatTimes(count: number) {
  return `${count} ${count === 1 ? "time" : "times"}`;
}

/** One signal paragraph, plain text: a single style and a single colour. */
export function SignalParagraph({ methodPhrase, signal }: { methodPhrase: string; signal: BeginnerSignalSummary }) {
  return (
    <p className="text-xs leading-5 text-[#c7d3e2]">
      when StockLens said cheap with {methodPhrase}, the price rose to target{" "}
      {formatTimes(signal.win)} ({signal.winPercent}%), fell first but eventually recovered{" "}
      {formatTimes(signal.recovered)}, and failed (risk) {formatTimes(signal.risk)}. When it said
      expensive, the price did fall {formatTimes(signal.confirmed)}, and instead rose{" "}
      {formatTimes(signal.repriced)}.
    </p>
  );
}

const CHEAP_VERDICTS = [
  { verdict: "WIN", meaning: "The price reached the upside target before the downside target. The framework was right.", color: "#36d991" },
  { verdict: "RECOVERED", meaning: "The price fell to the downside target first, then still rose to the upside target. \"Lost first, won later.\"", color: "#55c7f2" },
  { verdict: "RISK", meaning: "The price fell to the downside target and never reached the upside target. The framework was wrong.", color: "#ff827d" },
  { verdict: "FLAT", meaning: "Within 12 months the price touched neither target. Nothing decisive happened.", color: "#8290a4" },
] as const;

const EXPENSIVE_VERDICTS = [
  { verdict: "CONFIRMED", meaning: "The price did fall to the downside target. The framework was right that it was expensive.", color: "#55c7f2" },
  { verdict: "REPRICE", meaning: "The price instead rose to the upside target. The market re-rated it; the framework was wrong.", color: "#a882ff" },
  { verdict: "OBSERVE", meaning: "The price moved to neither target. Neutral, nothing to conclude.", color: "#8290a4" },
] as const;

function VerdictList({
  title,
  items,
}: {
  title: string;
  items: readonly { verdict: string; meaning: string; color: string }[];
}) {
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#8fa0b8]">{title}</div>
      <ul className="mt-2.5 space-y-2.5">
        {items.map((item) => (
          <li key={item.verdict} className="flex items-start gap-2.5">
            <span
              className="mt-1.5 h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: item.color }}
              aria-hidden="true"
            />
            <span className="text-xs leading-6 text-[#9aa9bf]">
              <span className="font-semibold text-[#d4dcec]">{item.verdict}</span> — {item.meaning}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The "report card, not a forecast" banner for the Backtest tab header. */
export function BacktestReportCard() {
  return (
    <div className="flex items-start gap-3 rounded-[20px] border border-[#3892d0]/25 bg-[#3892d0]/8 p-4 md:p-5">
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[#3892d0]/35 bg-[#3892d0]/12 text-[#65b7ee]">
        <InfoIcon className="h-4 w-4" />
      </span>
      <div>
        <p className="text-sm font-semibold leading-6 text-white">
          The backtest is a framework&apos;s report card on this stock.
        </p>
        <p className="mt-1 text-xs leading-5 text-[#9aa9bf]">
          It is historical evidence, not a forecast. It shows what actually happened to the price
          after the framework called a stock cheap or expensive.
        </p>
      </div>
    </div>
  );
}

/** "What each verdict means" — a subtitle button that opens the glossary popup. */
export function BacktestVerdictGlossary() {
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [isOpen]);

  const modal = isOpen ? (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="What each verdict means"
      onClick={() => setIsOpen(false)}
    >
      <div
        className="w-full max-w-lg overflow-hidden rounded-2xl border border-white/15 bg-[#0b1929] text-left shadow-[0_24px_80px_rgba(0,0,0,0.6)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-white/10 px-5 py-4">
          <h3 className="text-base font-normal text-white">What each verdict means</h3>
          <button
            type="button"
            onClick={() => setIsOpen(false)}
            className="rounded-lg p-1.5 text-[#9aa9bf] hover:bg-white/5 hover:text-white"
            aria-label="Close"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        </div>
        <div className="grid gap-6 px-5 py-5">
          <VerdictList title="When the framework said cheap" items={CHEAP_VERDICTS} />
          <VerdictList title="When the framework said expensive" items={EXPENSIVE_VERDICTS} />
          <p className="text-[11px] leading-5 text-[#8090a7]">
            &quot;Win or lose&quot; is decided by which target is touched first within the 12-month
            window. The targets follow the workbook rule (roughly +20% / −20%, or +15% / −10% for
            blue-chip types).
          </p>
        </div>
      </div>
    </div>
  ) : null;

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="inline-flex items-center gap-1 text-xs font-medium text-[#65b7ee] transition hover:text-[#a9d8ff]"
      >
        What each verdict means
        <HelpIcon className="h-3.5 w-3.5" />
      </button>
      {typeof document !== "undefined" && modal ? createPortal(modal, document.body) : null}
    </>
  );
}

function InfoIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <line x1="12" y1="11" x2="12" y2="16" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  );
}

function CloseIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
  );
}

function HelpIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M9.2 9.2a2.8 2.8 0 0 1 5.4.9c0 1.9-2.8 2.4-2.8 4" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}



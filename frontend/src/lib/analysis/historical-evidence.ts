import type { BacktestCase, EvidenceOutcomeBreakdown } from "@/data/mock-stock-details";
import { aggregateBacktestOverview } from "./backtest-overview";

/**
 * Historical Evidence preview for the Overview tab.
 *
 * It is built from the **stored backtest cases**, not from hand-written sample
 * numbers: `aggregateBacktestOverview` is the exact function the Backtest tab
 * renders, so the Overview card and the Backtest overview can never disagree
 * about how many cases there were or how they turned out.
 *
 * Rates use the Undervalued count as their denominator (the cases the rule
 * actually flagged), which is what makes them comparable between the two
 * rules: the method rule and the MoS rule flag different cases, so a rate
 * computed against `totalCases` would understate both.
 */

/**
 * One decimal place, matching the Backtest tab's `formatPercentage`. `100` is
 * rendered without a decimal so the common "everything worked" case reads
 * `100%` rather than `100.0%`.
 *
 * The fixed decimal is deliberate here: these three rates sit side by side, so
 * `75.0%` / `16.7%` / `8.3%` line up. The single headline figure uses
 * `formatEvidencePercent` instead, where alignment does not apply.
 */
export function formatEvidenceRate(value: number, total: number): string {
  if (total <= 0) return "0%";
  const result = (value / total) * 100;
  return result === 100 ? "100%" : `${result.toFixed(1)}%`;
}

/**
 * Compact percent for a single headline figure: `75` -> `75%`,
 * `66.666…` -> `66.7%`. Drops the decimal when it carries no information,
 * which is why the Key Metric card reads `75%` rather than `75.0%`.
 */
export function formatEvidencePercent(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? `${rounded}%` : `${rounded.toFixed(1)}%`;
}

/**
 * Shown when a rule flagged no Undervalued case, so its win rate is undefined
 * rather than 0%.
 *
 * Exported so the Key Metric card can recognise the unavailable state and size
 * the text for a word instead of a figure, without duplicating the literal.
 */
export const EVIDENCE_RATE_UNAVAILABLE = "Not available";

/**
 * Headline win rate for the Key Metric card: `(WIN + RECOVERED) / Undervalued`
 * for one classification rule, as a percentage number.
 *
 * Returns `null` when the rule flagged no Undervalued case. `0 of 0` is not a
 * 0% win rate, and printing one would claim the thesis failed every time it was
 * tested; "Not available" is the honest reading.
 */
export function evidenceWinRatePercent(
  breakdown: EvidenceOutcomeBreakdown,
): number | null {
  if (breakdown.undervalued <= 0) return null;
  return (breakdown.wins / breakdown.undervalued) * 100;
}

function buildBreakdown(
  aggregate: ReturnType<typeof aggregateBacktestOverview>["byMethod"],
  undervaluedOutcomes: ReturnType<typeof aggregateBacktestOverview>["undervaluedCases"]["byMethod"]["outcomes"],
): EvidenceOutcomeBreakdown {
  const { WIN, RECOVERED, RISK, FLAT } = undervaluedOutcomes;
  const undervalued = aggregate.valuationSignal.undervalued;
  // WIN and RECOVERED are merged into one success figure: both eventually
  // reached the upside target, RECOVERED only got there after dipping first.
  const wins = WIN + RECOVERED;

  return {
    undervalued,
    overvalued: aggregate.valuationSignal.overvaluedMixed,
    wins,
    recovered: RECOVERED,
    risk: RISK,
    flat: FLAT,
    winRate: formatEvidenceRate(wins, undervalued),
    riskRate: formatEvidenceRate(RISK, undervalued),
    flatRate: formatEvidenceRate(FLAT, undervalued),
    // FLAT is usually zero. A bare `0%` would then read as "nothing was
    // inconclusive", while `0 of 0` says "no case was flagged at all" — a very
    // different statement, so the two are told apart.
    flatSuffix: undervalued > 0 ? "" : " · 0 of 0",
  };
}

export function buildHistoricalEvidencePreview(
  cases: BacktestCase[],
): {
  totalCases: number;
  verdictMethod: EvidenceOutcomeBreakdown;
  verdictMos: EvidenceOutcomeBreakdown;
} | null {
  if (cases.length === 0) return null;

  const aggregates = aggregateBacktestOverview(cases);

  return {
    // Total cases is the whole backtest, including the cases neither rule
    // called Undervalued, so the subtitle describes the run and not a subset.
    totalCases: aggregates.byMethod.totalCases,
    verdictMethod: buildBreakdown(
      aggregates.byMethod,
      aggregates.undervaluedCases.byMethod.outcomes,
    ),
    verdictMos: buildBreakdown(
      aggregates.byMosMain,
      aggregates.undervaluedCases.byMosMain.outcomes,
    ),
  };
}

import type { BacktestCase, BacktestVerdict } from "@/data/mock-stock-details";

export const backtestMethodology = {
  observationMonths: 12,
  horizonsMonths: [3, 6, 9, 12] as const,
  /**
   * One threshold for both classifications: up +20%, down -15%.
   *
   * Previously `OVERVALUED` used +15%/-10%, so the classification also decided
   * the thresholds. Now the classification only picks the verdict **name**.
   */
  upsideThreshold: 0.2,
  downsideThreshold: -0.15,
  valuationMethodCount: 5,
  classification: { methodUndervaluedMinimum: 3, mosMainThreshold: 0.3 },
} as const;

export type ValuationClassification = "UNDERVALUED" | "OVERVALUED";

/**
 * Classification from a list of intrinsic values.
 *
 * **`IV = 0` is not a valid method.** The workbook marks it `⚪ N/A (Skip)`
 * (`=IF(B25=0, "N/A (Skip)", ...)`) and removes it from the denominator, so a
 * stock without dividends yields `3|4`, not `3|5`. `null` is skipped too.
 *
 * A negative `IV` **stays** valid: a model producing a negative value still
 * says something about the price.
 */
export function classifyIntrinsicValuesAbovePrice(values: (number | null)[], analysisPrice: number) {
  const valid = values.filter((value) => value !== null && value !== 0);
  const undervaluedMethods = valid.filter((value) => (value as number) > analysisPrice).length;
  return {
    classification: undervaluedMethods >= backtestMethodology.classification.methodUndervaluedMinimum
      ? "UNDERVALUED" as const
      : "OVERVALUED" as const,
    undervaluedMethods,
    //: Number of valid methods, not slots. This is the `/3`, `/4`, `/5` denominator.
    totalMethods: valid.length,
  };
}

export function classifyMethodsAbovePrice(methods: BacktestCase["methods"], analysisPrice: number) {
  return classifyIntrinsicValuesAbovePrice(methods.map((method) => method.intrinsicValue), analysisPrice);
}

export function backtestConsensusDescription(kind: "method" | "mos") {
  if (kind === "method") {
    return `Undervalued when at least ${backtestMethodology.classification.methodUndervaluedMinimum} valid methods produce an intrinsic value above the analysis price. Methods whose value is zero (e.g. DDM without dividends) count as N/A and stay out of the denominator, so the figure can be /3, /4, or /5.`;
  }
  const mosPercent = backtestMethodology.classification.mosMainThreshold * 100;
  return `Undervalued when MoS Main is ${mosPercent}% or higher. Below ${mosPercent}% means overvalued.`;
}

export function classifyMosMain(mosMain: number | null) {
  return mosMain !== null && mosMain >= backtestMethodology.classification.mosMainThreshold
    ? "UNDERVALUED" as const
    : "OVERVALUED" as const;
}

export function classifyCurrentValuationMos(mosPercent: number) {
  return classifyMosMain(mosPercent / 100);
}

function monthsBetween(startDate: string, endDate: string) {
  const start = new Date(`${startDate}T00:00:00Z`);
  const end = new Date(`${endDate}T00:00:00Z`);
  return (end.getUTCFullYear() - start.getUTCFullYear()) * 12 + end.getUTCMonth() - start.getUTCMonth();
}

function getObservationPath(testCase: BacktestCase) {
  return testCase.pricePath
    .filter((point) => {
      const months = monthsBetween(testCase.analysisDate, point.date);
      return point.date > testCase.analysisDate && months <= backtestMethodology.observationMonths;
    })
    .sort((left, right) => left.date.localeCompare(right.date));
}

/**
 * Verdict for a user-entered entry price, used only by the detail drawer's
 * "Your Entry Simulation" panel.
 *
 * The stored verdict is always shown as-is; this recomputes only for a price the
 * user typed, and it must follow the same rules as the backend so the simulation
 * cannot contradict the table:
 *
 *   * one threshold pair for both classifications (+20% / -15%);
 *   * neither touched -> `FLAT` (never `OBSERVE`);
 *   * up first (or same day) -> `WIN` / `REPRICE`;
 *   * down first -> `RECOVERED` / `CONFIRMED`.
 */
export function calculateSimulatedVerdict(testCase: BacktestCase, entryPrice: number): BacktestVerdict {
  const isUndervalued = classifyMethodsAbovePrice(testCase.methods, testCase.analysisPrice).classification === "UNDERVALUED";
  const upsideTarget = entryPrice * (1 + backtestMethodology.upsideThreshold);
  const downsideTarget = entryPrice * (1 + backtestMethodology.downsideThreshold);
  let upsideDate: string | null = null;
  let downsideDate: string | null = null;

  for (const point of getObservationPath(testCase)) {
    if (!upsideDate && point.high >= upsideTarget) upsideDate = point.date;
    if (!downsideDate && point.low <= downsideTarget) downsideDate = point.date;
    if (upsideDate || downsideDate) break;
  }

  if (!upsideDate && !downsideDate) return "FLAT";
  // Down yang lebih dulu berarti tesis sempat salah; kalau up yang lebih dulu
  // (atau hari yang sama), arah yang benar menang.
  if (downsideDate && (!upsideDate || downsideDate < upsideDate)) {
    return isUndervalued ? "RECOVERED" : "CONFIRMED";
  }
  return isUndervalued ? "WIN" : "REPRICE";
}

function rangeAtHorizon(testCase: BacktestCase, horizon: number, analysisPrice: number) {
  const points = getObservationPath(testCase).filter(
    (point) => monthsBetween(testCase.analysisDate, point.date) <= horizon,
  );
  const point = points.find((candidate) => monthsBetween(testCase.analysisDate, candidate.date) === horizon) ?? points.at(-1);
  if (!point) return { high: null, low: null, highReturn: null, lowReturn: null };
  return {
    high: point.high,
    low: point.low,
    highReturn: point.high / analysisPrice - 1,
    lowReturn: point.low / analysisPrice - 1,
  };
}

export function closeAtBacktestHorizon(testCase: BacktestCase, horizon: number) {
  return getObservationPath(testCase)
    .filter((point) => monthsBetween(testCase.analysisDate, point.date) <= horizon)
    .at(-1)?.close ?? null;
}

export function calculateBacktestMetrics(testCase: BacktestCase, analysisPrice = testCase.analysisPrice) {
  const pricePath = getObservationPath(testCase);
  const peak = pricePath.reduce<(typeof pricePath)[number] | null>(
    (current, point) => !current || point.high > current.high ? point : current, null,
  );
  const trough = pricePath.reduce<(typeof pricePath)[number] | null>(
    (current, point) => !current || point.low < current.low ? point : current, null,
  );
  const ranges = backtestMethodology.horizonsMonths.map((horizon) => rangeAtHorizon(testCase, horizon, analysisPrice));
  return {
    ranges,
    returns: ranges.map((range) => range.highReturn),
    peakReturn: peak ? peak.high / analysisPrice - 1 : null,
    troughReturn: trough ? trough.low / analysisPrice - 1 : null,
    downPrice: trough?.low ?? null,
    peakPrice: peak?.high ?? null,
    peakMonth: peak ? monthsBetween(testCase.analysisDate, peak.date) : null,
    troughMonth: trough ? monthsBetween(testCase.analysisDate, trough.date) : null,
  };
}

export function countMethodsAboveAnalysisPrice(testCase: BacktestCase, analysisPrice = testCase.analysisPrice) {
  const result = classifyMethodsAbovePrice(testCase.methods, analysisPrice);
  return `${result.undervaluedMethods}/${result.totalMethods}`;
}

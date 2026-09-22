import type { BacktestCase, BacktestVerdict } from "@/data/mock-stock-details";

export const backtestMethodology = {
  observationMonths: 12,
  horizonsMonths: [3, 6, 9, 12] as const,
  undervalued: { upsideThreshold: 0.2, downsideThreshold: -0.15 },
  overvaluedOrMixed: { upsideThreshold: 0.15, downsideThreshold: -0.1 },
  valuationMethodCount: 5,
  classification: { methodUndervaluedMinimum: 3, mosMainThreshold: 0.3 },
} as const;

export type ValuationClassification = "UNDERVALUED" | "OVERVALUED_MIXED";

export function classifyMethodsAbovePrice(methods: BacktestCase["methods"], analysisPrice: number) {
  return classifyIntrinsicValuesAbovePrice(methods.map((method) => method.intrinsicValue), analysisPrice);
}

export function classifyIntrinsicValuesAbovePrice(values: (number | null)[], analysisPrice: number) {
  const undervaluedMethods = values.filter((value) => value !== null && value > analysisPrice).length;
  return {
    classification: undervaluedMethods >= backtestMethodology.classification.methodUndervaluedMinimum
      ? "UNDERVALUED" as const
      : "OVERVALUED_MIXED" as const,
    undervaluedMethods,
    totalMethods: values.length,
  };
}

export function backtestConsensusDescription(kind: "method" | "mos") {
  if (kind === "method") {
    return `Undervalued jika minimal ${backtestMethodology.classification.methodUndervaluedMinimum} dari ${backtestMethodology.valuationMethodCount} metode menghasilkan intrinsic value di atas harga analisis. Selain itu overvalued.`;
  }
  const mosPercent = backtestMethodology.classification.mosMainThreshold * 100;
  return `Undervalued jika MoS Main ${mosPercent}% atau lebih. Di bawah ${mosPercent}% berarti overvalued.`;
}

export function buildBacktestOutcomeExplanation() {
  const upsidePercent = backtestMethodology.undervalued.upsideThreshold * 100;
  const downsidePercent = Math.abs(backtestMethodology.undervalued.downsideThreshold) * 100;
  return `A WIN means an undervalued case reached the +${upsidePercent}% target before the -${downsidePercent}% downside`;
}

export function classifyMosMain(mosMain: number | null) {
  return mosMain !== null && mosMain >= backtestMethodology.classification.mosMainThreshold
    ? "UNDERVALUED" as const
    : "OVERVALUED_MIXED" as const;
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

export function calculateSimulatedVerdict(testCase: BacktestCase, entryPrice: number): BacktestVerdict {
  const isUndervalued = classifyMethodsAbovePrice(testCase.methods, testCase.analysisPrice).classification === "UNDERVALUED";
  const thresholds = isUndervalued ? backtestMethodology.undervalued : backtestMethodology.overvaluedOrMixed;
  const upsideTarget = entryPrice * (1 + thresholds.upsideThreshold);
  const downsideTarget = entryPrice * (1 + thresholds.downsideThreshold);
  let upsideDate: string | null = null;
  let downsideDate: string | null = null;

  for (const point of getObservationPath(testCase)) {
    if (!upsideDate && point.high >= upsideTarget) upsideDate = point.date;
    if (!downsideDate && point.low <= downsideTarget) downsideDate = point.date;
    if (upsideDate || downsideDate) break;
  }

  if (!upsideDate && !downsideDate) return isUndervalued ? "FLAT" : "OBSERVE";
  if (upsideDate && (!downsideDate || upsideDate < downsideDate)) return isUndervalued ? "WIN" : "OBSERVE";
  return isUndervalued ? "RECOVERED" : "CONFIRMED";
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

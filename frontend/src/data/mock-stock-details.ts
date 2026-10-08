import { VALUATION_METHOD_LABELS } from "@/lib/valuation-methods";
import type { BacktestVerdict, BacktestCase } from "@/data/stock-detail-types";

type AutoBacktestSeed = {
  quarter: string;
  analysisDate: string;
  analysisPrice: number;
  /**
   * Stored consensus for this sample case, in the shape the database stores it
   * (`'3|5'`, or `'N/A'` when fewer than three methods are valid).
   *
   * These are literals, not a rule: the tab reads the badge, it does not derive
   * it. They reproduce exactly what this sample displayed before the badge
   * became a stored value, so the demo view does not change.
   */
  consensus: string;
  consensusUndervalued: number | null;
  consensusValid: number;
  methods: [number, number, number, number, number];
  mos: [number, number, number];
  revenueYoY: number;
  netIncomeYoY: number;
  epsMomentum: string;
  revenueMomentum: string;
  roeTrend: string;
  ranges: ([number, number] | null)[];
  peakPrice: number;
  peakMonth: number;
  verdict: BacktestVerdict;
  verdictMos: BacktestVerdict;
};

function backtestDateAtMonth(date: string, months: number) {
  const start = new Date(`${date}T00:00:00Z`);
  if (months === 0) return new Date(start.getTime() + 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  return new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + months, 15)).toISOString().slice(0, 10);
}

function makeAutoBacktestCase(seed: AutoBacktestSeed): BacktestCase {
  const horizonPoints = seed.ranges.flatMap((range, index) => range ? [{ date: backtestDateAtMonth(seed.analysisDate, (index + 1) * 3), high: range[0], low: range[1], close: (range[0] + range[1]) / 2 }] : []);
  const peakPoint = { date: backtestDateAtMonth(seed.analysisDate, seed.peakMonth), high: seed.peakPrice, low: seed.peakPrice, close: seed.peakPrice };
  const pricePath = [peakPoint, ...horizonPoints.filter((point) => point.date !== peakPoint.date)];
  return {
    id: `AUTO-${seed.quarter.replace(" ", "-")}`,
    ticker: "AUTO",
    quarter: seed.quarter,
    analysisDate: seed.analysisDate,
    analysisPrice: seed.analysisPrice,
    sector: "Automotive",
    stockType: "Cyclical",
    mosMain: seed.mos[0],
    mosPeter: seed.mos[1],
    mosWeight: seed.mos[2],
    consensus: seed.consensus,
    consensusUndervalued: seed.consensusUndervalued,
    consensusValid: seed.consensusValid,
    verdict: seed.verdict,
    verdictMos: seed.verdictMos,
    methods: [
      { method: VALUATION_METHOD_LABELS.PETER_LYNCH, methodCode: "PETER_LYNCH", intrinsicValue: seed.methods[0] },
      { method: VALUATION_METHOD_LABELS.TYPE_SECTOR_WEIGHTED, methodCode: "TYPE_SECTOR_WEIGHTED", intrinsicValue: seed.methods[1] },
      { method: VALUATION_METHOD_LABELS.MEAN_REVERSION_PBV, methodCode: "MEAN_REVERSION_PBV", intrinsicValue: seed.methods[2] },
      { method: VALUATION_METHOD_LABELS.DDM, methodCode: "DDM", intrinsicValue: seed.methods[3] },
      { method: VALUATION_METHOD_LABELS.DISCOUNTED_EARNINGS, methodCode: "DISCOUNTED_EARNINGS", intrinsicValue: seed.methods[4] },
    ],
    context: {
      revenueYoY: seed.revenueYoY,
      netIncomeYoY: seed.netIncomeYoY,
      epsMomentum: seed.epsMomentum,
      revenueMomentum: seed.revenueMomentum,
      roeTrend: seed.roeTrend,
      yield: null,
      ocfNi: null,
    },
    pricePath,
  };
}

export const mockStockDetails = {
  AUTO: {
    // The Historical Evidence preview is not stored here on purpose: it is
    // derived from the sample cases below by `buildHistoricalEvidencePreview`,
    // so it can never disagree with the Backtest tab.
    backtest: {
      isDemoData: true,
      methodology: {
      processSteps: [
          { number: "01", title: "Identify the Condition", text: "Each historical quarter is classified as Undervalued, Overvalued, or Mixed using the valuation framework available on the analysis date." },
          { number: "02", title: "Track Price Movement", text: "After the analysis date, price movement is observed for up to 12 months against predefined upside and downside thresholds." },
          { number: "03", title: "Determine the Outcome", text: "The first threshold reached determines the historical outcome. This is evidence of past behavior, not a prediction or recommendation." },
        ],
      },
      cases: [
        makeAutoBacktestCase({ quarter: "2022 Q1", analysisDate: "2022-03-31", analysisPrice: 1125, consensus: "2|5", consensusUndervalued: 2, consensusValid: 5, methods: [2505.247668, 1297.503507, 988.3189914, -100228.7124, 1041.622105], mos: [0.5509, 0.5509, 0.133], revenueYoY: 0.2669, netIncomeYoY: 0.3747, epsMomentum: "Slowing", revenueMomentum: "Slowing", roeTrend: "Improving", ranges: [[1285, 1080], [1375, 1085], [1590, 1155], [1855, 1335]], peakPrice: 1855, peakMonth: 11, verdict: "REPRICE", verdictMos: "WIN" }),
        makeAutoBacktestCase({ quarter: "2022 Q2", analysisDate: "2022-06-30", analysisPrice: 1140, consensus: "2|5", consensusUndervalued: 2, consensusValid: 5, methods: [2504.534761, 1282.526122, 1022.072242, -96187.68041, 999.6258733], mos: [0.5448, 0.5448, 0.1111], revenueYoY: 0.1314, netIncomeYoY: 1.0085, epsMomentum: "Slowing", revenueMomentum: "Slowing", roeTrend: "Improving", ranges: [[1375, 1085], [1590, 1155], [1855, 1335], [2560, 1580]], peakPrice: 2560, peakMonth: 11, verdict: "REPRICE", verdictMos: "WIN" }),
        makeAutoBacktestCase({ quarter: "2022 Q3", analysisDate: "2022-09-30", analysisPrice: 1245, consensus: "3|5", consensusUndervalued: 3, consensusValid: 5, methods: [2599.57884, 1416.664725, 1150.47515, -123313.9692, 1281.534533], mos: [0.5211, 0.5211, 0.1212], revenueYoY: 0.2637, netIncomeYoY: 1.2254, epsMomentum: "Slowing", revenueMomentum: "Slowing", roeTrend: "Improving", ranges: [[1590, 1155], [1855, 1335], [2560, 1580], [3620, 2470]], peakPrice: 3620, peakMonth: 10, verdict: "WIN", verdictMos: "WIN" }),
        makeAutoBacktestCase({ quarter: "2022 Q4", analysisDate: "2022-12-31", analysisPrice: 1460, consensus: "3|5", consensusUndervalued: 3, consensusValid: 5, methods: [2705.599288, 1544.243241, 1183.709284, -147516.0142, 1533.05313], mos: [0.4604, 0.4604, 0.0546], revenueYoY: 0.2367, netIncomeYoY: 2.001, epsMomentum: "Slowing", revenueMomentum: "Slowing", roeTrend: "Improving", ranges: [[1855, 1335], [2560, 1580], [3620, 2470], [3210, 2240]], peakPrice: 3620, peakMonth: 7, verdict: "WIN", verdictMos: "WIN" }),
        makeAutoBacktestCase({ quarter: "2023 Q1", analysisDate: "2023-03-31", analysisPrice: 1690, consensus: "2|5", consensusUndervalued: 2, consensusValid: 5, methods: [2805.259129, 1646.453524, 1204.522156, -222077.7115, 2154.766102], mos: [0.3976, 0.3976, -0.0264], revenueYoY: 0.0858, netIncomeYoY: 0.9213, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2560, 1580], [3620, 2470], [3210, 2240], [2680, 2140]], peakPrice: 3620, peakMonth: 4, verdict: "REPRICE", verdictMos: "WIN" }),
        makeAutoBacktestCase({ quarter: "2023 Q2", analysisDate: "2023-06-30", analysisPrice: 2480, consensus: "1|5", consensusUndervalued: 1, consensusValid: 5, methods: [2787.571013, 1598.368972, 1101.752722, -205583.8898, 1994.730556], mos: [0.1103, 0.1103, -0.5516], revenueYoY: 0.1023, netIncomeYoY: 0.7794, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[3620, 2470], [3210, 2240], [2680, 2140], [2250, 1795]], peakPrice: 3620, peakMonth: 1, verdict: "REPRICE", verdictMos: "REPRICE" }),
        makeAutoBacktestCase({ quarter: "2023 Q3", analysisDate: "2023-09-30", analysisPrice: 3180, consensus: "0|5", consensusUndervalued: 0, consensusValid: 5, methods: [2899.528252, 1688.646318, 1152.362138, -224282.0858, 2176.15461], mos: [-0.0967, -0.0967, -0.8832], revenueYoY: -0.0432, netIncomeYoY: 0.2779, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[3210, 2240], [2680, 2140], [2250, 1795], [2400, 1890]], peakPrice: 3210, peakMonth: 0, verdict: "CONFIRMED", verdictMos: "CONFIRMED" }),
        makeAutoBacktestCase({ quarter: "2023 Q4", analysisDate: "2023-12-31", analysisPrice: 2360, consensus: "1|5", consensusUndervalued: 1, consensusValid: 5, methods: [3016.707357, 1764.207252, 1325.561388, -236275.3813, 2292.522644], mos: [0.2177, 0.2177, -0.3377], revenueYoY: -0.1024, netIncomeYoY: 0.0725, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2680, 2140], [2250, 1795], [2400, 1890], [2620, 2120]], peakPrice: 2680, peakMonth: 0, verdict: "CONFIRMED", verdictMos: "CONFIRMED" }),
        makeAutoBacktestCase({ quarter: "2024 Q1", analysisDate: "2024-03-31", analysisPrice: 2230, consensus: "1|5", consensusUndervalued: 1, consensusValid: 5, methods: [3121.882893, 1970.564311, 1272.392381, 712.3427244, 2094.284548], mos: [0.2857, 0.2857, -0.1317], revenueYoY: -0.0757, netIncomeYoY: 0.0972, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2250, 1795], [2400, 1890], [2620, 2120], [2300, 1930]], peakPrice: 2620, peakMonth: 6, verdict: "CONFIRMED", verdictMos: "CONFIRMED" }),
        makeAutoBacktestCase({ quarter: "2024 Q2", analysisDate: "2024-06-30", analysisPrice: 1895, consensus: "3|5", consensusUndervalued: 3, consensusValid: 5, methods: [3079.235924, 1990.471111, 1313.254702, 760.1587507, 2234.86346], mos: [0.3846, 0.3846, 0.048], revenueYoY: 0.0427, netIncomeYoY: 0.4616, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2400, 1890], [2620, 2120], [2300, 1930], [2250, 1775]], peakPrice: 2620, peakMonth: 4, verdict: "WIN", verdictMos: "WIN" }),
        makeAutoBacktestCase({ quarter: "2024 Q3", analysisDate: "2024-09-30", analysisPrice: 2260, consensus: "1|5", consensusUndervalued: 1, consensusValid: 5, methods: [3194.136065, 2044.773541, 1466.213249, 763.9802139, 2246.098545], mos: [0.2925, 0.2925, -0.1053], revenueYoY: 0.0574, netIncomeYoY: 0.0087, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2620, 2120], [2300, 1930], [2250, 1775], [2500, 2020]], peakPrice: 2620, peakMonth: 1, verdict: "REPRICE", verdictMos: "REPRICE" }),
        makeAutoBacktestCase({ quarter: "2024 Q4", analysisDate: "2024-12-31", analysisPrice: 2300, consensus: "1|5", consensusUndervalued: 1, consensusValid: 5, methods: [3234.22978, 2061.358111, 1574.095861, 762.4085153, 2241.477758], mos: [0.2889, 0.2889, -0.1158], revenueYoY: 0.0751, netIncomeYoY: -0.048, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2300, 1930], [2250, 1775], [2500, 2020], [2940, 2280]], peakPrice: 2940, peakMonth: 11, verdict: "CONFIRMED", verdictMos: "CONFIRMED" }),
        makeAutoBacktestCase({ quarter: "2025 Q1", analysisDate: "2025-03-31", analysisPrice: 1975, consensus: "3|5", consensusUndervalued: 3, consensusValid: 5, methods: [3347.093708, 2303.198684, 1702.872654, 1007.139935, 2063.024095], mos: [0.4099, 0.4099, 0.1425], revenueYoY: 0.0645, netIncomeYoY: 0.0643, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2250, 1775], [2500, 2020], [2940, 2280], [2930, 2310]], peakPrice: 2940, peakMonth: 8, verdict: "WIN", verdictMos: "WIN" }),
        makeAutoBacktestCase({ quarter: "2025 Q2", analysisDate: "2025-06-30", analysisPrice: 2060, consensus: "2|5", consensusUndervalued: 2, consensusValid: 5, methods: [3288.339624, 2231.265661, 1761.627407, 935.2441981, 1915.752962], mos: [0.3735, 0.3735, 0.0768], revenueYoY: 0.0199, netIncomeYoY: -0.1956, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2500, 2020], [2940, 2280], [2930, 2310], [2860, 2230]], peakPrice: 2940, peakMonth: 5, verdict: "REPRICE", verdictMos: "WIN" }),
        makeAutoBacktestCase({ quarter: "2025 Q3", analysisDate: "2025-09-30", analysisPrice: 2310, consensus: "2|5", consensusUndervalued: 2, consensusValid: 5, methods: [3429.553048, 2365.525842, 1939.246982, 1041.564204, 2133.53872], mos: [0.3264, 0.3264, 0.0235], revenueYoY: 0.0507, netIncomeYoY: 0.2236, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2940, 2280], [2930, 2310], [2860, 2230], [3520, 2320]], peakPrice: 3520, peakMonth: 11, verdict: "REPRICE", verdictMos: "WIN" }),
        makeAutoBacktestCase({ quarter: "2025 Q4", analysisDate: "2025-12-31", analysisPrice: 2690, consensus: "1|5", consensusUndervalued: 1, consensusValid: 5, methods: [3519.776303, 2444.708644, 2088.47687, 1098.138612, 2249.425661], mos: [0.2357, 0.2357, -0.1003], revenueYoY: 0.0393, netIncomeYoY: 0.2596, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2930, 2310], [2860, 2230], [3520, 2320], null], peakPrice: 3520, peakMonth: 8, verdict: "CONFIRMED", verdictMos: "CONFIRMED" }),
        makeAutoBacktestCase({ quarter: "2026 Q1", analysisDate: "2026-03-31", analysisPrice: 2610, consensus: "1|5", consensusUndervalued: 1, consensusValid: 5, methods: [3628.774042, 2549.798833, 1713.604945, 1376.886434, 2237.750168], mos: [0.2807, 0.2807, -0.0236], revenueYoY: 0.074, netIncomeYoY: 0.1056, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2860, 2230], [3520, 2320], null, null], peakPrice: 3520, peakMonth: 5, verdict: "CONFIRMED", verdictMos: "CONFIRMED" }),
        makeAutoBacktestCase({ quarter: "2026 Q2", analysisDate: "2026-06-30", analysisPrice: 2350, consensus: "2|5", consensusUndervalued: 2, consensusValid: 5, methods: [3567.704684, 2536.600367, 1740.273242, 1418.193101, 2304.882793], mos: [0.3413, 0.3413, 0.0736], revenueYoY: 0.1934, netIncomeYoY: 0.3671, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[3520, 2320], null, null, null], peakPrice: 3520, peakMonth: 2, verdict: "REPRICE", verdictMos: "WIN" }),
      ],
    },
  },
};

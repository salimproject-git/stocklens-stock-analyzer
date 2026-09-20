export type StockDetail = {
  ticker: string;
  companyName: string;
  logoUrl?: string;
  sector: string;
  stockType: string;
  price: number;
  change: number;
  changePercent: number;
  updatedAt: string;
  verdict: "Undervalued" | "Fairly Valued" | "Overvalued";
  verdictDescription: string;
  intrinsicValue: number;
  mos: number;
  stockCharacter: string;
  stockCharacterDesc: string;
  evidenceWins: number;
  evidenceTotal: number;
  researchSummary: string;
  methodologyUrl: string;
  companyProfile: {
    description: string;
    sector: string;
    stockType: string;
    listedDate: string;
    headquarters: string;
    website: string;
  };
  priceChart: {
    timeframe: string;
    points: { date: string; value: number }[];
    low52W: number;
    high52W: number;
    ytdPercent: number;
    marketCap: string;
    peTTM: number;
  };
  currentValuation: {
    verdict: "Undervalued" | "Fairly Valued" | "Overvalued";
    currentPrice: number;
    intrinsicValue: number;
    mos: number;
  };
  financialHealth: {
    metrics: {
      label: string;
      value: string;
      badge: "Healthy" | "Stable" | "Caution" | "Positive";
      subtext: string;
    }[];
  };
  healthGrowth: {
    periodOptions: string[];
    defaultPeriod: string;
    growth: {
      revenueHistorical: { value: string; period: string };
      revenueFiveYear: { value: string; period: string };
      revenueYoY: { value: string; period: string };
      revenueMomentum: { value: string; period: string; tone: 'positive' | 'neutral' | 'negative' };
      epsHistorical: { value: string; period: string };
      epsFiveYear: { value: string; period: string };
      epsMomentum: { value: string; period: string; tone: 'positive' | 'neutral' | 'negative' };
    };
    growthVisuals: {
      periods: string[];
      revenueNetIncome: { revenue: number[]; netIncome: number[] };
      operatingCashFlow: number[];
      eps: number[];
      growthRate: { revenue: number[]; eps: number[] };
      keyInsights: string[];
    };
    profitability: { metrics: { label: string; value: string; context: string; tone: 'positive' | 'neutral' | 'negative' }[] };
    cashFlow: { metrics: { label: string; value: string; context: string; tone: 'positive' | 'neutral' | 'negative' }[] };
    forensic: { metrics: { label: string; value: string; context: string; tone: 'positive' | 'neutral' | 'negative' }[] };
    quarterlyMeaning: string;
    overall: { score: string; rating: string; clearance: string; context: string };
  };
  growthSummary: {
    metrics: {
      label: string;
      value: string;
      badge: "Positive" | "Stable" | "Caution";
      subtext: string;
    }[];
  };
  historicalEvidencePreview: {
  totalCases: number;
  positiveResults: string;
  medianReturn: number;
  worstResult: number;
  bestResult: number;
  cases: { caseName: string; returnPercent: number }[];

  verdictMethod: {
    undervalued: number;
    overvalued: number;
    wins: number;
    winRate: string;
  };

  verdictMos: {
    undervalued: number;
    overvalued: number;
    wins: number;
    winRate: string;
  };
};
  backtest?: {
    cases: BacktestCase[];
  };
  thesisValidator: {
    quarters: string[];
    rows: {
      item: string;
      q3: string;
      q4: string;
      q1: string;
      q2: string;
      trend: string;
      trendTone: "green" | "slate" | "yellow" | "red";
    }[];
    footnote: string;
  };
  dividendConsistency: {
    averageYield: string;
    years: string[];
    rows: {
      item: string;
      p2026: string;
      y2025: string;
      y2024: string;
      y2023: string;
      y2022: string;
      avg4Y: string;
    }[];
    callout: string;
  };
  financialHistory?: {
    subtitle: string;
    annualTrendCards: {
      id: string;
      title: string;
      unit: string;
      latestValue: string;
      cagrLabel: string;
      cagrValue: string;
      subtext: string;
      series: { year: string; value: number }[];
    }[];

    quarterlyTrendCards: {
      id: string;
      title: string;
      unit: string;
      latestValue: string;
      cagrLabel: string;
      cagrValue: string;
      subtext: string;
      series: { year: string; value: number }[];
    }[];
    annualMetrics: {
      label: string;
      value: string;
      subtext?: string;
    }[];

    quarterlyMetrics: {
      label: string;
      value: string;
      subtext?: string;
    }[];
    annualTable: {
      periods: string[];
      changeLabel: string;
      rows: {
        metric: string;
        values: string[];
        change: string;
        isHighlight?: boolean;
      }[];
    };

    quarterlyTable?: {
      periods: string[];
      changeLabel: string;
      rows: {
        metric: string;
        values: string[];
        change: string;
        isHighlight?: boolean;
      }[];
    };
  };
};

export type BacktestConsensus = "UNDERVALUED" | "OVERVALUED" | "MIXED";
export type BacktestVerdict =
  | "WIN"
  | "RISK"
  | "RECOVERED"
  | "FLAT"
  | "CONFIRMED"
  | "REPRICE"
  | "OBSERVE";

export type BacktestCase = {
  id: string;
  ticker: string;
  quarter: string;
  analysisDate: string;
  analysisPrice: number;
  sector: string;
  stockType: string;
  consensus: BacktestConsensus;
  mosMain: number | null;
  mosPeter: number | null;
  mosWeight: number | null;
  verdict: BacktestVerdict;
  verdictMos: BacktestVerdict;
  methods: { method: string; intrinsicValue: number | null }[];
  context: {
    revenueYoY: number | null;
    netIncomeYoY: number | null;
    epsMomentum: string;
    revenueMomentum: string;
    roeTrend: string;
    yield: number | null;
    ocfNi: number | null;
  };
  pricePath: { date: string; high: number; low: number; close: number }[];
};

type AutoBacktestSeed = {
  quarter: string;
  analysisDate: string;
  analysisPrice: number;
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
    consensus: seed.methods.filter((value) => value > seed.analysisPrice).length >= 3 ? "UNDERVALUED" : "OVERVALUED",
    mosMain: seed.mos[0],
    mosPeter: seed.mos[1],
    mosWeight: seed.mos[2],
    verdict: seed.verdict,
    verdictMos: seed.verdictMos,
    methods: [
      { method: "Peter Lynch / Adaptive", intrinsicValue: seed.methods[0] },
      { method: "Type & Sector Weighted", intrinsicValue: seed.methods[1] },
      { method: "Mean Reversion PBV", intrinsicValue: seed.methods[2] },
      { method: "Dividend Discount Model", intrinsicValue: seed.methods[3] },
      { method: "Discounted Earnings", intrinsicValue: seed.methods[4] },
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

export const mockStockDetails: Record<string, StockDetail> = {
  AUTO: {
    ticker: "AUTO",
    companyName: "Astra Otoparts Tbk",
    sector: "Automotive",
    stockType: "Cyclical",
    price: 1950,
    change: 50,
    changePercent: 2.63,
    updatedAt: "12 Sep 2026 16:00 WIB",
    verdict: "Undervalued",
    verdictDescription: "Based on our valuation model",
    intrinsicValue: 2780,
    mos: 29.9,
    stockCharacter: "Cyclical",
    stockCharacterDesc: "Tends to follow economic cycles",
    evidenceWins: 4,
    evidenceTotal: 4,
    researchSummary:
      "AUTO is currently below the estimated intrinsic value used by the analysis engine. Historical backtests show how similar valuation conditions have performed in previous periods.",
    methodologyUrl: "#",
    companyProfile: {
      description:
        "PT Astra Otoparts Tbk (AUTO) is one of the largest automotive component manufacturers in Indonesia. The company produces and distributes a wide range of automotive parts, including engine components, drive train, chassis, electrical, and accessories, supplying both OEMs and the aftermarket.",
      sector: "Automotive",
      stockType: "Cyclical",
      listedDate: "15 Jul 1997",
      headquarters: "Jakarta, Indonesia",
      website: "www.astra-otoparts.com",
    },
    priceChart: {
      timeframe: "1Y",
      points: [
        { date: "Sep 2025", value: 1550 },
        { date: "Oct 2025", value: 1680 },
        { date: "Nov 2025", value: 2150 },
        { date: "Dec 2025", value: 2000 },
        { date: "Jan 2026", value: 1850 },
        { date: "Feb 2026", value: 1720 },
        { date: "Mar 2026", value: 1540 },
        { date: "Apr 2026", value: 1650 },
        { date: "May 2026", value: 1780 },
        { date: "Jun 2026", value: 1840 },
        { date: "Jul 2026", value: 1910 },
        { date: "Aug 2026", value: 1890 },
        { date: "Sep 2026", value: 1950 },
      ],
      low52W: 1520,
      high52W: 2350,
      ytdPercent: -12.4,
      marketCap: "Rp12 T",
      peTTM: 18.4,
    },
    currentValuation: {
      verdict: "Undervalued",
      currentPrice: 1950,
      intrinsicValue: 2780,
      mos: 29.9,
    },
    financialHealth: {
      metrics: [
        {
          label: "Debt / Equity",
          value: "0,42x",
          badge: "Healthy",
          subtext: "Lower than industry average",
        },
        {
          label: "Current Ratio",
          value: "1,8x",
          badge: "Healthy",
          subtext: "Good short-term liquidity",
        },
        {
          label: "Interest Coverage",
          value: "12,4x",
          badge: "Healthy",
          subtext: "Comfortable coverage",
        },
        {
          label: "Net Margin",
          value: "7,2%",
          badge: "Stable",
          subtext: "Consistent over the past years",
        },
      ],
    },
    healthGrowth: {
      periodOptions: ['All Years', '5 Years', '3 Years'],
      defaultPeriod: 'All Years',
      growth: {
        revenueHistorical: { value: '4,32%', period: '2019 - 2024' },
        revenueFiveYear: { value: '10,90%', period: '2019 - 2024' },
        revenueYoY: { value: '4,37%', period: 'Latest annual (2025)' },
        revenueMomentum: { value: 'Accelerating', period: 'Current', tone: 'positive' },
        epsHistorical: { value: '19,97%', period: '2019 - 2024' },
        epsFiveYear: { value: '43255,73%', period: '2019 - 2024' },
      epsMomentum: { value: 'Accelerating', period: 'Current', tone: 'positive' },
      },
    growthVisuals: {
        periods: ['2019', '2020', '2021', '2022', '2023', '2024', '2025', '2026P'],
        revenueNetIncome: {
          revenue: [15444.8, 11869.2, 15151.7, 18579.9, 18649.1, 19073.7, 19906.8, 21705.4],
          netIncome: [739.7, -1, 611.3, 1326.6, 1842.4, 2033.6, 2205, 2302.9],
        },
        operatingCashFlow: [1072.1, 1148.3, 911.7, 708.4, 1836.3, 1532.7, 1944.3, 1500.9],
        eps: [153.5, -0.2, 126.8, 275.2, 382.3, 421.9, 457.5, 477.8],
        growthRate: {
          revenue: [0, -23.2, 27.7, 22.6, 0.4, 2.3, 4.4, 9.0],
          eps: [0, -100.1, 63500, 117.1, 38.9, 10.4, 8.4, 4.4],
        },
        keyInsights: [],
      },
      profitability: { metrics: [{ label: 'ROE Avg (Historical)', value: '9,38%', context: 'Historical average', tone: 'neutral' }, { label: 'ROE (Projected)', value: '13,39%', context: 'Above historical average', tone: 'positive' }, { label: 'ROE Trend', value: 'Improving', context: 'Return on equity is trending higher', tone: 'positive' }, { label: 'NPM Avg (Historical)', value: '6,80%', context: 'Historical average', tone: 'neutral' }, { label: 'NPM vs Historical Avg', value: '+4,28 ppt', context: 'Latest margin is above the average', tone: 'positive' }, { label: 'ROE Stability (StdDev)', value: '5,60%', context: 'Lower variation is more stable', tone: 'neutral' }] },
      cashFlow: { metrics: [{ label: 'Debt to Equity (DER)', value: '0,33x', context: 'Caution: slightly above 0,3x threshold', tone: 'negative' }, { label: 'Current Ratio', value: '2,21x', context: 'Healthy liquidity (target > 2,0x)', tone: 'positive' }, { label: 'Interest Coverage', value: '49,71x', context: 'Strong ability to pay interest', tone: 'positive' }, { label: 'Operating Cash Flow', value: 'Rp1.944 M', context: 'Positive cash generated from operations', tone: 'positive' }, { label: 'OCF / Net Income', value: '88%', context: 'Cash flow supports reported earnings', tone: 'positive' }] },
      forensic: { metrics: [{ label: 'Return on Equity (ROE)', value: '13,39%', context: 'Projected return on equity', tone: 'positive' }, { label: 'Gross Margin', value: '15,1%', context: 'Latest quarterly gross margin', tone: 'neutral' }, { label: 'Quality: CF vs Net Income', value: 'Strong', context: 'Operating cash flow supports reported earnings', tone: 'positive' }, { label: 'ROE Trend', value: 'Improving', context: 'Return on equity is trending higher', tone: 'positive' }, { label: 'Equity Growth Consistency', value: 'Consistent', context: 'Equity growth has remained consistent', tone: 'positive' }, { label: 'Current Asset Growth (YoY)', value: '12,27%', context: 'Current assets grew faster than revenue', tone: 'negative' }, { label: 'Asset Growth Gap (YoY)', value: '-7,90%', context: 'No excessive current-asset growth signal', tone: 'positive' }, { label: 'NWC / Revenue (Latest)', value: '27,38%', context: 'Working capital intensity', tone: 'neutral' }, { label: 'NWC Intensity Change (YoY)', value: '+4,30 ppt', context: 'Working capital intensity needs monitoring', tone: 'negative' }, { label: 'Cash Flow Check', value: 'OK', context: 'Earnings quality is supported by cash', tone: 'positive' }] },
      quarterlyMeaning: 'Revenue and net income both accelerated in the latest quarter, while gross margin remains under pressure and OCF conversion is moderate.',
      overall: { score: '80 / 100', rating: 'Healthy', clearance: 'OK', context: 'No major red flag detected.' },
    },
    growthSummary: {
      metrics: [
        {
          label: "Revenue Growth (3Y CAGR)",
          value: "8,6%",
          badge: "Positive",
          subtext: "Steady growth trend",
        },
        {
          label: "Net Income Growth (3Y CAGR)",
          value: "11,2%",
          badge: "Positive",
          subtext: "Faster than revenue",
        },
        {
          label: "EPS Growth (3Y CAGR)",
          value: "10,8%",
          badge: "Positive",
          subtext: "Consistent increase",
        },
      ],
    },
    historicalEvidencePreview: {
      totalCases: 18,
      positiveResults: "4 (100%)",
      medianReturn: 24.6,
      worstResult: 8.2,
      bestResult: 41.3,
      cases: [
        { caseName: "Case 1", returnPercent: 18.5 },
        { caseName: "Case 2", returnPercent: 24.6 },
        { caseName: "Case 3", returnPercent: 41.3 },
        { caseName: "Case 4", returnPercent: 8.2 },
      ],

      verdictMethod: {
        undervalued: 4,
        overvalued: 14,
        wins: 4,
        winRate: "100%",
      },

      verdictMos: {
        undervalued: 10,
        overvalued: 8,
        wins: 10,
        winRate: "100%",
      },
    },
    backtest: {
      cases: [
        makeAutoBacktestCase({ quarter: "2022 Q1", analysisDate: "2022-03-31", analysisPrice: 1125, methods: [2505.247668, 1297.503507, 988.3189914, -100228.7124, 1041.622105], mos: [0.5509, 0.5509, 0.133], revenueYoY: 0.2669, netIncomeYoY: 0.3747, epsMomentum: "Slowing", revenueMomentum: "Slowing", roeTrend: "Improving", ranges: [[1285, 1080], [1375, 1085], [1590, 1155], [1855, 1335]], peakPrice: 1855, peakMonth: 11, verdict: "REPRICE", verdictMos: "WIN" }),
        makeAutoBacktestCase({ quarter: "2022 Q2", analysisDate: "2022-06-30", analysisPrice: 1140, methods: [2504.534761, 1282.526122, 1022.072242, -96187.68041, 999.6258733], mos: [0.5448, 0.5448, 0.1111], revenueYoY: 0.1314, netIncomeYoY: 1.0085, epsMomentum: "Slowing", revenueMomentum: "Slowing", roeTrend: "Improving", ranges: [[1375, 1085], [1590, 1155], [1855, 1335], [2560, 1580]], peakPrice: 2560, peakMonth: 11, verdict: "REPRICE", verdictMos: "WIN" }),
        makeAutoBacktestCase({ quarter: "2022 Q3", analysisDate: "2022-09-30", analysisPrice: 1245, methods: [2599.57884, 1416.664725, 1150.47515, -123313.9692, 1281.534533], mos: [0.5211, 0.5211, 0.1212], revenueYoY: 0.2637, netIncomeYoY: 1.2254, epsMomentum: "Slowing", revenueMomentum: "Slowing", roeTrend: "Improving", ranges: [[1590, 1155], [1855, 1335], [2560, 1580], [3620, 2470]], peakPrice: 3620, peakMonth: 10, verdict: "WIN", verdictMos: "WIN" }),
        makeAutoBacktestCase({ quarter: "2022 Q4", analysisDate: "2022-12-31", analysisPrice: 1460, methods: [2705.599288, 1544.243241, 1183.709284, -147516.0142, 1533.05313], mos: [0.4604, 0.4604, 0.0546], revenueYoY: 0.2367, netIncomeYoY: 2.001, epsMomentum: "Slowing", revenueMomentum: "Slowing", roeTrend: "Improving", ranges: [[1855, 1335], [2560, 1580], [3620, 2470], [3210, 2240]], peakPrice: 3620, peakMonth: 7, verdict: "WIN", verdictMos: "WIN" }),
        makeAutoBacktestCase({ quarter: "2023 Q1", analysisDate: "2023-03-31", analysisPrice: 1690, methods: [2805.259129, 1646.453524, 1204.522156, -222077.7115, 2154.766102], mos: [0.3976, 0.3976, -0.0264], revenueYoY: 0.0858, netIncomeYoY: 0.9213, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2560, 1580], [3620, 2470], [3210, 2240], [2680, 2140]], peakPrice: 3620, peakMonth: 4, verdict: "REPRICE", verdictMos: "WIN" }),
        makeAutoBacktestCase({ quarter: "2023 Q2", analysisDate: "2023-06-30", analysisPrice: 2480, methods: [2787.571013, 1598.368972, 1101.752722, -205583.8898, 1994.730556], mos: [0.1103, 0.1103, -0.5516], revenueYoY: 0.1023, netIncomeYoY: 0.7794, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[3620, 2470], [3210, 2240], [2680, 2140], [2250, 1795]], peakPrice: 3620, peakMonth: 1, verdict: "REPRICE", verdictMos: "REPRICE" }),
        makeAutoBacktestCase({ quarter: "2023 Q3", analysisDate: "2023-09-30", analysisPrice: 3180, methods: [2899.528252, 1688.646318, 1152.362138, -224282.0858, 2176.15461], mos: [-0.0967, -0.0967, -0.8832], revenueYoY: -0.0432, netIncomeYoY: 0.2779, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[3210, 2240], [2680, 2140], [2250, 1795], [2400, 1890]], peakPrice: 3210, peakMonth: 0, verdict: "CONFIRMED", verdictMos: "CONFIRMED" }),
        makeAutoBacktestCase({ quarter: "2023 Q4", analysisDate: "2023-12-31", analysisPrice: 2360, methods: [3016.707357, 1764.207252, 1325.561388, -236275.3813, 2292.522644], mos: [0.2177, 0.2177, -0.3377], revenueYoY: -0.1024, netIncomeYoY: 0.0725, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2680, 2140], [2250, 1795], [2400, 1890], [2620, 2120]], peakPrice: 2680, peakMonth: 0, verdict: "CONFIRMED", verdictMos: "CONFIRMED" }),
        makeAutoBacktestCase({ quarter: "2024 Q1", analysisDate: "2024-03-31", analysisPrice: 2230, methods: [3121.882893, 1970.564311, 1272.392381, 712.3427244, 2094.284548], mos: [0.2857, 0.2857, -0.1317], revenueYoY: -0.0757, netIncomeYoY: 0.0972, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2250, 1795], [2400, 1890], [2620, 2120], [2300, 1930]], peakPrice: 2620, peakMonth: 6, verdict: "CONFIRMED", verdictMos: "CONFIRMED" }),
        makeAutoBacktestCase({ quarter: "2024 Q2", analysisDate: "2024-06-30", analysisPrice: 1895, methods: [3079.235924, 1990.471111, 1313.254702, 760.1587507, 2234.86346], mos: [0.3846, 0.3846, 0.048], revenueYoY: 0.0427, netIncomeYoY: 0.4616, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2400, 1890], [2620, 2120], [2300, 1930], [2250, 1775]], peakPrice: 2620, peakMonth: 4, verdict: "WIN", verdictMos: "WIN" }),
        makeAutoBacktestCase({ quarter: "2024 Q3", analysisDate: "2024-09-30", analysisPrice: 2260, methods: [3194.136065, 2044.773541, 1466.213249, 763.9802139, 2246.098545], mos: [0.2925, 0.2925, -0.1053], revenueYoY: 0.0574, netIncomeYoY: 0.0087, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2620, 2120], [2300, 1930], [2250, 1775], [2500, 2020]], peakPrice: 2620, peakMonth: 1, verdict: "REPRICE", verdictMos: "REPRICE" }),
        makeAutoBacktestCase({ quarter: "2024 Q4", analysisDate: "2024-12-31", analysisPrice: 2300, methods: [3234.22978, 2061.358111, 1574.095861, 762.4085153, 2241.477758], mos: [0.2889, 0.2889, -0.1158], revenueYoY: 0.0751, netIncomeYoY: -0.048, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2300, 1930], [2250, 1775], [2500, 2020], [2940, 2280]], peakPrice: 2940, peakMonth: 11, verdict: "CONFIRMED", verdictMos: "CONFIRMED" }),
        makeAutoBacktestCase({ quarter: "2025 Q1", analysisDate: "2025-03-31", analysisPrice: 1975, methods: [3347.093708, 2303.198684, 1702.872654, 1007.139935, 2063.024095], mos: [0.4099, 0.4099, 0.1425], revenueYoY: 0.0645, netIncomeYoY: 0.0643, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2250, 1775], [2500, 2020], [2940, 2280], [2930, 2310]], peakPrice: 2940, peakMonth: 8, verdict: "WIN", verdictMos: "WIN" }),
        makeAutoBacktestCase({ quarter: "2025 Q2", analysisDate: "2025-06-30", analysisPrice: 2060, methods: [3288.339624, 2231.265661, 1761.627407, 935.2441981, 1915.752962], mos: [0.3735, 0.3735, 0.0768], revenueYoY: 0.0199, netIncomeYoY: -0.1956, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2500, 2020], [2940, 2280], [2930, 2310], [2860, 2230]], peakPrice: 2940, peakMonth: 5, verdict: "REPRICE", verdictMos: "WIN" }),
        makeAutoBacktestCase({ quarter: "2025 Q3", analysisDate: "2025-09-30", analysisPrice: 2310, methods: [3429.553048, 2365.525842, 1939.246982, 1041.564204, 2133.53872], mos: [0.3264, 0.3264, 0.0235], revenueYoY: 0.0507, netIncomeYoY: 0.2236, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2940, 2280], [2930, 2310], [2860, 2230], [3520, 2320]], peakPrice: 3520, peakMonth: 11, verdict: "REPRICE", verdictMos: "WIN" }),
        makeAutoBacktestCase({ quarter: "2025 Q4", analysisDate: "2025-12-31", analysisPrice: 2690, methods: [3519.776303, 2444.708644, 2088.47687, 1098.138612, 2249.425661], mos: [0.2357, 0.2357, -0.1003], revenueYoY: 0.0393, netIncomeYoY: 0.2596, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2930, 2310], [2860, 2230], [3520, 2320], null], peakPrice: 3520, peakMonth: 8, verdict: "CONFIRMED", verdictMos: "CONFIRMED" }),
        makeAutoBacktestCase({ quarter: "2026 Q1", analysisDate: "2026-03-31", analysisPrice: 2610, methods: [3628.774042, 2549.798833, 1713.604945, 1376.886434, 2237.750168], mos: [0.2807, 0.2807, -0.0236], revenueYoY: 0.074, netIncomeYoY: 0.1056, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[2860, 2230], [3520, 2320], null, null], peakPrice: 3520, peakMonth: 5, verdict: "CONFIRMED", verdictMos: "CONFIRMED" }),
        makeAutoBacktestCase({ quarter: "2026 Q2", analysisDate: "2026-06-30", analysisPrice: 2350, methods: [3567.704684, 2536.600367, 1740.273242, 1418.193101, 2304.882793], mos: [0.3413, 0.3413, 0.0736], revenueYoY: 0.1934, netIncomeYoY: 0.3671, epsMomentum: "Accelerating", revenueMomentum: "Accelerating", roeTrend: "Improving", ranges: [[3520, 2320], null, null, null], peakPrice: 3520, peakMonth: 2, verdict: "REPRICE", verdictMos: "WIN" }),
      ],
    },
    thesisValidator: {
      quarters: ["Q3 2025", "Q4 2025", "Q1 2026", "Q2 2026"],
      rows: [
        {
          item: "Revenue YoY (%)",
          q3: "5,1%",
          q4: "3,9%",
          q1: "7,4%",
          q2: "19,3%",
          trend: "↑ Increased +19.3%",
          trendTone: "green",
        },
        {
          item: "Gross Margin (Actual %)",
          q3: "16,8%",
          q4: "18,8%",
          q1: "16,0%",
          q2: "15,1%",
          trend: "➖ Stable at 15.1%",
          trendTone: "slate",
        },
        {
          item: "Net Income YoY (%)",
          q3: "22,4%",
          q4: "26,0%",
          q1: "10,6%",
          q2: "36,7%",
          trend: "↑ Increased +36.7%",
          trendTone: "green",
        },
        {
          item: "OCF / NI Ratio (x)",
          q3: "0,53x",
          q4: "0,83x",
          q1: "0,73x",
          q2: "0,57x",
          trend: "⚠ Moderate — 0.57x",
          trendTone: "yellow",
        },
        {
          item: "Interest Expense (M Rp)",
          q3: "10,9",
          q4: "9,8",
          q1: "9,1",
          q2: "9,2",
          trend: "↓ Decreased -15.3%",
          trendTone: "green",
        },
      ],
      footnote:
        "Gross Margin (Actual %) shows the actual margin value each quarter, not the YoY change. Compare the latest quarter with the earliest quarter to assess the trend.",
    },
    dividendConsistency: {
      averageYield: "5,2%",
      years: ["2026 (Proyeksi)", "2025", "2024", "2023", "2022", "Avg (4Y)"],
      rows: [
        {
          item: "DPS [Rp]",
          p2026: "113,59",
          y2025: "192,00",
          y2024: "189,00",
          y2023: "128,00",
          y2022: "62,00",
          avg4Y: "136,92",
        },
        {
          item: "DPR [%]",
          p2026: "23,8%",
          y2025: "42,0%",
          y2024: "44,8%",
          y2023: "33,5%",
          y2022: "22,5%",
          avg4Y: "33,3%",
        },
        {
          item: "Yield [%]",
          p2026: "4,8%",
          y2025: "7,1%",
          y2024: "8,2%",
          y2023: "5,4%",
          y2022: "4,2%",
          avg4Y: "6,0%",
        },
      ],
      callout:
        "Dividend signal: Dividend payouts have remained positive across the historical period, with average 4Y DPR of 33.3%.",
    },
    financialHistory: {
      subtitle: "Review how the company's financial performance has evolved over time.",
      annualTrendCards: [
        {
          id: "revenue",
          title: "Revenue",
          unit: "Rp Trillion",
          latestValue: "19,4",
          cagrLabel: "Revenue CAGR (5Y)",
          cagrValue: "8,6%",
          subtext: "Steady growth over the past 5 years.",
          series: [
            { year: "2020", value: 12.1 },
            { year: "2021", value: 13.4 },
            { year: "2022", value: 15.2 },
            { year: "2023", value: 16.8 },
            { year: "2024", value: 18.1 },
            { year: "2025", value: 19.4 },
          ],
        },
        {
          id: "netIncome",
          title: "Net Income",
          unit: "Rp Trillion",
          latestValue: "1,82",
          cagrLabel: "Net Income CAGR (5Y)",
          cagrValue: "15,2%",
          subtext: "Faster expansion than top-line revenue.",
          series: [
            { year: "2020", value: 0.9 },
            { year: "2021", value: 1.1 },
            { year: "2022", value: 1.3 },
            { year: "2023", value: 1.5 },
            { year: "2024", value: 1.7 },
            { year: "2025", value: 1.82 },
          ],
        },
        {
          id: "eps",
          title: "Earnings per Share (EPS)",
          unit: "Rp per share",
          latestValue: "210",
          cagrLabel: "EPS CAGR (5Y)",
          cagrValue: "10,8%",
          subtext: "Consistent increase over the past 5 years.",
          series: [
            { year: "2020", value: 102 },
            { year: "2021", value: 124 },
            { year: "2022", value: 148 },
            { year: "2023", value: 171 },
            { year: "2024", value: 195 },
            { year: "2025", value: 210 },
          ],
        },
      ],
      quarterlyTrendCards: [
        {
          id: "quarterlyRevenue",
          title: "Revenue",
          unit: "Rp Trillion",
          latestValue: "5,60",
          cagrLabel: "Revenue YoY Growth",
          cagrValue: "19,3%",
          subtext: "Q2 2026 vs Q2 2025.",
          series: [
            { year: "Q2 2025", value: 4.688897 },
            { year: "Q3 2025", value: 5.22 },
            { year: "Q4 2025", value: 5.10 },
            { year: "Q1 2026", value: 5.26 },
            { year: "Q2 2026", value: 5.60 },
          ],
        },
        {
          id: "quarterlyNetIncome",
          title: "Net Income",
          unit: "Rp Trillion",
          latestValue: "0,59",
          cagrLabel: "Net Income YoY Growth",
          cagrValue: "36,7%",
          subtext: "Q2 2026 vs Q2 2025.",
          series: [
            { year: "Q2 2025", value: 0.433393 },
            { year: "Q3 2025", value: 0.63 },
            { year: "Q4 2025", value: 0.64 },
            { year: "Q1 2026", value: 0.56 },
            { year: "Q2 2026", value: 0.59 },
          ],
        },
        {
          id: "quarterlyOperatingCashFlow",
          title: "Operating Cash Flow",
          unit: "Rp Trillion",
          latestValue: "0,34",
          cagrLabel: "OCF YoY Growth",
          cagrValue: "-51,9%",
          subtext: "Q2 2026 vs Q2 2025.",
          series: [
            { year: "Q2 2025", value: 0.705674 },
            { year: "Q3 2025", value: 0.33 },
            { year: "Q4 2025", value: 0.53 },
            { year: "Q1 2026", value: 0.41 },
            { year: "Q2 2026", value: 0.34 },
          ],
        },
      ],
      annualMetrics: [
        {
          label: "Return on Equity (ROE)",
          value: "17,8%",
        },
        {
          label: "Gross Margin",
          value: "18,4%",
        },
        {
          label: "Net Margin",
          value: "7,2%",
        },
        {
          label: "Operating Profit",
          value: "2,5",
        },
        {
          label: "Total Assets",
          value: "22,0",
        },
        {
          label: "Total Equity",
          value: "10,2",
        },
      ],
      quarterlyMetrics: [
        {
          label: "Interest Expense",
          value: "9,2",
        },
        {
          label: "Gross Margin",
          value: "15,1%",
        },
        {
          label: "Net Margin",
          value: "10,6%",
        },
        {
          label: "Operating Cash Flow",
          value: "0,34",
        },
        {
          label: "Total Liabilities",
          value: "6,69",
        },
        {
          label: "Total Equity",
          value: "17,20",
        },
      ],
      annualTable: {
        periods: ["2020", "2021", "2022", "2023", "2024", "2025"],
        changeLabel: "CAGR (5Y)",
        rows: [
          {
            metric: "Revenue (Rp T)",
            values: ["12,1", "13,4", "15,2", "16,8", "18,1", "19,4"],
            change: "8,6%",
          },
          {
            metric: "Gross Profit (Rp T)",
            values: ["2,1", "2,4", "2,8", "3,1", "3,4", "3,6"],
            change: "11,3%",
          },
          {
            metric: "Operating Profit (Rp T)",
            values: ["1,3", "1,5", "1,8", "2,0", "2,2", "2,5"],
            change: "14,0%",
          },
          {
            metric: "Net Income (Rp T)",
            values: ["0,9", "1,1", "1,3", "1,5", "1,7", "1,82"],
            change: "15,2%",
          },
          {
            metric: "EPS (Rp)",
            values: ["102", "124", "148", "171", "195", "210"],
            change: "10,8%",
          },
          {
            metric: "Total Assets (Rp T)",
            values: ["14,2", "15,6", "17,8", "19,1", "20,5", "22,0"],
            change: "9,2%",
          },
          {
            metric: "Total Equity (Rp T)",
            values: ["6,1", "6,8", "7,6", "8,5", "9,4", "10,2"],
            change: "10,8%",
          },
          {
            metric: "Return on Equity (ROE)",
            values: ["15,2%", "16,1%", "17,1%", "17,6%", "18,0%", "17,8%"],
            change: "-",
          },
          {
            metric: "Gross Margin",
            values: ["17,4%", "17,6%", "18,2%", "18,5%", "18,8%", "18,4%"],
            change: "-",
          },
          {
            metric: "Net Margin",
            values: ["7,1%", "7,4%", "7,6%", "7,8%", "7,9%", "7,2%"],
            change: "-",
          },
          {
            metric: "Book Value per Share (BVPS)",
            values: ["1.265", "1.410", "1.576", "1.763", "1.950", "2.116"],
            change: "10,8%",
          },
        ],
      },
      quarterlyTable: {
        periods: ["Q3 2025", "Q4 2025", "Q1 2026", "Q2 2026"],
        changeLabel: "YoY (Latest)",
        rows: [
          {
            metric: "Revenue (Rp T)",
            values: ["5,22", "5,10", "5,26", "5,60"],
            change: "19,3%",
          },
          {
            metric: "Gross Profit (Rp T)",
            values: ["0,88", "0,96", "0,84", "0,85"],
            change: "15,1%",
          },
          {
            metric: "Net Income (Rp T)",
            values: ["0,63", "0,64", "0,56", "0,59"],
            change: "36,7%",
          },
          {
            metric: "Operating Cash Flow (Rp T)",
            values: ["0,33", "0,53", "0,41", "0,34"],
            change: "-51,9%",
          },
          {
            metric: "Total Equity (Rp T)",
            values: ["16,53", "16,96", "17,49", "17,20"],
            change: "8,5%",
          },
          {
            metric: "Total Liabilities (Rp T)",
            values: ["6,49", "5,65", "6,07", "6,69"],
            change: "8,1%",
          },
          {
            metric: "Gross Margin",
            values: ["16,8%", "18,8%", "16,0%", "15,1%"],
            change: "-",
          },
          {
            metric: "Net Margin",
            values: ["12,1%", "12,5%", "10,6%", "10,6%"],
            change: "-",
          },
        ],
      },
    },
  },
};

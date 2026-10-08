import type { ValuationMethodCode, ValuationMethodStatus } from "@/lib/valuation-methods";

export type ValuationMetric = {
  label: string;
  value: string | number;
  note: string;
};

/**
 * Display status for one valuation-method row. Re-exported from the method
 * registry so the table, the badge and the adapter share one definition.
 */
export type { ValuationMethodStatus };

export type ValuationMethodResult = {
  method: string;
  /** Stored `method_code`, used for fixed ordering and chart colours. */
  methodCode?: string;
  intrinsicValue: number;
  marginOfSafety: string;
  status: ValuationMethodStatus;
  description: string;
};

export type MarketOverviewStock = {
  ticker: string;
  companyName: string;
  sector: string;
  stockType: string;
  price: number;
  change: number;
  changePercent: number;
  sparkline: number[];
  verdict: "Undervalued" | "Fairly Valued" | "Overvalued";
  mos: number;
  evidenceWins: number;
  evidenceTotal: number;
  updatedAt: string;
};

/**
 * Outcome mix for one Undervalued classification rule, as shown by the
 * Historical Evidence preview.
 *
 * `winRate` counts `RECOVERED` as a success on purpose: a case that dipped
 * first but still reached the upside target eventually proved the thesis, so
 * the Overview reports "WIN + RECOVERED / Undervalued". `RISK` is the only
 * failure â€” the downside was touched and the upside never was â€” which is why
 * `riskRate` is its own figure instead of being folded into a single number.
 *
 * `winRate`, `riskRate` and `flatRate` partition the same denominator, so they
 * always add up to 100%: each case the rule flagged as Undervalued ended up
 * WIN, RECOVERED, RISK, or FLAT. All three use `undervalued` as the
 * denominator (the cases the rule actually flagged), not `totalCases`.
 */
export type EvidenceOutcomeBreakdown = {
  /** Cases this rule classified as Undervalued. */
  undervalued: number;
  /** Cases this rule classified as Overvalued (or Mixed). */
  overvalued: number;
  /**
   * Raw counts behind the three rates. `wins` is already `WIN + RECOVERED`,
   * the numerator of `winRate`. Not rendered on their own â€” the card shows the
   * rates and the `Undervalued` / `Overvalued` totals.
   */
  wins: number;
  recovered: number;
  risk: number;
  flat: number;
  /** `(wins + recovered) / undervalued`, already formatted as `87.5%`. */
  winRate: string;
  /** `risk / undervalued`, already formatted as `12.5%`. */
  riskRate: string;
  /** `flat / undervalued`, already formatted as `0.0%`. */
  flatRate: string;
  /** Non-empty only when there were no Undervalued cases at all. */
  flatSuffix: string;
};

export type StockDetail = {
  ticker: string;
  companyName: string;
  logoUrl?: string;
  sector: string;
  stockType: string;
  price: number | null;
  change: number | null;
  changePercent: number | null;
  updatedAt: string;
  verdict: "Undervalued" | "Fairly Valued" | "Overvalued" | "Not available";
  verdictDescription: string;
  /** Combined frontend-only verdict from method consensus and main-method MoS. */
  valuationSignal: "UNDERVALUED" | "OVERVALUED" | "MIXED" | "NOT AVAILABLE";
  intrinsicValue: number | null;
  mos: number | null;
  stockCharacter: string;
  stockCharacterDesc: string;
  /**
   * Historical Evidence headline figures for the Key Metric row: the win rate
   * of each classification rule, already formatted for display (`75%`, `100%`),
   * or `"Not available"` when that rule flagged no Undervalued case or the
   * ticker has no backtest.
   *
   * Both rules are shown because they disagree by design â€” the five-method
   * consensus and the `MoS Main >= 30%` rule flag different cases, so one
   * figure would hide the other. Display-ready on purpose so the card cannot
   * format the same figure differently from the Historical Evidence panel.
   */
  evidenceWinRates: {
    /** `(WIN + RECOVERED) / Undervalued` for the five-method consensus rule. */
    method: string;
    /** `(WIN + RECOVERED) / Undervalued` for the `MoS Main >= 30%` rule. */
    mos: string;
  };
  /** Active valuation methods that indicate undervaluation, as a compact `x/y` string. */
  undervaluedMethods: string;
  undervaluedMethodsVerdict: "UNDERVALUED" | "OVERVALUED" | null;
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
    low52W: number | null;
    high52W: number | null;
    ytdPercent: number | null;
    marketCap: string;
    peTTM: number | null;
  };
  currentValuation: {
    verdict: "Undervalued" | "Fairly Valued" | "Overvalued" | "Not available";
    currentPrice: number | null;
    intrinsicValue: number | null;
    mos: number | null;
    /** Stored database consensus across the valid valuation methods. */
    methodVerdict: "UNDERVALUED" | "OVERVALUED" | "N/A" | null;
    /** Stored database classification of the main method's margin of safety. */
    mosVerdict: "UNDERVALUED" | "OVERVALUED" | "N/A" | null;
    /** Database threshold used for the MoS classification, as a ratio. */
    mosThreshold: number | null;
    metrics: ValuationMetric[];
    methods: ValuationMethodResult[];
    /**
     * Which row carries the "Main" badge and supplies the headline IV / MoS.
     *
     * Usually the workbook's main rule for the stock type, but it **falls back to
     * the other main-rule candidate** when that rule produced no usable value
     * (IV <= 0). A company whose main rule values it at or below zero still needs
     * a headline figure, and the other rule is the next-best candidate by design:
     * GEMA's Peter Lynch IV is `âˆ’22`, so its headline comes from Weighted IV.
     *
     * The backtest keeps its own `mos_method_code` without this fallback (decision
     * D5); this field only governs the valuation screen.
     */
    mainMethodCode: ValuationMethodCode | null;
    comparison: {
      takeaway: string;
      readouts: string[];
    };
  };
  financialHealth?: {
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
      // `null` marks a year where the underlying fact is missing, so the chart
      // can show a gap instead of drawing a fake zero.
      revenueNetIncome: { revenue: (number | null)[]; netIncome: (number | null)[] };
      operatingCashFlow: (number | null)[];
      eps: (number | null)[];
      growthRate: { revenue: (number | null)[]; eps: (number | null)[] };
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
    annualPerformance: {
      revenueGrowth: string;
      netIncomeGrowth: string;
      grossMargin: string;
      ocfNetIncome: string;
      period: string;
    };
  };
  /**
   * Historical Evidence preview for the Overview tab.
   *
   * Every number here is derived from the stored backtest cases
   * (`buildHistoricalEvidencePreview`), never hand-written: the two breakdowns
   * are the same aggregation the Backtest tab renders, so the two screens
   * cannot disagree. There are deliberately no return statistics (median /
   * best / worst) because nothing stores them yet â€” inventing them would put
   * numbers on screen that no run produced.
   */
  historicalEvidencePreview?: {
    /** Every case in the backtest, both classifications. */
    totalCases: number;
    /** Outcomes restricted to the cases this rule called Undervalued. */
    verdictMethod: EvidenceOutcomeBreakdown;
    verdictMos: EvidenceOutcomeBreakdown;
    /**
     * True when the numbers shown are illustrative sample data and are NOT
     * backed by any database table yet. The UI must label these clearly so
     * they are never mistaken for stored research results.
     */
    isDemoData?: boolean;
  };

  backtest?: {
    cases: BacktestCase[];
    methodology: {
      processSteps: { number: string; title: string; text: string }[];
    };
    /**
     * True when the cases shown are illustrative sample data and are NOT
     * backed by any database table yet.
     */
    isDemoData?: boolean;
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

/**
 * Consensus badge, stored in `calc_backtest_cases.consensus`.
 *
 * `"N/A"` is a real third state, not a placeholder: the database writes it when
 * fewer than three valuation methods are valid. A two-branch browser rule can
 * only ever produce `UNDERVALUED`/`OVERVALUED`, so it silently turned those
 * cases into a verdict (docs/CONSENSUS_ARCHITECTURE.md section 2.3).
 */
export type BacktestConsensus = "UNDERVALUED" | "OVERVALUED" | "MIXED" | "N/A";
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
  mosMain: number | null;
  mosPeter: number | null;
  mosWeight: number | null;
  /**
   * Stored consensus, read verbatim from `calc_backtest_cases.consensus`:
   * `'undervalued|valid'` (e.g. `'3|5'`) or `'N/A'` when fewer than three
   * methods are valid.
   *
   * Kept as the stored string rather than the `BacktestConsensus` badge so the
   * type shows exactly what the database holds; the tab translates it for
   * display. The tab must never recompute it: the browser does not know the
   * "at least three valid methods" threshold, so it cannot tell `N/A` from
   * `OVERVALUED` and displayed the wrong badge on 44 stored cases.
   */
  consensus?: string | null;
  /** Stored `consensus_undervalued`; `null` whenever the badge is `N/A`. */
  consensusUndervalued?: number | null;
  /** Stored `consensus_valid` — the `/3`, `/4` or `/5` denominator. */
  consensusValid?: number | null;
  /**
   * Stored `Peak Month` / `Trough Month`, in months. Authoritative when present.
   *
   * These must NOT be recomputed from `pricePath`: the workbook uses
   * `DATEDIF(T0, date, "m")`, which counts *completed* months, while
   * `monthsBetween` in `@/lib/analysis/backtest` counts month *boundaries*.
   * For a month-end analysis date the two disagree — AUTO 2023-Q3 peaks on
   * 2023-10-02, which is `0` months by DATEDIF but `1` by `monthsBetween`.
   */
  peakMonth?: number | null;
  troughMonth?: number | null;
  /**
   * Stored window metrics, in nominal currency. Authoritative when present.
   *
   * The UI must read these rather than recompute from `pricePath`: the stored
   * table keeps only the window extremes, and extremes alone cannot rebuild the
   * per-horizon windows (a peak in month 6 can lie outside the 6M window once
   * `DATEDIF` month arithmetic is involved). Recomputing produced 18 wrong cells
   * across the 18 AUTO cases, so the stored columns are the source of truth.
   */
  stored?: {
    high3m: number | null;
    low3m: number | null;
    high6m: number | null;
    low6m: number | null;
    high9m: number | null;
    low9m: number | null;
    high12m: number | null;
    low12m: number | null;
    peakPrice: number | null;
    troughPrice: number | null;
    returnPeak: number | null;
    returnDown: number | null;
  };
  verdict: BacktestVerdict;
  verdictMos: BacktestVerdict;
  methods: {
    method: string;
    methodCode?: string;
    intrinsicValue: number | null;
    calculationStatus?: string;
    flags?: string[];
    details?: Record<string, unknown>;
  }[];
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

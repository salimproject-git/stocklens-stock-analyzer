import "server-only";

import { createClient } from "@supabase/supabase-js";
import type { MarketOverviewStock } from "@/lib/stock-types";
import {
  DEFAULT_MARKET_PAGE_SIZE,
  type MarketPageSize,
} from "@/lib/market-page-size";

type JsonObject = Record<string, unknown>;

export type MarketOverviewData = {
  stocks: MarketOverviewStock[];
  totalCount: number;
  currentPage: number;
  pageSize: number;
};

export type StockPrice = {
  tradingDate: string;
  closePrice: number | null;
  marketCap: number | null;
  currencyCode: string;
};

export type FinancialFact = {
  metricCode: string;
  value: number | null;
  unitCode: string;
  currencyCode: string | null;
  qualityStatus: string;
};

export type FinancialPeriod = {
  periodType: string;
  periodLabel: string;
  periodEnd: string;
  periodBasis: string;
  statementScope: string;
  facts: FinancialFact[];
};

export type ValuationMethod = {
  methodCode: string;
  methodName: string;
  valuationDate: string;
  intrinsicValue: number | null;
  currentPrice: number | null;
  gapRatio: number | null;
  /**
   * Margin of safety, workbook rule D6: `(IV − price) / IV`.
   *
   * Distinct from `gapRatio`, which divides by the price. The backend stores it
   * so the UI no longer computes it; `null` means the model produced no positive
   * IV, and the row's `flags` say which guard fired.
   */
  mos: number | null;
  verdict: string;
  calculationStatus: string;
  flags: string[];
  stockType: string | null;
};

export type ValuationSummary = {
  methodVerdict: string | null;
  methodUndervaluedCount: number;
  methodValidCount: number;
  mosMethodCode: string | null;
  mos: number | null;
  mosVerdict: string | null;
  mosThreshold: number | null;
  currentPrice?: number | null;
  tradingDate?: string | null;
  methods?: ValuationMethod[];
  stockType?: string | null;
};

export type ValuationFrequency = {
  fundamental: {
    snapshotId: string;
    stockType: string | null;
    methods: Array<{
      methodCode: string;
      intrinsicValue: number | null;
      calculationStatus: string;
    }>;
  } | null;
  daily: {
    tradingDate: string;
    currentPrice: number | null;
    consensusVerdict: string | null;
    basedMethodCode: string | null;
    basedMos: number | null;
    basedMosVerdict: string | null;
    methods: ValuationMethod[];
  } | null;
};

export type AnnualRatioMetric = {
  periodEnd: string;
  periodLabel: string;
  metricCode: string;
  value: number | null;
  /**
   * Unit of `value`: `IDR`, `IDR_PER_SHARE`, `RATIO`, `PERCENT`, `SHARES` or
   * `YEARS`. Stored beside the value so a ratio can never be read as an amount.
   */
  unitCode: string;
  calculationStatus: string;
  flags: string[];
};

export type StockClassification = {
  finalType: string | null;
  systemRecommendation: string | null;
  confidence: number | null;
  ruleFlags: string[];
};

export type DataQuality = {
  warnings: string[];
};

export type AnnualGrowthMetric = {
  periodEnd: string;
  periodLabel: string;
  metricCode: string;
  value: number | null;
  calculationStatus: string;
};

export type QuarterlyQualityMetric = {
  periodEnd: string;
  periodLabel: string;
  metricCode: string;
  value: number | null;
  calculationStatus: string;
};

export type DividendFact = {
  factType: string;
  periodYear: number | null;
  eventDate: string | null;
  amountPerShare: number | null;
  yieldRatio: number | null;
  currencyCode: string | null;
};

export type ProjectionValue = {
  metricCode: string;
  value: number | null;
  unitCode: string;
  periodLabel: string;
  sourceKind: string;
};

export type ActiveProjection = {
  scenarioCode: string;
  scenarioVersion: number | null;
  projectionYear: number | null;
  asOfQuarter: number | null;
  yearsAvailable: number | null;
  averageDprRatio: number | null;
  manualDprRatio: number | null;
  projectedSharesOutstanding: number | null;
  sourceName: string;
  sourceReference: string;
  values: ProjectionValue[];
};

export type BacktestMethod = {
  methodCode: string;
  methodName: string;
  intrinsicValue: number | null;
  currentPrice: number | null;
  gapRatio: number | null;
  mos: number | null;
  verdict: string;
  calculationStatus: string;
  flags: string[];
  details: Record<string, unknown>;
};

/**
 * Fundamental signals shown next to each historical case. Every field is
 * optional-by-value (`null` = not available) because only some of them can be
 * derived from stored data; the UI renders `null` as "Not available" rather
 * than inventing a number.
 */
export type BacktestContext = {
  revenueYoY: number | null;
  netIncomeYoY: number | null;
  epsMomentum: string | null;
  revenueMomentum: string | null;
  roeTrend: string | null;
  yield: number | null;
  ocfNi: number | null;
};

export type BacktestCaseData = {
  caseId: string;
  caseQuarter: string;
  baseYear: number | null;
  analysisDate: string;
  analysisPrice: number | null;
  analysisPriceSource: string;
  stockType: string | null;
  yearsAvailable: number | null;
  yearsCompare: number | null;
  mosMain: number | null;
  mosPeter: number | null;
  mosWeight: number | null;
  mosMethodCode: string | null;
  consensus: string | null;
  consensusUndervalued: number | null;
  consensusValid: number | null;
  verdict: string | null;
  verdictMos: string | null;
  calculationStatus: string;
  flags: string[];
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
  peakMonth: number | null;
  troughMonth: number | null;
  returnPeak: number | null;
  returnDown: number | null;
  methods: BacktestMethod[];
  context: BacktestContext;
};

export type BacktestData = {
  ticker: string;
  sectorName: string | null;
  methodVersion: string | null;
  completedAt: string | null;
  cases: BacktestCaseData[];
};

export type StockResearchData = {
  instrument: {
    ticker: string;
    companyName: string | null;
    sectorName: string | null;
    subsectorName: string | null;
    currencyCode: string;
  };
  prices: StockPrice[];
  financialPeriods: FinancialPeriod[];
  valuationMethods: ValuationMethod[];
  valuationSummary: ValuationSummary | null;
  valuationFrequency: ValuationFrequency | null;
  annualGrowth: AnnualGrowthMetric[];
  annualRatios: AnnualRatioMetric[];
  quarterlyQuality: QuarterlyQualityMetric[];
  dividends: DividendFact[];
  projection: ActiveProjection | null;
  stockClassification: StockClassification | null;
  dataQuality: DataQuality | null;
};

function getSupabaseClient() {
  const url = process.env.SUPABASE_URL;
  const publishableKey = process.env.SUPABASE_PUBLISHABLE_KEY;

  if (!url || !publishableKey) {
    throw new Error("Supabase server environment is not configured.");
  }

  return createClient(url, publishableKey, {
    auth: {
      autoRefreshToken: false,
      persistSession: false,
      detectSessionInUrl: false,
    },
  });
}

function asObject(value: unknown): JsonObject | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as JsonObject)
    : null;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNullableString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/**
 * A JSONB flag column arrives as an array of strings. A non-array (or an array
 * holding non-strings) yields an empty list rather than `null`, so callers can
 * always ask `flags.includes(...)` without a guard.
 */
function asStringArray(value: unknown): string[] {
  return asArray(value).filter((entry): entry is string => typeof entry === "string");
}

function asFiniteNumber(value: unknown): number | null {
  if (typeof value !== "number" && typeof value !== "string") return null;
  if (typeof value === "string" && value.trim() === "") return null;

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function mapMarketOverviewRow(value: unknown): MarketOverviewStock | null {
  const row = asObject(value);
  if (!row || typeof row.ticker !== "string") return null;

  const prices = asArray(row.sparkline)
    .map(asFiniteNumber)
    .filter((price): price is number => price !== null);

  return {
    ticker: row.ticker,
    companyName: asString(row.company_name, row.ticker),
    sector: asString(row.sector_name, "Not available"),
    stockType: "Not available",
    currencyCode: asString(row.currency_code, "IDR"),
    price: asFiniteNumber(row.latest_close),
    change: asFiniteNumber(row.price_change),
    changePercent: asFiniteNumber(row.change_percent),
    sparkline: prices,
    verdict: "Not available",
    recommendationAvailable: false,
    mos: null,
    evidenceWins: null,
    evidenceTotal: null,
    updatedAt: asNullableString(row.latest_trading_date),
  };
}

function mapMarketOverview(value: unknown): MarketOverviewData {
  const result = asObject(value);
  if (!result) throw new Error("Supabase returned an invalid market response.");

  return {
    stocks: asArray(result.stocks)
      .map(mapMarketOverviewRow)
      .filter((stock): stock is MarketOverviewStock => stock !== null),
    totalCount: asFiniteNumber(result.total_count) ?? 0,
    currentPage: asFiniteNumber(result.current_page) ?? 1,
    pageSize: asFiniteNumber(result.page_size) ?? DEFAULT_MARKET_PAGE_SIZE,
  };
}

function mapPrice(value: unknown): StockPrice | null {
  const row = asObject(value);
  if (!row || typeof row.trading_date !== "string") return null;

  return {
    tradingDate: row.trading_date,
    closePrice: asFiniteNumber(row.close_price),
    marketCap: asFiniteNumber(row.market_cap),
    currencyCode: asString(row.currency_code, "IDR"),
  };
}

function mapFinancialFact(value: unknown): FinancialFact | null {
  const row = asObject(value);
  if (!row || typeof row.metric_code !== "string") return null;

  return {
    metricCode: row.metric_code,
    value: asFiniteNumber(row.value_numeric),
    unitCode: asString(row.unit_code),
    currencyCode: asNullableString(row.currency_code),
    qualityStatus: asString(row.quality_status, "UNKNOWN"),
  };
}

function mapFinancialPeriod(value: unknown): FinancialPeriod | null {
  const row = asObject(value);
  if (!row || typeof row.period_end !== "string") return null;

  return {
    periodType: asString(row.period_type),
    periodLabel: asString(row.period_label, row.period_end),
    periodEnd: row.period_end,
    periodBasis: asString(row.period_basis, "UNKNOWN"),
    statementScope: asString(row.statement_scope, "UNKNOWN"),
    facts: asArray(row.facts)
      .map(mapFinancialFact)
      .filter((fact): fact is FinancialFact => fact !== null),
  };
}

function mapValuationMethod(value: unknown): ValuationMethod | null {
  const row = asObject(value);
  if (!row || typeof row.method_code !== "string") return null;

  return {
    methodCode: row.method_code,
    methodName: asString(row.method_name, row.method_code),
    valuationDate: asString(row.valuation_date),
    intrinsicValue: asFiniteNumber(row.intrinsic_value),
    currentPrice: asFiniteNumber(row.current_price),
    gapRatio: asFiniteNumber(row.gap_ratio),
    mos: asFiniteNumber(row.mos),
    verdict: asString(row.verdict, "NOT_APPLICABLE"),
    calculationStatus: asString(row.calculation_status, "UNAVAILABLE"),
    flags: asStringArray(row.flags),
    stockType: asNullableString(row.stock_type),
  };
}

function mapValuationSummary(value: unknown): ValuationSummary | null {
  const row = asObject(value);
  if (!row) return null;
  return {
    methodVerdict: asNullableString(row.method_verdict),
    methodUndervaluedCount: asFiniteNumber(row.method_undervalued_count) ?? 0,
    methodValidCount: asFiniteNumber(row.method_valid_count) ?? 0,
    mosMethodCode: asNullableString(row.mos_method_code),
    mos: asFiniteNumber(row.mos),
    mosVerdict: asNullableString(row.mos_verdict),
    mosThreshold: asFiniteNumber(row.mos_threshold),
  };
}

function mapAnnualRatioMetric(value: unknown): AnnualRatioMetric | null {
  const row = asObject(value);
  if (!row || typeof row.metric_code !== "string" || typeof row.period_end !== "string") return null;

  return {
    periodEnd: row.period_end,
    periodLabel: asString(row.period_label, row.period_end),
    metricCode: row.metric_code,
    value: asFiniteNumber(row.value_numeric),
    unitCode: asString(row.unit_code, "UNKNOWN"),
    calculationStatus: asString(row.calculation_status, "UNAVAILABLE"),
    flags: asStringArray(row.flags),
  };
}

function mapStockClassification(value: unknown): StockClassification | null {
  const row = asObject(value);
  if (!row) return null;
  return {
    finalType: asNullableString(row.final_type),
    systemRecommendation: asNullableString(row.system_recommendation),
    confidence: asFiniteNumber(row.confidence),
    ruleFlags: asStringArray(row.rule_flags),
  };
}

function mapDataQuality(value: unknown): DataQuality | null {
  const row = asObject(value);
  if (!row) return null;
  return { warnings: asStringArray(row.warnings) };
}

function mapStockResearchData(value: unknown): StockResearchData | null {
  const result = asObject(value);
  const instrument = asObject(result?.instrument);
  if (!instrument || typeof instrument.ticker !== "string") return null;

  return {
    instrument: {
      ticker: instrument.ticker,
      companyName: asNullableString(instrument.company_name),
      sectorName: asNullableString(instrument.sector_name),
      subsectorName: asNullableString(instrument.subsector_name),
      currencyCode: asString(instrument.currency_code, "IDR"),
    },
    prices: asArray(result?.prices)
      .map(mapPrice)
      .filter((price): price is StockPrice => price !== null),
    financialPeriods: asArray(result?.financial_periods)
      .map(mapFinancialPeriod)
      .filter((period): period is FinancialPeriod => period !== null),
    valuationMethods: asArray(asObject(result?.valuation_frequency)?.daily
      ? asObject(asObject(result?.valuation_frequency)?.daily)?.methods
      : result?.valuation_methods)
      .map((row) => {
        const method = asObject(row);
        return method && !("valuation_date" in method)
          ? mapValuationMethod({ ...method, valuation_date: asObject(asObject(result?.valuation_frequency)?.daily)?.trading_date })
          : mapValuationMethod(row);
      })
      .filter((method): method is ValuationMethod => method !== null),
    valuationSummary: mapValuationSummary(result?.valuation_summary),
    valuationFrequency: mapValuationFrequency(result?.valuation_frequency),
    annualGrowth: asArray(result?.annual_growth)
      .map(mapAnnualGrowthMetric)
      .filter((metric): metric is AnnualGrowthMetric => metric !== null),
    annualRatios: asArray(result?.annual_ratios)
      .map(mapAnnualRatioMetric)
      .filter((metric): metric is AnnualRatioMetric => metric !== null),
    quarterlyQuality: asArray(result?.quarterly_quality)
      .map(mapQuarterlyQualityMetric)
      .filter((metric): metric is QuarterlyQualityMetric => metric !== null),
    dividends: asArray(result?.dividends)
      .map(mapDividendFact)
      .filter((fact): fact is DividendFact => fact !== null),
    projection: mapActiveProjection(result?.projection),
    stockClassification: mapStockClassification(result?.stock_classification),
    dataQuality: mapDataQuality(result?.data_quality),
  };
}

function mapValuationFrequency(value: unknown): ValuationFrequency | null {
  const result = asObject(value);
  if (!result) return null;
  const fundamentalRow = asObject(result.fundamental);
  const dailyRow = asObject(result.daily);
  const methods = (rows: unknown): ValuationMethod[] => asArray(rows)
    .map(mapValuationMethod)
    .filter((method): method is ValuationMethod => method !== null);
  return {
    fundamental: fundamentalRow ? {
      snapshotId: asString(fundamentalRow.snapshot_id),
      stockType: asNullableString(fundamentalRow.stock_type),
      methods: asArray(fundamentalRow.methods).map((row) => {
        const method = asObject(row);
        return {
          methodCode: asString(method?.method_code),
          intrinsicValue: asFiniteNumber(method?.intrinsic_value),
          calculationStatus: asString(method?.calculation_status),
        };
      }),
    } : null,
    daily: dailyRow ? {
      tradingDate: asString(dailyRow.trading_date),
      currentPrice: asFiniteNumber(dailyRow.current_price),
      consensusVerdict: asNullableString(dailyRow.consensus_verdict),
      basedMethodCode: asNullableString(dailyRow.based_method_code),
      basedMos: asFiniteNumber(dailyRow.based_mos),
      basedMosVerdict: asNullableString(dailyRow.based_mos_verdict),
      methods: methods(dailyRow.methods),
    } : null,
  };
}

function mapAnnualGrowthMetric(value: unknown): AnnualGrowthMetric | null {
  const row = asObject(value);
  if (!row || typeof row.metric_code !== "string" || typeof row.period_end !== "string") return null;

  return {
    periodEnd: row.period_end,
    periodLabel: asString(row.period_label, row.period_end),
    metricCode: row.metric_code,
    value: asFiniteNumber(row.value_numeric),
    calculationStatus: asString(row.calculation_status, "UNAVAILABLE"),
  };
}

function mapQuarterlyQualityMetric(value: unknown): QuarterlyQualityMetric | null {
  const row = asObject(value);
  if (!row || typeof row.metric_code !== "string" || typeof row.period_end !== "string") return null;

  return {
    periodEnd: row.period_end,
    periodLabel: asString(row.period_label, row.period_end),
    metricCode: row.metric_code,
    value: asFiniteNumber(row.value_numeric),
    calculationStatus: asString(row.calculation_status, "UNAVAILABLE"),
  };
}

function mapDividendFact(value: unknown): DividendFact | null {
  const row = asObject(value);
  if (!row || typeof row.fact_type !== "string") return null;

  return {
    factType: row.fact_type,
    periodYear: asFiniteNumber(row.period_year),
    eventDate: asNullableString(row.event_date),
    amountPerShare: asFiniteNumber(row.amount_per_share),
    yieldRatio: asFiniteNumber(row.yield_ratio),
    currencyCode: asNullableString(row.currency_code),
  };
}

function mapProjectionValue(value: unknown): ProjectionValue | null {
  const row = asObject(value);
  if (!row || typeof row.metric_code !== "string") return null;

  return {
    metricCode: row.metric_code,
    value: asFiniteNumber(row.value_numeric),
    unitCode: asString(row.unit_code, ""),
    periodLabel: asString(row.period_label, ""),
    sourceKind: asString(row.source_kind, ""),
  };
}

function mapActiveProjection(value: unknown): ActiveProjection | null {
  const row = asObject(value);
  if (!row || typeof row.scenario_code !== "string") return null;

  return {
    scenarioCode: row.scenario_code,
    scenarioVersion: asFiniteNumber(row.scenario_version),
    projectionYear: asFiniteNumber(row.projection_year),
    asOfQuarter: asFiniteNumber(row.as_of_quarter),
    yearsAvailable: asFiniteNumber(row.years_available),
    averageDprRatio: asFiniteNumber(row.average_dpr_ratio),
    manualDprRatio: asFiniteNumber(row.manual_dpr_ratio),
    projectedSharesOutstanding: asFiniteNumber(row.projected_shares_outstanding),
    sourceName: asString(row.source_name, ""),
    sourceReference: asString(row.source_reference, ""),
    values: asArray(row.values)
      .map(mapProjectionValue)
      .filter((entry): entry is ProjectionValue => entry !== null),
  };
}

function mapBacktestMethod(value: unknown): BacktestMethod | null {
  const row = asObject(value);
  if (!row || typeof row.method_code !== "string") return null;

  return {
    methodCode: row.method_code,
    methodName: asString(row.method_name, row.method_code),
    intrinsicValue: asFiniteNumber(row.intrinsic_value),
    currentPrice: asFiniteNumber(row.current_price),
    gapRatio: asFiniteNumber(row.gap_ratio),
    mos: asFiniteNumber(row.mos),
    verdict: asString(row.verdict, "NOT_APPLICABLE"),
    calculationStatus: asString(row.calculation_status, "UNAVAILABLE"),
    flags: asArray(row.flags).filter((flag): flag is string => typeof flag === "string"),
    details: asObject(row.details) ?? {},
  };
}

function mapBacktestContext(value: unknown): BacktestContext {
  const row = asObject(value) ?? {};
  return {
    revenueYoY: asFiniteNumber(row.revenueYoY),
    netIncomeYoY: asFiniteNumber(row.netIncomeYoY),
    epsMomentum: asNullableString(row.epsMomentum),
    revenueMomentum: asNullableString(row.revenueMomentum),
    roeTrend: asNullableString(row.roeTrend),
    yield: asFiniteNumber(row.yield),
    ocfNi: asFiniteNumber(row.ocfNi),
  };
}

function mapBacktestCase(value: unknown): BacktestCaseData | null {
  const row = asObject(value);
  if (!row || typeof row.case_quarter !== "string" || typeof row.analysis_date !== "string") {
    return null;
  }

  return {
    caseId: asString(row.case_id, row.case_quarter),
    caseQuarter: row.case_quarter,
    baseYear: asFiniteNumber(row.base_year),
    analysisDate: row.analysis_date,
    analysisPrice: asFiniteNumber(row.analysis_price),
    analysisPriceSource: asString(row.analysis_price_source, "CLOSE_PIT"),
    stockType: asNullableString(row.stock_type),
    yearsAvailable: asFiniteNumber(row.years_available),
    yearsCompare: asFiniteNumber(row.years_compare),
    mosMain: asFiniteNumber(row.mos_main),
    mosPeter: asFiniteNumber(row.mos_peter),
    mosWeight: asFiniteNumber(row.mos_weight),
    mosMethodCode: asNullableString(row.mos_method_code),
    consensus: asNullableString(row.consensus),
    consensusUndervalued: asFiniteNumber(row.consensus_undervalued),
    consensusValid: asFiniteNumber(row.consensus_valid),
    verdict: asNullableString(row.verdict),
    verdictMos: asNullableString(row.verdict_mos),
    calculationStatus: asString(row.calculation_status, "UNAVAILABLE"),
    flags: asArray(row.flags).filter((flag): flag is string => typeof flag === "string"),
    high3m: asFiniteNumber(row.high_3m),
    low3m: asFiniteNumber(row.low_3m),
    high6m: asFiniteNumber(row.high_6m),
    low6m: asFiniteNumber(row.low_6m),
    high9m: asFiniteNumber(row.high_9m),
    low9m: asFiniteNumber(row.low_9m),
    high12m: asFiniteNumber(row.high_12m),
    low12m: asFiniteNumber(row.low_12m),
    peakPrice: asFiniteNumber(row.peak_price),
    troughPrice: asFiniteNumber(row.trough_price),
    peakMonth: asFiniteNumber(row.peak_month),
    troughMonth: asFiniteNumber(row.trough_month),
    returnPeak: asFiniteNumber(row.return_peak),
    returnDown: asFiniteNumber(row.return_down),
    methods: asArray(row.methods)
      .map(mapBacktestMethod)
      .filter((method): method is BacktestMethod => method !== null),
    context: mapBacktestContext(row.context),
  };
}

function mapBacktestData(value: unknown): BacktestData | null {
  const result = asObject(value);
  const instrument = asObject(result?.instrument);
  const run = asObject(result?.run);
  if (!result || !instrument || typeof instrument.ticker !== "string") return null;

  return {
    ticker: instrument.ticker,
    sectorName: asNullableString(instrument.sector_name),
    methodVersion: asNullableString(run?.method_version),
    completedAt: asNullableString(run?.completed_at),
    cases: asArray(result.cases)
      .map(mapBacktestCase)
      .filter((testCase): testCase is BacktestCaseData => testCase !== null),
  };
}

function isTickerExistsResponse(value: unknown): boolean {
  const response = asObject(value);
  return asObject(response?.instrument) !== null;
}

export async function getMarketOverviewData(
  page: number,
  pageSize: MarketPageSize = DEFAULT_MARKET_PAGE_SIZE,
): Promise<MarketOverviewData> {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase.rpc("get_market_overview_page", {
    p_page: Math.max(1, Math.floor(page)),
    p_page_size: pageSize,
  });

  if (error) throw new Error("Unable to load market data from Supabase.");
  return mapMarketOverview(data);
}

export async function getStockResearchData(ticker: string): Promise<StockResearchData | null> {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase.rpc("get_stock_research_data", {
    p_ticker: ticker.trim().toUpperCase(),
  });

  if (error) throw new Error("Unable to load stock data from Supabase.");
  return mapStockResearchData(data);
}

export async function getStockBacktestData(ticker: string): Promise<BacktestData | null> {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase.rpc("get_stock_backtest", {
    p_ticker: ticker.trim().toUpperCase(),
  });

  if (error) throw new Error("Unable to load backtest data from Supabase.");
  return mapBacktestData(data);
}

export async function getStockValuationSummary(
  ticker: string,
): Promise<ValuationSummary | null> {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase.rpc("get_stock_valuation_frequency", {
    p_ticker: ticker.trim().toUpperCase(),
  });

  if (error) throw new Error("Unable to load valuation summary from Supabase.");
  const frequency = mapValuationFrequency(data);
  const daily = frequency?.daily;
  if (!daily) {
    // Additive rollout guard: before the first new snapshot/status is safely
    // backfilled, keep the existing read-only database contract available.
    const { data: legacy, error: legacyError } = await supabase.rpc("get_stock_valuation_summary", {
      p_ticker: ticker.trim().toUpperCase(),
    });
    if (legacyError) throw new Error("Unable to load valuation summary from Supabase.");
    return mapValuationSummary(legacy);
  }
  const validMethods = daily.methods.filter((method) => method.calculationStatus === "VALID" || method.calculationStatus === "APPROXIMATED");
  const undervalued = validMethods.filter((method) => method.verdict === "UNDERVALUED").length;
  return {
    currentPrice: daily.currentPrice,
    tradingDate: daily.tradingDate,
    methods: daily.methods,
    stockType: frequency?.fundamental?.stockType ?? null,
    methodVerdict: daily.consensusVerdict,
    methodUndervaluedCount: undervalued,
    methodValidCount: validMethods.length,
    mosMethodCode: daily.basedMethodCode,
    mos: daily.basedMos,
    mosVerdict: daily.basedMosVerdict,
    mosThreshold: asFiniteNumber(asObject(data)?.daily && asObject(asObject(data)?.daily)?.mos_threshold),
  };
}

export async function getTickerExists(ticker: string): Promise<boolean> {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase.rpc("get_stock_research_data", {
    p_ticker: ticker.trim().toUpperCase(),
  });

  if (error) throw new Error("Unable to verify stock ticker in Supabase.");
  return isTickerExistsResponse(data);
}
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
      marketCap: "Rp 12,8 T",
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
    thesisValidator: {
      quarters: ["Q3 2025", "Q4 2025", "Q1 2026", "Q2 2026"],
      rows: [
        {
          item: "Revenue YoY (%)",
          q3: "5,1%",
          q4: "3,9%",
          q1: "7,4%",
          q2: "19,3%",
          trend: "↑ Naik +19,3%",
          trendTone: "green",
        },
        {
          item: "Gross Margin (Actual %)",
          q3: "16,8%",
          q4: "18,8%",
          q1: "16,0%",
          q2: "15,1%",
          trend: "➖ GM Stabil 15,1%",
          trendTone: "slate",
        },
        {
          item: "Net Income YoY (%)",
          q3: "22,4%",
          q4: "26,0%",
          q1: "10,6%",
          q2: "36,7%",
          trend: "↑ Naik +36,7%",
          trendTone: "green",
        },
        {
          item: "OCF / NI Ratio (x)",
          q3: "0,53x",
          q4: "0,83x",
          q1: "0,73x",
          q2: "0,57x",
          trend: "⚠️ Cukup — 0,57x",
          trendTone: "yellow",
        },
        {
          item: "Interest Expense (M Rp)",
          q3: "10,9",
          q4: "9,8",
          q1: "9,1",
          q2: "9,2",
          trend: "↓ Turun -15,3%",
          trendTone: "green",
        },
      ],
      footnote:
        "💡 Gross Margin (Actual %) shows the actual margin value each quarter — not YoY change. Compare latest quarter vs earliest quarter to assess trend direction.",
    },
    dividendConsistency: {
      averageYield: "13,2%",
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
          p2026: "40,9%",
          y2025: "7,1%",
          y2024: "8,2%",
          y2023: "5,4%",
          y2022: "4,2%",
          avg4Y: "13,2%",
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

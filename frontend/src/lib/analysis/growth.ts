type GrowthCard = { title: string; cagrValue: string };
type GrowthTable = { rows: { metric: string; values: string[] }[] };

function parseGrowthNumeric(value: string | undefined) {
  if (!value) return Number.NaN;
  const cleaned = value.replace(/[^0-9.,-]/g, "").replace(/\./g, "").replace(",", ".");
  if (!cleaned) return Number.NaN;
  const numeric = Number(cleaned);
  return Number.isNaN(numeric) ? Number.NaN : numeric;
}

export function analyzeHistoricalGrowth(cards: GrowthCard[], table: GrowthTable) {
  const insights: string[] = [];
  const measured = cards.map((card) => ({ card, value: parseGrowthNumeric(card.cagrValue) })).filter((entry) => !Number.isNaN(entry.value));
  const ranked = [...measured].sort((left, right) => right.value - left.value);
  const leader = ranked[0];
  const laggard = ranked.at(-1);
  if (leader && laggard && leader.value !== laggard.value) insights.push(`${leader.card.title} is the strongest available growth measure at ${leader.card.cagrValue}, while ${laggard.card.title} is the slowest.`);
  const revenue = measured.find((entry) => /revenue/i.test(entry.card.title));
  const netIncome = measured.find((entry) => /net income/i.test(entry.card.title));
  const fasterCompoundingMetric = revenue && netIncome && revenue.value !== netIncome.value ? netIncome.value > revenue.value ? "Net income" : "Revenue" : null;
  if (fasterCompoundingMetric) insights.push(fasterCompoundingMetric === "Net income" ? "Net income compounded faster than revenue across the available periods." : "Revenue compounded faster than net income across the available periods.");
  const marginObservations = table.rows.filter((row) => /margin/i.test(row.metric)).flatMap((row) => {
    const first = row.values[0];
    const last = row.values.at(-1);
    const firstNumeric = parseGrowthNumeric(first);
    const lastNumeric = parseGrowthNumeric(last);
    if (!first || !last || Number.isNaN(firstNumeric) || Number.isNaN(lastNumeric) || firstNumeric === lastNumeric) return [];
    return [`${row.metric} moved from ${first} to ${last} between the earliest and latest available periods.`];
  });
  insights.push(...marginObservations);
  const positiveGrowth = measured.length > 0 && measured.every((entry) => entry.value > 0);
  if (positiveGrowth) insights.push("All available growth measures are positive across the reported periods.");
  return {
    strongestGrowth: leader ? { metric: leader.card.title, value: leader.card.cagrValue } : null,
    slowestGrowth: laggard ? { metric: laggard.card.title, value: laggard.card.cagrValue } : null,
    fasterCompoundingMetric,
    marginObservations,
    positiveGrowth,
    insights: insights.slice(0, 4),
  };
}

/** Short month labels shared by the price chart series and its axis labels. */
const MONTH_LABELS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/**
 * Convert an ISO trading date ("2026-09-24") into the chart label format
 * ("Sep 2026"). Returns null when the input is not an ISO date, so callers can
 * skip malformed rows instead of rendering a wrong label.
 */
export function toMonthLabel(isoDate: string): string | null {
  const [year, month] = isoDate.split("-");
  const monthIndex = Number(month) - 1;
  if (!year || !Number.isInteger(monthIndex) || monthIndex < 0 || monthIndex > 11) {
    return null;
  }
  return `${MONTH_LABELS[monthIndex]} ${year}`;
}

/**
 * Convert a chart month label ("Sep 2026") into a comparable month index
 * (`year * 12 + monthIndex`) so a window can be measured in calendar months
 * instead of array length. Returns null when the label cannot be parsed.
 */
export function toMonthIndex(label: string): number | null {
  const [month, year] = label.trim().split(/\s+/);
  const monthIndex = MONTH_LABELS.indexOf(month);
  const parsedYear = Number(year);
  if (monthIndex < 0 || !Number.isInteger(parsedYear)) return null;
  return parsedYear * 12 + monthIndex;
}

/**
 * Convert an ISO trading date ("2026-09-24") into a readable day label
 * ("24 Sep 2026"). Used where a surface must state *when* the data was last
 * refreshed, so callers can fall back to a placeholder instead of printing a
 * raw ISO string or a wrong date.
 */
export function toDayLabel(isoDate: string): string | null {
  const [year, month, day] = isoDate.split("-");
  const monthIndex = Number(month) - 1;
  const dayNumber = Number(day);
  if (
    !year ||
    !Number.isInteger(monthIndex) ||
    monthIndex < 0 ||
    monthIndex > 11 ||
    !Number.isInteger(dayNumber) ||
    dayNumber < 1 ||
    dayNumber > 31
  ) {
    return null;
  }
  return `${day} ${MONTH_LABELS[monthIndex]} ${year}`;
}


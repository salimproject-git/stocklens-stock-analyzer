const rupiahFormatter = new Intl.NumberFormat("id-ID", {
  maximumFractionDigits: 0,
});

export function formatRupiah(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "N/A";
  return `Rp${rupiahFormatter.format(Math.trunc(value))}`;
}

export function parseNumericValue(value: string | number) {
  if (typeof value === "number") return value;
  const normalized = value.trim().replace(/\s/g, "");
  if (normalized.includes(",")) {
    return Number(normalized.replace(/\./g, "").replace(",", "."));
  }
  if (/^-?\d{1,3}(?:\.\d{3})+$/.test(normalized)) {
    return Number(normalized.replace(/\./g, ""));
  }
  return Number(normalized);
}

export function formatRupiahValue(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "N/A";
  return formatRupiah(parseNumericValue(value));
}

/**
 * Parse a display value into its signed numeric magnitude so a caller can pick a
 * tone (red for negative, green for zero/positive) and an arrow direction.
 *
 * Handles the two shapes the UI produces: locale percentages (`"-51,9%"`, comma
 * decimal) and plain amounts (`"19.07"`, dot decimal). Returns `NaN` for a value
 * that carries no number (`"N/A"`, `"-"`, `"Not available"`), so callers can fall
 * back to a neutral tone instead of guessing a sign.
 */
export function parseSignedNumber(value: string | null | undefined) {
  if (value == null) return Number.NaN;
  const isPercent = value.includes("%");
  const cleaned = value.replace(/[^0-9.,-]/g, "");
  if (!cleaned || cleaned === "-") return Number.NaN;
  const normalized = isPercent
    ? cleaned.replace(/\./g, "").replace(",", ".")
    : cleaned.replace(/,/g, "");
  const numeric = Number(normalized);
  return Number.isNaN(numeric) ? Number.NaN : numeric;
}

const decimalFormatters = new Map<number, Intl.NumberFormat>();

function getDecimalFormatter(maximumFractionDigits: number) {
  const cached = decimalFormatters.get(maximumFractionDigits);
  if (cached) return cached;

  const formatter = new Intl.NumberFormat("id-ID", { maximumFractionDigits });
  decimalFormatters.set(maximumFractionDigits, formatter);
  return formatter;
}

/**
 * Shared default for numeric values that are shown as-is (chart labels, tooltips,
 * small tables). Values coming from the database can carry long floating point
 * tails, so the default is capped at two decimal places.
 */
export function formatDecimal(
  value: number | null | undefined,
  maximumFractionDigits = 2,
) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "N/A";
  }
  return getDecimalFormatter(maximumFractionDigits).format(value);
}

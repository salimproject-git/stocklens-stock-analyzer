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

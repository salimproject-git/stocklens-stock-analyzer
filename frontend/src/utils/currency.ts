const rupiahFormatter = new Intl.NumberFormat("id-ID", {
  maximumFractionDigits: 0,
});

export function formatRupiah(value: number) {
  if (!Number.isFinite(value)) return "N/A";
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

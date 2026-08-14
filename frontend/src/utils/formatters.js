const integerFormatter = new Intl.NumberFormat("fr-FR", {
  maximumFractionDigits: 0,
});

const decimalFormatter = new Intl.NumberFormat("fr-FR", {
  maximumFractionDigits: 1,
});

function normalizeNumberSpaces(value) {
  return value.replace(/\u202f/g, " ");
}

export function formatInteger(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return normalizeNumberSpaces(integerFormatter.format(Number(value)));
}

export function formatKm(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${normalizeNumberSpaces(decimalFormatter.format(Number(value)))} km`;
}

export function formatCarbon(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${normalizeNumberSpaces(integerFormatter.format(Number(value)))} kgCO2`;
}

export function formatDuration(minutes) {
  if (minutes === null || minutes === undefined || Number.isNaN(Number(minutes))) {
    return "-";
  }
  const rounded = Math.round(Number(minutes));
  const hours = Math.floor(rounded / 60);
  const remainingMinutes = rounded % 60;
  if (!hours) {
    return `${remainingMinutes} min`;
  }
  return `${hours} h ${String(remainingMinutes).padStart(2, "0")}`;
}

export function formatTimeFromMinutes(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  const minutes = Math.round(Number(value));
  const hours = Math.floor(minutes / 60) % 24;
  const remainingMinutes = minutes % 60;
  return `${String(hours).padStart(2, "0")}:${String(remainingMinutes).padStart(2, "0")}`;
}

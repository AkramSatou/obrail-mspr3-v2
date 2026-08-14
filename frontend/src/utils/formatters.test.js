import { describe, expect, it } from "vitest";
import {
  formatCarbon,
  formatDuration,
  formatInteger,
  formatKm,
  formatTimeFromMinutes,
} from "./formatters.js";

describe("formatters", () => {
  it("formats dashboard metrics in French locale", () => {
    expect(formatInteger(12500)).toBe("12 500");
    expect(formatKm(174.25)).toBe("174,3 km");
    expect(formatCarbon(75624.4)).toBe("75 624 kgCO2");
  });

  it("formats durations and clock values from API minutes", () => {
    expect(formatDuration(116)).toBe("1 h 56");
    expect(formatDuration(45)).toBe("45 min");
    expect(formatTimeFromMinutes(556)).toBe("09:16");
  });

  it("keeps empty values readable", () => {
    expect(formatInteger(null)).toBe("-");
    expect(formatKm(undefined)).toBe("-");
    expect(formatCarbon(Number.NaN)).toBe("-");
    expect(formatTimeFromMinutes(null)).toBe("-");
  });
});

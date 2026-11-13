// @vitest-environment node
import { describe, expect, it } from "vitest";
import { chartRows } from "@/lib/chart-data";
import { formatValue, groupDigits, periodLabel, sectionLabel } from "@/lib/format";
import { marginTrend, revenueTrend } from "./fixtures";

describe("groupDigits", () => {
  it.each([
    ["391035000000", "391,035,000,000"],
    ["1200", "1,200"],
    ["999", "999"],
    ["0", "0"],
    ["-9038000000", "-9,038,000,000"],
    ["46.206350", "46.206350"],
    ["1234567.891000", "1,234,567.891000"],
    ["-0.5", "-0.5"],
    // Beyond what a JavaScript number holds exactly: the text is grouped, never parsed.
    ["9007199254740993", "9,007,199,254,740,993"],
    ["123456789012345678901234567890", "123,456,789,012,345,678,901,234,567,890"],
  ])("groups %s as %s without changing a digit", (value, shown) => {
    expect(groupDigits(value)).toBe(shown);
  });

  it("returns text that is not a plain decimal unchanged", () => {
    expect(groupDigits("1e9")).toBe("1e9");
    expect(groupDigits("n/a")).toBe("n/a");
  });
});

describe("formatValue", () => {
  it.each([
    ["391035000000", "USD", "$391,035,000,000"],
    ["-9038000000", "USD", "-$9,038,000,000"],
    ["6.08", "USD/shares", "$6.08 per share"],
    ["15343783000", "shares", "15,343,783,000 shares"],
    ["46.206350", "percent", "46.206350%"],
    ["-2.800000", "percent", "-2.800000%"],
    ["0.867313", "times", "0.867313×"],
    ["42", "widgets", "42 widgets"],
  ])("shows %s %s as %s", (value, unit, shown) => {
    expect(formatValue(value, unit)).toBe(shown);
  });
});

describe("periodLabel", () => {
  it("names the fiscal year, and the quarter before it", () => {
    expect(periodLabel(2024, "FY")).toBe("FY2024");
    expect(periodLabel(2024, "Q2")).toBe("Q2 FY2024");
  });
});

describe("sectionLabel", () => {
  it("names the filing section a passage comes from", () => {
    expect(sectionLabel("mdna")).toBe("MD&A");
    expect(sectionLabel("risk_factors")).toBe("Risk factors");
    expect(sectionLabel("business")).toBe("Business");
    expect(sectionLabel("market_risk")).toBe("Market risk");
    expect(sectionLabel("something_new")).toBe("something_new");
  });
});

describe("chartRows", () => {
  it("turns one series into a row per point, for plotting only", () => {
    expect(chartRows(revenueTrend)).toEqual([
      { x: "FY2022", AAPL: 394328000000 },
      { x: "FY2023", AAPL: 383285000000 },
      { x: "FY2024", AAPL: 391035000000 },
    ]);
  });

  it("lines series up by fiscal year and leaves a missing point out", () => {
    expect(chartRows(marginTrend)).toEqual([
      { x: "FY2023", NVDA: 56.928894 },
      { x: "FY2024", NVDA: 72.717573, AAPL: 46.20635 },
    ]);
  });
});

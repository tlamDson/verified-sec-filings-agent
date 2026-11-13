// How a tool's value is shown. A value arrives as exact decimal text and is shown with
// the same digits: digits are grouped as text, never parsed into a float.

const DECIMAL = /^(-?)(\d+)(\.\d+)?$/;

const SECTIONS: Record<string, string> = {
  business: "Business",
  risk_factors: "Risk factors",
  mdna: "MD&A",
  market_risk: "Market risk",
};

/** "391035000000" as "391,035,000,000". Text that is not a plain decimal is returned as is. */
export function groupDigits(value: string): string {
  const match = DECIMAL.exec(value);
  if (match === null) {
    return value;
  }
  const [, sign = "", whole = "", fraction = ""] = match;
  return `${sign}${whole.replace(/\B(?=(\d{3})+$)/g, ",")}${fraction}`;
}

/** A value with its unit as XBRL names it: USD, USD/shares, shares, percent, times. */
export function formatValue(value: string, unit: string): string {
  const negative = value.startsWith("-");
  const digits = groupDigits(negative ? value.slice(1) : value);
  const sign = negative ? "-" : "";
  switch (unit) {
    case "USD":
      return `${sign}$${digits}`;
    case "USD/shares":
      return `${sign}$${digits} per share`;
    case "percent":
      return `${sign}${digits}%`;
    case "times":
      return `${sign}${digits}×`;
    default:
      return `${sign}${digits} ${unit}`;
  }
}

/** "FY2024", or "Q2 FY2024" for a quarter: always the company's own fiscal year. */
export function periodLabel(fiscalYear: number, fiscalPeriod: string): string {
  return fiscalPeriod === "FY" ? `FY${fiscalYear}` : `${fiscalPeriod} FY${fiscalYear}`;
}

export function sectionLabel(section: string): string {
  return SECTIONS[section] ?? section;
}

/** Whether a link may be shown: sources are filings on sec.gov, nothing else. */
export function isSecUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && parsed.hostname === "www.sec.gov";
  } catch {
    return false;
  }
}

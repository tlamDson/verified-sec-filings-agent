// A chart's series as rows a plotting library reads. This is the one place a value becomes
// a float, and only to place a point on an axis: every label and table shows the exact text.

import type { Chart } from "./chat/types";

export type ChartRow = { x: string } & Record<string, string | number>;

/** One row per x value, in the order first seen, with one number per series that has it. */
export function chartRows(chart: Chart): ChartRow[] {
  const rows = new Map<string, ChartRow>();
  for (const series of chart.series) {
    for (const point of series.points) {
      const row = rows.get(point.x) ?? { x: point.x };
      row[series.name] = Number(point.value);
      rows.set(point.x, row);
    }
  }
  return [...rows.values()].sort((a, b) => (chart.kind === "trend" ? a.x.localeCompare(b.x) : 0));
}

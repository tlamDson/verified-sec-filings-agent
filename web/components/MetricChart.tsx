"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { chartRows } from "@/lib/chart-data";
import type { Chart, ChartPoint } from "@/lib/chat/types";
import { formatValue } from "@/lib/format";

const COLORS = ["#2563eb", "#d97706", "#059669", "#dc2626"];
const NONE = "–";
const AXIS = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

/** The exact text of the value a point was drawn from. */
function exactValue(chart: Chart, series: string, x: string): string | null {
  const points = chart.series.find((candidate) => candidate.name === series)?.points ?? [];
  return points.find((point) => point.x === x)?.value ?? null;
}

function Plot({ chart }: { chart: Chart }) {
  const rows = chartRows(chart);
  const tooltip = (
    <Tooltip
      formatter={(value, name, item) => {
        const exact = exactValue(chart, String(name), String(item.payload?.x ?? ""));
        return exact === null ? String(value) : formatValue(exact, chart.unit);
      }}
    />
  );
  const axes = (
    <>
      <CartesianGrid strokeDasharray="3 3" vertical={false} />
      <XAxis dataKey="x" tickLine={false} />
      <YAxis tickFormatter={(value: number) => AXIS.format(value)} tickLine={false} width={56} />
    </>
  );
  if (chart.kind === "peers") {
    return (
      <BarChart data={rows}>
        {axes}
        {tooltip}
        {chart.series.map((series, at) => (
          <Bar key={series.name} dataKey={series.name} fill={COLORS[at % COLORS.length]} />
        ))}
      </BarChart>
    );
  }
  return (
    <LineChart data={rows}>
      {axes}
      {tooltip}
      {chart.series.length > 1 && <Legend />}
      {chart.series.map((series, at) => (
        <Line
          key={series.name}
          dataKey={series.name}
          stroke={COLORS[at % COLORS.length]}
          strokeWidth={2}
          dot
          connectNulls={false}
          isAnimationActive={false}
        />
      ))}
    </LineChart>
  );
}

/** The values behind the plot, exactly as the tools returned them. */
function ValueTable({ chart }: { chart: Chart }) {
  const labels = [...new Set(chart.series.flatMap((series) => series.points.map((p) => p.x)))];
  if (chart.kind === "trend") {
    labels.sort();
  }
  const pointAt = (points: ChartPoint[], x: string) => points.find((point) => point.x === x);
  return (
    <table className="mt-3 w-full text-left text-xs tabular-nums">
      <thead className="text-neutral-500">
        <tr>
          <th className="py-1 pr-3 font-normal">{chart.kind === "trend" ? "Period" : "Company"}</th>
          {chart.series.flatMap((series) => [
            <th key={series.name} className="py-1 pr-3 font-normal">
              {series.name}
            </th>,
            <th key={`${series.name}-end`} className="py-1 pr-3 font-normal">
              Period ended
            </th>,
          ])}
        </tr>
      </thead>
      <tbody>
        {labels.map((x) => (
          <tr key={x} className="border-t border-neutral-100 dark:border-neutral-800">
            <td className="py-1 pr-3">{x}</td>
            {chart.series.flatMap((series) => {
              const point = pointAt(series.points, x);
              return [
                <td key={series.name} className="py-1 pr-3">
                  {point === undefined ? NONE : formatValue(point.value, chart.unit)}
                </td>,
                <td key={`${series.name}-end`} className="py-1 pr-3">
                  {point?.period_end ?? NONE}
                </td>,
              ];
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** A chart of tool values. The plot is for shape; the table under it holds the figures. */
export function MetricChart({ chart }: { chart: Chart }) {
  return (
    <figure
      aria-label={chart.title}
      className="rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900"
    >
      <figcaption className="mb-2 text-sm font-medium">{chart.title}</figcaption>
      <div className="h-56 w-full" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <Plot chart={chart} />
        </ResponsiveContainer>
      </div>
      <ValueTable chart={chart} />
    </figure>
  );
}

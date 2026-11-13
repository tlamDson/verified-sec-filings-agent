import type { PeersCard, RiskChange, RiskDiffCard } from "@/lib/chat/types";
import { formatValue, periodLabel } from "@/lib/format";
import { CardShell, Missing } from "./CardShell";

const NONE = "–";
const CHANGE_LABELS: Record<RiskChange["kind"], string> = {
  added: "Added",
  removed: "Removed",
  changed: "Reworded",
};

/** One metric across companies, ranked; each row keeps its own period end. */
export function PeersCardView({ card }: { card: PeersCard }) {
  const period = periodLabel(card.fiscal_year, card.fiscal_period);
  return (
    <CardShell title={card.label} subject="peers" period={period}>
      <table className="w-full text-left tabular-nums">
        <thead className="text-xs text-neutral-500">
          <tr>
            <th className="py-1 pr-3 font-normal">Rank</th>
            <th className="py-1 pr-3 font-normal">Company</th>
            <th className="py-1 pr-3 font-normal">{card.label}</th>
            <th className="py-1 font-normal">Period ended</th>
          </tr>
        </thead>
        <tbody>
          {card.rows.map((row) => (
            <tr
              key={row.company.ticker}
              className="border-t border-neutral-100 dark:border-neutral-800"
            >
              <td className="py-1 pr-3">{row.rank ?? NONE}</td>
              <td className="py-1 pr-3" title={row.company.name}>
                {row.company.ticker}
              </td>
              <td className="py-1 pr-3" title={row.reason ?? undefined}>
                {row.value === null
                  ? row.status === "undefined"
                    ? "Not defined"
                    : "Not reported"
                  : formatValue(row.value, card.unit)}
              </td>
              <td className="py-1">{row.period_end ?? NONE}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-neutral-500">{card.note}</p>
    </CardShell>
  );
}

/** Risk factor paragraphs that differ between two 10-Ks of one company. */
export function RiskDiffCardView({ card }: { card: RiskDiffCard }) {
  const { current, previous } = card;
  const period =
    current !== null && previous !== null
      ? `FY${current.fiscal_year} against FY${previous.fiscal_year}`
      : "no comparison";
  return (
    <CardShell title="Risk factors" subject={card.company.ticker} period={period}>
      {card.status === "not_found" ? (
        <Missing>{card.reason ?? "No risk factor section was found to compare."}</Missing>
      ) : (
        <>
          <p className="text-xs text-neutral-500">
            {card.added} added, {card.removed} removed, {card.changed} reworded, {card.unchanged}{" "}
            unchanged
          </p>
          <ul className="mt-2 space-y-2">
            {card.changes.map((change) => (
              <li key={`${change.kind}-${change.text ?? change.previous_text}`}>
                <span className="mr-2 rounded bg-neutral-100 px-1.5 py-0.5 text-xs font-medium dark:bg-neutral-800">
                  {CHANGE_LABELS[change.kind]}
                </span>
                <span>{change.text ?? change.previous_text}</span>
              </li>
            ))}
          </ul>
          {card.changes_total > card.changes.length && (
            <p className="mt-2 text-xs text-neutral-500">
              Showing {card.changes.length} of {card.changes_total} changed paragraphs.
            </p>
          )}
        </>
      )}
    </CardShell>
  );
}

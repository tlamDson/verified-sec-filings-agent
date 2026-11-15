import type { FactCard, RatioCard } from "@/lib/chat/types";
import { formatValue, periodLabel } from "@/lib/format";
import { CardShell, FilingLink, Missing } from "./CardShell";

const VALUE = "text-2xl font-semibold tabular-nums tracking-tight";

/** One reported value with its period end and filing, or the statement that there is none. */
export function FactCardView({ card }: { card: FactCard }) {
  const period = periodLabel(card.fiscal_year, card.fiscal_period);
  return (
    <CardShell title={card.label} subject={card.company.ticker} period={period}>
      {card.value === null ? (
        <Missing>Not reported in the filings.</Missing>
      ) : (
        <>
          <p className={VALUE}>{formatValue(card.value, card.unit)}</p>
          <p className="mt-1 text-xs text-neutral-500">
            {card.period_end !== null && <>Period ended {card.period_end}</>}
            {card.source !== null && (
              <>
                {" · "}
                <FilingLink source={card.source} />
              </>
            )}
          </p>
          {card.restated && card.original_value !== null && (
            <p className="mt-2 rounded bg-amber-50 px-2 py-1 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200">
              Restated. First reported as {formatValue(card.original_value, card.unit)}, filed{" "}
              {card.original_filed}.
            </p>
          )}
        </>
      )}
    </CardShell>
  );
}

/** A ratio computed in code, with the formula and the reported facts it used. */
export function RatioCardView({ card }: { card: RatioCard }) {
  const period = periodLabel(card.fiscal_year, card.fiscal_period);
  return (
    <CardShell title={card.label} subject={card.company.ticker} period={period}>
      {card.value === null ? (
        <Missing>{card.reason ?? "Not reported in the filings."}</Missing>
      ) : (
        <>
          <p className={VALUE}>{formatValue(card.value, card.unit)}</p>
          {card.period_end !== null && (
            <p className="mt-1 text-xs text-neutral-500">Period ended {card.period_end}</p>
          )}
        </>
      )}
      <p className="mt-2 text-xs text-neutral-500">
        Computed as <code className="font-mono">{card.formula}</code>
      </p>
      {card.inputs.length > 0 && (
        <ul className="mt-1 space-y-0.5 text-xs">
          {card.inputs.map((input) => (
            <li key={`${input.concept}-${input.period_end}`} className="flex justify-between gap-3">
              <span className="text-neutral-500">
                {input.label}, period ended {input.period_end}
              </span>
              <span className="tabular-nums">{formatValue(input.value, input.unit)}</span>
            </li>
          ))}
        </ul>
      )}
    </CardShell>
  );
}

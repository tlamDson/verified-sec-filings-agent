import type { Card } from "@/lib/chat/types";
import { PeersCardView, RiskDiffCardView } from "./cards/ComparisonCards";
import { FactCardView, RatioCardView } from "./cards/FactCardView";

function CardView({ card }: { card: Card }) {
  switch (card.kind) {
    case "fact":
      return <FactCardView card={card} />;
    case "ratio":
      return <RatioCardView card={card} />;
    case "peers":
      return <PeersCardView card={card} />;
    case "risk_diff":
      return <RiskDiffCardView card={card} />;
    case "notice":
      return (
        <p className="rounded-lg border border-dashed border-neutral-300 p-3 text-sm text-neutral-600 dark:border-neutral-700 dark:text-neutral-400">
          {card.message}
        </p>
      );
  }
}

/** The figures of a turn, exactly as the tools returned them. */
export function CardList({ cards }: { cards: Card[] }) {
  if (cards.length === 0) {
    return null;
  }
  return (
    <section aria-label="Figures from the filings" className="grid gap-3 sm:grid-cols-2">
      {cards.map((card) => (
        <div
          key={`${card.call_id}-${card.kind}`}
          className={card.kind === "peers" || card.kind === "risk_diff" ? "sm:col-span-2" : ""}
        >
          <CardView card={card} />
        </div>
      ))}
    </section>
  );
}

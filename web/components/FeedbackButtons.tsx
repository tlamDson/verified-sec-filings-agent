"use client";

import { useState } from "react";
import type { Rating, SendFeedback } from "@/lib/chat/types";

const CHOICES: { rating: Rating; label: string; icon: string }[] = [
  { rating: "up", label: "Helpful", icon: "👍" },
  { rating: "down", label: "Not helpful", icon: "👎" },
];

/** Thumbs up or down on one answered turn. A rating shows as given only once it is saved. */
export function FeedbackButtons({
  threadId,
  turn,
  rate,
}: {
  threadId: string;
  turn: number;
  rate: SendFeedback;
}) {
  const [given, setGiven] = useState<Rating | null>(null);
  const [failed, setFailed] = useState(false);

  async function choose(rating: Rating) {
    setFailed(false);
    if (await rate({ threadId, turn, rating })) {
      setGiven(rating);
    } else {
      setFailed(true);
    }
  }

  return (
    <div className="flex items-center gap-2 text-sm">
      {CHOICES.map(({ rating, label, icon }) => (
        <button
          key={rating}
          type="button"
          aria-label={label}
          aria-pressed={given === rating}
          onClick={() => choose(rating)}
          className="rounded-md border border-neutral-200 px-2 py-1 hover:bg-neutral-100 aria-pressed:border-neutral-900 aria-pressed:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800 dark:aria-pressed:border-neutral-200 dark:aria-pressed:bg-neutral-800"
        >
          <span aria-hidden="true">{icon}</span>
        </button>
      ))}
      {failed && (
        <p role="alert" className="text-xs text-red-700 dark:text-red-400">
          Your feedback was not saved.
        </p>
      )}
    </div>
  );
}

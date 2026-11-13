import { answerSegments } from "@/lib/chat/citations";
import type { Citation } from "@/lib/chat/types";

/** The checked answer, with each citation key replaced by its number in the sources panel. */
export function AnswerText({
  text,
  citations,
  onCite,
}: {
  text: string;
  citations: Citation[];
  onCite: (key: string) => void;
}) {
  const segments = answerSegments(text, citations);
  return (
    <p className="whitespace-pre-wrap leading-relaxed">
      {segments.map((segment, at) =>
        segment.kind === "text" ? (
          // biome-ignore lint/suspicious/noArrayIndexKey: segments of one text never reorder
          <span key={at}>{segment.text}</span>
        ) : (
          <button
            // biome-ignore lint/suspicious/noArrayIndexKey: segments of one text never reorder
            key={at}
            type="button"
            aria-label={`Source ${segment.index}: ${segment.key}`}
            onClick={() => onCite(segment.key)}
            className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-neutral-200 px-1 align-text-top text-xs font-medium hover:bg-neutral-300 dark:bg-neutral-700 dark:hover:bg-neutral-600"
          >
            {segment.index}
          </button>
        ),
      )}
    </p>
  );
}

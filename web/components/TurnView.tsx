import type { Turn } from "@/lib/chat/state";
import type { AnswerEvent, CheckSummary, SendFeedback } from "@/lib/chat/types";
import { AnswerText } from "./AnswerText";
import { CardList } from "./CardList";
import { FeedbackButtons } from "./FeedbackButtons";
import { MetricChart } from "./MetricChart";

/** Turns that ended without the model's answer: what the banner is called. */
const NOTICE_TITLES: Partial<Record<AnswerEvent["status"], string>> = {
  degraded: "Degraded mode",
  blocked: "Answer withheld",
  step_limit: "No answer written",
};

function Notice({ title, text }: { title: string; text: string }) {
  return (
    <div
      role="status"
      aria-label={title}
      className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
    >
      <p className="font-medium">{title}</p>
      <p className="mt-1">{text}</p>
    </div>
  );
}

function CheckLine({ check }: { check: CheckSummary }) {
  const removed =
    check.removed === 1
      ? "1 statement removed because it could not be traced"
      : `${check.removed} statements removed because they could not be traced`;
  return (
    <div className="text-xs text-neutral-500">
      {check.figures > 0 && (
        <p>
          {check.traced} of {check.figures} figures traced to the filings
        </p>
      )}
      {check.verdict === "trimmed" && check.removed > 0 && <p>{removed}</p>}
    </div>
  );
}

/** One question and everything shown for it: text, figures, charts, feedback. */
export function TurnView({
  turn,
  threadId,
  onCite,
  rate,
}: {
  turn: Turn;
  threadId: string;
  onCite: (key: string) => void;
  rate: SendFeedback;
}) {
  const { answer } = turn;
  const noticeTitle = answer === null ? undefined : NOTICE_TITLES[answer.status];
  return (
    <section className="space-y-4">
      <h3 className="text-base font-semibold">{turn.question}</h3>
      {turn.phase === "pending" && (
        <p role="status" aria-label="Working" className="animate-pulse text-sm text-neutral-500">
          Looking up the filings…
        </p>
      )}
      {answer !== null &&
        (noticeTitle !== undefined ? (
          <Notice title={noticeTitle} text={answer.text} />
        ) : (
          <AnswerText text={answer.text} citations={turn.citations} onCite={onCite} />
        ))}
      {answer?.check != null && answer.status === "answered" && <CheckLine check={answer.check} />}
      <CardList cards={turn.cards} />
      {turn.charts.map((chart) => (
        <MetricChart key={`${chart.kind}-${chart.title}-${chart.unit}`} chart={chart} />
      ))}
      {turn.phase === "failed" && turn.error !== null && (
        <p
          role="alert"
          className="rounded-lg border border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-200"
        >
          {turn.error.message}
        </p>
      )}
      {turn.phase === "done" && answer !== null && (
        <FeedbackButtons threadId={threadId} turn={answer.turn} rate={rate} />
      )}
    </section>
  );
}

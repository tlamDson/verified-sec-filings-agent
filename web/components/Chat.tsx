"use client";

import { type FormEvent, type KeyboardEvent, useReducer, useState } from "react";
import { chatReducer, initialChat } from "@/lib/chat/state";
import type { Cohort, SendFeedback, SendQuestion, Usage } from "@/lib/chat/types";
import { CitationPanel } from "./CitationPanel";
import { TurnView } from "./TurnView";

const EXAMPLES = [
  "What was Apple's revenue in fiscal 2024?",
  "NVDA vs AMD gross margin over the last 3 years",
  "What new risks did Microsoft add in its latest 10-K?",
];

/** The chat page: questions on the left, the sources of the turn in focus on the right. */
export function Chat({
  threadId,
  cohort,
  send,
  rate,
  initialUsage = null,
  onSignOut,
}: {
  threadId: string;
  cohort: Cohort;
  send: SendQuestion;
  rate: SendFeedback;
  initialUsage?: Usage | null;
  onSignOut?: () => void;
}) {
  const [state, dispatch] = useReducer(chatReducer, initialChat(threadId, initialUsage));
  const [question, setQuestion] = useState("");
  const [focus, setFocus] = useState<{ turn: number; key: string } | null>(null);
  const closed = state.busy || state.limit !== null;

  async function ask(text: string) {
    const trimmed = text.trim();
    if (trimmed === "" || closed) {
      return;
    }
    setQuestion("");
    setFocus(null);
    dispatch({ type: "asked", question: trimmed });
    for await (const event of send(trimmed, threadId)) {
      dispatch(event);
    }
    dispatch({ type: "ended" });
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(question);
  }

  function submitOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void ask(question);
    }
  }

  const shown = state.turns.find((turn) => turn.id === focus?.turn) ?? state.turns.at(-1);
  return (
    <div className="mx-auto grid min-h-screen max-w-6xl gap-8 px-4 py-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <main className="flex min-w-0 flex-col gap-6">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-lg font-semibold">Verified SEC Filings Research Agent</h1>
          <div className="flex items-center gap-3 text-xs text-neutral-500">
            {cohort === "simulated" && (
              <span className="rounded-full border border-neutral-300 px-2 py-0.5 dark:border-neutral-700">
                Simulated test account
              </span>
            )}
            {state.usage !== null && (
              <span>
                {state.usage.used} of {state.usage.limit} questions today
              </span>
            )}
            {onSignOut !== undefined && (
              <button type="button" onClick={onSignOut} className="underline underline-offset-2">
                Sign out
              </button>
            )}
          </div>
        </header>

        <div className="flex flex-1 flex-col gap-8">
          {state.turns.length === 0 && (
            <ul className="space-y-2 text-sm text-neutral-600 dark:text-neutral-400">
              {EXAMPLES.map((example) => (
                <li key={example}>
                  <button
                    type="button"
                    onClick={() => setQuestion(example)}
                    className="text-left underline decoration-neutral-300 underline-offset-2 hover:decoration-current"
                  >
                    {example}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {state.turns.map((turn) => (
            <TurnView
              key={turn.id}
              turn={turn}
              threadId={threadId}
              rate={rate}
              onCite={(key) => setFocus({ turn: turn.id, key })}
            />
          ))}
        </div>

        <form onSubmit={submit} className="sticky bottom-0 space-y-2 bg-inherit pb-2">
          {state.limit !== null && (
            <p className="rounded-lg border border-neutral-300 p-3 text-sm dark:border-neutral-700">
              {state.limit.message}
            </p>
          )}
          <div className="flex items-end gap-2">
            <textarea
              aria-label="Your question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={submitOnEnter}
              rows={2}
              maxLength={2000}
              placeholder="Ask about a company's 10-K or 10-Q"
              className="min-h-12 flex-1 resize-none rounded-lg border border-neutral-300 bg-transparent p-3 text-sm outline-none focus:border-neutral-900 dark:border-neutral-700 dark:focus:border-neutral-200"
            />
            <button
              type="submit"
              disabled={closed}
              className="rounded-lg bg-neutral-900 px-4 py-3 text-sm font-medium text-white disabled:opacity-40 dark:bg-neutral-100 dark:text-neutral-900"
            >
              Ask
            </button>
          </div>
          <p className="text-xs text-neutral-500">
            Every figure comes from an SEC filing through a deterministic tool. Not investment
            advice.
          </p>
        </form>
      </main>
      <div className="lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:overflow-y-auto">
        <CitationPanel citations={shown?.citations ?? []} active={focus?.key ?? null} />
      </div>
    </div>
  );
}

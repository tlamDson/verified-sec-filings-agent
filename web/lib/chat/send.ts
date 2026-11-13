// The browser's two calls to this app's own routes: ask a question, rate a turn. Neither
// throws: a refusal or a network failure becomes an error event, or `false`.

import { readSse, toChatEvent } from "./sse";
import type { ChatEvent, ErrorEvent, FeedbackRequest } from "./types";

type Fetch = (url: string, init?: RequestInit) => Promise<Response>;

const JSON_HEADERS = { "content-type": "application/json" };

/** The user's own calendar date, which relative periods in a question anchor on. */
function localDate(now: Date): string {
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

async function refusal(response: Response): Promise<ErrorEvent> {
  try {
    const body: unknown = await response.json();
    const error = (body as { error?: Partial<ErrorEvent> } | null)?.error;
    if (typeof error?.code === "string" && typeof error.message === "string") {
      return error as ErrorEvent;
    }
  } catch {
    // not JSON: fall through to the status
  }
  return {
    code: `http_${response.status}`,
    message: `The service answered with an error (${response.status}).`,
  };
}

export async function* sendQuestion(
  question: string,
  threadId: string,
  options: { fetchImpl?: Fetch; today?: Date } = {},
): AsyncGenerator<ChatEvent> {
  const fetchImpl = options.fetchImpl ?? fetch;
  let response: Response;
  try {
    response = await fetchImpl("/api/chat", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({
        thread_id: threadId,
        question,
        asked_on: localDate(options.today ?? new Date()),
      }),
    });
  } catch {
    yield { type: "error", data: { code: "network", message: "The service cannot be reached." } };
    return;
  }
  if (!response.ok || response.body === null) {
    yield { type: "error", data: await refusal(response) };
    return;
  }
  try {
    for await (const message of readSse(response.body)) {
      const event = toChatEvent(message);
      if (event !== null) {
        yield event;
      }
    }
  } catch {
    yield { type: "error", data: { code: "network", message: "The connection was lost." } };
  }
}

export async function sendFeedback(
  feedback: FeedbackRequest,
  fetchImpl: Fetch = fetch,
): Promise<boolean> {
  try {
    const response = await fetchImpl("/api/feedback", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({
        thread_id: feedback.threadId,
        turn: feedback.turn,
        rating: feedback.rating,
      }),
    });
    return response.ok;
  } catch {
    return false;
  }
}

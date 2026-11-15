// @vitest-environment node
import { describe, expect, it } from "vitest";
import { sendFeedback, sendQuestion } from "@/lib/chat/send";
import type { ChatEvent } from "@/lib/chat/types";
import { answer, THREAD, usage } from "./fixtures";

// No network: `fetchImpl` is a stand-in that records the request and plays a response.
function recording(response: Response | Error) {
  const seen: { url: string; init: RequestInit }[] = [];
  const fetchImpl = async (url: string | URL | Request, init?: RequestInit) => {
    seen.push({ url: String(url), init: init ?? {} });
    if (response instanceof Error) {
      throw response;
    }
    return response;
  };
  return { fetchImpl, seen };
}

async function collect(events: AsyncIterable<ChatEvent>): Promise<ChatEvent[]> {
  const all: ChatEvent[] = [];
  for await (const event of events) {
    all.push(event);
  }
  return all;
}

function sse(...events: [string, unknown][]): Response {
  const body = events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`);
  return new Response(body.join(""), { headers: { "content-type": "text/event-stream" } });
}

describe("sendQuestion", () => {
  it("posts the question with its thread and the user's own date", async () => {
    const { fetchImpl, seen } = recording(sse());
    const today = new Date(2026, 10, 13, 23, 30); // local time, late evening
    await collect(sendQuestion("Apple revenue?", THREAD, { fetchImpl, today }));
    expect(seen[0]?.url).toBe("/api/chat");
    expect(seen[0]?.init.method).toBe("POST");
    expect(JSON.parse(String(seen[0]?.init.body))).toEqual({
      thread_id: THREAD,
      question: "Apple revenue?",
      asked_on: "2026-11-13",
    });
  });

  it("yields the events of the stream in order", async () => {
    const turn = { thread_id: THREAD, cohort: "real", usage };
    const { fetchImpl } = recording(sse(["turn", turn], ["ping", {}], ["answer", answer]));
    expect(await collect(sendQuestion("Apple revenue?", THREAD, { fetchImpl }))).toEqual([
      { type: "turn", data: turn },
      { type: "answer", data: answer },
    ]);
  });

  it("turns a refusal into one error event with what the API said", async () => {
    const refusal = { code: "daily_limit", message: "2 of 2", limit: 2, resets_at: "2026-11-14" };
    const { fetchImpl } = recording(
      new Response(JSON.stringify({ error: refusal }), {
        status: 429,
        headers: { "content-type": "application/json" },
      }),
    );
    expect(await collect(sendQuestion("One more?", THREAD, { fetchImpl }))).toEqual([
      { type: "error", data: refusal },
    ]);
  });

  it("turns a refusal that is not JSON into an error event with the status", async () => {
    const { fetchImpl } = recording(new Response("<html>Bad gateway</html>", { status: 502 }));
    const [event] = await collect(sendQuestion("Anyone there?", THREAD, { fetchImpl }));
    expect(event).toEqual({
      type: "error",
      data: { code: "http_502", message: "The service answered with an error (502)." },
    });
  });

  it("turns a network failure into an error event", async () => {
    const { fetchImpl } = recording(new TypeError("Failed to fetch"));
    const [event] = await collect(sendQuestion("Anyone there?", THREAD, { fetchImpl }));
    expect(event?.type).toBe("error");
    expect(event?.type === "error" && event.data.code).toBe("network");
  });
});

describe("sendFeedback", () => {
  it("posts the rating of one turn and says whether it was kept", async () => {
    const { fetchImpl, seen } = recording(new Response(null, { status: 204 }));
    expect(await sendFeedback({ threadId: THREAD, turn: 2, rating: "down" }, fetchImpl)).toBe(true);
    expect(seen[0]?.url).toBe("/api/feedback");
    expect(JSON.parse(String(seen[0]?.init.body))).toEqual({
      thread_id: THREAD,
      turn: 2,
      rating: "down",
    });
  });

  it("says so when the rating was not kept", async () => {
    const refused = recording(new Response("{}", { status: 404 }));
    expect(await sendFeedback({ threadId: THREAD, turn: 9, rating: "up" }, refused.fetchImpl)).toBe(
      false,
    );
    const offline = recording(new TypeError("Failed to fetch"));
    expect(await sendFeedback({ threadId: THREAD, turn: 1, rating: "up" }, offline.fetchImpl)).toBe(
      false,
    );
  });
});

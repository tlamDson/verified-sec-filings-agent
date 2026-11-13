// @vitest-environment node
import { describe, expect, it } from "vitest";
import { createSseParser, readSse, toChatEvent } from "@/lib/chat/sse";
import { answer, usage } from "./fixtures";

function stream(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

async function collect(body: ReadableStream<Uint8Array>) {
  const messages = [];
  for await (const message of readSse(body)) {
    messages.push(message);
  }
  return messages;
}

describe("createSseParser", () => {
  it("returns each complete event and keeps the rest for the next chunk", () => {
    const parser = createSseParser();
    expect(parser.push('event: turn\ndata: {"a"')).toEqual([]);
    expect(parser.push(":1}\n\nevent: answer\n")).toEqual([{ event: "turn", data: '{"a":1}' }]);
    expect(parser.push("data: {}\n\n")).toEqual([{ event: "answer", data: "{}" }]);
  });

  it("reads several events from one chunk", () => {
    const parser = createSseParser();
    expect(parser.push("event: a\ndata: 1\n\nevent: b\ndata: 2\n\n")).toEqual([
      { event: "a", data: "1" },
      { event: "b", data: "2" },
    ]);
  });

  it("accepts CRLF line ends, comments and a missing event name", () => {
    const parser = createSseParser();
    expect(parser.push(": keep-alive\r\n\r\nevent: a\r\ndata: 1\r\n\r\ndata: 2\n\n")).toEqual([
      { event: "a", data: "1" },
      { event: "message", data: "2" },
    ]);
  });

  it("joins the data lines of one event", () => {
    expect(createSseParser().push("event: a\ndata: one\ndata: two\n\n")).toEqual([
      { event: "a", data: "one\ntwo" },
    ]);
  });
});

describe("readSse", () => {
  it("reads events across chunk borders, even inside a multi-byte character", async () => {
    const bytes = new TextEncoder().encode('event: answer\ndata: {"text":"Mondelēz"}\n\n');
    const cut = bytes.indexOf(0xc4) + 1; // between the two bytes of "ē"
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, cut));
        controller.enqueue(bytes.slice(cut));
        controller.close();
      },
    });
    expect(await collect(body)).toEqual([{ event: "answer", data: '{"text":"Mondelēz"}' }]);
  });

  it("drops an event the stream ended in the middle of", async () => {
    const messages = await collect(stream("event: turn\ndata: {}\n\n", "event: answer\ndata: {"));
    expect(messages).toEqual([{ event: "turn", data: "{}" }]);
  });
});

describe("toChatEvent", () => {
  it("types the events of a turn", () => {
    const turn = { thread_id: "thread-0001", cohort: "real", usage };
    expect(toChatEvent({ event: "turn", data: JSON.stringify(turn) })).toEqual({
      type: "turn",
      data: turn,
    });
    expect(toChatEvent({ event: "answer", data: JSON.stringify(answer) })).toEqual({
      type: "answer",
      data: answer,
    });
  });

  it("ignores an event it does not know and data that is not JSON", () => {
    expect(toChatEvent({ event: "ping", data: "{}" })).toBeNull();
    expect(toChatEvent({ event: "answer", data: "{not json" })).toBeNull();
    expect(toChatEvent({ event: "answer", data: "[]" })).toBeNull();
  });
});

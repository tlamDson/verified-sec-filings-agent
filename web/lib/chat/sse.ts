// Server-sent events, read from a fetch body. The parser is pure: push text, get the
// events it completed; whatever is left waits for the next chunk.

import type { ChatEvent } from "./types";

export interface SseMessage {
  event: string;
  data: string;
}

const EVENT_TYPES = new Set(["turn", "evidence", "answer", "error"]);

function parseBlock(block: string): SseMessage | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith(":")) {
      continue; // a comment, sent to keep the connection open
    }
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "event") {
      event = value;
    } else if (field === "data") {
      data.push(value);
    }
  }
  return data.length === 0 ? null : { event, data: data.join("\n") };
}

export function createSseParser(): { push(chunk: string): SseMessage[] } {
  let buffer = "";
  return {
    push(chunk) {
      buffer = (buffer + chunk).replace(/\r\n?/g, "\n");
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      return blocks.map(parseBlock).filter((message) => message !== null);
    },
  };
}

/** The events of a response body. An event cut off by the end of the stream is dropped. */
export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseMessage> {
  const parser = createSseParser();
  const decoder = new TextDecoder();
  const reader = body.getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        return;
      }
      yield* parser.push(decoder.decode(value, { stream: true }));
    }
  } finally {
    reader.releaseLock();
  }
}

/** The typed event of a message, or null for an event this app does not know. */
export function toChatEvent(message: SseMessage): ChatEvent | null {
  if (!EVENT_TYPES.has(message.event)) {
    return null;
  }
  let data: unknown;
  try {
    data = JSON.parse(message.data);
  } catch {
    return null;
  }
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    return null;
  }
  return { type: message.event, data } as ChatEvent;
}

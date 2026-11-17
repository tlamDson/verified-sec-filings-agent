// @vitest-environment node
import { describe, expect, it } from "vitest";
import { type ChatAction, type ChatState, chatReducer, initialChat } from "@/lib/chat/state";
import type { ChatEvent } from "@/lib/chat/types";
import {
  answer,
  answeredTurn,
  degradedAnswer,
  filingCitation,
  revenue,
  THREAD,
  usage,
} from "./fixtures";

function run(state: ChatState, ...actions: ChatAction[]): ChatState {
  return actions.reduce(chatReducer, state);
}

const asked: ChatAction = { type: "asked", question: "Apple revenue 2024?" };
const [turnEvent, evidenceEvent] = answeredTurn as [ChatEvent, ChatEvent, ChatEvent];

describe("chatReducer", () => {
  it("starts empty, on its thread, able to ask", () => {
    expect(initialChat(THREAD, usage)).toEqual({
      threadId: THREAD,
      turns: [],
      usage,
      busy: false,
      limit: null,
    });
  });

  it("shows the question at once and waits for the answer", () => {
    const state = run(initialChat(THREAD), asked);
    expect(state.busy).toBe(true);
    expect(state.turns).toEqual([
      {
        id: 1,
        question: "Apple revenue 2024?",
        phase: "pending",
        cards: [],
        citations: [],
        charts: [],
        answer: null,
        error: null,
      },
    ]);
  });

  it("updates the usage when the turn starts", () => {
    const state = run(initialChat(THREAD), asked, turnEvent);
    expect(state.usage).toEqual(usage);
    expect(state.turns[0]?.phase).toBe("pending");
  });

  it("shows cards as their evidence arrives, before the answer", () => {
    const turn = run(initialChat(THREAD), asked, turnEvent, evidenceEvent).turns[0];
    expect(turn?.cards).toEqual([revenue]);
    expect(turn?.citations).toEqual([filingCitation]);
    expect(turn?.phase).toBe("pending");
  });

  it("adds later evidence without repeating a citation already listed", () => {
    const more: ChatEvent = {
      type: "evidence",
      data: { cards: [{ ...revenue, call_id: "c2" }], citations: [filingCitation] },
    };
    const turn = run(initialChat(THREAD), asked, evidenceEvent, more).turns[0];
    expect(turn?.cards.map((card) => card.call_id)).toEqual(["c1", "c2"]);
    expect(turn?.citations).toEqual([filingCitation]);
  });

  it("ends the turn with the answer, which carries the final cards and charts", () => {
    const state = run(initialChat(THREAD), asked, ...answeredTurn);
    expect(state.busy).toBe(false);
    expect(state.turns[0]).toMatchObject({
      phase: "done",
      answer,
      cards: answer.cards,
      citations: answer.citations,
      charts: answer.charts,
    });
  });

  it("keeps a degraded answer as an answer, not as a failure", () => {
    const state = run(initialChat(THREAD), asked, turnEvent, {
      type: "answer",
      data: degradedAnswer,
    });
    expect(state.turns[0]?.phase).toBe("done");
    expect(state.turns[0]?.answer?.degraded).toBe(true);
    expect(state.turns[0]?.error).toBeNull();
  });

  it("marks the turn failed on an error event and lets the user ask again", () => {
    const error = { code: "conversation_conflict", message: "Reload and ask again." };
    const state = run(initialChat(THREAD), asked, { type: "error", data: error });
    expect(state.busy).toBe(false);
    expect(state.turns[0]).toMatchObject({ phase: "failed", error });
  });

  it("marks a stream that ended without an answer as failed, keeping its cards", () => {
    const state = run(initialChat(THREAD), asked, evidenceEvent, { type: "ended" });
    expect(state.busy).toBe(false);
    expect(state.turns[0]?.phase).toBe("failed");
    expect(state.turns[0]?.error?.code).toBe("stream_ended");
    expect(state.turns[0]?.cards).toEqual([revenue]);
  });

  it("leaves a finished turn alone when the stream ends", () => {
    const done = run(initialChat(THREAD), asked, ...answeredTurn);
    expect(run(done, { type: "ended" })).toEqual(done);
  });

  it("remembers that the daily limit was reached", () => {
    const refusal = {
      code: "daily_limit",
      message: "You have asked 20 of 20 questions today. The count resets at 00:00 UTC.",
      limit: 20,
      resets_at: "2026-11-14T00:00:00Z",
    };
    const state = run(initialChat(THREAD, usage), asked, { type: "error", data: refusal });
    expect(state.limit).toEqual({ message: refusal.message, resetsAt: refusal.resets_at });
    expect(state.usage).toEqual({ used: 20, limit: 20, resets_at: refusal.resets_at });
    expect(state.turns[0]?.phase).toBe("failed");
    expect(state.busy).toBe(false);
  });

  describe("after a daily-limit refusal", () => {
    const refusal = {
      code: "daily_limit",
      message: "You have asked 20 of 20 questions today. The count resets at 00:00 UTC.",
      limit: 20,
      resets_at: "2026-11-14T00:00:00Z",
    };
    const refused = () => run(initialChat(THREAD, usage), asked, { type: "error", data: refusal });
    const resets = Date.parse(refusal.resets_at);

    it("keeps the refusal before the reset time", () => {
      const state = run(refused(), { type: "clock", now: resets - 1 });
      expect(state.limit).not.toBeNull();
      expect(state.usage?.used).toBe(20);
    });

    it("clears the refusal and the spent count once the reset time has passed", () => {
      const state = run(refused(), { type: "clock", now: resets });
      expect(state.limit).toBeNull();
      expect(state.usage).toBeNull();
      expect(state.turns).toEqual(refused().turns);
    });

    it("clears the refusal when a turn reports quota left", () => {
      const fresh = { used: 1, limit: 20, resets_at: "2026-11-15T00:00:00Z" };
      const state = run(refused(), {
        type: "turn",
        data: { ...turnEvent.data, usage: fresh },
      } as ChatAction);
      expect(state.limit).toBeNull();
      expect(state.usage).toEqual(fresh);
    });

    it("keeps the refusal when the usage shown still has no quota left", () => {
      const spent = { used: 20, limit: 20, resets_at: refusal.resets_at };
      const state = run(refused(), {
        type: "turn",
        data: { ...turnEvent.data, usage: spent },
      } as ChatAction);
      expect(state.limit).not.toBeNull();
    });

    it("ignores the clock when no refusal is held", () => {
      const state = initialChat(THREAD, usage);
      expect(run(state, { type: "clock", now: resets })).toEqual(state);
    });

    it("keeps a refusal whose reset time is unknown", () => {
      const state = run(
        initialChat(THREAD),
        asked,
        { type: "error", data: { code: "daily_limit", message: "Limit." } },
        { type: "clock", now: 0 },
      );
      expect(state.limit).not.toBeNull();
    });
  });

  it("numbers the turns of a conversation and only changes the one in flight", () => {
    const first = run(initialChat(THREAD), asked, ...answeredTurn);
    const second = run(first, { type: "asked", question: "And net income?" });
    expect(second.turns.map((turn) => [turn.id, turn.phase])).toEqual([
      [1, "done"],
      [2, "pending"],
    ]);
    expect(second.turns[0]).toBe(first.turns[0]);
  });

  it("ignores a question asked while another is in flight", () => {
    const state = run(initialChat(THREAD), asked);
    expect(run(state, { type: "asked", question: "Too soon?" })).toBe(state);
  });
});

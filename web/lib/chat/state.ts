// The chat as the page shows it, and how each event of a turn changes it. Pure: the
// component dispatches what happened, this decides what is shown.

import type {
  AnswerEvent,
  Card,
  Chart,
  ChatEvent,
  Citation,
  ErrorEvent,
  EvidenceEvent,
  Usage,
} from "./types";

export interface Turn {
  /** The turn's number in this page's conversation, from 1. */
  id: number;
  question: string;
  phase: "pending" | "done" | "failed";
  cards: Card[];
  citations: Citation[];
  charts: Chart[];
  answer: AnswerEvent | null;
  error: ErrorEvent | null;
}

export interface ChatState {
  threadId: string;
  turns: Turn[];
  usage: Usage | null;
  /** A question is in flight; another cannot be asked yet. */
  busy: boolean;
  /** Set once the API refused a question for the daily limit. */
  limit: { message: string; resetsAt: string } | null;
}

export type ChatAction =
  | ChatEvent
  | { type: "asked"; question: string }
  | { type: "ended" }
  /** The time now in milliseconds since the epoch; lets a held daily-limit refusal lapse. */
  | { type: "clock"; now: number };

const STREAM_ENDED: ErrorEvent = {
  code: "stream_ended",
  message: "The connection closed before the answer arrived. Please ask again.",
};

export function initialChat(threadId: string, usage: Usage | null = null): ChatState {
  return { threadId, turns: [], usage, busy: false, limit: null };
}

/** The state with its turn in flight replaced; unchanged when none is in flight. */
function updatePending(state: ChatState, change: (turn: Turn) => Turn): ChatState {
  const last = state.turns.at(-1);
  if (last === undefined || last.phase !== "pending") {
    return state;
  }
  return { ...state, turns: [...state.turns.slice(0, -1), change(last)] };
}

function withEvidence(turn: Turn, evidence: EvidenceEvent): Turn {
  const known = new Set(turn.citations.map((citation) => citation.key));
  const fresh = evidence.citations.filter((citation) => !known.has(citation.key));
  return {
    ...turn,
    cards: [...turn.cards, ...evidence.cards],
    citations: [...turn.citations, ...fresh],
  };
}

function withAnswer(turn: Turn, answer: AnswerEvent): Turn {
  return {
    ...turn,
    phase: "done",
    answer,
    cards: answer.cards,
    citations: answer.citations,
    charts: answer.charts,
  };
}

function failed(state: ChatState, error: ErrorEvent): ChatState {
  const next = updatePending(state, (turn) => ({ ...turn, phase: "failed", error }));
  if (error.code !== "daily_limit") {
    return { ...next, busy: false };
  }
  const resetsAt = error.resets_at ?? state.usage?.resets_at ?? "";
  const limit = error.limit ?? state.usage?.limit ?? 0;
  return {
    ...next,
    busy: false,
    limit: { message: error.message, resetsAt },
    usage: { used: limit, limit, resets_at: resetsAt },
  };
}

/** The state with its daily-limit refusal dropped once its reset time has passed. */
function lapsed(state: ChatState, now: number): ChatState {
  if (state.limit === null || !(Date.parse(state.limit.resetsAt) <= now)) {
    return state;
  }
  return { ...state, limit: null, usage: null };
}

/** A turn's usage replaces the shown one; a refusal is dropped when it shows quota left. */
function withUsage(state: ChatState, usage: Usage): ChatState {
  return { ...state, usage, limit: usage.used < usage.limit ? null : state.limit };
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "asked": {
      if (state.busy) {
        return state;
      }
      const turn: Turn = {
        id: state.turns.length + 1,
        question: action.question,
        phase: "pending",
        cards: [],
        citations: [],
        charts: [],
        answer: null,
        error: null,
      };
      return { ...state, busy: true, turns: [...state.turns, turn] };
    }
    case "turn":
      return withUsage(state, action.data.usage);
    case "evidence":
      return updatePending(state, (turn) => withEvidence(turn, action.data));
    case "answer":
      return { ...updatePending(state, (turn) => withAnswer(turn, action.data)), busy: false };
    case "error":
      return failed(state, action.data);
    case "clock":
      return lapsed(state, action.now);
    case "ended":
      return state.turns.at(-1)?.phase === "pending" ? failed(state, STREAM_ENDED) : state;
  }
}

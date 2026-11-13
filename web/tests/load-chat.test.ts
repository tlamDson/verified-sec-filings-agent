// @vitest-environment node
// Runs `infra/load/chat.js` (the k6 load script, s-20) against stub k6 modules, so the turn
// accounting is checked by behaviour, not by grepping the script: a turn that does not end
// with an `answer` event is a failed turn, and a conversation whose first turn failed still
// tries to resume on the same thread and is counted in the recovery metrics.
import path from "node:path";
import { beforeAll, beforeEach, expect, it, vi } from "vitest";

type Reply = { status: number; body: string };
type Post = { thread_id: string; question: string };

const k6 = vi.hoisted(() => {
  const samples: Record<string, unknown[]> = {};
  const posts: { thread_id: string; question: string }[] = [];
  const replies: { status: number; body: string }[] = [];
  class Metric {
    readonly name: string;
    constructor(name: string) {
      this.name = name;
      samples[name] = [];
    }
    add(value: unknown) {
      samples[this.name]?.push(value);
    }
  }
  return { samples, posts, replies, Metric };
});

vi.mock("k6", () => ({ check: () => true, sleep: () => undefined }));
vi.mock("k6/crypto", () => ({ default: { hmac: () => "signature" } }));
vi.mock("k6/encoding", () => ({ default: { b64encode: (text: string) => text } }));
vi.mock("k6/metrics", () => ({ Counter: k6.Metric, Rate: k6.Metric, Trend: k6.Metric }));
vi.mock("k6/http", () => ({
  default: {
    post: (_url: string, body: string) => {
      k6.posts.push(JSON.parse(body) as Post);
      const reply = k6.replies.shift();
      if (reply === undefined) throw new Error("the script asked more turns than the test set");
      return reply;
    },
  },
}));

const ANSWERED: Reply = {
  status: 200,
  body: 'event: token\ndata: {"text":"ok"}\n\nevent: answer\ndata: {"status":"answered"}\n\n',
};
const DEGRADED: Reply = {
  status: 200,
  body: 'event: answer\ndata: {"status":"degraded"}\n\n',
};
const REFUSED: Reply = { status: 502, body: "" };
const ERRORED: Reply = { status: 200, body: 'event: error\ndata: {"reason":"internal"}\n\n' };
const DROPPED: Reply = { status: 200, body: 'event: token\ndata: {"text":"o"}\n\n' };

let conversation: () => void;

beforeAll(async () => {
  Object.assign(globalThis, {
    __ENV: { API_AUTH_SECRET: "test-secret", BASE_URL: "http://lb" },
    __VU: 7,
    __ITER: 0,
  });
  const script = path.resolve(import.meta.dirname, "../../infra/load/chat.js");
  conversation = (await import(/* @vite-ignore */ script)).default;
});

beforeEach(() => {
  for (const name of Object.keys(k6.samples)) k6.samples[name] = [];
  k6.posts.length = 0;
  k6.replies.length = 0;
});

function run(...replies: Reply[]) {
  k6.replies.push(...replies);
  conversation();
  expect(k6.replies).toEqual([]);
}

it("counts a turn that ends with an answer as completed", () => {
  run(ANSWERED, DEGRADED);
  expect(k6.samples.turn_failed).toEqual([false, false]);
  expect(k6.samples.turn_answered).toEqual([1]);
  expect(k6.samples.turn_degraded).toEqual([1]);
  expect(k6.samples.turn_ms).toHaveLength(2);
});

it.each([
  ["refused by the load balancer", REFUSED],
  ["ended by an error event", ERRORED],
  ["dropped before the answer", DROPPED],
])("counts a turn %s as failed", (_case, failure) => {
  run(ANSWERED, failure);
  expect(k6.samples.turn_failed).toEqual([false, true]);
  expect(k6.samples.resume_failed).toEqual([true]);
  expect(k6.samples.turn_answered).toEqual([1]);
});

it("resumes a conversation on the same thread after its first turn failed", () => {
  run(REFUSED, ANSWERED);
  expect(k6.posts).toHaveLength(2);
  expect(k6.posts[1]?.thread_id).toBe(k6.posts[0]?.thread_id);
  expect(k6.samples.turn_failed).toEqual([true, false]);
  expect(k6.samples.resume_failed).toEqual([false]);
  expect(k6.samples.interrupted_resume_failed).toEqual([false]);
});

it("counts an interrupted conversation that cannot resume as a failed recovery", () => {
  run(ERRORED, REFUSED);
  expect(k6.samples.turn_failed).toEqual([true, true]);
  expect(k6.samples.resume_failed).toEqual([true]);
  expect(k6.samples.interrupted_resume_failed).toEqual([true]);
});

it("keeps uninterrupted conversations out of the interrupted recovery metric", () => {
  run(ANSWERED, ANSWERED);
  expect(k6.samples.resume_failed).toEqual([false]);
  expect(k6.samples.interrupted_resume_failed).toEqual([]);
});

it("fails the run when turns or recoveries fail too often", async () => {
  const script = path.resolve(import.meta.dirname, "../../infra/load/chat.js");
  const { options } = await import(/* @vite-ignore */ script);
  expect(Object.keys(options.thresholds).sort()).toEqual([
    "interrupted_resume_failed",
    "resume_failed",
    "turn_failed",
  ]);
});

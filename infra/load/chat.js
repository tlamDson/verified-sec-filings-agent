// k6 load on the API replicas behind nginx (s-20). Every request is a simulated account
// (`sim:load-NNN`, cohort `simulated`) asking a simulated model: nothing here is real usage.
//
// Each iteration is one conversation: a first question, then a follow-up on the same
// thread, so a conversation started on one replica continues on whichever replica nginx
// picks next (state lives in Postgres). A turn counts as failed unless its stream ends
// with an `answer` event. The custom metrics below are what `sec-agent chaos load-rows`
// reads from the summary export.
import { check, sleep } from "k6";
import crypto from "k6/crypto";
import encoding from "k6/encoding";
import http from "k6/http";
import { Counter, Rate, Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8080";
const SECRET = __ENV.API_AUTH_SECRET;
const PEAK = Number(__ENV.PEAK_VUS || 200);

const turnFailed = new Rate("turn_failed");
const resumeFailed = new Rate("resume_failed");
const turnMs = new Trend("turn_ms", true);
const turnAnswered = new Counter("turn_answered");
const turnDegraded = new Counter("turn_degraded");

export const options = {
  scenarios: {
    chat: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "1m", target: PEAK },
        { duration: "4m", target: PEAK },
        { duration: "30s", target: 0 },
      ],
      gracefulRampDown: "30s",
    },
  },
  // The thresholds of the plan's chaos check: turns keep succeeding with a replica down.
  thresholds: {
    turn_failed: ["rate<0.05"],
    resume_failed: ["rate<0.05"],
  },
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)"],
};

const QUESTIONS = [
  "What was Apple revenue in fiscal 2024?",
  "What was NVIDIA net income in fiscal 2024?",
  "Compare gross margin of AAPL and MSFT in 2023.",
  "How much cash did Amazon hold at the end of 2023?",
];
const FOLLOW_UP = "And the year before?";

function b64url(text) {
  return encoding.b64encode(text, "rawurl");
}

function token(userId) {
  const now = Math.floor(Date.now() / 1000);
  const header = b64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const claims = b64url(
    JSON.stringify({
      sub: userId,
      cohort: "simulated",
      aud: "sec-agent-api",
      iat: now,
      exp: now + 60,
    }),
  );
  const signature = crypto.hmac("sha256", SECRET, `${header}.${claims}`, "base64rawurl");
  return `${header}.${claims}.${signature}`;
}

// The status of the `answer` event, or null when the stream ended without one.
function answerStatus(body) {
  const marker = "event: answer\ndata: ";
  const at = typeof body === "string" ? body.lastIndexOf(marker) : -1;
  if (at < 0) return null;
  const line = body.slice(at + marker.length).split("\n")[0];
  try {
    return JSON.parse(line).status || null;
  } catch (_error) {
    return null;
  }
}

function ask(userId, threadId, question) {
  const started = Date.now();
  const response = http.post(
    `${BASE_URL}/v1/chat`,
    JSON.stringify({ thread_id: threadId, question: question }),
    {
      headers: {
        Authorization: `Bearer ${token(userId)}`,
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      timeout: "120s",
      tags: { name: "chat" },
    },
  );
  const status = response.status === 200 ? answerStatus(response.body) : null;
  turnMs.add(Date.now() - started);
  turnFailed.add(status === null);
  if (status === "degraded") turnDegraded.add(1);
  if (status === "answered") turnAnswered.add(1);
  check(response, { "turn ends with an answer": () => status !== null });
  return status !== null;
}

export default function () {
  if (!SECRET) throw new Error("set API_AUTH_SECRET");
  const userId = `sim:load-${String(__VU).padStart(3, "0")}`;
  const threadId = `load-${__VU}-${__ITER}-${Date.now()}`;
  const question = QUESTIONS[(__VU + __ITER) % QUESTIONS.length];
  const first = ask(userId, threadId, question);
  sleep(1 + Math.random() * 2);
  if (first) {
    resumeFailed.add(!ask(userId, threadId, FOLLOW_UP));
  }
  sleep(1 + Math.random() * 2);
}

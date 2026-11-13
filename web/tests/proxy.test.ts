// @vitest-environment node
import { describe, expect, it } from "vitest";
import { forwardToApi } from "@/lib/api/proxy";

// The API is never called: `fetchImpl` is a stand-in that records the request. The user
// and the secrets are made up for tests.
const ENV = {
  API_BASE_URL: "http://api.test:8000/",
  API_AUTH_SECRET: "sim-shared-secret-0123456789abcdef0123456789",
};
const USER = { id: "github:42", cohort: "real" } as const;
const NOW_SECONDS = 1794562215;

function recording(response: Response) {
  const seen: { url: string; init: RequestInit }[] = [];
  const fetchImpl = async (url: string | URL | Request, init?: RequestInit) => {
    seen.push({ url: String(url), init: init ?? {} });
    return response;
  };
  return { fetchImpl, seen };
}

function forward(response: Response, overrides: Partial<Parameters<typeof forwardToApi>[0]> = {}) {
  const { fetchImpl, seen } = recording(response);
  const result = forwardToApi({
    identity: USER,
    path: "/v1/chat",
    method: "POST",
    body: JSON.stringify({ thread_id: "thread-0001", question: "A question?" }),
    env: ENV,
    fetchImpl,
    nowSeconds: NOW_SECONDS,
    ...overrides,
  });
  return { result, seen };
}

describe("forwardToApi", () => {
  it("refuses a visitor who is not signed in, without calling the API", async () => {
    const { result, seen } = forward(new Response("unused"), { identity: null });
    const response = await result;
    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({
      error: { code: "unauthorized", message: "Sign in to ask a question." },
    });
    expect(seen).toEqual([]);
  });

  it("calls the API with a short-lived token for the signed-in user", async () => {
    const { result, seen } = forward(new Response("{}", { status: 200 }));
    await result;
    expect(seen).toHaveLength(1);
    expect(seen[0]?.url).toBe("http://api.test:8000/v1/chat");
    expect(seen[0]?.init.method).toBe("POST");
    expect(seen[0]?.init.body).toBe('{"thread_id":"thread-0001","question":"A question?"}');
    const headers = new Headers(seen[0]?.init.headers);
    expect(headers.get("content-type")).toBe("application/json");
    const token = headers.get("authorization")?.replace("Bearer ", "") ?? "";
    const claims = JSON.parse(Buffer.from(token.split(".")[1] ?? "", "base64url").toString());
    expect(claims).toMatchObject({ sub: "github:42", cohort: "real", exp: NOW_SECONDS + 60 });
  });

  it("passes the event stream through as it arrives", async () => {
    const upstream = new Response("event: turn\ndata: {}\n\n", {
      status: 200,
      headers: { "content-type": "text/event-stream; charset=utf-8", "x-internal": "hidden" },
    });
    const response = await forward(upstream).result;
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("text/event-stream; charset=utf-8");
    expect(response.headers.get("cache-control")).toBe("no-cache, no-transform");
    expect(response.headers.get("x-internal")).toBeNull();
    expect(await response.text()).toBe("event: turn\ndata: {}\n\n");
  });

  it("passes a refusal through with its status and retry time", async () => {
    const body = JSON.stringify({ error: { code: "daily_limit", message: "2 of 2", limit: 2 } });
    const upstream = new Response(body, {
      status: 429,
      headers: { "content-type": "application/json", "retry-after": "52185" },
    });
    const response = await forward(upstream).result;
    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("52185");
    expect((await response.json()).error.code).toBe("daily_limit");
  });

  it("passes an empty success through", async () => {
    const response = await forward(new Response(null, { status: 204 })).result;
    expect(response.status).toBe(204);
    expect(await response.text()).toBe("");
  });

  it("answers 502 when the API cannot be reached, without leaking why", async () => {
    const result = forwardToApi({
      identity: USER,
      path: "/v1/me",
      method: "GET",
      env: ENV,
      fetchImpl: async () => {
        throw new Error("connect ECONNREFUSED 10.0.0.7:8000");
      },
      nowSeconds: NOW_SECONDS,
    });
    const response = await result;
    expect(response.status).toBe(502);
    const error = (await response.json()).error;
    expect(error.code).toBe("api_unreachable");
    expect(JSON.stringify(error)).not.toContain("10.0.0.7");
  });

  it("answers 500 when the web app is not configured, naming the variable only", async () => {
    const { result, seen } = forward(new Response("unused"), {
      env: { API_BASE_URL: ENV.API_BASE_URL },
    });
    const response = await result;
    expect(response.status).toBe(500);
    expect((await response.json()).error).toEqual({
      code: "not_configured",
      message: "The web app is missing API_AUTH_SECRET.",
    });
    expect(seen).toEqual([]);
  });
});

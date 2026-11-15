// forwardToApi: one call from this app's server to the API, on behalf of the signed-in
// user. The browser never holds the API's secret or address. The API's answer is passed
// through as it arrives (a turn is an event stream), with only the headers the browser
// needs. Server only.

import type { ApiIdentity } from "@/lib/auth/identity";
import { signApiToken } from "./token";

type Fetch = (url: string, init?: RequestInit) => Promise<Response>;

export interface ForwardRequest {
  /** Who is asking; null when the visitor is not signed in. */
  identity: ApiIdentity | null;
  path: string;
  method: "GET" | "POST";
  body?: string;
  env: Record<string, string | undefined>;
  fetchImpl?: Fetch;
  nowSeconds?: number;
}

const PASSED_HEADERS = ["content-type", "retry-after"];
const MIN_SECRET_CHARS = 32;

function refuse(status: number, code: string, message: string): Response {
  return Response.json({ error: { code, message } }, { status });
}

export async function forwardToApi(request: ForwardRequest): Promise<Response> {
  if (request.identity === null) {
    return refuse(401, "unauthorized", "Sign in to ask a question.");
  }
  const secret = request.env.API_AUTH_SECRET?.trim() ?? "";
  if (secret.length < MIN_SECRET_CHARS) {
    return refuse(500, "not_configured", "The web app is missing API_AUTH_SECRET.");
  }
  const base = request.env.API_BASE_URL?.trim() ?? "";
  if (base === "") {
    return refuse(500, "not_configured", "The web app is missing API_BASE_URL.");
  }
  const nowSeconds = request.nowSeconds ?? Math.floor(Date.now() / 1000);
  const headers: Record<string, string> = {
    authorization: `Bearer ${signApiToken(request.identity, secret, nowSeconds)}`,
  };
  if (request.body !== undefined) {
    headers["content-type"] = "application/json";
  }
  let upstream: Response;
  try {
    upstream = await (request.fetchImpl ?? fetch)(`${base.replace(/\/+$/, "")}${request.path}`, {
      method: request.method,
      headers,
      body: request.body,
      cache: "no-store",
    });
  } catch {
    return refuse(502, "api_unreachable", "The research service cannot be reached right now.");
  }
  const passed = new Headers({ "cache-control": "no-cache, no-transform" });
  for (const name of PASSED_HEADERS) {
    const value = upstream.headers.get(name);
    if (value !== null) {
      passed.set(name, value);
    }
  }
  return new Response(upstream.body, { status: upstream.status, headers: passed });
}

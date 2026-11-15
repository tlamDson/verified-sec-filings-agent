// The identity token this app's server signs for each call to the API: a compact HS256
// token (header.claims.signature) naming the user, the cohort and the API, valid for one
// minute. `sec_agent.api.identity` verifies it with the same secret. Server only.

import { createHmac } from "node:crypto";
import type { ApiIdentity } from "@/lib/auth/identity";

export const API_AUDIENCE = "sec-agent-api";
export const TOKEN_TTL_SECONDS = 60;
const MIN_SECRET_CHARS = 32;

function base64url(text: string): string {
  return Buffer.from(text, "utf-8").toString("base64url");
}

export function signApiToken(identity: ApiIdentity, secret: string, nowSeconds: number): string {
  if (secret.length < MIN_SECRET_CHARS) {
    throw new Error(`API_AUTH_SECRET must be at least ${MIN_SECRET_CHARS} characters`);
  }
  const header = base64url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const claims = base64url(
    JSON.stringify({
      sub: identity.id,
      cohort: identity.cohort,
      aud: API_AUDIENCE,
      iat: nowSeconds,
      exp: nowSeconds + TOKEN_TTL_SECONDS,
    }),
  );
  const signature = createHmac("sha256", secret).update(`${header}.${claims}`).digest("base64url");
  return `${header}.${claims}.${signature}`;
}

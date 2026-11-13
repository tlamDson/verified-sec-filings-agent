// @vitest-environment node
import { describe, expect, it } from "vitest";
import { signApiToken } from "@/lib/api/token";

// The same secret, user, time and token as `packages/sec-agent/tests/api/test_identity.py`:
// what this function signs is what the API verifies. All of it is made up for tests.
const SECRET = "sim-shared-secret-0123456789abcdef0123456789";
const NOW_SECONDS = 1794562215; // 2026-11-13T09:30:15Z
const WEB_TOKEN =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." +
  "eyJzdWIiOiJnaXRodWI6NDIiLCJjb2hvcnQiOiJyZWFsIiwiYXVkIjoic2VjLWFnZW50LWFwaSIsImlhdCI6" +
  "MTc5NDU2MjIxNSwiZXhwIjoxNzk0NTYyMjc1fQ." +
  "SIm7T2_D7Cmhg9X4ClDtUvntGY7J1fUpjv9vzA_a5FQ";

function claims(token: string): Record<string, unknown> {
  const payload = token.split(".")[1] ?? "";
  return JSON.parse(Buffer.from(payload, "base64url").toString("utf-8"));
}

describe("signApiToken", () => {
  it("signs the token the API accepts", () => {
    const token = signApiToken({ id: "github:42", cohort: "real" }, SECRET, NOW_SECONDS);
    expect(token).toBe(WEB_TOKEN);
  });

  it("names the user, the cohort and the API, and lasts one minute", () => {
    const token = signApiToken(
      { id: "sim:sim-07@example.com", cohort: "simulated" },
      SECRET,
      NOW_SECONDS,
    );
    expect(claims(token)).toEqual({
      sub: "sim:sim-07@example.com",
      cohort: "simulated",
      aud: "sec-agent-api",
      iat: NOW_SECONDS,
      exp: NOW_SECONDS + 60,
    });
  });

  it("changes with the secret", () => {
    const user = { id: "github:42", cohort: "real" } as const;
    const other = signApiToken(user, "another-secret-0123456789abcdef0123456789", NOW_SECONDS);
    expect(other).not.toBe(WEB_TOKEN);
    expect(other.split(".").slice(0, 2)).toEqual(WEB_TOKEN.split(".").slice(0, 2));
  });

  it("refuses a secret too short to sign with", () => {
    expect(() => signApiToken({ id: "github:42", cohort: "real" }, "short", NOW_SECONDS)).toThrow(
      /API_AUTH_SECRET/,
    );
  });
});

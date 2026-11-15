// The sign-in of the simulated cohort: fifty test accounts, sim-01@example.com to
// sim-50@example.com (example.com is reserved for testing, RFC 2606), that share one
// password, `SIM_LOGIN_SECRET`. It is off unless that variable is set. These accounts are
// test traffic: their id starts "sim:", their cohort is "simulated", and they are never
// counted as real users.

import { createHash, timingSafeEqual } from "node:crypto";

export interface SimulatedUser {
  id: string;
  email: string;
  name: string;
  cohort: "simulated";
}

const SIMULATED_EMAIL = /^sim-(0[1-9]|[1-4][0-9]|50)@example\.com$/;

function sameText(a: string, b: string): boolean {
  const digest = (text: string) => createHash("sha256").update(text).digest();
  return timingSafeEqual(digest(a), digest(b));
}

export function simulatedUser(
  email: string,
  password: string,
  secret: string | undefined,
): SimulatedUser | null {
  const expected = secret?.trim() ?? "";
  if (expected === "" || !sameText(password, expected)) {
    return null;
  }
  const address = email.trim().toLowerCase();
  const match = SIMULATED_EMAIL.exec(address);
  if (match === null) {
    return null;
  }
  return {
    id: `sim:${address}`,
    email: address,
    name: `Simulated user ${match[1]}`,
    cohort: "simulated",
  };
}

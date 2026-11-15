// @vitest-environment node
import { describe, expect, it } from "vitest";
import { identityOf, signInChoices } from "@/lib/auth/identity";
import { simulatedUser } from "@/lib/auth/simulated";

// Every account and secret here is made up for tests.
const SIM_SECRET = "change-me-sim-login-secret";

describe("simulatedUser", () => {
  it("signs in one of the fifty simulated accounts with the shared secret", () => {
    expect(simulatedUser("sim-07@example.com", SIM_SECRET, SIM_SECRET)).toEqual({
      id: "sim:sim-07@example.com",
      email: "sim-07@example.com",
      name: "Simulated user 07",
      cohort: "simulated",
    });
    expect(simulatedUser("sim-01@example.com", SIM_SECRET, SIM_SECRET)?.cohort).toBe("simulated");
    expect(simulatedUser("sim-50@example.com", SIM_SECRET, SIM_SECRET)?.cohort).toBe("simulated");
    expect(simulatedUser(" SIM-07@Example.com ", SIM_SECRET, SIM_SECRET)?.id).toBe(
      "sim:sim-07@example.com",
    );
  });

  it.each([
    "sim-00@example.com",
    "sim-51@example.com",
    "sim-7@example.com",
    "sim-007@example.com",
    "someone@example.com",
    "sim-07@gmail.com",
    "sim-07@example.com.evil.test",
    "",
  ])("refuses %s: only sim-01 to sim-50 at example.com exist", (email) => {
    expect(simulatedUser(email, SIM_SECRET, SIM_SECRET)).toBeNull();
  });

  it("refuses a wrong password", () => {
    expect(simulatedUser("sim-07@example.com", "guess", SIM_SECRET)).toBeNull();
    expect(simulatedUser("sim-07@example.com", "", SIM_SECRET)).toBeNull();
  });

  it("is off when no secret is configured", () => {
    expect(simulatedUser("sim-07@example.com", "", undefined)).toBeNull();
    expect(simulatedUser("sim-07@example.com", "", "")).toBeNull();
    expect(simulatedUser("sim-07@example.com", "x", "   ")).toBeNull();
  });
});

describe("identityOf", () => {
  it("labels an account from an OAuth provider as real", () => {
    expect(identityOf({ provider: "github", providerAccountId: "42" })).toEqual({
      id: "github:42",
      cohort: "real",
    });
    expect(identityOf({ provider: "google", providerAccountId: "1009" })).toEqual({
      id: "google:1009",
      cohort: "real",
    });
  });

  it("labels an account from the simulated sign-in as simulated", () => {
    expect(
      identityOf({ provider: "simulated", providerAccountId: "sim:sim-07@example.com" }),
    ).toEqual({ id: "sim:sim-07@example.com", cohort: "simulated" });
  });

  it("never lets an OAuth account take a simulated id", () => {
    expect(identityOf({ provider: "sim", providerAccountId: "42" })).toBeNull();
    expect(identityOf({ provider: "simulated", providerAccountId: "github:42" })).toBeNull();
    expect(identityOf({ provider: "", providerAccountId: "42" })).toBeNull();
    expect(identityOf({ provider: "github", providerAccountId: "" })).toBeNull();
  });
});

describe("signInChoices", () => {
  it("offers nothing when nothing is configured", () => {
    expect(signInChoices({})).toEqual([]);
  });

  it("offers each OAuth provider that has both its id and its secret", () => {
    const env = {
      AUTH_GITHUB_ID: "id",
      AUTH_GITHUB_SECRET: "change-me",
      AUTH_GOOGLE_ID: "id-without-secret",
    };
    expect(signInChoices(env)).toEqual([{ id: "github", name: "GitHub", cohort: "real" }]);
  });

  it("offers the simulated sign-in only when its secret is set, labelled simulated", () => {
    expect(signInChoices({ SIM_LOGIN_SECRET: SIM_SECRET })).toEqual([
      { id: "simulated", name: "Simulated test account", cohort: "simulated" },
    ]);
    expect(signInChoices({ SIM_LOGIN_SECRET: "  " })).toEqual([]);
  });
});

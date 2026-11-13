import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SignInPanel } from "@/components/SignInPanel";
import type { SignInChoice } from "@/lib/auth/identity";

const github: SignInChoice = { id: "github", name: "GitHub", cohort: "real" };
const simulated: SignInChoice = {
  id: "simulated",
  name: "Simulated test account",
  cohort: "simulated",
};

describe("SignInPanel", () => {
  it("names the product and shows the not-investment-advice notice", () => {
    render(<SignInPanel choices={[github]} onSignIn={vi.fn()} />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Verified SEC Filings Research Agent",
    );
    expect(screen.getByText(/not investment advice/i)).toBeTruthy();
  });

  it("signs in with an OAuth provider", () => {
    const onSignIn = vi.fn();
    render(<SignInPanel choices={[github]} onSignIn={onSignIn} />);
    fireEvent.click(screen.getByRole("button", { name: "Continue with GitHub" }));
    expect(onSignIn).toHaveBeenCalledWith("github", undefined);
    expect(screen.queryByLabelText("Simulated account email")).toBeNull();
  });

  it("offers the simulated sign-in only when it is enabled, and labels it", () => {
    const onSignIn = vi.fn();
    render(<SignInPanel choices={[github, simulated]} onSignIn={onSignIn} />);
    expect(
      screen.getByText(
        "Simulated accounts are test traffic. They are labelled simulated and counted apart from real users.",
      ),
    ).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Simulated account email"), {
      target: { value: "sim-07@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Simulated account password"), {
      target: { value: "change-me-sim-login-secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in as a simulated user" }));
    expect(onSignIn).toHaveBeenCalledWith("simulated", {
      email: "sim-07@example.com",
      password: "change-me-sim-login-secret",
    });
  });

  it("says so when no sign-in is configured", () => {
    render(<SignInPanel choices={[]} onSignIn={vi.fn()} />);
    expect(screen.getByText("Sign-in is not configured for this deployment.")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });
});

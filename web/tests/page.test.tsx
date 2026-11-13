import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Home from "../app/page";

describe("Home", () => {
  it("names the product", () => {
    render(<Home />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Verified SEC Filings Research Agent",
    );
  });

  it("shows the not-investment-advice notice", () => {
    render(<Home />);
    expect(screen.getByText(/not investment advice/i)).toBeTruthy();
  });
});

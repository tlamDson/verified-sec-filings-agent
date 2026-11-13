import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CitationPanel } from "@/components/CitationPanel";
import { FeedbackButtons } from "@/components/FeedbackButtons";
import { MetricChart } from "@/components/MetricChart";
import {
  APPLE_10K,
  filingCitation,
  marginTrend,
  PASSAGE_KEY,
  passageCitation,
  revenueTrend,
  THREAD,
} from "./fixtures";

describe("CitationPanel", () => {
  it("lists the sources in the order the answer numbers them", () => {
    render(<CitationPanel citations={[filingCitation, passageCitation]} active={null} />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);

    const filing = within(items[0] as HTMLElement);
    expect(filing.getByText("1")).toBeTruthy();
    expect(filing.getByText(/AAPL/)).toBeTruthy();
    expect(filing.getByText(/10-K, filed 2025-10-31/)).toBeTruthy();
    expect(filing.getByRole("link", { name: "Open on sec.gov" }).getAttribute("href")).toBe(
      APPLE_10K.url,
    );

    const passage = within(items[1] as HTMLElement);
    expect(passage.getByText("SIMULATED passage about supply constraints.")).toBeTruthy();
    expect(passage.getByText(/MD&A/)).toBeTruthy();
    expect(passage.getByText(/period ended 2024-12-31/)).toBeTruthy();
    expect(passage.getByText(PASSAGE_KEY)).toBeTruthy();
  });

  it("marks the source the reader clicked in the answer", () => {
    render(<CitationPanel citations={[filingCitation, passageCitation]} active={PASSAGE_KEY} />);
    const [first, second] = screen.getAllByRole("listitem");
    expect(first?.getAttribute("aria-current")).toBeNull();
    expect(second?.getAttribute("aria-current")).toBe("true");
  });

  it("says so when a turn has no source", () => {
    render(<CitationPanel citations={[]} active={null} />);
    expect(screen.getByText("No sources for this answer yet.")).toBeTruthy();
  });

  it("only links to sec.gov", () => {
    const elsewhere = { ...passageCitation, url: "https://example.com/evil" };
    const scripted = { ...filingCitation, url: "javascript:alert(1)" };
    render(<CitationPanel citations={[elsewhere, scripted]} active={null} />);
    expect(screen.queryByRole("link")).toBeNull();
  });
});

describe("FeedbackButtons", () => {
  it("sends a thumbs up for the turn and shows it as given", async () => {
    const rate = vi.fn(async () => true);
    render(<FeedbackButtons threadId={THREAD} turn={2} rate={rate} />);
    const up = screen.getByRole("button", { name: "Helpful" });
    expect(up.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(up);
    await waitFor(() => expect(up.getAttribute("aria-pressed")).toBe("true"));
    expect(rate).toHaveBeenCalledWith({ threadId: THREAD, turn: 2, rating: "up" });
    expect(screen.getByRole("button", { name: "Not helpful" }).getAttribute("aria-pressed")).toBe(
      "false",
    );
  });

  it("lets the reader change their mind", async () => {
    const rate = vi.fn(async () => true);
    render(<FeedbackButtons threadId={THREAD} turn={1} rate={rate} />);
    fireEvent.click(screen.getByRole("button", { name: "Helpful" }));
    const down = screen.getByRole("button", { name: "Not helpful" });
    fireEvent.click(down);
    await waitFor(() => expect(down.getAttribute("aria-pressed")).toBe("true"));
    expect(screen.getByRole("button", { name: "Helpful" }).getAttribute("aria-pressed")).toBe(
      "false",
    );
    expect(rate).toHaveBeenLastCalledWith({ threadId: THREAD, turn: 1, rating: "down" });
  });

  it("says so when the rating could not be saved, and shows nothing as given", async () => {
    render(<FeedbackButtons threadId={THREAD} turn={1} rate={async () => false} />);
    const up = screen.getByRole("button", { name: "Helpful" });
    fireEvent.click(up);
    expect((await screen.findByRole("alert")).textContent).toBe("Your feedback was not saved.");
    expect(up.getAttribute("aria-pressed")).toBe("false");
  });
});

describe("MetricChart", () => {
  it("draws a trend and lists the exact values under it", () => {
    render(<MetricChart chart={revenueTrend} />);
    const figure = screen.getByRole("figure", { name: "Revenue" });
    const rows = within(figure).getAllByRole("row");
    expect(rows.map((row) => row.textContent)).toEqual([
      "PeriodAAPLPeriod ended",
      "FY2022$394,328,000,0002022-09-24",
      "FY2023$383,285,000,0002023-09-30",
      "FY2024$391,035,000,0002024-09-28",
    ]);
  });

  it("gives each company its own columns, with its own period ends", () => {
    render(<MetricChart chart={marginTrend} />);
    const rows = within(screen.getByRole("figure", { name: "Gross margin" })).getAllByRole("row");
    expect(rows.map((row) => row.textContent)).toEqual([
      "PeriodNVDAPeriod endedAAPLPeriod ended",
      "FY202356.928894%2023-01-29––",
      "FY202472.717573%2024-01-2846.206350%2024-09-28",
    ]);
  });
});

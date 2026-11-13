import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TurnView } from "@/components/TurnView";
import type { Turn } from "@/lib/chat/state";
import type { AnswerEvent, Card } from "@/lib/chat/types";
import {
  APPLE_10K,
  answer,
  blockedAnswer,
  degradedAnswer,
  filingCitation,
  grossMargin,
  notReported,
  outOfScope,
  PASSAGE_KEY,
  peers,
  restated,
  revenue,
  riskDiff,
  THREAD,
} from "./fixtures";

function done(event: AnswerEvent, cards: Card[] = event.cards): Turn {
  return {
    id: 1,
    question: "What was Apple's revenue in fiscal 2024?",
    phase: "done",
    cards,
    citations: event.citations,
    charts: event.charts,
    answer: { ...event, cards },
    error: null,
  };
}

function show(turn: Turn, onCite = vi.fn()) {
  render(<TurnView turn={turn} threadId={THREAD} onCite={onCite} rate={async () => true} />);
  return onCite;
}

describe("TurnView", () => {
  it("shows the question, the answer and a numbered reference for each citation", () => {
    const onCite = show(done(answer));
    expect(screen.getByText("What was Apple's revenue in fiscal 2024?")).toBeTruthy();
    expect(screen.getByText(/Apple reported revenue of \$391,035 million/)).toBeTruthy();
    expect(screen.queryByText(new RegExp(PASSAGE_KEY))).toBeNull();

    const first = screen.getByRole("button", { name: `Source 1: ${APPLE_10K.accession}` });
    const second = screen.getByRole("button", { name: `Source 2: ${PASSAGE_KEY}` });
    expect([first.textContent, second.textContent]).toEqual(["1", "2"]);
    fireEvent.click(second);
    expect(onCite).toHaveBeenCalledWith(PASSAGE_KEY);
  });

  it("says how many figures of the answer were traced", () => {
    show(done(answer));
    expect(screen.getByText("1 of 1 figures traced to the filings")).toBeTruthy();
  });

  it("shows a fact with its exact value, period end and filing", () => {
    show(done(answer));
    const card = screen.getByRole("article", { name: "Revenue, AAPL, FY2024" });
    expect(within(card).getByText("$391,035,000,000")).toBeTruthy();
    expect(within(card).getByText(/Period ended 2024-09-28/)).toBeTruthy();
    const link = within(card).getByRole("link", { name: /10-K filed 2025-10-31/ });
    expect(link.getAttribute("href")).toBe(APPLE_10K.url);
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("says a restated value differs from the one first reported", () => {
    show(done(answer, [restated]));
    const card = screen.getByRole("article", { name: "Revenue, SIMW, FY2024" });
    expect(within(card).getByText("$1,250,000,000")).toBeTruthy();
    expect(
      within(card).getByText("Restated. First reported as $1,200,000,000, filed 2025-02-20."),
    ).toBeTruthy();
  });

  it("says a value was not reported instead of showing a figure", () => {
    show(done(answer, [notReported]));
    const card = screen.getByRole("article", { name: "Revenue, AAPL, FY2019" });
    expect(within(card).getByText("Not reported in the filings.")).toBeTruthy();
    expect(within(card).queryByText(/\$/)).toBeNull();
  });

  it("shows a ratio with its formula and the facts it was computed from", () => {
    show(done(answer, [grossMargin]));
    const card = screen.getByRole("article", { name: "Gross margin, AAPL, FY2024" });
    expect(within(card).getByText("46.206350%")).toBeTruthy();
    expect(within(card).getByText("gross_profit / revenue * 100")).toBeTruthy();
    expect(within(card).getByText("$180,683,000,000")).toBeTruthy();
    expect(within(card).getByText("$391,035,000,000")).toBeTruthy();
  });

  it("shows a peer comparison ranked, each company with its own period end", () => {
    show(done(answer, [peers]));
    const card = screen.getByRole("article", { name: "Gross margin, peers, FY2024" });
    const rows = within(card).getAllByRole("row").slice(1);
    expect(rows.map((row) => row.textContent)).toEqual([
      "1NVDA72.717573%2024-01-28",
      "2AAPL46.206350%2024-09-28",
      "–MSFTNot reported–",
    ]);
    expect(within(card).getByText(/own fiscal year/)).toBeTruthy();
  });

  it("shows which risk factor paragraphs changed between two filings", () => {
    show(done(answer, [riskDiff]));
    const card = screen.getByRole("article", { name: "Risk factors, SIMW, FY2024 against FY2023" });
    expect(within(card).getByText("1 added, 0 removed, 0 reworded, 2 unchanged")).toBeTruthy();
    expect(within(card).getByText("SIMULATED new risk about supply.")).toBeTruthy();
    expect(within(card).getByText("Added")).toBeTruthy();
  });

  it("shows a tool refusal as a notice", () => {
    show(done(answer, [outOfScope]));
    expect(screen.getByText("'ZZZZ' is not in the 98 companies this product covers")).toBeTruthy();
  });

  it("marks a degraded answer and still shows the figures", () => {
    show(done(degradedAnswer));
    const banner = screen.getByRole("status", { name: "Degraded mode" });
    expect(banner.textContent).toContain("The language model is unavailable right now");
    expect(screen.getByRole("article", { name: "Revenue, AAPL, FY2024" })).toBeTruthy();
    expect(screen.queryByText(/figures traced/)).toBeNull();
  });

  it("marks a withheld answer and still shows the figures", () => {
    show(done(blockedAnswer));
    const banner = screen.getByRole("status", { name: "Answer withheld" });
    expect(banner.textContent).toContain("could not be traced to the filings");
    expect(screen.getByRole("article", { name: "Revenue, AAPL, FY2024" })).toBeTruthy();
  });

  it("says when statements were removed from an answer", () => {
    const trimmed: AnswerEvent = {
      ...answer,
      check: { verdict: "trimmed", figures: 3, traced: 2, removed: 1 },
    };
    show(done(trimmed));
    expect(screen.getByText("2 of 3 figures traced to the filings")).toBeTruthy();
    expect(screen.getByText("1 statement removed because it could not be traced")).toBeTruthy();
  });

  it("shows cards while the answer is still being written", () => {
    show({
      id: 1,
      question: "Apple revenue?",
      phase: "pending",
      cards: [revenue],
      citations: [filingCitation],
      charts: [],
      answer: null,
      error: null,
    });
    expect(screen.getByRole("status", { name: "Working" })).toBeTruthy();
    expect(screen.getByRole("article", { name: "Revenue, AAPL, FY2024" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Helpful" })).toBeNull();
  });

  it("shows why a turn failed", () => {
    show({
      id: 1,
      question: "Apple revenue?",
      phase: "failed",
      cards: [],
      citations: [],
      charts: [],
      answer: null,
      error: { code: "conversation_conflict", message: "Reload and ask again." },
    });
    expect(screen.getByRole("alert").textContent).toContain("Reload and ask again.");
  });

  it("offers feedback once the turn is answered", () => {
    show(done(answer));
    expect(screen.getByRole("button", { name: "Helpful" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Not helpful" })).toBeTruthy();
  });
});

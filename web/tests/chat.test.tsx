import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Chat } from "@/components/Chat";
import type { ChatEvent } from "@/lib/chat/types";
import { answeredTurn, degradedAnswer, PASSAGE_KEY, playing, THREAD, usage } from "./fixtures";

function ask(question: string) {
  fireEvent.change(screen.getByRole("textbox", { name: "Your question" }), {
    target: { value: question },
  });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
}

const rate = async () => true;

describe("Chat", () => {
  it("asks a question and shows the streamed answer with its figures and sources", async () => {
    const { send, asked } = playing(answeredTurn);
    render(<Chat threadId={THREAD} cohort="real" send={send} rate={rate} />);
    ask("What was Apple's revenue in fiscal 2024?");

    expect(await screen.findByText(/Apple reported revenue of \$391,035 million/)).toBeTruthy();
    expect(asked).toEqual([
      { question: "What was Apple's revenue in fiscal 2024?", threadId: THREAD },
    ]);
    expect(screen.getByRole("article", { name: "Revenue, AAPL, FY2024" })).toBeTruthy();
    expect(screen.getByText("1 of 20 questions today")).toBeTruthy();
    expect((screen.getByRole("textbox", { name: "Your question" }) as HTMLInputElement).value).toBe(
      "",
    );
  });

  it("highlights a source in the panel when its reference is clicked", async () => {
    const { send } = playing(answeredTurn);
    render(<Chat threadId={THREAD} cohort="real" send={send} rate={rate} />);
    ask("Apple revenue?");
    fireEvent.click(await screen.findByRole("button", { name: `Source 2: ${PASSAGE_KEY}` }));
    const current = screen
      .getAllByRole("listitem")
      .filter((item) => item.hasAttribute("aria-current"));
    expect(current).toHaveLength(1);
    expect(current[0]?.textContent).toContain("SIMULATED passage about supply constraints.");
  });

  it("does not send an empty question", () => {
    const { send, asked } = playing();
    render(<Chat threadId={THREAD} cohort="real" send={send} rate={rate} />);
    ask("   ");
    expect(asked).toEqual([]);
  });

  it("shows degraded mode when the model is unavailable", async () => {
    const turn: ChatEvent[] = [
      answeredTurn[0] as ChatEvent,
      { type: "answer", data: degradedAnswer },
    ];
    const { send } = playing(turn);
    render(<Chat threadId={THREAD} cohort="real" send={send} rate={rate} />);
    ask("Apple revenue?");
    expect(await screen.findByRole("status", { name: "Degraded mode" })).toBeTruthy();
    expect(screen.getByRole("article", { name: "Revenue, AAPL, FY2024" })).toBeTruthy();
  });

  it("stops taking questions once the daily limit is reached", async () => {
    const refusal = {
      code: "daily_limit",
      message: "You have asked 20 of 20 questions today. The count resets at 00:00 UTC.",
      limit: 20,
      resets_at: "2026-11-14T00:00:00Z",
    };
    const { send } = playing([{ type: "error", data: refusal }]);
    render(<Chat threadId={THREAD} cohort="real" send={send} rate={rate} initialUsage={usage} />);
    ask("One more?");
    await waitFor(() =>
      expect(screen.getAllByText(refusal.message).length).toBeGreaterThanOrEqual(1),
    );
    expect(screen.getByText("20 of 20 questions today")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("labels a simulated account as simulated", () => {
    const { send } = playing();
    const { unmount } = render(
      <Chat threadId={THREAD} cohort="simulated" send={send} rate={rate} />,
    );
    expect(screen.getByText("Simulated test account")).toBeTruthy();
    unmount();
    render(<Chat threadId={THREAD} cohort="real" send={send} rate={rate} />);
    expect(screen.queryByText("Simulated test account")).toBeNull();
  });

  it("always shows that this is not investment advice", () => {
    const { send } = playing();
    render(<Chat threadId={THREAD} cohort="real" send={send} rate={rate} />);
    expect(screen.getByText(/not investment advice/i)).toBeTruthy();
  });
});

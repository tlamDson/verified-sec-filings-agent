// @vitest-environment node
import { describe, expect, it } from "vitest";
import { answerSegments } from "@/lib/chat/citations";
import { ANSWER_TEXT, APPLE_10K, filingCitation, PASSAGE_KEY, passageCitation } from "./fixtures";

const citations = [filingCitation, passageCitation];

describe("answerSegments", () => {
  it("splits an answer into text and numbered references to the panel", () => {
    expect(answerSegments(ANSWER_TEXT, citations)).toEqual([
      {
        kind: "text",
        text: "SIMULATED: Apple reported revenue of $391,035 million for fiscal 2024 ",
      },
      { kind: "citation", key: APPLE_10K.accession, index: 1 },
      { kind: "text", text: ". Supply was constrained " },
      { kind: "citation", key: PASSAGE_KEY, index: 2 },
      { kind: "text", text: "." },
    ]);
  });

  it("numbers a reference by its place in the panel, however often it is cited", () => {
    const text = `One [${PASSAGE_KEY}]. Two [${PASSAGE_KEY}].`;
    const found = answerSegments(text, citations).filter((s) => s.kind === "citation");
    expect(found).toEqual([
      { kind: "citation", key: PASSAGE_KEY, index: 2 },
      { kind: "citation", key: PASSAGE_KEY, index: 2 },
    ]);
  });

  it("reads several keys in one pair of brackets", () => {
    const text = `Both [${APPLE_10K.accession}; ${PASSAGE_KEY}] agree.`;
    expect(answerSegments(text, citations)).toEqual([
      { kind: "text", text: "Both " },
      { kind: "citation", key: APPLE_10K.accession, index: 1 },
      { kind: "citation", key: PASSAGE_KEY, index: 2 },
      { kind: "text", text: " agree." },
    ]);
  });

  it("leaves brackets that are not a citation of this turn as text", () => {
    const text = "A range [1] and a key [0000000000-00-000000/mdna/9] nobody returned.";
    expect(answerSegments(text, citations)).toEqual([{ kind: "text", text }]);
  });

  it("returns plain text whole, and nothing for an empty answer", () => {
    expect(answerSegments("No citation here.", citations)).toEqual([
      { kind: "text", text: "No citation here." },
    ]);
    expect(answerSegments("", citations)).toEqual([]);
  });
});

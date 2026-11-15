// The answer's text split where it cites a source. An answer cites with the source's key
// in square brackets, `[accession/section/ordinal]` or `[accession]`; several keys may
// share one pair of brackets. Only keys of this turn's sources become references: any
// other bracket stays text.

import type { Citation } from "./types";

export type Segment =
  | { kind: "text"; text: string }
  | { kind: "citation"; key: string; index: number };

const BRACKETS = /\[([^[\]]+)\]/g;

export function answerSegments(text: string, citations: Citation[]): Segment[] {
  const numbers = new Map(citations.map((citation, at) => [citation.key, at + 1]));
  const segments: Segment[] = [];
  let pending = "";
  let cursor = 0;
  for (const match of text.matchAll(BRACKETS)) {
    const keys = (match[1] ?? "").split(/[;,]/).map((key) => key.trim());
    if (!keys.every((key) => numbers.has(key))) {
      continue;
    }
    pending += text.slice(cursor, match.index);
    if (pending !== "") {
      segments.push({ kind: "text", text: pending });
      pending = "";
    }
    for (const key of keys) {
      segments.push({ kind: "citation", key, index: numbers.get(key) ?? 0 });
    }
    cursor = match.index + match[0].length;
  }
  pending += text.slice(cursor);
  if (pending !== "") {
    segments.push({ kind: "text", text: pending });
  }
  return segments;
}

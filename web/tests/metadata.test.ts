import { describe, expect, it } from "vitest";
import { metadata } from "@/app/layout";

describe("app metadata", () => {
  it("uses the display name as the page title", () => {
    expect(metadata.title).toBe("Verified SEC Filings Agent");
  });
});

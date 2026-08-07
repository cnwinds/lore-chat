import { describe, expect, it } from "vitest";
import { clipToolQuery, stripLegacyEchoedPrompt } from "./toolQuery";

describe("toolQuery", () => {
  it("clips at 1024", () => {
    const long = "a".repeat(1100);
    expect(clipToolQuery(long)).toBe(`${"a".repeat(1024)}…`);
  });

  it("stripLegacyEchoedPrompt matches truncated stems", () => {
    const cmd = "x".repeat(200);
    const out = stripLegacyEchoedPrompt(`$ ${cmd.slice(0, 80)}…\nok\n`, cmd);
    expect(out).toBe("ok\n");
  });

  it("does not strip unrelated stdout that starts with $", () => {
    const out = stripLegacyEchoedPrompt("$ 9.99\n[exit 0]", "cat price.txt");
    expect(out).toBe("$ 9.99\n[exit 0]");
  });
});

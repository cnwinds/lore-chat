import { describe, expect, it } from "vitest";
import {
  compactTokenCount,
  exactTokenCount,
  getMessageTokenUsage,
} from "./chatMessageFormat";

describe("compactTokenCount", () => {
  it("keeps counts under a thousand as integers", () => {
    expect(compactTokenCount(0)).toBe("0");
    expect(compactTokenCount(12)).toBe("12");
    expect(compactTokenCount(999)).toBe("999");
  });

  it("uses K and M with two decimal places", () => {
    expect(compactTokenCount(1000)).toBe("1.00K");
    expect(compactTokenCount(2466)).toBe("2.47K");
    expect(compactTokenCount(67406)).toBe("67.41K");
    expect(compactTokenCount(1_000_000)).toBe("1.00M");
    expect(compactTokenCount(1_234_567)).toBe("1.23M");
  });
});

describe("exactTokenCount", () => {
  it("groups thousands for the hover detail", () => {
    expect(exactTokenCount(678)).toBe("678");
    expect(exactTokenCount(2466)).toBe("2,466");
    expect(exactTokenCount(67406)).toBe("67,406");
  });
});

describe("getMessageTokenUsage", () => {
  it("hides when both sides are missing", () => {
    expect(getMessageTokenUsage({})).toBeNull();
  });

  it("treats a missing side as zero", () => {
    expect(getMessageTokenUsage({ prompt_tokens: 12 })).toEqual({
      prompt: 12,
      completion: 0,
    });
  });
});

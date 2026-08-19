import { describe, expect, it } from "vitest";
import { maskApiKeyPlaceholder } from "./providerPresets";

describe("maskApiKeyPlaceholder", () => {
  it("keeps backend-masked values", () => {
    expect(maskApiKeyPlaceholder("sk***abcd")).toBe("sk***abcd");
    expect(maskApiKeyPlaceholder("****")).toBe("****");
  });

  it("masks short secrets entirely", () => {
    expect(maskApiKeyPlaceholder("ab")).toBe("****");
    expect(maskApiKeyPlaceholder("abcd")).toBe("****");
  });

  it("masks long secrets with head and tail", () => {
    expect(maskApiKeyPlaceholder("sk-abcdefghijklmnop")).toBe("sk***mnop");
  });
});

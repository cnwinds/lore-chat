import { describe, expect, it, vi, afterEach } from "vitest";
import { newId } from "./id";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("newId", () => {
  it("uses crypto.randomUUID when available", () => {
    vi.stubGlobal("crypto", {
      randomUUID: () => "11111111-2222-4333-8444-555555555555",
    });
    expect(newId()).toBe("11111111-2222-4333-8444-555555555555");
  });

  it("falls back when randomUUID is missing (insecure context)", () => {
    const bytes = new Uint8Array(16).fill(0xab);
    vi.stubGlobal("crypto", {
      getRandomValues: (out: Uint8Array) => {
        out.set(bytes);
        return out;
      },
    });
    const id = newId();
    expect(id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
  });

  it("uses weak last-resort id when crypto is unavailable", () => {
    vi.stubGlobal("crypto", undefined);
    const id = newId();
    expect(id).toMatch(/^id-[a-z0-9]+-[a-z0-9]+$/);
  });
});

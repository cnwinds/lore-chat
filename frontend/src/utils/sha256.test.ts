import { describe, expect, it } from "vitest";
import { sha256Hex } from "./sha256";

describe("sha256Hex", () => {
  it("matches NIST empty-string vector", async () => {
    await expect(sha256Hex(new Uint8Array(0))).resolves.toBe(
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    );
  });

  it("matches 'abc' vector and sliceLen", async () => {
    const full =
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
    const bytes = new TextEncoder().encode("abc");
    await expect(sha256Hex(bytes)).resolves.toBe(full);
    await expect(sha256Hex(bytes, 32)).resolves.toBe(full.slice(0, 32));
  });

  it("works when crypto.subtle is unavailable (HTTP 非安全上下文)", async () => {
    const original = globalThis.crypto;
    Object.defineProperty(globalThis, "crypto", {
      configurable: true,
      value: { subtle: undefined },
    });
    try {
      await expect(sha256Hex(new TextEncoder().encode("abc"))).resolves.toBe(
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
      );
    } finally {
      Object.defineProperty(globalThis, "crypto", {
        configurable: true,
        value: original,
      });
    }
  });
});

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { ttlSecFromPreset, parseSharePathname, SharePublicError } from "./share";
import { showToast } from "../utils/toast";

describe("ttlSecFromPreset", () => {
  it("returns null for permanent", () => {
    expect(ttlSecFromPreset("permanent")).toBeNull();
  });

  it("returns seconds for presets", () => {
    expect(ttlSecFromPreset("1d")).toBe(86400);
    expect(ttlSecFromPreset("7d")).toBe(7 * 86400);
  });

  it("returns ttl from custom datetime", () => {
    const future = new Date(Date.now() + 3600 * 1000).toISOString();
    const sec = ttlSecFromPreset("custom", future);
    expect(sec).not.toBeNull();
    expect(sec!).toBeGreaterThanOrEqual(60);
  });

  it("rejects past custom datetime", () => {
    const past = new Date(Date.now() - 3600 * 1000).toISOString();
    expect(ttlSecFromPreset("custom", past)).toBeNull();
  });
});

describe("parseSharePathname", () => {
  it("parses valid share path", () => {
    expect(parseSharePathname("/share/abcdefghijklmnopqr")).toBe(
      "abcdefghijklmnopqr",
    );
  });

  it("rejects short or invalid ids", () => {
    expect(parseSharePathname("/share/short")).toBeNull();
    expect(parseSharePathname("/share/bad id!!!!!!!!!!!!")).toBeNull();
    expect(parseSharePathname("/other/abcdefghijklmnopqr")).toBeNull();
  });
});

describe("SharePublicError", () => {
  it("carries status", () => {
    const err = new SharePublicError(410, "分享链接已过期");
    expect(err.status).toBe(410);
    expect(err.message).toContain("过期");
  });
});

describe("showToast", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  it("mounts and removes toast", () => {
    showToast("链接已复制", 1000);
    const host = document.getElementById("lorechat-toast-host");
    expect(host).toBeTruthy();
    expect(host?.textContent).toContain("链接已复制");
    vi.advanceTimersByTime(1500);
    expect(document.getElementById("lorechat-toast-host")).toBeNull();
  });
});

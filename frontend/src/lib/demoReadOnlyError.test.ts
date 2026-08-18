import { describe, expect, it } from "vitest";
import { isDemoReadOnlyError } from "./httpTransport";

describe("isDemoReadOnlyError", () => {
  it("识别顶层 code", () => {
    expect(isDemoReadOnlyError({ code: "demo_read_only" })).toBe(true);
  });

  it("识别 FastAPI detail 包裹的 code", () => {
    expect(isDemoReadOnlyError({ detail: { code: "demo_read_only" } })).toBe(true);
  });

  it("其他错误不误判", () => {
    expect(isDemoReadOnlyError({ code: "auth_required" })).toBe(false);
    expect(isDemoReadOnlyError(null)).toBe(false);
  });
});

import { describe, expect, it } from "vitest";
import { resolveDemoCapability } from "./useDemoCapability";

describe("resolveDemoCapability", () => {
  it("访客只读且对话不落库", () => {
    const cap = resolveDemoCapability({
      setup_required: false,
      authenticated: false,
      demo: true,
      role: "guest",
    });
    expect(cap.isDemo).toBe(true);
    expect(cap.canWrite).toBe(false);
    expect(cap.canPersistChat).toBe(false);
  });

  it("demo 站的管理员不受限", () => {
    const cap = resolveDemoCapability({
      setup_required: false,
      authenticated: true,
      demo: true,
      role: "admin",
    });
    expect(cap.canWrite).toBe(true);
    expect(cap.canPersistChat).toBe(true);
  });

  it("非 demo 部署一切照旧", () => {
    const cap = resolveDemoCapability({
      setup_required: false,
      authenticated: true,
      demo: false,
      role: "admin",
    });
    expect(cap.isDemo).toBe(false);
    expect(cap.canWrite).toBe(true);
  });
});

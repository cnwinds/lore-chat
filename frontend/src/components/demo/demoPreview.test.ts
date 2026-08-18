import { describe, expect, it } from "vitest";
import { extractDemoPreview } from "./DemoPreviewCard";

describe("extractDemoPreview", () => {
  it("提取文档预览", () => {
    const preview = extractDemoPreview({
      status: "preview_only",
      preview: { kind: "doc", path: "技术/检索/选型.md", content: "# 选型" },
    });
    expect(preview).toEqual({
      kind: "doc",
      path: "技术/检索/选型.md",
      content: "# 选型",
    });
  });

  it("提取记忆预览", () => {
    const preview = extractDemoPreview({
      status: "preview_only",
      preview: { kind: "memory", action: "remember", content: "偏好结论先行" },
    });
    expect(preview?.kind).toBe("memory");
    expect(preview?.content).toBe("偏好结论先行");
  });

  it("非预览结果返回 null", () => {
    expect(extractDemoPreview({ status: "ok", summary: "已写入" })).toBeNull();
    expect(extractDemoPreview(null)).toBeNull();
  });
});

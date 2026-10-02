import { describe, expect, it } from "vitest";
import { resolveToolLabel, TOOL_LABELS } from "./toolLabels";

describe("TOOL_LABELS", () => {
  it("includes unified read tools and legacy tool names", () => {
    expect(TOOL_LABELS.search).toBe("检索知识与会话");
    expect(TOOL_LABELS.read).toBe("读取内容");
    expect(TOOL_LABELS.list).toBe("浏览目录");
    expect(TOOL_LABELS.read_last_tool_results).toBe("读取上一轮工具结果");
    expect(TOOL_LABELS.search_kb).toBe("检索本地知识库");
    expect(TOOL_LABELS.list_kb_structure).toBe("查看知识库目录结构");
    expect(TOOL_LABELS.read_conversation_context).toBe("读取会话上下文");
    expect(TOOL_LABELS.recall_memory).toBe("回忆已确认的用户画像");
    expect(TOOL_LABELS.recall_cards).toBe("查阅角色知识卡");
  });
});

describe("resolveToolLabel", () => {
  it("labels svg write_kb_file as vector image", () => {
    expect(resolveToolLabel("write_kb_file", { filename: "logo.svg" })).toBe(
      "写入知识库矢量图",
    );
  });

  it("keeps code/text label for scripts", () => {
    expect(resolveToolLabel("write_kb_file", { filename: "run.sh" })).toBe(
      TOOL_LABELS.write_kb_file,
    );
  });
});

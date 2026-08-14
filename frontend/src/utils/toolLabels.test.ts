import { describe, expect, it } from "vitest";
import { resolveToolLabel, TOOL_LABELS } from "./toolLabels";

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

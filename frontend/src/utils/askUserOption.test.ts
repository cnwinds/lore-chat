import { describe, expect, it } from "vitest";
import {
  extractChoiceNote,
  formatChoiceLabel,
  optionAllowsInput,
  optionInvitesInput,
  optionIsChosen,
} from "./askUserOption";

describe("optionInvitesInput", () => {
  it("treats labels that ask the user to write as input", () => {
    expect(optionInvitesInput("其他（我来描述，不限于上面几类）")).toBe(true);
    expect(optionInvitesInput("其他——我脑子里另有机制，说说看")).toBe(true);
    expect(optionInvitesInput("其他")).toBe(true);
    expect(optionInvitesInput("Other (please specify)")).toBe(true);
  });

  it("does not treat a complete canned answer as input", () => {
    expect(optionInvitesInput("研究分析（资料调研、数据整理、行业分析等）")).toBe(
      false,
    );
    expect(optionInvitesInput("A：重力翻转")).toBe(false);
    expect(optionInvitesInput("其他方向的研究")).toBe(false);
  });
});

describe("optionAllowsInput", () => {
  it("honors the explicit input flag", () => {
    expect(optionAllowsInput({ id: "x", label: "研究分析", input: true })).toBe(
      true,
    );
  });

  it("never opens input on sandbox confirm", () => {
    expect(
      optionAllowsInput(
        { id: "other", label: "其他（我来描述）", input: true },
        { sandbox: true },
      ),
    ).toBe(false);
  });
});

describe("choice label helpers", () => {
  it("joins a note onto the option label", () => {
    expect(formatChoiceLabel("其他（我来描述）", " 陪伴写作 ")).toBe(
      "其他（我来描述）：陪伴写作",
    );
    expect(formatChoiceLabel("研究分析", "")).toBe("研究分析");
  });

  it("matches resolved labels with or without a note", () => {
    expect(optionIsChosen("研究分析", "研究分析")).toBe(true);
    expect(optionIsChosen("其他（我来描述）", "其他（我来描述）：陪伴写作")).toBe(
      true,
    );
    expect(optionIsChosen("研究分析", "内容创作")).toBe(false);
  });

  it("extracts the user note from a resolved label", () => {
    expect(extractChoiceNote("其他（我来描述）", "其他（我来描述）：陪伴写作")).toBe(
      "陪伴写作",
    );
    expect(extractChoiceNote("研究分析", "研究分析")).toBe("");
  });
});

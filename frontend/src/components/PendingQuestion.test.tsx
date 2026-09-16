import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { resolveQuestion } from "../api";
import { PendingQuestion } from "./PendingQuestion";

vi.mock("../api", () => ({
  getQuestions: vi.fn(async () => ({ questions: [{ id: "q1" }] })),
  resolveQuestion: vi.fn(async () => ({
    status: "continue",
    rel_path: null,
    question_id: null,
    message: "正在根据你的选择继续处理…",
    continue_prompt: "其他（我来描述，不限于上面几类）：陪伴写作",
  })),
}));

afterEach(() => {
  cleanup();
  vi.mocked(resolveQuestion).mockClear();
});

const question = {
  id: "q1",
  question: "这个角色主要负责什么方向？",
  options: [
    { id: "research", label: "研究分析（资料调研、数据整理、行业分析等）" },
    { id: "other", label: "其他（我来描述，不限于上面几类）" },
  ],
};

describe("PendingQuestion inline input", () => {
  it("lets the user write inside an inviting option and submit once", async () => {
    const user = userEvent.setup();
    const onResolved = vi.fn();
    render(<PendingQuestion question={question} onResolved={onResolved} />);

    expect(screen.queryByPlaceholderText("写下你的想法")).toBeNull();
    await user.click(screen.getByRole("button", { name: /其他/ }));
    const field = screen.getByPlaceholderText("写下你的想法");
    expect(field).toBeInTheDocument();

    await user.type(field, "陪伴写作");
    await user.click(screen.getByRole("button", { name: "确认" }));

    expect(resolveQuestion).toHaveBeenCalledWith("q1", {
      choice: "other",
      inputs: { other: "陪伴写作" },
    });
    expect(onResolved).toHaveBeenCalled();
    expect(screen.getByText("陪伴写作")).toBeInTheDocument();
  });

  it("still submits a canned option in one click", async () => {
    const user = userEvent.setup();
    vi.mocked(resolveQuestion).mockResolvedValueOnce({
      status: "continue",
      rel_path: null,
      question_id: null,
      message: "正在根据你的选择继续处理…",
      continue_prompt: "研究分析（资料调研、数据整理、行业分析等）",
    });
    render(<PendingQuestion question={question} onResolved={vi.fn()} />);

    await user.click(
      screen.getByRole("button", { name: /研究分析/ }),
    );
    expect(resolveQuestion).toHaveBeenCalledWith("q1", {
      choice: "research",
    });
    expect(screen.queryByPlaceholderText("写下你的想法")).toBeNull();
  });
});

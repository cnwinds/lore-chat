import { describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ShareDocViewer } from "./ShareDocViewer";

vi.mock("../../hooks/useNarrowViewport", () => ({
  useNarrowViewport: vi.fn(() => false),
}));

import { useNarrowViewport } from "../../hooks/useNarrowViewport";

describe("ShareDocViewer", () => {
  beforeEach(() => {
    cleanup();
    vi.mocked(useNarrowViewport).mockReturnValue(false);
  });
  it("renders outline nav and body for headings", () => {
    render(
      <ShareDocViewer body={"# 第一章\n\n正文\n\n## 第二节"} />,
    );
    expect(screen.getByRole("navigation", { name: "章节导航" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /第一章/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /第二节/ })).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "文档正文" })).toBeInTheDocument();
  });

  it("renders body only when no headings", () => {
    const { container } = render(<ShareDocViewer body="纯段落，无标题。" />);
    expect(container.querySelector(".share-page-doc-layout--solo")).toBeInTheDocument();
    expect(screen.getByText("纯段落，无标题。")).toBeInTheDocument();
  });

  it("opens mobile toc sheet on narrow viewport", () => {
    vi.mocked(useNarrowViewport).mockReturnValue(true);
    render(<ShareDocViewer body={"# 第一章\n\n## 第二节"} />);

    expect(screen.queryByRole("navigation", { name: "章节导航" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /打开目录/ }));

    expect(screen.getByRole("dialog", { name: "文档目录" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /第一章/ }).length).toBeGreaterThan(0);
  });
});

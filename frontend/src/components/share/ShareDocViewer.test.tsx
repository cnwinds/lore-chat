import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ShareDocViewer } from "./ShareDocViewer";

describe("ShareDocViewer", () => {
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
});

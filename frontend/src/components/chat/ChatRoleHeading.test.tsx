import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ChatRoleHeading } from "./ChatRoleHeading";

afterEach(() => {
  cleanup();
});

describe("ChatRoleHeading", () => {
  it("shows the role avatar letter in front of the name", () => {
    render(<ChatRoleHeading name="新闻助手" roleId="news" />);
    expect(screen.getByText("新闻助手")).toBeInTheDocument();
    expect(document.querySelector(".role-avatar-letter")).toHaveTextContent(
      "新",
    );
    expect(document.querySelector("img")).toBeNull();
  });

  it("uses a knowledge-base avatar when provided", () => {
    const path = "媒体/2026-09/a.png";
    render(
      <ChatRoleHeading name="通用" roleId="default" avatar={path} />,
    );
    const img = document.querySelector(".chat-role-heading img");
    expect(img?.getAttribute("src")).toContain("/api/download");
    expect(decodeURIComponent(img?.getAttribute("src") || "")).toContain(path);
    expect(screen.getByText("通用")).toBeInTheDocument();
  });
});

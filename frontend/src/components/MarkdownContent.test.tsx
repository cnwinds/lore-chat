import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MarkdownContent } from "./MarkdownContent";

describe("MarkdownContent lore links", () => {
  it("opens conversation from lore session link", async () => {
    const user = userEvent.setup();
    const onOpenConversation = vi.fn();
    render(
      <MarkdownContent onOpenConversation={onOpenConversation}>
        {"[会话](lore://conversations/rooms/6d51bce5465f/m1)"}
      </MarkdownContent>,
    );
    await user.click(screen.getByRole("button", { name: "会话" }));
    expect(onOpenConversation).toHaveBeenCalledWith({
      conversationId: "6d51bce5465f",
      messageId: "m1",
    });
    expect(document.querySelector('a[href^="lore://"]')).toBeNull();
  });

  it("opens kb file with decoded path and renders static chips for dir and memory", async () => {
    const user = userEvent.setup();
    const onOpenKbPath = vi.fn();
    const { container } = render(
      <MarkdownContent onOpenKbPath={onOpenKbPath}>
        {[
          "[文档](lore://kb/%E6%96%87%E6%A1%A3/a.md)",
          "[目录](lore://kb/%E6%8A%80%E8%83%BD/)",
          "[记忆](lore://memory/owner/identity/x)",
        ].join("\n\n")}
      </MarkdownContent>,
    );
    await user.click(screen.getByRole("button", { name: "文档" }));
    expect(onOpenKbPath).toHaveBeenCalledWith("文档/a.md");
    expect(
      screen.getByText("目录").closest(".conversation-md-link--static"),
    ).not.toBeNull();
    expect(
      screen.getByText("记忆").closest(".conversation-md-link--static"),
    ).not.toBeNull();
    expect(container.querySelector('a[href^="lore://"]')).toBeNull();
  });
});

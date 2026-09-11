import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Role } from "../../api";
import { MobileChatHeader } from "./MobileChatHeader";

afterEach(() => {
  cleanup();
});

const sampleRole = {
  id: "news",
  name: "新闻助手",
  avatar: null,
  system_prompt: "写快讯",
  is_default: false,
  sort_order: 1,
  created_at: "2026-08-07T15:00:00+08:00",
  updated_at: "2026-08-07T15:36:00+08:00",
} satisfies Role;

describe("MobileChatHeader", () => {
  it("shows the role avatar in front of the name", () => {
    render(
      <MobileChatHeader
        title="对话"
        onOpenNav={() => undefined}
        roles={[sampleRole]}
        activeRoleId="news"
      />,
    );
    expect(screen.getByText("新闻助手")).toBeInTheDocument();
    expect(document.querySelector(".role-avatar-letter")).toHaveTextContent(
      "新",
    );
  });
});

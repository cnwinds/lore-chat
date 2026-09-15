import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatSources } from "./ChatSources";

vi.mock("../hooks/useImageLightbox", () => ({
  useImageLightbox: () => ({ openPreview: vi.fn(), lightbox: null }),
}));

afterEach(() => {
  cleanup();
});

describe("ChatSources", () => {
  it("starts collapsed even when there are conversation links or images", () => {
    render(
      <ChatSources
        sources={[
          { type: "conversation", cid: "aaaaaaaaaaaa" },
          { type: "kb", path: "媒体/生成/2026/cat.png" },
        ]}
        onOpen={() => {}}
      />,
    );
    expect(
      screen.getByRole("button", { name: /参考/ }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(document.querySelector(".chat-sources-body")).toBeNull();
  });

  it("expands when the user clicks the header", () => {
    render(
      <ChatSources
        sources={[{ type: "web", url: "https://example.com", title: "例", snippet: "" }]}
        onOpen={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /参考/ }));
    expect(
      screen.getByRole("button", { name: /参考/ }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(document.querySelector(".chat-sources-body")).not.toBeNull();
  });
});

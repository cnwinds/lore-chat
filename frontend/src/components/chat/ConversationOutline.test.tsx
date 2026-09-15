import { describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useRef, type RefObject } from "react";
import { ConversationOutline } from "./ConversationOutline";
import type { ChatMessage } from "../../api";

function msgsWithQuestions(n: number): ChatMessage[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `u${i + 1}`,
    role: "user" as const,
    text: `问题 ${i + 1}`,
  }));
}

function Harness({
  layout,
  msgs,
  historicalSegments,
}: {
  layout: "rail" | "sheet";
  msgs: ChatMessage[];
  historicalSegments?: { messages: ChatMessage[] }[];
}) {
  const scrollRootRef = useRef<HTMLDivElement | null>(null);
  return (
    <div ref={scrollRootRef}>
      <ConversationOutline
        msgs={msgs}
        historicalSegments={historicalSegments}
        conversationId="c1"
        scrollRootRef={scrollRootRef as RefObject<HTMLElement | null>}
        layout={layout}
      />
    </div>
  );
}

describe("ConversationOutline", () => {
  it("rail layout shows side handle", () => {
    cleanup();
    render(<Harness layout="rail" msgs={msgsWithQuestions(3)} />);
    expect(
      screen.getByRole("button", { name: /会话导航/ }),
    ).toBeInTheDocument();
  });

  it("sheet layout opens bottom dialog", () => {
    cleanup();
    render(<Harness layout="sheet" msgs={msgsWithQuestions(3)} />);
    const fab = screen.getByRole("button", { name: /打开提问导航/ });
    expect(fab.classList.contains("share-sheet-fab--compact")).toBe(true);
    expect(
      fab.querySelector(".share-sheet-fab-label")?.classList.contains(
        "visually-hidden",
      ),
    ).toBe(true);
    fireEvent.click(fab);
    expect(
      screen.getByRole("dialog", { name: "会话提问导航" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /问题 1/ })).toBeInTheDocument();
  });

  it("updates the badge when older tip messages are prepended", () => {
    cleanup();
    const { rerender } = render(
      <Harness layout="rail" msgs={msgsWithQuestions(3)} />,
    );
    expect(
      screen.getByRole("button", { name: /会话导航（3 条提问）/ }),
    ).toBeInTheDocument();
    rerender(
      <Harness
        layout="rail"
        msgs={[
          { id: "older", role: "user", text: "更早的问题" },
          ...msgsWithQuestions(3),
        ]}
      />,
    );
    expect(
      screen.getByRole("button", { name: /会话导航（4 条提问）/ }),
    ).toBeInTheDocument();
  });

  it("includes questions from historical segments after load-more", () => {
    cleanup();
    const tip: ChatMessage[] = [{ id: "tip", role: "user", text: "当前问" }];
    const { rerender } = render(
      <Harness layout="rail" msgs={tip} historicalSegments={[]} />,
    );
    expect(screen.queryByRole("button", { name: /会话导航/ })).toBeNull();

    rerender(
      <Harness
        layout="rail"
        msgs={tip}
        historicalSegments={[
          {
            messages: [
              { id: "old1", role: "user", text: "很早的问" },
              { id: "old2", role: "user", text: "中间问" },
            ],
          },
        ]}
      />,
    );
    const handle = screen.getByRole("button", { name: /会话导航（3 条提问）/ });
    fireEvent.click(handle);
    expect(screen.getByRole("button", { name: /很早的问/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /中间问/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /当前问/ })).toBeInTheDocument();
  });
});

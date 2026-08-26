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
}: {
  layout: "rail" | "sheet";
  msgs: ChatMessage[];
}) {
  const scrollRootRef = useRef<HTMLDivElement | null>(null);
  return (
    <div ref={scrollRootRef}>
      <ConversationOutline
        msgs={msgs}
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
    fireEvent.click(screen.getByRole("button", { name: /打开提问导航/ }));
    expect(
      screen.getByRole("dialog", { name: "会话提问导航" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /问题 1/ })).toBeInTheDocument();
  });
});

import { describe, expect, it } from "vitest";
import {
  isWorkspaceSearchHotkey,
  workspaceSearchHitKey,
  workspaceSearchHotkeyLabel,
} from "./workspaceSearch";

describe("workspaceSearchHitKey", () => {
  it("is stable for the same message / role / file", () => {
    expect(
      workspaceSearchHitKey({
        kind: "message",
        conversation_id: "c1",
        message_id: "m1",
        role_id: "news",
      }),
    ).toBe("message:c1:m1:news:");
    expect(
      workspaceSearchHitKey({
        kind: "role",
        conversation_id: "",
        message_id: null,
        role_id: "default",
      }),
    ).toBe("role:::default:");
    expect(
      workspaceSearchHitKey({
        kind: "file",
        conversation_id: "",
        path: "笔记/a.md",
      }),
    ).toBe("file::::笔记/a.md");
  });
});

describe("workspaceSearchHotkeyLabel", () => {
  it("uses the command key on Apple platforms", () => {
    expect(workspaceSearchHotkeyLabel("Mozilla/5.0 (Macintosh; Intel Mac OS X)")).toBe(
      "⌘K",
    );
    expect(workspaceSearchHotkeyLabel("Mozilla/5.0 (Windows NT 10.0)")).toBe("Ctrl+K");
  });
});

describe("isWorkspaceSearchHotkey", () => {
  it("matches Ctrl/Cmd+K without extra modifiers", () => {
    expect(
      isWorkspaceSearchHotkey({ key: "k", ctrlKey: true, metaKey: false }),
    ).toBe(true);
    expect(
      isWorkspaceSearchHotkey({ key: "K", ctrlKey: false, metaKey: true }),
    ).toBe(true);
    expect(
      isWorkspaceSearchHotkey({
        key: "k",
        ctrlKey: true,
        metaKey: false,
        shiftKey: true,
      }),
    ).toBe(false);
    expect(
      isWorkspaceSearchHotkey({ key: "k", ctrlKey: false, metaKey: false }),
    ).toBe(false);
  });
});

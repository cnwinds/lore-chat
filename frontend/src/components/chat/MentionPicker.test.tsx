import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MentionPicker } from "./MentionPicker";

afterEach(() => {
  cleanup();
});

const roles = [
  { id: "default", name: "通用助手大师", avatar: null },
  { id: "game", name: "游戏开发助手", avatar: null },
];

describe("MentionPicker", () => {
  it("renders avatars and names, and highlights the query", () => {
    render(
      <MentionPicker
        roles={roles}
        query="游戏"
        selectedIndex={1}
        onHover={() => {}}
        onPick={() => {}}
      />,
    );
    expect(screen.getByRole("listbox", { name: "点名成员" })).toBeTruthy();
    expect(screen.getByText("通用助手大师")).toBeTruthy();
    expect(document.querySelector("mark")?.textContent).toBe("游戏");
    expect(document.querySelectorAll(".role-avatar")).toHaveLength(2);
    expect(screen.getByRole("option", { name: /游戏开发助手/ }).className).toContain(
      "is-active",
    );
  });

  it("picks a member on mousedown so the textarea keeps focus", () => {
    const onPick = vi.fn();
    render(
      <MentionPicker
        roles={roles}
        query=""
        selectedIndex={0}
        onHover={() => {}}
        onPick={onPick}
      />,
    );
    fireEvent.mouseDown(screen.getByRole("option", { name: /游戏开发助手/ }));
    expect(onPick).toHaveBeenCalledWith(roles[1]);
  });

  it("shows an empty hint when nobody matches", () => {
    render(
      <MentionPicker
        roles={[]}
        query="没有"
        selectedIndex={0}
        onHover={() => {}}
        onPick={() => {}}
      />,
    );
    expect(screen.getByText("没有叫这个名字的成员")).toBeTruthy();
  });
});

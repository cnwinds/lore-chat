import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { GroupAvatar } from "./GroupAvatar";

afterEach(() => {
  cleanup();
});

describe("GroupAvatar", () => {
  it("falls back to the group title letter", () => {
    render(<GroupAvatar name="登录页协作" seed="g1" />);
    expect(document.querySelector(".role-avatar-letter")).toHaveTextContent("登");
  });

  it("collages member avatars when the group has no custom image", () => {
    render(
      <GroupAvatar
        name="登录页"
        seed="g1"
        members={[
          { id: "a", name: "通用助手大师" },
          { id: "b", name: "游戏开发助手" },
        ]}
      />,
    );
    expect(document.querySelector(".group-avatar--2")).toBeTruthy();
    const letters = [...document.querySelectorAll(".role-avatar-letter")].map(
      (el) => el.textContent,
    );
    expect(letters).toEqual(["通", "游"]);
    const mark = document.querySelector(".group-avatar-mark");
    expect(mark).toHaveTextContent("群");
    expect(mark).toHaveAttribute("title", "群聊");
  });

  it("marks a custom group avatar as a group", () => {
    render(
      <GroupAvatar name="登录页" seed="g1" avatar="媒体/g.png" />,
    );
    const mark = document.querySelector(".group-avatar-mark");
    expect(mark).toHaveTextContent("群");
    expect(mark).toHaveAttribute("title", "群聊");
  });
});

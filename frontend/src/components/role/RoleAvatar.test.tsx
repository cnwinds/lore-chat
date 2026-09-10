import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { RoleAvatar } from "./RoleAvatar";

afterEach(() => {
  cleanup();
});

describe("RoleAvatar", () => {
  it("shows the first letter when avatar is empty", () => {
    render(<RoleAvatar name="通用" seed="default" />);
    expect(document.querySelector(".role-avatar-letter")).toHaveTextContent("通");
    expect(document.querySelector("img")).toBeNull();
  });

  it("turns a knowledge-base path into a download URL", () => {
    const path = "媒体/2026-09/20260910_084039_74b0c2929.png";
    render(<RoleAvatar name="通用" seed="default" avatar={path} />);
    const img = document.querySelector("img");
    expect(img).toBeTruthy();
    expect(img?.getAttribute("src")).toContain("/api/download");
    expect(decodeURIComponent(img?.getAttribute("src") || "")).toContain(path);
  });

  it("keeps remote http avatars", () => {
    render(
      <RoleAvatar
        name="通用"
        seed="default"
        avatar="https://cdn.example/avatar.png"
      />,
    );
    expect(document.querySelector("img")?.getAttribute("src")).toBe(
      "https://cdn.example/avatar.png",
    );
  });

  it("falls back to the letter when the image fails to load", () => {
    render(
      <RoleAvatar
        name="通用"
        seed="default"
        avatar="https://cdn.example/missing.png"
      />,
    );
    const img = document.querySelector("img");
    expect(img).toBeTruthy();
    fireEvent.error(img!);
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector(".role-avatar-letter")).toHaveTextContent("通");
  });
});

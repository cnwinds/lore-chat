import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { STORAGE_KEY, applyTheme } from "../theme";
import { ThemeToggle } from "./ThemeToggle";

afterEach(() => {
  cleanup();
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  delete document.documentElement.dataset.themeTone;
});

describe("ThemeToggle", () => {
  it("opens a menu of four palettes from the theme button", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle compact />);
    await user.click(screen.getByRole("button", { name: /主题/ }));
    const menu = screen.getByRole("menu", { name: "选择主题" });
    expect(menu).toBeInTheDocument();
    expect(screen.getByRole("menuitemradio", { name: "青瓷" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByRole("menuitemradio", { name: "墨砚" })).toBeInTheDocument();
    expect(screen.getByRole("menuitemradio", { name: "紫藤" })).toBeInTheDocument();
    expect(screen.getByRole("menuitemradio", { name: "米色" })).toBeInTheDocument();
  });

  it("applies and persists the chosen palette", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);
    await user.click(screen.getByRole("button", { name: /选择主题/ }));
    await user.click(screen.getByRole("menuitemradio", { name: "米色" }));
    expect(localStorage.getItem(STORAGE_KEY)).toBe("beige");
    expect(document.documentElement.dataset.theme).toBe("beige");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(screen.getByRole("button", { name: /当前为米色/ })).toBeInTheDocument();
  });

  it("keeps two toggles in sync in the same tab", async () => {
    const user = userEvent.setup();
    render(
      <>
        <ThemeToggle compact />
        <ThemeToggle />
      </>,
    );
    await user.click(screen.getByRole("button", { name: /选择主题/ }));
    await user.click(screen.getByRole("menuitemradio", { name: "紫藤" }));
    expect(
      screen.getByRole("button", { name: "选择主题，当前为紫藤" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "主题，当前为紫藤" }),
    ).toBeInTheDocument();
  });

  it("shows the restored palette after a stored iris value", () => {
    localStorage.setItem(STORAGE_KEY, "iris");
    applyTheme("iris");
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: /当前为紫藤/ })).toBeInTheDocument();
  });
});

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { SharePage } from "../pages/SharePage";
import * as shareApi from "../api/share";

vi.mock("../api/share", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/share")>();
  return {
    ...actual,
    getPublicShare: vi.fn(),
    unlockShare: vi.fn(),
  };
});

describe("SharePage", () => {
  beforeEach(() => {
    vi.mocked(shareApi.getPublicShare).mockReset();
    vi.mocked(shareApi.unlockShare).mockReset();
    sessionStorage.clear();
  });

  afterEach(() => {
    document.title = "";
    sessionStorage.clear();
  });

  it("shows friendly expired state for 410", async () => {
    vi.mocked(shareApi.getPublicShare).mockRejectedValue(
      new shareApi.SharePublicError(410, "分享链接已过期"),
    );
    render(<SharePage shareId="abcdefghijklmnopqr" />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.getAllByText("分享已过期").length).toBeGreaterThan(0);
    expect(screen.getByText(/有效期已结束/)).toBeInTheDocument();
    expect(screen.getByText("HTTP 410")).toBeInTheDocument();
  });

  it("shows unavailable state for 404", async () => {
    vi.mocked(shareApi.getPublicShare).mockRejectedValue(
      new shareApi.SharePublicError(404, "分享链接不存在或已失效"),
    );
    render(<SharePage shareId="abcdefghijklmnopqr" />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    expect(screen.getAllByText("分享不可用").length).toBeGreaterThan(0);
    expect(screen.getByText(/已被作者撤销/)).toBeInTheDocument();
  });

  it("renders conversation share title", async () => {
    vi.mocked(shareApi.getPublicShare).mockResolvedValue({
      type: "conversation",
      title: "测试对话分享",
      exp: null,
      messages: [],
    });
    render(<SharePage shareId="abcdefghijklmnopqr" />);
    await waitFor(() => {
      expect(screen.getByText("测试对话分享")).toBeInTheDocument();
    });
    expect(screen.getByText("永久有效")).toBeInTheDocument();
  });

  it("shows password gate then unlocks", async () => {
    vi.mocked(shareApi.getPublicShare)
      .mockRejectedValueOnce(
        new shareApi.SharePublicError(
          401,
          "需要访问密码",
          shareApi.SHARE_PASSWORD_REQUIRED,
        ),
      )
      .mockResolvedValueOnce({
        type: "conversation",
        title: "加密分享",
        exp: null,
        messages: [],
      });
    vi.mocked(shareApi.unlockShare).mockResolvedValue({
      ok: true,
      unlock_token: "unlock-token-abcdefgh",
      ttl_sec: 3600,
    });

    render(<SharePage shareId="abcdefghijklmnopqr" />);
    await waitFor(() => {
      expect(screen.getByText("需要访问密码")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("访问密码"), {
      target: { value: "secret42" },
    });
    fireEvent.click(screen.getByRole("button", { name: "解锁" }));

    await waitFor(() => {
      expect(shareApi.unlockShare).toHaveBeenCalledWith(
        "abcdefghijklmnopqr",
        "secret42",
      );
    });
    await waitFor(() => {
      expect(screen.getByText("加密分享")).toBeInTheDocument();
    });
    expect(sessionStorage.getItem(shareApi.shareUnlockStorageKey("abcdefghijklmnopqr"))).toBe(
      "unlock-token-abcdefgh",
    );
  });

  it("after unlock succeeds, load failure stays off password gate", async () => {
    vi.mocked(shareApi.getPublicShare).mockImplementation(async (_id, token) => {
      if (!token) {
        throw new shareApi.SharePublicError(
          401,
          "需要访问密码",
          shareApi.SHARE_PASSWORD_REQUIRED,
        );
      }
      throw new shareApi.SharePublicError(404, "分享链接不存在或已失效");
    });
    vi.mocked(shareApi.unlockShare).mockResolvedValue({
      ok: true,
      unlock_token: "unlock-token-abcdefgh",
      ttl_sec: 3600,
    });

    render(<SharePage shareId="abcdefghijklmnopqr" />);
    await waitFor(() => {
      expect(screen.getByText("需要访问密码")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("访问密码"), {
      target: { value: "secret42" },
    });
    fireEvent.click(screen.getByRole("button", { name: "解锁" }));

    await waitFor(() => {
      expect(screen.getByText("分享不可用")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.queryByPlaceholderText("访问密码")).not.toBeInTheDocument();
    });
  });
});

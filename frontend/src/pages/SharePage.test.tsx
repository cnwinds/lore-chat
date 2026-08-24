import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { SharePage } from "../pages/SharePage";
import * as shareApi from "../api/share";

vi.mock("../api/share", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/share")>();
  return {
    ...actual,
    getPublicShare: vi.fn(),
  };
});

describe("SharePage", () => {
  beforeEach(() => {
    vi.mocked(shareApi.getPublicShare).mockReset();
  });

  afterEach(() => {
    document.title = "";
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
});

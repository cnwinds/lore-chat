import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ShareLinkItem } from "../../api/share";
import * as shareApi from "../../api/share";
import * as clipboard from "../../utils/clipboard";
import { ShareSettingsTab } from "./ShareSettingsTab";

vi.mock("../../api/share", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/share")>();
  return {
    ...actual,
    listShares: vi.fn(),
    revokeShare: vi.fn(),
  };
});

vi.mock("../../utils/toast", () => ({
  showToast: vi.fn(),
}));

vi.mock("../../utils/clipboard", () => ({
  copyTextToClipboard: vi.fn(),
}));

const listShares = vi.mocked(shareApi.listShares);
const revokeShare = vi.mocked(shareApi.revokeShare);
const copyTextToClipboard = vi.mocked(clipboard.copyTextToClipboard);

const docShare: ShareLinkItem = {
  share_id: "docshareid12345678",
  type: "doc",
  title: "战略学家乌鸦聊产业变现：我的非共识判断.md",
  created_at: "2026-09-13T07:49:00.000Z",
  exp: null,
  revoked: false,
  view_count: 4,
  last_viewed_at: "2026-09-13T09:40:00.000Z",
  recent_views: [{ ts: "2026-09-13T09:40:00.000Z", referer: "https://example.com" }],
  options: {
    pin_version: false,
    source_path: "/专栏/战略学家乌鸦聊产业变现：我的非共识判断.md",
  },
  url: "https://app.example.com/share/docshareid12345678",
};

const convShare: ShareLinkItem = {
  share_id: "convshareid1234567",
  type: "conversation",
  title: "本周检索整理",
  created_at: "2026-09-12T02:00:00.000Z",
  exp: "2026-09-20T02:00:00.000Z",
  revoked: false,
  view_count: 2,
  last_viewed_at: null,
  recent_views: [],
  options: {
    pin_version: false,
    has_password: true,
    message_count: 12,
  },
  url: "https://app.example.com/share/convshareid1234567",
};

async function renderLoaded(shares: ShareLinkItem[] = [docShare, convShare]) {
  listShares.mockResolvedValue({ shares });
  render(<ShareSettingsTab />);
  await waitFor(() => {
    expect(screen.getByText(docShare.title)).toBeInTheDocument();
  });
}

function cardToggle(title: string) {
  return screen.getByRole("button", {
    name: (accessibleName) => accessibleName.includes(title),
  });
}

describe("ShareSettingsTab compact cards", () => {
  beforeEach(() => {
    listShares.mockReset();
    revokeShare.mockReset();
    copyTextToClipboard.mockReset();
    copyTextToClipboard.mockResolvedValue(true);
    revokeShare.mockResolvedValue({ ok: true });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("shows compact cards by default without path, stats or actions", async () => {
    await renderLoaded();

    expect(cardToggle(docShare.title)).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText(/4 次/)).toBeInTheDocument();
    expect(screen.getAllByText("永久有效").length).toBeGreaterThan(0);
    expect(
      screen.queryByText(docShare.options.source_path as string),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("最近访问")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "复制链接" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "打开" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "撤销" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "详情" })).not.toBeInTheDocument();
  });

  it("expands a card on click to reveal details and actions", async () => {
    const user = userEvent.setup();
    await renderLoaded();

    await user.click(cardToggle(docShare.title));

    const toggle = cardToggle(docShare.title);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByText(docShare.options.source_path as string),
    ).toBeInTheDocument();
    expect(screen.getByText("最近访问")).toBeInTheDocument();
    expect(screen.getByText("跟随文档")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制链接" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "打开" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "撤销" })).toBeInTheDocument();
  });

  it("collapses the open card when it is clicked again", async () => {
    const user = userEvent.setup();
    await renderLoaded();

    await user.click(cardToggle(docShare.title));
    expect(screen.getByText("最近访问")).toBeInTheDocument();

    await user.click(cardToggle(docShare.title));
    expect(cardToggle(docShare.title)).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("最近访问")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "复制链接" })).not.toBeInTheDocument();
  });

  it("keeps only one card expanded at a time", async () => {
    const user = userEvent.setup();
    await renderLoaded();

    await user.click(cardToggle(docShare.title));
    await user.click(cardToggle(convShare.title));

    expect(cardToggle(docShare.title)).toHaveAttribute("aria-expanded", "false");
    expect(cardToggle(convShare.title)).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.queryByText(docShare.options.source_path as string),
    ).not.toBeInTheDocument();
    expect(screen.getByText("跟随会话")).toBeInTheDocument();
    expect(screen.getByText("暂无记录")).toBeInTheDocument();
  });

  it("copies the share url from the expanded card", async () => {
    const user = userEvent.setup();
    await renderLoaded();
    await user.click(cardToggle(docShare.title));
    await user.click(screen.getByRole("button", { name: "复制链接" }));

    await waitFor(() => {
      expect(copyTextToClipboard).toHaveBeenCalledWith(docShare.url);
    });
    expect(screen.getByRole("button", { name: "已复制" })).toBeInTheDocument();
  });

  it("opens the public link from the expanded card", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    const user = userEvent.setup();
    await renderLoaded();
    await user.click(cardToggle(docShare.title));
    await user.click(screen.getByRole("button", { name: "打开" }));

    expect(open).toHaveBeenCalledWith(
      docShare.url,
      "_blank",
      "noopener,noreferrer",
    );
  });

  it("revokes a share after confirm", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    listShares
      .mockResolvedValueOnce({ shares: [docShare, convShare] })
      .mockResolvedValueOnce({ shares: [convShare] });
    const user = userEvent.setup();
    render(<ShareSettingsTab />);
    await waitFor(() => {
      expect(screen.getByText(docShare.title)).toBeInTheDocument();
    });

    await user.click(cardToggle(docShare.title));
    await user.click(screen.getByRole("button", { name: "撤销" }));

    await waitFor(() => {
      expect(revokeShare).toHaveBeenCalledWith(docShare.share_id);
    });
    await waitFor(() => {
      expect(screen.queryByText(docShare.title)).not.toBeInTheDocument();
    });
  });

  it("shows a locked conversation summary without expanding", async () => {
    await renderLoaded();
    const toggle = cardToggle(convShare.title);
    expect(within(toggle).getByText("锁")).toBeInTheDocument();
    expect(within(toggle).getByText(/跟随更新/)).toBeInTheDocument();
    expect(within(toggle).getByText(/2 次/)).toBeInTheDocument();
  });
});

import { describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { DocHistoryModal } from "./DocHistoryModal";

const listDocRevisions = vi.fn();
const getDocRevision = vi.fn();

vi.mock("../api", () => ({
  listDocRevisions: (...args: unknown[]) => listDocRevisions(...args),
  getDocRevision: (...args: unknown[]) => getDocRevision(...args),
}));

describe("DocHistoryModal", () => {
  beforeEach(() => {
    cleanup();
    listDocRevisions.mockReset();
    getDocRevision.mockReset();
  });

  it("lists revisions and shows selected body", async () => {
    listDocRevisions.mockResolvedValue({
      path: "笔记/a.md",
      revisions: [
        {
          sha: "aaa1111",
          short_sha: "aaa1111",
          message: "编辑",
          committed_at: "2026-09-19 16:00:00",
        },
        {
          sha: "bbb2222",
          short_sha: "bbb2222",
          message: "初次写入",
          committed_at: "2026-09-18 09:00:00",
        },
      ],
    });
    getDocRevision.mockImplementation(async (_path: string, sha: string) => ({
      path: "笔记/a.md",
      sha,
      short_sha: sha,
      message: sha === "aaa1111" ? "编辑" : "初次写入",
      committed_at: "2026-09-19 16:00:00",
      text: sha === "aaa1111" ? "第二版\n" : "第一版\n",
      binary: false,
      size: 8,
    }));

    render(
      <DocHistoryModal open path="笔记/a.md" onClose={() => undefined} />,
    );
    expect(screen.getByRole("dialog", { name: "修订" })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("这一版")).toBeInTheDocument();
    });
    const compare = screen.getByRole("button", { name: "和上一版比" });
    expect(compare).toHaveAttribute("aria-pressed", "true");
    expect(document.querySelector(".precepts-merge-triple")).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /初次写入/ }));
    await waitFor(() => {
      expect(screen.getByText("第一版")).toBeInTheDocument();
    });
    expect(screen.queryByText("第二版")).toBeNull();
    expect(screen.getByRole("button", { name: "和上一版比" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("keeps the compare toggle off after switching revisions", async () => {
    listDocRevisions.mockResolvedValue({
      path: "笔记/a.md",
      revisions: [
        {
          sha: "aaa1111",
          short_sha: "aaa1111",
          message: "编辑",
          committed_at: "2026-09-19 16:00:00",
        },
        {
          sha: "bbb2222",
          short_sha: "bbb2222",
          message: "初次写入",
          committed_at: "2026-09-18 09:00:00",
        },
      ],
    });
    getDocRevision.mockImplementation(async (_path: string, sha: string) => ({
      path: "笔记/a.md",
      sha,
      short_sha: sha,
      message: sha === "aaa1111" ? "编辑" : "初次写入",
      committed_at: "2026-09-19 16:00:00",
      text: sha === "aaa1111" ? "第二版\n" : "第一版\n",
      binary: false,
      size: 8,
    }));

    render(
      <DocHistoryModal open path="笔记/a.md" onClose={() => undefined} />,
    );
    const compare = await screen.findByRole("button", { name: "和上一版比" });
    await waitFor(() => {
      expect(document.querySelector(".precepts-merge-triple")).not.toBeNull();
    });
    fireEvent.click(compare);
    expect(compare).toHaveAttribute("aria-pressed", "false");
    expect(document.querySelector(".precepts-merge-triple")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /初次写入/ }));
    await waitFor(() => {
      expect(screen.getByText("第一版")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "和上一版比" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(document.querySelector(".precepts-merge-triple")).toBeNull();
  });

  it("shows preview text before the revision list returns", async () => {
    let resolveList: (value: unknown) => void = () => undefined;
    listDocRevisions.mockReturnValue(
      new Promise((resolve) => {
        resolveList = resolve;
      }),
    );
    render(
      <DocHistoryModal
        open
        path="笔记/a.md"
        previewText="当前打开的正文"
        onClose={() => undefined}
      />,
    );
    expect(screen.getByRole("dialog", { name: "修订" })).toBeInTheDocument();
    expect(screen.getByText("当前打开的正文")).toBeInTheDocument();
    expect(screen.getByText("正在读取…")).toBeInTheDocument();
    resolveList({
      path: "笔记/a.md",
      revisions: [
        {
          sha: "aaa1111aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          short_sha: "aaa1111",
          message: "编辑",
          committed_at: "2026-09-19 16:00:00",
        },
      ],
      bodies: {
        aaa1111aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa: {
          path: "笔记/a.md",
          sha: "aaa1111aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          short_sha: "aaa1111",
          message: "编辑",
          committed_at: "2026-09-19 16:00:00",
          text: "仓库里的这一版\n",
          binary: false,
          size: 8,
        },
      },
    });
    await waitFor(() => {
      expect(screen.getByText("仓库里的这一版")).toBeInTheDocument();
    });
    expect(getDocRevision).not.toHaveBeenCalled();
  });

  it("shows this version before the previous version arrives", async () => {
    let resolveOlder: (value: unknown) => void = () => undefined;
    listDocRevisions.mockResolvedValue({
      path: "笔记/a.md",
      revisions: [
        {
          sha: "aaa1111",
          short_sha: "aaa1111",
          message: "编辑",
          committed_at: "2026-09-19 16:00:00",
        },
        {
          sha: "bbb2222",
          short_sha: "bbb2222",
          message: "初次写入",
          committed_at: "2026-09-18 09:00:00",
        },
      ],
    });
    getDocRevision.mockImplementation(async (_path: string, sha: string) => {
      if (sha === "aaa1111") {
        return {
          path: "笔记/a.md",
          sha,
          short_sha: sha,
          message: "编辑",
          committed_at: "2026-09-19 16:00:00",
          text: "第二版\n",
          binary: false,
          size: 8,
        };
      }
      return new Promise((resolve) => {
        resolveOlder = resolve;
      });
    });
    render(
      <DocHistoryModal open path="笔记/a.md" onClose={() => undefined} />,
    );
    await waitFor(() => {
      expect(screen.getByText("第二版")).toBeInTheDocument();
    });
    expect(document.querySelector(".precepts-merge-triple")).toBeNull();
    resolveOlder({
      path: "笔记/a.md",
      sha: "bbb2222",
      short_sha: "bbb2222",
      message: "初次写入",
      committed_at: "2026-09-18 09:00:00",
      text: "第一版\n",
      binary: false,
      size: 8,
    });
    await waitFor(() => {
      expect(document.querySelector(".precepts-merge-triple")).not.toBeNull();
    });
  });

  it("shows conflict controls for replace hunks", async () => {
    listDocRevisions.mockResolvedValue({
      path: "笔记/a.md",
      revisions: [
        {
          sha: "aaa1111",
          short_sha: "aaa1111",
          message: "编辑",
          committed_at: "2026-09-19 16:00:00",
        },
        {
          sha: "bbb2222",
          short_sha: "bbb2222",
          message: "初次写入",
          committed_at: "2026-09-18 09:00:00",
        },
      ],
    });
    getDocRevision.mockImplementation(async (_path: string, sha: string) => ({
      path: "笔记/a.md",
      sha,
      short_sha: sha,
      message: "编辑",
      committed_at: "2026-09-19 16:00:00",
      text: sha === "aaa1111" ? "A\nnew\n" : "A\nold\n",
      binary: false,
      size: 8,
    }));

    render(
      <DocHistoryModal open path="笔记/a.md" onClose={() => undefined} />,
    );
    await waitFor(() => {
      expect(screen.getByText(/1 处冲突/)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "用这一版" })).toBeInTheDocument();
  });
});

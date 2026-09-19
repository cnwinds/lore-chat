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
      expect(screen.getByText("第二版")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /初次写入/ }));
    await waitFor(() => {
      expect(screen.getByText("第一版")).toBeInTheDocument();
    });
  });
});

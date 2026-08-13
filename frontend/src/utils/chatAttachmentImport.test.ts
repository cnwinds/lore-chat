import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({
  kbImport: vi.fn(),
}));

import { kbImport } from "../api";
import {
  chatAttachmentFilename,
  importChatAttachment,
} from "./chatAttachmentImport";

describe("chatAttachmentFilename", () => {
  it("hashes image content for stable path reuse", async () => {
    const bytes = new Uint8Array([1, 2, 3, 4]);
    const a = new File([bytes], "image.png", { type: "image/png" });
    const b = new File([bytes], "paste.png", { type: "image/png" });
    const fa = await chatAttachmentFilename(a);
    const fb = await chatAttachmentFilename(b);
    expect(fa).toBe(fb);
    expect(fa).toMatch(/^[0-9a-f]{32}\.png$/);
  });

  it("keeps original name for non-images", async () => {
    const f = new File([new Uint8Array([1])], "notes.txt", {
      type: "text/plain",
    });
    await expect(chatAttachmentFilename(f)).resolves.toBe("notes.txt");
  });
});

describe("importChatAttachment", () => {
  beforeEach(() => {
    vi.mocked(kbImport).mockReset();
  });

  it("returns rel_path on first success", async () => {
    vi.mocked(kbImport).mockResolvedValueOnce({
      rel_path: "未分类/a.png",
      kind: "file",
      indexed: false,
    });
    const file = new File([new Uint8Array([1])], "a.png", { type: "image/png" });
    await expect(importChatAttachment(file)).resolves.toBe("未分类/a.png");
    expect(kbImport).toHaveBeenCalledWith(
      file,
      "未分类",
      expect.stringMatching(/^[0-9a-f]{32}\.png$/),
    );
  });

  it("auto-retries with suggested_filename on 409", async () => {
    vi.mocked(kbImport)
      .mockRejectedValueOnce({
        status: 409,
        pathExists: {
          code: "PATH_EXISTS",
          path: "未分类/a.png",
          message: "目标路径已存在：未分类/a.png",
          suggested_filename: "a (1).png",
        },
      })
      .mockResolvedValueOnce({
        rel_path: "未分类/a (1).png",
        kind: "file",
        indexed: false,
      });
    const file = new File([new Uint8Array([9])], "a.png", { type: "image/png" });
    await expect(importChatAttachment(file)).resolves.toBe("未分类/a (1).png");
    expect(kbImport).toHaveBeenCalledTimes(2);
    expect(kbImport).toHaveBeenNthCalledWith(2, file, "未分类", "a (1).png");
  });
});

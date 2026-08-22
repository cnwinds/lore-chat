import { afterEach, describe, expect, it, vi } from "vitest";
import {
  copyTextToClipboard,
  extractClipboardFiles,
  extractClipboardImageFiles,
} from "./clipboard";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("extractClipboardFiles", () => {
  it("returns empty when clipboard is null or has no files", () => {
    expect(extractClipboardFiles(null)).toEqual([]);
    expect(
      extractClipboardFiles({
        items: [{ kind: "string", type: "text/plain", getAsFile: () => null }],
      }),
    ).toEqual([]);
  });

  it("extracts all file items from clipboard (local file copy)", () => {
    const png = new File([new Uint8Array([1, 2, 3])], "image.png", {
      type: "image/png",
    });
    const pdf = new File([new Uint8Array([9])], "report.pdf", {
      type: "application/pdf",
    });
    const got = extractClipboardFiles({
      items: [
        { kind: "string", type: "text/plain", getAsFile: () => null },
        { kind: "file", type: "image/png", getAsFile: () => png },
        { kind: "file", type: "application/pdf", getAsFile: () => pdf },
      ],
    });
    expect(got).toEqual([png, pdf]);
  });

  it("falls back to files list when items are empty", () => {
    const mp4 = new File([new Uint8Array([7])], "clip.mp4", {
      type: "video/mp4",
    });
    const txt = new File([new Uint8Array([5])], "a.txt", {
      type: "text/plain",
    });
    expect(extractClipboardFiles({ items: [], files: [mp4, txt] })).toEqual([
      mp4,
      txt,
    ]);
  });
});

describe("extractClipboardImageFiles", () => {
  it("returns empty when clipboard is null or has no images", () => {
    expect(extractClipboardImageFiles(null)).toEqual([]);
    expect(
      extractClipboardImageFiles({
        items: [{ kind: "string", type: "text/plain", getAsFile: () => null }],
      }),
    ).toEqual([]);
  });

  it("extracts image/* file items (screenshot paste)", () => {
    const png = new File([new Uint8Array([1, 2, 3])], "image.png", {
      type: "image/png",
    });
    const got = extractClipboardImageFiles({
      items: [
        { kind: "string", type: "text/plain", getAsFile: () => null },
        { kind: "file", type: "image/png", getAsFile: () => png },
        {
          kind: "file",
          type: "application/pdf",
          getAsFile: () =>
            new File([new Uint8Array([9])], "x.pdf", { type: "application/pdf" }),
        },
      ],
    });
    expect(got).toEqual([png]);
  });

  it("falls back to files list when items yield no images", () => {
    const jpg = new File([new Uint8Array([4])], "shot.jpg", {
      type: "image/jpeg",
    });
    const txt = new File([new Uint8Array([5])], "a.txt", {
      type: "text/plain",
    });
    const got = extractClipboardImageFiles({
      items: [],
      files: [jpg, txt],
    });
    expect(got).toEqual([jpg]);
  });
});

describe("copyTextToClipboard", () => {
  it("uses clipboard API in secure context", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    Object.defineProperty(window, "isSecureContext", {
      configurable: true,
      value: true,
    });

    await expect(copyTextToClipboard("hello")).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledWith("hello");
  });

  it("falls back to execCommand when not secure context (HTTP)", async () => {
    const writeText = vi.fn();
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    Object.defineProperty(window, "isSecureContext", {
      configurable: true,
      value: false,
    });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: vi.fn().mockReturnValue(true),
    });

    await expect(copyTextToClipboard("http-copy")).resolves.toBe(true);
    expect(writeText).not.toHaveBeenCalled();
    expect(document.execCommand).toHaveBeenCalledWith("copy");
  });

  it("falls back when clipboard API throws", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    Object.defineProperty(window, "isSecureContext", {
      configurable: true,
      value: true,
    });
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: vi.fn().mockReturnValue(true),
    });

    await expect(copyTextToClipboard("retry")).resolves.toBe(true);
    expect(document.execCommand).toHaveBeenCalledWith("copy");
  });
});

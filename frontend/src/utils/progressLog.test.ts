import { describe, expect, it } from "vitest";
import {
  appendProgressChunk,
  joinProgressChunks,
} from "./progressLog";
import { sandboxTerminalBody } from "../components/SandboxTerminal";

describe("progressLog newlines", () => {
  it("inserts newline between line-oriented chunks", () => {
    let log = appendProgressChunk([], "$ ls\n");
    log = appendProgressChunk(log, "total 12");
    log = appendProgressChunk(log, "drwx .");
    expect(joinProgressChunks(log)).toBe("$ ls\ntotal 12\ndrwx .");
  });

  it("does not double newlines", () => {
    let log = appendProgressChunk([], "a\n");
    log = appendProgressChunk(log, "b\n");
    expect(joinProgressChunks(log)).toBe("a\nb\n");
  });

  it("renders legacy per-line progress_log with separators", () => {
    const body = sandboxTerminalBody({
      type: "tool",
      id: "1",
      tool: "sandbox_run",
      label: "run",
      ts: "t",
      status: "done",
      query: "ls -la",
      progress_log: [
        "$ ls -la\n",
        "total 12",
        "drwxr-xr-x 3 root root 4096 Aug  6 07:41 .",
        "drwxr-xr-x 1 root root 4096 Aug  6 09:02 ..",
        "\n[exit 0]",
      ],
    });
    expect(body).toContain("total 12\n");
    expect(body).toContain("drwxr-xr-x 3 root root");
    expect(body).not.toMatch(/total 12drwx/);
  });
});

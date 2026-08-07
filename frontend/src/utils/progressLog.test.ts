import { describe, expect, it } from "vitest";
import {
  appendProgressChunk,
  joinProgressChunks,
  normalizeStreamChunk,
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

  it("overwrites ANSI spinner frames instead of stacking lines", () => {
    let log = appendProgressChunk([], "◐ Downloading 1%\n");
    log = appendProgressChunk(log, "\x1b[1G\x1b[J◑ Downloading 2%");
    log = appendProgressChunk(log, "\x1b[1G\x1b[J◒ Downloading 3%");
    const body = joinProgressChunks(log);
    expect(body).toContain("Downloading 3%");
    expect(body.match(/Downloading/g)?.length).toBe(1);
  });

  it("collapses persisted progress spam on display", () => {
    const spam = Array.from(
      { length: 40 },
      (_, i) => `Downloading Chrome | ${i + 1}% | 1.0s`,
    );
    expect(normalizeStreamChunk(spam.join("\n"))).toContain("40%");
    expect(normalizeStreamChunk(spam.join("\n")).split("\n").length).toBe(1);
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
    expect(body.match(/^\$ /gm)).toHaveLength(1);
  });

  it("keeps a single prompt when progress has no echoed command", () => {
    const body = sandboxTerminalBody({
      type: "tool",
      id: "1",
      tool: "sandbox_run",
      label: "run",
      ts: "t",
      status: "done",
      query: "echo hi",
      progress_log: ["hi\n", "[exit 0]"],
    });
    expect(body).toBe("$ echo hi\nhi\n[exit 0]");
  });

  it("dedupes legacy truncated progress prompt against query", () => {
    const long = "x".repeat(200);
    const body = sandboxTerminalBody({
      type: "tool",
      id: "1",
      tool: "sandbox_run",
      label: "run",
      ts: "t",
      status: "done",
      query: long,
      progress_log: [`$ ${long.slice(0, 120)}…\n`, "ok\n", "[exit 0]"],
    });
    expect(body.startsWith(`$ ${long}\n`)).toBe(true);
    expect(body.match(/^\$ /gm)).toHaveLength(1);
    expect(body).toContain("ok\n[exit 0]");
  });

  it("does not strip unrelated stdout that starts with $", () => {
    const body = sandboxTerminalBody({
      type: "tool",
      id: "1",
      tool: "sandbox_run",
      label: "run",
      ts: "t",
      status: "done",
      query: "cat price.txt",
      progress_log: ["$ 9.99\n", "[exit 0]"],
    });
    expect(body).toBe("$ cat price.txt\n$ 9.99\n[exit 0]");
  });
});

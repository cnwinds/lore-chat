import { describe, expect, it, vi } from "vitest";
import { kbMutateWithConflictRetry } from "./kbMutateWithConflictRetry";

describe("kbMutateWithConflictRetry", () => {
  it("returns result on first success", async () => {
    const run = vi.fn(async () => "ok");
    const onConflict = vi.fn();
    const out = await kbMutateWithConflictRetry({
      initialFilename: "a.md",
      run,
      onConflict,
    });
    expect(out).toBe("ok");
    expect(onConflict).not.toHaveBeenCalled();
  });

  it("retries after 409 and uses chosen name", async () => {
    const run = vi
      .fn()
      .mockRejectedValueOnce({
        status: 409,
        pathExists: {
          suggested_filename: "a (1).md",
          message: "exists",
        },
      })
      .mockResolvedValueOnce({ rel_path: "a (1).md" });

    const out = await kbMutateWithConflictRetry({
      initialFilename: "a.md",
      run,
      onConflict: ({ suggestedFilename, resolve }) => {
        resolve({ kind: "rename", filename: suggestedFilename });
      },
    });
    expect(out).toEqual({ rel_path: "a (1).md" });
    expect(run).toHaveBeenCalledTimes(2);
    expect(run.mock.calls[1][0]).toEqual({
      filename: "a (1).md",
      overwrite: false,
    });
  });

  it("retries with overwrite when user chooses覆盖", async () => {
    const run = vi
      .fn()
      .mockRejectedValueOnce({
        status: 409,
        pathExists: { suggested_filename: "a (1).md", message: "exists" },
      })
      .mockResolvedValueOnce({ rel_path: "a.md" });

    const out = await kbMutateWithConflictRetry({
      initialFilename: "a.md",
      run,
      onConflict: ({ resolve }) => resolve({ kind: "overwrite" }),
    });
    expect(out).toEqual({ rel_path: "a.md" });
    expect(run.mock.calls[1][0]).toEqual({ filename: "a.md", overwrite: true });
  });

  it("returns null when user cancels conflict dialog", async () => {
    const run = vi.fn().mockRejectedValue({
      status: 409,
      pathExists: { suggested_filename: "b.md", message: "m" },
    });
    const out = await kbMutateWithConflictRetry({
      initialFilename: "a.md",
      run,
      onConflict: ({ resolve }) => resolve({ kind: "cancel" }),
    });
    expect(out).toBeNull();
  });
});

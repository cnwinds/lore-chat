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
        resolve(suggestedFilename);
      },
    });
    expect(out).toEqual({ rel_path: "a (1).md" });
    expect(run).toHaveBeenCalledTimes(2);
    expect(run.mock.calls[1][0]).toBe("a (1).md");
  });

  it("returns null when user cancels conflict dialog", async () => {
    const run = vi.fn().mockRejectedValue({
      status: 409,
      pathExists: { suggested_filename: "b.md", message: "m" },
    });
    const out = await kbMutateWithConflictRetry({
      initialFilename: "a.md",
      run,
      onConflict: ({ resolve }) => resolve(null),
    });
    expect(out).toBeNull();
  });
});

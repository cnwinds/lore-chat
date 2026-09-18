import { describe, expect, it } from "vitest";
import {
  isInteractiveKbImportError,
  isZipUploadName,
  planKbImportRuns,
} from "./kbImportBatch";
import type { DroppedFile } from "./droppedFiles";

function item(relativePath: string): DroppedFile {
  return {
    file: new File(["x"], relativePath.split("/").pop() ?? relativePath),
    relativePath,
  };
}

describe("isZipUploadName", () => {
  it("detects zip by filename", () => {
    expect(isZipUploadName("demo.zip")).toBe(true);
    expect(isZipUploadName("dir/Pack.ZIP")).toBe(true);
    expect(isZipUploadName("n.ipynb")).toBe(false);
  });
});

describe("planKbImportRuns", () => {
  it("batches consecutive notebook files into one request", () => {
    const items = [
      item("notebooks/a.ipynb"),
      item("notebooks/b.py"),
      item("notebooks/c.md"),
    ];
    expect(planKbImportRuns(items)).toEqual([
      { kind: "batch", items },
    ]);
  });

  it("keeps a lone file as one import", () => {
    const one = item("readme.md");
    expect(planKbImportRuns([one])).toEqual([{ kind: "one", item: one }]);
  });

  it("isolates zip so pack path choice stays sequential", () => {
    const a = item("a.txt");
    const z = item("技能/demo.zip");
    const b = item("b.txt");
    expect(planKbImportRuns([a, z, b])).toEqual([
      { kind: "one", item: a },
      { kind: "one", item: z },
      { kind: "one", item: b },
    ]);
  });

  it("splits when exceeding batch size", () => {
    const items = Array.from({ length: 3 }, (_, i) => item(`f${i}.txt`));
    const runs = planKbImportRuns(items, 2);
    expect(runs).toEqual([
      { kind: "batch", items: items.slice(0, 2) },
      { kind: "one", item: items[2] },
    ]);
  });
});

describe("isInteractiveKbImportError", () => {
  it("treats 409 path/pack conflicts as interactive", () => {
    expect(
      isInteractiveKbImportError({
        status: 409,
        pathExists: { suggested_filename: "a (1).txt" },
      }),
    ).toBe(true);
    expect(
      isInteractiveKbImportError({
        status: 409,
        packPathChoice: { code: "PACK_PATH_CHOICE" },
      }),
    ).toBe(true);
    expect(isInteractiveKbImportError({ status: 400, message: "bad" })).toBe(
      false,
    );
  });
});

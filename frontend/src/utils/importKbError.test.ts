import { describe, expect, it } from "vitest";
import { messageFromImportErrorBody } from "./importKbError";

describe("messageFromImportErrorBody", () => {
  it("maps stable import error codes to UI copy", () => {
    expect(
      messageFromImportErrorBody({
        detail: { detail: "knowledge base is not empty", code: "kb_not_empty" },
      }),
    ).toContain("覆盖导入");
    expect(
      messageFromImportErrorBody({
        detail: { detail: "missing manifest.json", code: "invalid_manifest" },
      }),
    ).toContain("manifest.json");
    expect(
      messageFromImportErrorBody({
        detail: { detail: "unsupported format_version: 2", code: "unsupported_format" },
      }),
    ).toContain("版本");
  });

  it("uses import_failed copy and appends backup_path", () => {
    expect(
      messageFromImportErrorBody({
        detail: {
          detail: "rolled back: disk full",
          code: "import_failed",
          backup_path: "C:/backups/kb.zip",
        },
      }),
    ).toBe("导入失败：rolled back: disk full（备份：C:/backups/kb.zip）");
  });

  it("maps FastAPI string detail", () => {
    expect(
      messageFromImportErrorBody({
        detail: "mode must be empty_only or overwrite",
      }),
    ).toBe("mode must be empty_only or overwrite");
  });

  it("maps top-level maintenance code from the write-lock guard", () => {
    expect(
      messageFromImportErrorBody({
        detail: "service unavailable: export in progress",
        code: "maintenance",
      }),
    ).toContain("维护");
  });
});

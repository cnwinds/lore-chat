import type { ApiError } from "../api";
import type { DroppedFile } from "./droppedFiles";

/** 与 backend `MAX_KB_IMPORT_BATCH_FILES` 对齐。 */
export const KB_IMPORT_BATCH_SIZE = 32;

export function isZipUploadName(name: string): boolean {
  const base = name.replace(/\\/g, "/").split("/").pop() ?? name;
  return /\.zip$/i.test(base);
}

export type KbImportRun =
  | { kind: "batch"; items: DroppedFile[] }
  | { kind: "one"; item: DroppedFile };

/** 连续的普通文件合并成一批；zip（可能要解压选路）仍逐个导入。 */
export function planKbImportRuns(
  items: DroppedFile[],
  batchSize = KB_IMPORT_BATCH_SIZE,
): KbImportRun[] {
  const runs: KbImportRun[] = [];
  let buffer: DroppedFile[] = [];
  const flush = () => {
    if (!buffer.length) return;
    if (buffer.length === 1) {
      runs.push({ kind: "one", item: buffer[0] });
    } else {
      runs.push({ kind: "batch", items: buffer });
    }
    buffer = [];
  };
  for (const item of items) {
    const name = item.relativePath || item.file.name;
    if (isZipUploadName(name)) {
      flush();
      runs.push({ kind: "one", item });
      continue;
    }
    buffer.push(item);
    if (buffer.length >= batchSize) flush();
  }
  flush();
  return runs;
}

export function isInteractiveKbImportError(err: unknown): boolean {
  const e = err as ApiError;
  return e.status === 409 && Boolean(e.pathExists || e.packPathChoice);
}

export const IMPORT_ERROR_BY_CODE: Record<string, string> = {
  kb_not_empty: "知识库不是空的。请改用「覆盖导入」，或先清空知识库。",
  invalid_manifest: "不是有效的知识库备份（缺少或损坏 manifest.json）",
  unsupported_format: "备份格式版本不受支持",
  import_failed: "导入失败",
  maintenance: "系统正在维护，请稍后再试",
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object"
    ? (value as Record<string, unknown>)
    : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}

export function messageFromImportErrorBody(body: unknown): string | null {
  const rec = asRecord(body);
  if (!rec) return null;

  const nested = asRecord(rec.detail);
  const code = asString(nested?.code) ?? asString(rec.code);
  const detailText = asString(rec.detail) ?? asString(nested?.detail);
  const backupPath = asString(nested?.backup_path) ?? asString(rec.backup_path);

  const mapped = code ? IMPORT_ERROR_BY_CODE[code] : undefined;
  let text: string | null = mapped ?? detailText;
  if (!text) return null;
  if (code === "import_failed" && mapped && detailText && detailText !== mapped) {
    text = `${mapped}：${detailText}`;
  }
  if (backupPath) text = `${text}（备份：${backupPath}）`;
  return text;
}

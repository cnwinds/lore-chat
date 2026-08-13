import { formatDisplayDateTime } from "./displayTime";
import { labelFor, orderedKeys } from "./orderedLabels";

const META_LABELS: Record<string, string> = {
  title: "标题",
  created: "创建时间",
  updated: "更新时间",
  tags: "标签",
  source: "来源",
  merged_from: "合并自",
  conversation_ids: "关联会话",
  memory_revision: "记忆版本",
};

const META_ORDER = [
  "title",
  "created",
  "updated",
  "tags",
  "source",
  "merged_from",
  "conversation_ids",
  "memory_revision",
] as const;

const META_DATETIME_KEYS = new Set(["created", "updated"]);

export type MetaEntry = { key: string; label: string; value: string };

function formatMetaValue(key: string, value: unknown): string {
  const raw = Array.isArray(value) ? value.join(", ") : String(value);
  if (META_DATETIME_KEYS.has(key)) {
    const formatted = formatDisplayDateTime(raw);
    if (formatted) return formatted;
  }
  return raw;
}

export function formatMetaEntries(meta: Record<string, unknown>): MetaEntry[] {
  const filtered = Object.entries(meta).filter(([k]) => k !== "conversation_id");
  return orderedKeys(
    filtered.map(([k]) => k),
    META_ORDER,
  ).map((key) => {
    const value = meta[key];
    return {
      key,
      label: labelFor(key, META_LABELS),
      value: formatMetaValue(key, value),
    };
  });
}

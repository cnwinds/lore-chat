import { formatDisplayDateTime } from "./displayTime";

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
];

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
  const orderIndex = (key: string) => {
    const index = META_ORDER.indexOf(key);
    return index === -1 ? META_ORDER.length : index;
  };

  return filtered
    .sort(([a], [b]) => {
      const orderDiff = orderIndex(a) - orderIndex(b);
      if (orderDiff !== 0) return orderDiff;
      return a.localeCompare(b, "zh-CN");
    })
    .map(([key, value]) => ({
      key,
      label: META_LABELS[key] ?? key,
      value: formatMetaValue(key, value),
    }));
}

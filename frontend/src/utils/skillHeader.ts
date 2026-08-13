/** Skill 正文 YAML 头：与 backend `kb_skill._BODY_YAML` 对齐（仅展示拆分，不写回改写）。 */
import { parse as parseYaml } from "yaml";
import { labelFor, orderedKeys } from "./orderedLabels";

const BODY_YAML = /^\uFEFF?---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/;

const FIELD_LABELS: Record<string, string> = {
  name: "名称",
  description: "描述",
  starter_prompts: "启动提示",
  license: "许可证",
  compatibility: "兼容性",
  metadata: "元数据",
  allowed_tools: "允许工具",
};

const FIELD_ORDER = [
  "name",
  "description",
  "starter_prompts",
  "license",
  "compatibility",
  "allowed_tools",
  "metadata",
] as const;

export type SkillHeaderValue = string | string[];

export type SkillHeaderEntry = {
  key: string;
  label: string;
  value: SkillHeaderValue;
};

export type SkillBodySplit = {
  /** 含首尾 `---` 的原始块；无头时为 null */
  headerBlock: string | null;
  fields: SkillHeaderEntry[];
  content: string;
};

export function isSkillMdPath(path: string): boolean {
  const norm = path.replace(/\\/g, "/");
  return norm === "SKILL.md" || norm.endsWith("/SKILL.md");
}

export function splitSkillBodyHeader(body: string): SkillBodySplit {
  const text = body ?? "";
  const m = BODY_YAML.exec(text);
  if (!m) {
    return { headerBlock: null, fields: [], content: text };
  }
  return {
    headerBlock: m[0],
    fields: formatSkillHeaderEntries(parseSkillYamlMapping(m[1])),
    content: text.slice(m[0].length),
  };
}

export function joinSkillBody(
  headerBlock: string | null | undefined,
  content: string,
): string {
  if (!headerBlock) return content;
  return headerBlock + content;
}

export function formatSkillHeaderEntries(
  data: Record<string, unknown>,
): SkillHeaderEntry[] {
  return orderedKeys(Object.keys(data), FIELD_ORDER).map((key) => ({
    key,
    label: labelFor(key, FIELD_LABELS),
    value: formatSkillHeaderValue(data[key]),
  }));
}

function formatSkillHeaderValue(value: unknown): SkillHeaderValue {
  if (value == null) return "";
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (item == null) return "";
        if (typeof item === "string") return item.trim();
        if (typeof item === "number" || typeof item === "boolean") {
          return String(item);
        }
        return JSON.stringify(item);
      })
      .filter(Boolean);
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([k, v]) => {
        const inner = formatSkillHeaderValue(v);
        return `${k}: ${Array.isArray(inner) ? inner.join(", ") : inner}`;
      })
      .join("\n");
  }
  return String(value);
}

/** 仅用于预览展示；落盘仍保留原始 headerBlock。 */
export function parseSkillYamlMapping(yamlInner: string): Record<string, unknown> {
  try {
    const data = parseYaml(yamlInner);
    if (data && typeof data === "object" && !Array.isArray(data)) {
      const out: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(data as Record<string, unknown>)) {
        if (!k) continue;
        out[k] = v;
      }
      return out;
    }
  } catch {
    /* 解析失败时返回空映射；调用方仍应剥离 headerBlock */
  }
  return {};
}

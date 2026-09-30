import type { KnowledgeCard, OwnerMemoryKind } from "../../api";

export const CARD_KIND_LABELS: Record<KnowledgeCard["kind"], string> = {
  domain: "领域知识",
  owner_context: "主人在此",
  practice: "做法",
  lesson: "经验",
  audience: "受众",
};

export const OWNER_MEMORY_KIND_LABELS: Record<OwnerMemoryKind, string> = {
  identity: "身份",
  preference: "偏好",
  goal: "目标",
  project: "项目",
  workflow: "协作方式",
  constraint: "硬约束",
};

export function growthKindLabel(kind: string): string | undefined {
  if (kind in CARD_KIND_LABELS) {
    return CARD_KIND_LABELS[kind as KnowledgeCard["kind"]];
  }
  if (kind in OWNER_MEMORY_KIND_LABELS) {
    return OWNER_MEMORY_KIND_LABELS[kind as OwnerMemoryKind];
  }
  return undefined;
}

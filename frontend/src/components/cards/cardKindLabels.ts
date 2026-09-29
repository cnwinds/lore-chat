import type { KnowledgeCard } from "../../api";

export const CARD_KIND_LABELS: Record<KnowledgeCard["kind"], string> = {
  domain: "领域知识",
  owner_context: "主人在此",
  practice: "做法",
  lesson: "经验",
  audience: "受众",
};

export type BgChain = "utility" | "chat" | "embed";
export type BgNodeType = "trigger" | "llm" | "embed" | "code" | "turn" | "store";
export type BgTriggerKind = "schedule" | "event" | "manual";

export interface BgPromptVariant {
  id: string;
  label: string;
  system: string;
  user_template: string;
  notes: string[];
}

export interface BgConstant {
  label: string;
  value: string | number;
  source: string;
}

export interface BgNode {
  id: string;
  type: BgNodeType;
  title: string;
  subtitle: string;
  trigger_kind: BgTriggerKind | null;
  description: string;
  conditions: string[];
  limits: string[];
  chain: BgChain | null;
  temperature: number | null;
  purpose: string | null;
  prompts: BgPromptVariant[];
  guards: string[];
  outputs: string[];
  settings: string[];
  constants: BgConstant[];
  source_files: string[];
  links: { lane: string; label: string }[];
  pause_key: string | null;
}

export interface BgStep {
  kind: "trigger" | "stage" | "output";
  label: string | null;
  nodes: string[];
}

export interface BgLane {
  id: string;
  group: "auto" | "auto_turn" | "on_demand";
  title: string;
  summary: string;
  cadence: string;
  worker: string | null;
  pause_key: string | null;
  steps: BgStep[];
}

export interface BgSettingMeta {
  key: string;
  label: string;
  kind: "number";
  value: number;
  unit: string | null;
  min: number | null;
  max: number | null;
  step: number | null;
  hint: string;
}

export interface BgChainSummary {
  chain: BgChain;
  label: string;
  models: { label: string; model: string }[];
}

export interface BgPausable {
  key: string;
  label: string;
  hint: string;
}

export interface BgWorkerStatus {
  name: string;
  label: string;
  interval_seconds: number;
  running: boolean;
  last_run_at: string | null;
  last_active_at: string | null;
  last_result: Record<string, unknown> | null;
  last_error: string | null;
  last_error_at: string | null;
}

export interface BgPurposeStats {
  calls_24h: number;
  errors_24h: number;
  calls_7d: number;
  prompt_tokens_7d: number;
  completion_tokens_7d: number;
  cost_7d: number | null;
  last_call_at: string | null;
  last_status: string | null;
}

export interface BgStatus {
  generated_at: string;
  paused: string[];
  workers: Record<string, BgWorkerStatus>;
  backlog: {
    session_observe_pending: number;
    memory_dirty_conversations: number;
    embed_pending: number | null;
  };
  stats: Record<string, BgPurposeStats>;
  totals_24h: {
    calls: number;
    errors: number;
    prompt_tokens: number;
    completion_tokens: number;
    cost: number | null;
  };
}

export interface BgOverview {
  generated_at: string;
  groups: { id: "auto" | "auto_turn" | "on_demand"; title: string; hint: string }[];
  lanes: BgLane[];
  nodes: Record<string, BgNode>;
  settings: Record<string, BgSettingMeta>;
  chains: Record<BgChain, BgChainSummary>;
  pausable: BgPausable[];
  status: BgStatus;
}

export interface BgCallSummary {
  id: number;
  purpose: string;
  variant: string | null;
  ts: string;
  model: string | null;
  model_label: string | null;
  chain: BgChain | null;
  status: "ok" | "error";
  duration_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  conversation_id: string | null;
  scope: string | null;
  error: string | null;
}

export interface BgCallDetail extends BgCallSummary {
  params: Record<string, unknown>;
  messages: { role: string; content: string }[];
  response: string | null;
  response_truncated: boolean;
}

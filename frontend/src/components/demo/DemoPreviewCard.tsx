import { MarkdownContent } from "../MarkdownContent";

export type DemoPreview = {
  kind: "doc" | "doc_edit" | "doc_meta" | "memory";
  path?: string;
  content?: string;
  action?: string;
};

export function extractDemoPreview(toolResult: unknown): DemoPreview | null {
  if (!toolResult || typeof toolResult !== "object") return null;
  const record = toolResult as Record<string, unknown>;
  if (record.status !== "preview_only" && record.result_status !== "preview_only") {
    return null;
  }
  const preview = record.preview ?? record.demo_preview;
  if (!preview || typeof preview !== "object") return null;
  const p = preview as Record<string, unknown>;
  return {
    kind: p.kind as DemoPreview["kind"],
    path: typeof p.path === "string" ? p.path : undefined,
    content: typeof p.content === "string" ? p.content : undefined,
    action: typeof p.action === "string" ? p.action : undefined,
  };
}

const TITLES: Record<DemoPreview["kind"], string> = {
  doc: "将写入",
  doc_edit: "将局部编辑",
  doc_meta: "将更新元数据",
  memory: "将记住",
};

export function DemoPreviewCard({ preview }: { preview: DemoPreview }) {
  return (
    <div className="demo-preview-card">
      <div className="demo-preview-card__head">
        <strong>{TITLES[preview.kind]}</strong>
        {preview.path && <code>{preview.path}</code>}
        <span className="demo-preview-card__badge">演示环境 · 未落盘</span>
      </div>
      {preview.content && (
        <div className="demo-preview-card__body">
          <MarkdownContent text={preview.content} />
        </div>
      )}
    </div>
  );
}

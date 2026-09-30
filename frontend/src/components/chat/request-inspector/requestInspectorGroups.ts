import type { RequestDetail, RequestMessage, RequestSegment } from "../../../api";

export type ScrollTarget =
  | { kind: "segment"; messageIndex: number; segmentIndex: number }
  | { kind: "message"; messageIndex: number }
  | { kind: "tools"; toolIndex?: number };

export type CatalogLine = {
  id: string;
  label: string;
  tokens: number;
  category: string;
  target: ScrollTarget;
  summary?: string;
};

export type CatalogGroup = {
  id: string;
  title: string;
  defaultOpen: boolean;
  lines: CatalogLine[];
};

function firstLine(text: string, max = 48): string {
  const line = (text || "").split("\n")[0]?.trim() || "";
  return line.length > max ? `${line.slice(0, max)}…` : line;
}

function turnSpeaker(msg: RequestMessage): string {
  const ut = msg.segments.find((s) => s.kind === "user_text");
  return ut?.label ?? "主人";
}

export function buildCatalogGroups(detail: RequestDetail): CatalogGroup[] {
  const groups: CatalogGroup[] = [];
  const systemLines: CatalogLine[] = [];
  const historyLines: CatalogLine[] = [];
  let turnMsg: RequestMessage | null = null;
  const toolLines: CatalogLine[] = [];
  const injectLines: CatalogLine[] = [];

  for (const msg of detail.messages) {
    if (msg.role === "system" && !turnMsg) {
      msg.segments.forEach((seg, si) => {
        systemLines.push({
          id: `sys-${msg.index}-${si}`,
          label: seg.label,
          tokens: seg.tokens,
          category: seg.category,
          target: { kind: "segment", messageIndex: msg.index, segmentIndex: si },
        });
      });
      continue;
    }
    const histSeg = msg.segments.find((s) => s.kind === "history");
    if (histSeg) {
      historyLines.push({
        id: `hist-${msg.index}`,
        label: histSeg.label,
        tokens: msg.tokens,
        category: histSeg.category,
        target: { kind: "message", messageIndex: msg.index },
        summary: firstLine(histSeg.text),
      });
      continue;
    }
    if (msg.segments.some((s) => s.kind === "user_text")) {
      turnMsg = msg;
      continue;
    }
    if (msg.segments.some((s) => s.kind === "tool_call" || s.kind === "tool_result")) {
      const seg = msg.segments[0];
      toolLines.push({
        id: `toolio-${msg.index}`,
        label: seg?.label ?? msg.role,
        tokens: msg.tokens,
        category: "tool_io",
        target: { kind: "message", messageIndex: msg.index },
      });
      continue;
    }
    if (msg.segments.some((s) => s.kind === "inject")) {
      injectLines.push({
        id: `inject-${msg.index}`,
        label: "插话",
        tokens: msg.tokens,
        category: "turn",
        target: { kind: "message", messageIndex: msg.index },
        summary: firstLine(msg.segments.map((s) => s.text).join("")),
      });
    }
  }

  if (systemLines.length) {
    groups.push({
      id: "system",
      title: "system",
      defaultOpen: true,
      lines: systemLines,
    });
  }
  if (historyLines.length) {
    groups.push({
      id: "history",
      title: `历史 · ${historyLines.length} 条`,
      defaultOpen: false,
      lines: historyLines,
    });
  }
  if (turnMsg) {
    const speaker = turnSpeaker(turnMsg);
    groups.push({
      id: "turn",
      title: `本轮 · ${speaker}`,
      defaultOpen: true,
      lines: turnMsg.segments.map((seg, si) => ({
        id: `turn-${turnMsg!.index}-${si}`,
        label: seg.kind === "user_text" ? "正文" : seg.label,
        tokens: seg.tokens,
        category: seg.category,
        target: {
          kind: "segment",
          messageIndex: turnMsg!.index,
          segmentIndex: si,
        },
      })),
    });
  }
  if (toolLines.length) {
    groups.push({
      id: "tool_io",
      title: `工具往返 · ${toolLines.length} 次`,
      defaultOpen: true,
      lines: toolLines,
    });
  }
  if (injectLines.length) {
    groups.push({
      id: "inject",
      title: "插话",
      defaultOpen: true,
      lines: injectLines,
    });
  }
  if (detail.tools.length) {
    groups.push({
      id: "tools",
      title: `工具定义 · ${detail.tools.length} 个`,
      defaultOpen: false,
      lines: detail.tools.map((t, i) => ({
        id: `tooldef-${i}`,
        label: t.name || `工具 ${i + 1}`,
        tokens: t.tokens,
        category: "tools",
        target: { kind: "tools", toolIndex: i },
        summary: (t.description || "").split(/[。.!?\n]/)[0],
      })),
    });
  }
  return groups;
}

const JUMP_FLASH_CLASS = "chat-message-jump-flash";

export function scrollToAndFlash(el: Element | null | undefined): void {
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
  el.classList.add(JUMP_FLASH_CLASS);
  window.setTimeout(() => el.classList.remove(JUMP_FLASH_CLASS), 3000);
}

export function segmentDimmed(
  seg: RequestSegment,
  filter: string | null,
): boolean {
  return filter != null && seg.category !== filter;
}

import { useEffect, useRef } from "react";
import type { TimelineBlock } from "../api";
import {
  isNoiseProgressLine,
  joinProgressChunks,
  normalizeStreamChunk,
} from "../utils/progressLog";
import { stripLegacyEchoedPrompt } from "../utils/toolQuery";

type ToolBlock = Extract<TimelineBlock, { type: "tool" }>;

/** 将 progress_log 拼成终端正文（兼容旧「每项一行无尾换行」与流式块）。 */
export function sandboxTerminalBody(block: ToolBlock): string {
  const cmd = (block.query || "").trim();
  const raw = (block.progress_log || []).filter((l) => !isNoiseProgressLine(l));
  let output = joinProgressChunks(raw);

  // 旧数据：progress 里可能回显过 `$ cmd`；新后端不再写入。
  if (cmd && output) {
    output = stripLegacyEchoedPrompt(output, cmd);
  }

  const parts: string[] = [];
  if (cmd) parts.push(`$ ${cmd}`);
  if (output.trim()) {
    parts.push(output.replace(/^\n+/, "").replace(/\n+$/, ""));
  } else if (
    block.status !== "running" &&
    block.summary &&
    !isNoiseProgressLine(block.summary) &&
    !block.question_id
  ) {
    // summary 里可能是 "exit=0\\n..." 多行
    parts.push(normalizeStreamChunk(block.summary).trim());
  }
  return parts.join("\n");
}

/** 从 progress / summary 解析最后一次退出码；未能解析则 null。 */
export function parseSandboxExitCode(block: ToolBlock): number | null {
  const text = [...(block.progress_log || []), block.summary || ""].join("\n");
  const matches = [
    ...text.matchAll(/\[exit\s+(-?\d+)\]|exit[=:](-?\d+)/gi),
  ];
  if (!matches.length) return null;
  const m = matches[matches.length - 1];
  const raw = m[1] ?? m[2];
  if (raw === undefined) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

/** 边框色调：运行中 / 成功 / 失败；无法判断则空。 */
export function sandboxTerminalTone(
  block: ToolBlock,
): "live" | "ok" | "err" | "" {
  if (block.status === "running") return "live";
  const code = parseSandboxExitCode(block);
  if (code === null) return "";
  return code === 0 ? "ok" : "err";
}

export function SandboxTerminal({
  block,
}: {
  block: ToolBlock;
  /** 兼容旧调用；光标与边框以 block.status / exit 为准，忽略此值 */
  live?: boolean;
}) {
  const preRef = useRef<HTMLPreElement>(null);
  const stickRef = useRef(true);
  const body = sandboxTerminalBody(block);
  // 整轮仍在流式时父组件可能仍传 live，但已完成的沙箱不应再闪光标
  const running = block.status === "running";
  const tone = sandboxTerminalTone(block);

  useEffect(() => {
    const el = preRef.current;
    if (!el || !stickRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [body, running]);

  function onScroll() {
    const el = preRef.current;
    if (!el) return;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickRef.current = dist < 48;
  }

  if (!body && !running) return null;

  return (
    <div
      className={`timeline-sandbox-term${tone ? ` timeline-sandbox-term-${tone}` : ""}`}
    >
      <div className="timeline-sandbox-term-bar">
        <span className="timeline-sandbox-term-title">sandbox</span>
        <span className="timeline-sandbox-term-cwd">/workspace</span>
      </div>
      <pre
        ref={preRef}
        className="timeline-sandbox-term-body"
        onScroll={onScroll}
      >
        {body}
        {running ? (
          <span className="timeline-sandbox-term-cursor" aria-hidden />
        ) : null}
      </pre>
    </div>
  );
}

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

export function SandboxTerminal({
  block,
  live,
}: {
  block: ToolBlock;
  live?: boolean;
}) {
  const preRef = useRef<HTMLPreElement>(null);
  const stickRef = useRef(true);
  const body = sandboxTerminalBody(block);
  const running = live || block.status === "running";

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
      className={`timeline-sandbox-term${running ? " timeline-sandbox-term-live" : ""}`}
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
        {running ? <span className="timeline-sandbox-term-cursor" aria-hidden /> : null}
      </pre>
    </div>
  );
}

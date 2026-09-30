import type { RequestMessage, RequestSegment, RequestTool } from "../../../api";
import { countMatches } from "./searchHighlight";

// 渲染与搜索计数必须共用这些文本且顺序一致，否则「第 i 处」对不上高亮。

function prettyJson(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

export function segmentDisplayText(message: RequestMessage, seg: RequestSegment): string {
  return message.role === "tool" ? prettyJson(seg.text) : seg.text;
}

export function toolCallsText(message: RequestMessage): string {
  if (!message.tool_calls?.length) return "";
  return message.tool_calls
    .map((tc) => `${tc.name}(${JSON.stringify(tc.arguments, null, 2)})`)
    .join("\n");
}

export function toolParamsText(tool: RequestTool): string {
  return JSON.stringify(tool.parameters, null, 2);
}

export function messageSearchTexts(message: RequestMessage): string[] {
  return [
    ...message.segments.map((seg) => segmentDisplayText(message, seg)),
    toolCallsText(message),
  ];
}

export function toolSearchTexts(tool: RequestTool): string[] {
  return [tool.name || "", tool.description || "", toolParamsText(tool)];
}

export function countInTexts(texts: string[], query: string): number {
  return texts.reduce((n, text) => n + countMatches(text, query), 0);
}

export function textMatches(text: string, query: string): boolean {
  return countMatches(text, query) > 0;
}

import { MERGE_LINE_HEIGHT } from "./constants";

export function visibleLinesOf(clientHeight: number): number {
  return Math.max(1, Math.floor(clientHeight / MERGE_LINE_HEIGHT));
}

export function scrollTopForLine(line: number, clientHeight: number): number {
  return Math.max(
    0,
    (line - visibleLinesOf(clientHeight) / 2 + 0.5) * MERGE_LINE_HEIGHT,
  );
}

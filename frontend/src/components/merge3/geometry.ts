import { MERGE_LINE_HEIGHT } from "./constants";

export function visibleLinesOf(clientHeight: number): number {
  return Math.max(1, Math.floor(clientHeight / MERGE_LINE_HEIGHT));
}

/** 滚动位置 → 视口中心所在的行（与 scrollTopForLine 严格互逆，否则同步会漂移）。 */
export function centerLineOf(scrollTop: number, clientHeight: number): number {
  return Math.round(
    scrollTop / MERGE_LINE_HEIGHT + visibleLinesOf(clientHeight) / 2 - 0.5,
  );
}

/** 行 → 让该行居于视口中心的滚动位置。 */
export function scrollTopForLine(line: number, clientHeight: number): number {
  return Math.max(
    0,
    (line - visibleLinesOf(clientHeight) / 2 + 0.5) * MERGE_LINE_HEIGHT,
  );
}

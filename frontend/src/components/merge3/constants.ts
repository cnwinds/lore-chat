/** 三栏合并器的几何常量：CSS 里的行高与上下内边距必须与此保持一致。 */
export const MERGE_LINE_HEIGHT = 21;
export const MERGE_PAD_Y = 8;

export type PaneKey = "ours" | "result" | "theirs";

/** 行块在结果稿里的展示语气，供行背景与连接线共用。 */
export type ChunkTone =
  | "pending"
  | "resolved"
  | "ignored"
  | "rejected"
  | "custom"
  | "context";

/** 设置待办红点（侧栏 / Tab / 分区 / 价目行共用）。 */
export function SettingsAttentionDot({
  title = "需要处理",
}: {
  title?: string;
}) {
  return <span className="settings-attention-dot" title={title} aria-hidden />;
}

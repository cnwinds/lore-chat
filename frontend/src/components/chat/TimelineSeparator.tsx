type Props = {
  idleHours: number;
};

/** 角色时间线：段与段之间的分隔（超时/新话题，上文未带入）。 */
export function TimelineSeparator({ idleHours }: Props) {
  const n =
    Number.isFinite(idleHours) && idleHours > 0
      ? idleHours % 1 === 0
        ? String(idleHours)
        : idleHours.toFixed(1)
      : "6";
  return (
    <div className="chat-timeline-separator" role="separator">
      <span className="chat-timeline-separator-line" aria-hidden />
      <span className="chat-timeline-separator-label">
        间隔超过 {n} 小时 · 未带入上文
      </span>
      <span className="chat-timeline-separator-line" aria-hidden />
    </div>
  );
}

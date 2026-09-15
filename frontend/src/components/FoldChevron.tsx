type FoldChevronProps = {
  open: boolean;
  className?: string;
  /** end：收起朝右、展开朝下（手风琴 / 树）。down：收起朝下、展开朝上（下拉）。 */
  from?: "end" | "down";
  size?: number;
};

/** 折叠开合指示：细线圆角箭头，靠旋转表达状态，不用字符三角。 */
export function FoldChevron({
  open,
  className,
  from = "end",
  size = 12,
}: FoldChevronProps) {
  const classes = [
    "fold-chevron",
    from === "down" ? "fold-chevron--from-down" : "",
    open ? "is-open" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <span className={classes} aria-hidden>
      <svg
        viewBox="0 0 16 16"
        width={size}
        height={size}
        fill="none"
        aria-hidden
      >
        <path
          d="M5.4 3.2 11.2 8 5.4 12.8"
          stroke="currentColor"
          strokeWidth="1.55"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

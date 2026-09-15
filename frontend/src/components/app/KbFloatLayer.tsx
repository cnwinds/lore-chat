import type { MouseEvent, ReactNode } from "react";

type Props = {
  onClose: () => void;
  showBackdrop?: boolean;
  children: ReactNode;
};

/**
 * 聊天区左缘浮窗壳：媒体图库 / 记忆 / 文档 / 聊天通道共用。
 * 定位、遮罩、进场动画都走 `.doc-float-*`，内容自己用 `.kb-float-panel`。
 */
export function KbFloatLayer({
  onClose,
  showBackdrop = true,
  children,
}: Props) {
  function stop(e: MouseEvent) {
    e.stopPropagation();
  }

  return (
    <>
      {showBackdrop ? (
        <div className="doc-float-backdrop" aria-hidden onClick={onClose} />
      ) : null}
      <div className="doc-float-panel" onClick={stop} onMouseDown={stop}>
        {children}
      </div>
    </>
  );
}

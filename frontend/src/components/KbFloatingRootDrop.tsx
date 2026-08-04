import type { DragEvent } from "react";

type Props = {
  visible: boolean;
  active: boolean;
  uploadMode: boolean;
  onDragOver: (e: DragEvent) => void;
  onDrop: (e: DragEvent) => void;
};

/** 拖放/移动进行时，在知识库树顶部显示的根目录投放区。 */
export function KbFloatingRootDrop({
  visible,
  active,
  uploadMode,
  onDragOver,
  onDrop,
}: Props) {
  if (!visible) return null;

  return (
    <div className="kb-floating-root-drop-shell">
      <div className="kb-floating-root-drop-backdrop" aria-hidden />
      <div
        className={`kb-floating-root-drop${active ? " active" : ""}`}
        role="region"
        aria-label="根目录拖放区"
        onDragOver={onDragOver}
        onDrop={onDrop}
      >
        <span className="kb-floating-root-drop-title">根目录</span>
        <span className="kb-floating-root-drop-hint">
          {uploadMode ? "松手上传到根目录" : "松手移动到根目录"}
        </span>
      </div>
    </div>
  );
}

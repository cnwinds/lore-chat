import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { SKILLS_DIR } from "../utils/fileTree";

type Props = {
  open: boolean;
  candidates: string[];
  initiallySelected: string[];
  saving?: boolean;
  onConfirm: (selected: string[]) => void;
  onCancel: () => void;
};

export function SkillPickModal({
  open,
  candidates,
  initiallySelected,
  saving = false,
  onConfirm,
  onCancel,
}: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (open) {
      setSelected(new Set(initiallySelected));
    }
  }, [open, initiallySelected]);

  if (!open) return null;

  function toggle(path: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  function selectAll() {
    setSelected(new Set(candidates));
  }

  function selectNone() {
    setSelected(new Set());
  }

  return createPortal(
    <div className="modal-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="modal-panel skill-pick-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="skill-pick-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="skill-pick-title">默认启用的 Skill</h3>
        <p className="skill-pick-hint">
          勾选后跨会话生效：每次对话自动带上这些 Skill 的 name /
          description，命中后再读 SKILL.md。与文档托盘无关；要对某包改内容，请
          Ctrl+单击该包目录或文件加入托盘。
        </p>
        <div className="skill-pick-toolbar">
          <button type="button" className="btn-secondary" onClick={selectAll}>
            全选
          </button>
          <button type="button" className="btn-secondary" onClick={selectNone}>
            全不选
          </button>
        </div>
        {candidates.length === 0 ? (
          <p className="skill-pick-empty">
            「{SKILLS_DIR}」下未发现包含 SKILL.md 的包。
          </p>
        ) : (
          <ul className="skill-pick-list">
            {candidates.map((root) => (
              <li key={root}>
                <label>
                  <input
                    type="checkbox"
                    checked={selected.has(root)}
                    onChange={() => toggle(root)}
                    disabled={saving}
                  />
                  <span className="skill-pick-path">{root}</span>
                </label>
              </li>
            ))}
          </ul>
        )}
        <div className="modal-actions">
          <button
            type="button"
            className="btn-secondary"
            onClick={onCancel}
            disabled={saving}
          >
            取消
          </button>
          <button
            type="button"
            className="btn-primary"
            disabled={saving || candidates.length === 0}
            onClick={() => onConfirm([...selected])}
          >
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

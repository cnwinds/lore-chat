import { useEffect, useState } from "react";

type Props = {
  open: boolean;
  folderLabel: string;
  candidates: string[];
  maxSelectable: number;
  onConfirm: (selected: string[]) => void;
  onCancel: () => void;
};

export function SkillPickModal({
  open,
  folderLabel,
  candidates,
  maxSelectable,
  onConfirm,
  onCancel,
}: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (open) {
      setSelected(new Set(candidates));
    }
  }, [open, candidates]);

  if (!open) return null;

  function toggle(path: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else {
        if (next.size >= maxSelectable) {
          window.alert(`最多还能选 ${maxSelectable} 个 Skill`);
          return prev;
        }
        next.add(path);
      }
      return next;
    });
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="modal-panel skill-pick-modal"
        role="dialog"
        aria-labelledby="skill-pick-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="skill-pick-title">附加 Skill</h3>
        <p className="skill-pick-hint">
          在「{folderLabel || "根目录"}」下发现 {candidates.length} 个 Skill 包，请勾选要加入对话托盘的项。
        </p>
        {candidates.length === 0 ? (
          <p className="skill-pick-empty">未发现包含 SKILL.md 的子目录。</p>
        ) : (
          <ul className="skill-pick-list">
            {candidates.map((root) => (
              <li key={root}>
                <label>
                  <input
                    type="checkbox"
                    checked={selected.has(root)}
                    onChange={() => toggle(root)}
                  />
                  <span className="skill-pick-path">{root || "(根目录)"}</span>
                </label>
              </li>
            ))}
          </ul>
        )}
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>
            取消
          </button>
          <button
            type="button"
            className="btn-primary"
            disabled={candidates.length === 0 || selected.size === 0}
            onClick={() => onConfirm([...selected])}
          >
            加入托盘
          </button>
        </div>
      </div>
    </div>
  );
}

import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { SettingsAttentionDot } from "./SettingsAttentionDot";

type FoldSectionProps = {
  title: string;
  /** 折叠时展示的数量 */
  count: number;
  countUnit?: string;
  defaultOpen?: boolean;
  /** 需要用户处理时显示红点 */
  attention?: boolean;
  children: ReactNode;
};

/** 设置页大区块：默认折叠，标题旁显示条目数量。 */
export function SettingsFoldSection({
  title,
  count,
  countUnit = "项",
  defaultOpen = false,
  attention = false,
  children,
}: FoldSectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  useEffect(() => {
    if (defaultOpen) setOpen(true);
  }, [defaultOpen]);
  return (
    <section
      className={`settings-group settings-chain${open ? "" : " settings-group--folded"}`}
    >
      <button
        type="button"
        className="settings-fold-header"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="settings-fold-chevron" aria-hidden>
          {open ? "▾" : "▸"}
        </span>
        <span className="settings-fold-header-main">
          <span className="settings-group-title">
            {title}
            {attention ? <SettingsAttentionDot title="需要配置" /> : null}
          </span>
          <span className="settings-fold-count">
            {count} {countUnit}
          </span>
        </span>
      </button>
      {open ? <div className="settings-fold-body">{children}</div> : null}
    </section>
  );
}

/** 条目级折叠：默认全收起；新增 id 时自动展开以便填写。 */
export function useSettingsItemFold(ids: string[]) {
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const seen = useRef<Set<string> | null>(null);
  const idsKey = ids.join("\0");

  useEffect(() => {
    const list = idsKey ? idsKey.split("\0") : [];
    if (seen.current === null) {
      seen.current = new Set(list);
      return;
    }
    const added = list.filter((id) => !seen.current!.has(id));
    seen.current = new Set(list);
    if (!added.length) return;
    setExpanded((prev) => {
      const next = new Set(prev);
      for (const id of added) next.add(id);
      return next;
    });
  }, [idsKey]);

  function isOpen(id: string): boolean {
    return expanded.has(id);
  }

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return { isOpen, toggle };
}

type FoldToggleProps = {
  open: boolean;
  onToggle: () => void;
  title: string;
  priority?: number;
  primary?: boolean;
  titleAttr?: string;
};

/** 候选行左侧：折叠箭头 + 优先级 + 标题（点击展开/收起）。 */
export function SettingsCandidateFoldToggle({
  open,
  onToggle,
  title,
  priority,
  primary,
  titleAttr,
}: FoldToggleProps) {
  return (
    <button
      type="button"
      className="settings-candidate-fold-toggle"
      aria-expanded={open}
      onClick={onToggle}
      title={open ? "收起配置" : "展开配置"}
    >
      <span className="settings-fold-chevron" aria-hidden>
        {open ? "▾" : "▸"}
      </span>
      {priority != null ? (
        <span
          className={`settings-priority-badge${primary ? " settings-priority-badge--primary" : ""}`}
          title={primary ? "最高优先级" : `优先级 ${priority}`}
        >
          {priority}
        </span>
      ) : null}
      <span className="settings-candidate-name" title={titleAttr || title}>
        {title}
      </span>
    </button>
  );
}

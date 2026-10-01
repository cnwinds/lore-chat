import { useMemo, useState, useEffect } from "react";
import { putSettings } from "../../api";
import type { BgLane, BgNode, BgOverview } from "../../types/background";
import { pauseKeyLabel } from "./backgroundUtils";
import { showToast } from "../../utils/toast";

type Props = {
  node: BgNode;
  lane: BgLane | null;
  overview: BgOverview;
  pauseBusy: boolean;
  onPauseChange: (pauseKey: string, paused: boolean) => void;
  onSaved: () => void;
};

export function NodeConfigTab({
  node,
  lane,
  overview,
  pauseBusy,
  onPauseChange,
  onSaved,
}: Props) {
  const initial = useMemo(() => {
    const v: Record<string, number> = {};
    for (const key of node.settings) {
      const meta = overview.settings[key];
      if (meta) v[key] = meta.value;
    }
    return v;
  }, [node.settings, overview.settings]);

  const [draft, setDraft] = useState(initial);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraft(initial);
  }, [initial]);

  const dirtyKeys = node.settings.filter((key) => draft[key] !== initial[key]);

  const effectivePauseKey = node.pause_key ?? lane?.pause_key ?? null;
  const paused =
    effectivePauseKey != null &&
    overview.status.paused.includes(effectivePauseKey);
  const pauseLabel = effectivePauseKey
    ? pauseKeyLabel(overview.pausable, effectivePauseKey)
    : null;

  async function save() {
    if (dirtyKeys.length === 0) return;
    const patch: Record<string, number> = {};
    for (const key of dirtyKeys) patch[key] = draft[key];
    setSaving(true);
    try {
      await putSettings(patch);
      showToast("已保存");
      onSaved();
    } catch {
      showToast("保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      {effectivePauseKey && pauseLabel ? (
        <div className="bgflow-config-field">
          <label>
            <input
              type="checkbox"
              checked={paused}
              disabled={pauseBusy}
              aria-label={`暂停 ${pauseLabel}`}
              onChange={(e) => onPauseChange(effectivePauseKey, e.target.checked)}
            />{" "}
            暂停 {pauseLabel}
          </label>
        </div>
      ) : null}

      {node.settings.map((key) => {
        const meta = overview.settings[key];
        if (!meta) return null;
        return (
          <div key={key} className="bgflow-config-field">
            <label htmlFor={`bgflow-setting-${key}`}>
              {meta.label}
              {meta.unit ? `（${meta.unit}）` : ""}
            </label>
            <input
              id={`bgflow-setting-${key}`}
              type="number"
              value={draft[key] ?? meta.value}
              min={meta.min ?? undefined}
              max={meta.max ?? undefined}
              step={meta.step ?? undefined}
              onChange={(e) =>
                setDraft((d) => ({ ...d, [key]: Number(e.target.value) }))
              }
            />
            {meta.hint ? <p className="bgflow-config-hint">{meta.hint}</p> : null}
          </div>
        );
      })}

      {dirtyKeys.length > 0 ? (
        <button
          type="button"
          className="bgflow-open-flow-btn"
          disabled={saving}
          onClick={() => void save()}
        >
          {saving ? "保存中…" : "保存"}
        </button>
      ) : null}

      {node.constants.length > 0 ? (
        <div className="bgflow-detail-section">
          <h4>代码常量</h4>
          <table className="bgflow-constants-table">
            <thead>
              <tr>
                <th>名称</th>
                <th>值</th>
                <th>来源</th>
              </tr>
            </thead>
            <tbody>
              {node.constants.map((c) => (
                <tr key={c.source}>
                  <td>{c.label}</td>
                  <td>{String(c.value)}</td>
                  <td>{c.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </>
  );
}

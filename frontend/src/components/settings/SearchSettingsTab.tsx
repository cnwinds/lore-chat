import { clampWebSearchDefaultK } from "./settingsDrafts";

type Props = {
  minVectorScore: number;
  onMinVectorScoreChange: (v: number) => void;
  rrfK: number;
  onRrfKChange: (v: number) => void;
  laneCandidateK: number;
  onLaneCandidateKChange: (v: number) => void;
  webSearchDefaultK: number;
  onWebSearchDefaultKChange: (v: number) => void;
  saving: boolean;
};

/** 检索 tunables（与 IndexSubgraph.apply_settings 热应用对齐）。 */
export function SearchSettingsTab({
  minVectorScore,
  onMinVectorScoreChange,
  rrfK,
  onRrfKChange,
  laneCandidateK,
  onLaneCandidateKChange,
  webSearchDefaultK,
  onWebSearchDefaultKChange,
  saving,
}: Props) {
  return (
    <>
      <div className="settings-group">
        <h3 className="settings-group-title">检索参数</h3>
        <p className="settings-group-hint">控制知识库混合检索的召回与融合策略。</p>
        <label className="settings-field">
          <span>向量相似度下限</span>
          <input
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={minVectorScore}
            onChange={(e) => onMinVectorScoreChange(Number(e.target.value))}
            disabled={saving}
          />
        </label>
        <label className="settings-field">
          <span>RRF K</span>
          <input
            type="number"
            min="1"
            value={rrfK}
            onChange={(e) => onRrfKChange(Number(e.target.value))}
            disabled={saving}
          />
        </label>
        <label className="settings-field">
          <span>通道候选数</span>
          <input
            type="number"
            min="1"
            value={laneCandidateK}
            onChange={(e) => onLaneCandidateKChange(Number(e.target.value))}
            disabled={saving}
          />
        </label>
      </div>

      <div className="settings-group">
        <h3 className="settings-group-title">联网搜索</h3>
        <label className="settings-field">
          <span>默认条数</span>
          <input
            type="number"
            min={1}
            max={20}
            step={1}
            value={webSearchDefaultK}
            onChange={(e) =>
              onWebSearchDefaultKChange(
                clampWebSearchDefaultK(Number(e.target.value)),
              )
            }
            disabled={saving}
          />
        </label>
        <p className="settings-group-hint">
          Agent 调用 web_search 且未指定条数时使用；范围 1–20。搜索服务商在「模型」页签配置。
        </p>
      </div>
    </>
  );
}

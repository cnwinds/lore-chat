type Props = {
  minVectorScore: number;
  onMinVectorScoreChange: (v: number) => void;
  rrfK: number;
  onRrfKChange: (v: number) => void;
  laneCandidateK: number;
  onLaneCandidateKChange: (v: number) => void;
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
  saving,
}: Props) {
  return (
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
  );
}

import type { SkillHeaderEntry } from "../../utils/skillHeader";

type Props = {
  entries: SkillHeaderEntry[];
};

function renderValue(entry: SkillHeaderEntry) {
  if (Array.isArray(entry.value)) {
    if (entry.value.length === 0) return null;
    return (
      <ul className="skill-header-list">
        {entry.value.map((line, i) => (
          <li key={`${entry.key}-${i}`}>{line}</li>
        ))}
      </ul>
    );
  }
  if (entry.value.includes("\n")) {
    return <div className="skill-header-multiline">{entry.value}</div>;
  }
  return entry.value;
}

export function SkillHeaderTable({ entries }: Props) {
  if (entries.length === 0) {
    return (
      <div className="skill-header-panel" aria-label="Skill 触发头">
        <p className="skill-header-empty">
          触发头无法解析为字段，请切换到源码模式查看或修改。
        </p>
      </div>
    );
  }

  return (
    <div className="skill-header-panel" aria-label="Skill 触发头">
      <table className="skill-header-table">
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.key}>
              <th scope="row">{entry.label}</th>
              <td>{renderValue(entry)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

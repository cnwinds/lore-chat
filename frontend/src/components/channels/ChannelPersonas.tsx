import type { ApiPersona } from "../../api/openApi";

type Props = {
  personas: ApiPersona[];
  usage: Map<string, string[]>;
  busy: boolean;
  editingId: string | null;
  editName: string;
  editPrompt: string;
  creating: boolean;
  createName: string;
  createPrompt: string;
  onToggleCreate: () => void;
  onCreateName: (value: string) => void;
  onCreatePrompt: (value: string) => void;
  onCreate: () => void;
  onEditName: (value: string) => void;
  onEditPrompt: (value: string) => void;
  onStartEdit: (persona: ApiPersona) => void;
  onCancelEdit: () => void;
  onSave: (id: string) => void;
  onDelete: (id: string) => void;
};

export function ChannelPersonas({
  personas,
  usage,
  busy,
  editingId,
  editName,
  editPrompt,
  creating,
  createName,
  createPrompt,
  onToggleCreate,
  onCreateName,
  onCreatePrompt,
  onCreate,
  onEditName,
  onEditPrompt,
  onStartEdit,
  onCancelEdit,
  onSave,
  onDelete,
}: Props) {
  return (
    <div className="channel-personas">
      <p className="channel-panel-muted">
        多个通道可以共用一套提示词。改完下一轮都生效。
      </p>
      <ul className="openapi-persona-list">
        {personas.map((p) => {
          const used = usage.get(p.id)?.length || 0;
          const editing = editingId === p.id;
          return (
            <li key={p.id} className="openapi-persona">
              {editing ? (
                <div className="openapi-persona-edit">
                  <label className="settings-field">
                    <span>名称</span>
                    <input
                      type="text"
                      value={editName}
                      onChange={(e) => onEditName(e.target.value)}
                      disabled={busy}
                    />
                  </label>
                  <label className="settings-field">
                    <span>提示词</span>
                    <textarea
                      rows={3}
                      value={editPrompt}
                      onChange={(e) => onEditPrompt(e.target.value)}
                      disabled={busy}
                    />
                  </label>
                  <div className="openapi-card-actions">
                    <button
                      type="button"
                      className="settings-btn settings-btn--compact settings-btn--primary"
                      disabled={busy || !editName.trim()}
                      onClick={() => onSave(p.id)}
                    >
                      保存
                    </button>
                    <button
                      type="button"
                      className="openapi-btn"
                      disabled={busy}
                      onClick={onCancelEdit}
                    >
                      取消
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <div className="openapi-persona-main">
                    <strong>{p.name}</strong>
                    <span>{used > 0 ? `${used} 个通道在用` : "未被使用"}</span>
                  </div>
                  <div className="openapi-card-actions">
                    <button
                      type="button"
                      className="openapi-btn"
                      disabled={busy}
                      onClick={() => onStartEdit(p)}
                    >
                      编辑
                    </button>
                    <button
                      type="button"
                      className="openapi-btn openapi-btn--danger"
                      disabled={busy}
                      onClick={() => onDelete(p.id)}
                    >
                      删除
                    </button>
                  </div>
                </>
              )}
            </li>
          );
        })}
      </ul>
      {creating ? (
        <div className="openapi-persona-edit">
          <label className="settings-field">
            <span>名称</span>
            <input
              type="text"
              value={createName}
              onChange={(e) => onCreateName(e.target.value)}
              disabled={busy}
              placeholder="例如：客服语气"
            />
          </label>
          <label className="settings-field">
            <span>提示词</span>
            <textarea
              rows={3}
              value={createPrompt}
              onChange={(e) => onCreatePrompt(e.target.value)}
              disabled={busy}
              placeholder="怎么说话、做什么（可选）"
            />
          </label>
          <div className="openapi-card-actions">
            <button
              type="button"
              className="settings-btn settings-btn--compact settings-btn--primary"
              disabled={busy || !createName.trim()}
              onClick={onCreate}
            >
              创建
            </button>
            <button
              type="button"
              className="openapi-btn"
              disabled={busy}
              onClick={onToggleCreate}
            >
              取消
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          className="openapi-btn"
          disabled={busy}
          onClick={onToggleCreate}
        >
          新建共用角色
        </button>
      )}
    </div>
  );
}

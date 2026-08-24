import { useCallback, useEffect, useState } from "react";
import { listShares, revokeShare, type ShareLinkItem } from "../../api/share";
import { useCopyShareUrl } from "../../hooks/useShareLink";

function formatExp(exp: string | null): string {
  if (!exp) return "永久";
  const ms = Date.parse(exp);
  if (!Number.isFinite(ms)) return exp;
  if (ms <= Date.now()) return "已过期";
  return new Date(ms).toLocaleString();
}

export function ShareSettingsTab() {
  const copyUrl = useCopyShareUrl();
  const [items, setItems] = useState<ShareLinkItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    listShares()
      .then((res) => setItems(res.shares.filter((s) => !s.revoked)))
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "加载失败");
        setItems([]);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const handleCopy = async (item: ShareLinkItem) => {
    if (!item.url) return;
    const ok = await copyUrl(item.url);
    if (ok) {
      setCopiedId(item.share_id);
      window.setTimeout(() => setCopiedId(null), 2000);
    }
  };

  const handleRevoke = async (shareId: string) => {
    if (!window.confirm("确定撤销此分享链接？访客将无法再访问。")) return;
    try {
      await revokeShare(shareId);
      reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "撤销失败");
    }
  };

  if (loading) return <p className="settings-muted">加载分享列表…</p>;
  if (error) return <p className="settings-error">{error}</p>;
  if (!items.length) {
    return <p className="settings-muted">暂无有效分享链接。可在对话或文档预览中创建。</p>;
  }

  return (
    <div className="share-settings-tab">
      <table className="share-settings-table">
        <thead>
          <tr>
            <th>类型</th>
            <th>标题</th>
            <th>创建时间</th>
            <th>过期</th>
            <th>访问</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.share_id}>
              <td>{item.type === "conversation" ? "对话" : "文档"}</td>
              <td>{item.title}</td>
              <td>{new Date(item.created_at).toLocaleString()}</td>
              <td>{formatExp(item.exp)}</td>
              <td>{item.view_count}</td>
              <td className="share-settings-actions">
                <button
                  type="button"
                  className="btn-link"
                  disabled={!item.url}
                  onClick={() => void handleCopy(item)}
                >
                  {copiedId === item.share_id ? "已复制" : "复制"}
                </button>
                <button
                  type="button"
                  className="btn-link btn-link-danger"
                  onClick={() => void handleRevoke(item.share_id)}
                >
                  撤销
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

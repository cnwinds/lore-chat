import { useEffect, useState } from "react";
import { useDemoCapability } from "../../hooks/useDemoCapability";

const TOAST_MS = 2600;
const GITHUB_URL = "https://github.com/cnwinds/lore-chat";

/** 侧栏 Logo 旁的演示说明（替代原顶部整条横幅）。 */
export function DemoBrandBadge() {
  const { isDemo, canWrite } = useDemoCapability();
  if (!isDemo || canWrite) return null;

  return (
    <div className="demo-brand-badge" role="status">
      <span className="demo-brand-badge__meta">演示 · 只读 · 对话不保存</span>
      <a href={GITHUB_URL} target="_blank" rel="noreferrer">
        部署你自己的 Lore
      </a>
    </div>
  );
}

/** 只读拦截时的浮动提示。 */
export function DemoBanner() {
  const { isDemo, canWrite } = useDemoCapability();
  const [toast, setToast] = useState(false);

  useEffect(() => {
    let timer = 0;
    const onBlocked = () => {
      setToast(true);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setToast(false), TOAST_MS);
    };
    window.addEventListener("demo:read-only", onBlocked);
    return () => {
      window.removeEventListener("demo:read-only", onBlocked);
      window.clearTimeout(timer);
    };
  }, []);

  if (!isDemo || canWrite || !toast) return null;

  return <div className="demo-toast">演示环境不可修改</div>;
}

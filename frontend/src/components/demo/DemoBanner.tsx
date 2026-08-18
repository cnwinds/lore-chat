import { useEffect, useState } from "react";
import { useDemoCapability } from "../../hooks/useDemoCapability";

const TOAST_MS = 2600;

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

  if (!isDemo || canWrite) return null;

  return (
    <>
      <div className="demo-banner" role="status">
        <span>演示环境 · 只读 · 对话不会被保存</span>
        <a href="https://github.com/cnwinds/lore-chat" target="_blank" rel="noreferrer">
          部署你自己的 Lore
        </a>
      </div>
      {toast && <div className="demo-toast">演示环境不可修改</div>}
      <div className="demo-disclaimer">演示内容为虚构示例，人物与机构均非真实。</div>
    </>
  );
}

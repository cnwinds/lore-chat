import { useCallback, useEffect, useState } from "react";
import {
  getSettingsAttention,
  type SettingsAttention,
} from "../../api";

const EMPTY: SettingsAttention = {
  any: false,
  model: { any: false, chat: false, utility: false, embed: false },
  memory: { any: false, pending_count: 0 },
  usage: { any: false, incomplete_price_count: 0 },
};

/** 拉取设置红点；由调用方在打开/关闭设置、保存后主动 refresh。 */
export function useSettingsAttention(): {
  attention: SettingsAttention;
  refreshAttention: () => void;
} {
  const [attention, setAttention] = useState<SettingsAttention>(EMPTY);

  const refreshAttention = useCallback(() => {
    getSettingsAttention()
      .then((res) => {
        if (res?.attention) setAttention(res.attention);
      })
      .catch(() => {
        /* 红点失败不阻断主界面 */
      });
  }, []);

  useEffect(() => {
    refreshAttention();
  }, [refreshAttention]);

  return { attention, refreshAttention };
}

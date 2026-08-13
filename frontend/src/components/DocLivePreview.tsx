import { useEffect, useRef } from "react";
import { Crepe } from "@milkdown/crepe";
import "@milkdown/crepe/theme/common/style.css";
import { isMarkdownCosmeticallyEqual } from "../utils/docMarkdown";
import {
  restoreMarkdownImageSrcsForStorage,
  rewriteMarkdownImageSrcsForDisplay,
} from "../utils/kbImageUrls";

export type DocSelection = { start: number; end: number };

type Props = {
  /** 初始正文；仅在挂载时读取。切换文档请用 key 强制重新挂载。 */
  initialBody: string;
  onChange: (body: string) => void;
  /** 编辑器完成初始化并稳定后回调（用于对齐 saved 基线，避免误报 dirty） */
  onStable?: (body: string) => void;
  /** 用户主动编辑后回调（区分 Crepe 初始化与用户输入） */
  onUserEdit?: () => void;
  readOnly?: boolean;
};

export function DocLivePreview({
  initialBody,
  onChange,
  onStable,
  onUserEdit,
  readOnly = false,
}: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const crepeRef = useRef<Crepe | null>(null);
  const onChangeRef = useRef(onChange);
  const onStableRef = useRef(onStable);
  const onUserEditRef = useRef(onUserEdit);
  onChangeRef.current = onChange;
  onStableRef.current = onStable;
  onUserEditRef.current = onUserEdit;
  const readyRef = useRef(false);
  const lastMarkdownRef = useRef(initialBody);
  const initialBodyRef = useRef(initialBody);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const displayInitial = rewriteMarkdownImageSrcsForDisplay(initialBodyRef.current);
    const crepe = new Crepe({ root, defaultValue: displayInitial });
    crepe.on((listener) => {
      listener.markdownUpdated((_ctx, markdown) => {
        if (!readyRef.current) return;
        let stored: string;
        try {
          stored = restoreMarkdownImageSrcsForStorage(markdown);
        } catch {
          // 无法还原的 API 绝对链：不写回，避免污染 KB 正文
          return;
        }
        if (stored === lastMarkdownRef.current) return;
        const prev = lastMarkdownRef.current;
        lastMarkdownRef.current = stored;
        if (!isMarkdownCosmeticallyEqual(stored, prev)) {
          onUserEditRef.current?.();
        }
        onChangeRef.current(stored);
      });
    });
    crepe.setReadonly(readOnly);
    crepeRef.current = crepe;

    let destroyed = false;
    void crepe.create().then(() => {
      if (destroyed) {
        void crepe.destroy();
        return;
      }
      const md = (() => {
        try {
          return restoreMarkdownImageSrcsForStorage(crepe.getMarkdown());
        } catch {
          return initialBodyRef.current;
        }
      })();
      lastMarkdownRef.current = md;
      onStableRef.current?.(md);
      readyRef.current = true;
    });

    return () => {
      destroyed = true;
      readyRef.current = false;
      crepeRef.current = null;
      void crepe.destroy();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    crepeRef.current?.setReadonly(readOnly);
  }, [readOnly]);

  return <div className="doc-live-preview" ref={rootRef} />;
}

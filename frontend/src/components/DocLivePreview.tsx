import { useEffect, useRef } from "react";
import { Crepe } from "@milkdown/crepe";
import "@milkdown/crepe/theme/common/style.css";

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

    const crepe = new Crepe({ root, defaultValue: initialBodyRef.current });
    crepe.on((listener) => {
      listener.markdownUpdated((_ctx, markdown) => {
        if (!readyRef.current) return;
        if (markdown === lastMarkdownRef.current) return;
        lastMarkdownRef.current = markdown;
        onUserEditRef.current?.();
        onChangeRef.current(markdown);
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
      const md = crepe.getMarkdown();
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

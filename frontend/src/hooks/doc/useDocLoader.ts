import { useCallback, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { getDoc, type DocContent } from "../../api";
import type { DocSelection } from "../../components/DocLivePreview";

type UseDocLoaderOptions = {
  path: string;
  refreshKey: number;
  setSaveError: Dispatch<SetStateAction<string | null>>;
  setMergeEditing: Dispatch<SetStateAction<boolean>>;
  setSelection: Dispatch<SetStateAction<DocSelection>>;
};

export function useDocLoader({
  path,
  refreshKey,
  setSaveError,
  setMergeEditing,
  setSelection,
}: UseDocLoaderOptions) {
  const [doc, setDoc] = useState<DocContent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [body, setBody] = useState("");
  const [savedBody, setSavedBody] = useState("");
  const [loadedPath, setLoadedPath] = useState(path);
  const [previewRemountKey, setPreviewRemountKey] = useState(0);
  const loadGenRef = useRef(0);
  const lastRefreshKeyRef = useRef(refreshKey);
  const userEditedRef = useRef(false);

  const bumpPreviewRemount = useCallback(() => {
    setPreviewRemountKey((k) => k + 1);
  }, []);

  const loadDoc = useCallback(async (targetPath: string, gen: number) => {
    setLoading(true);
    setError(null);
    setSaveError(null);
    try {
      const d = await getDoc(targetPath);
      if (gen !== loadGenRef.current) return;
      setDoc(d);
      setBody(d.body);
      setSavedBody(d.body);
      setSelection({ start: d.body.length, end: d.body.length });
      setLoadedPath(targetPath);
      setMergeEditing(false);
      userEditedRef.current = false;
      setPreviewRemountKey((k) => k + 1);
    } catch (e) {
      if (gen !== loadGenRef.current) return;
      setDoc(null);
      setBody("");
      setSavedBody("");
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      if (gen === loadGenRef.current) setLoading(false);
    }
  }, [setMergeEditing, setSaveError, setSelection]);

  return {
    doc,
    setDoc,
    body,
    setBody,
    savedBody,
    setSavedBody,
    loading,
    error,
    loadedPath,
    loadDoc,
    loadGenRef,
    lastRefreshKeyRef,
    userEditedRef,
    previewRemountKey,
    bumpPreviewRemount,
  };
}

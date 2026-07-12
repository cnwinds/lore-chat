import { createContext, useContext } from "react";

export type DocPreviewContextValue = {
  previewPath: string | null;
  openDoc: (path: string, excerpt?: string, options?: { pin?: boolean }) => void;
  closeDoc: () => void;
  refreshKb: (changedPath?: string) => void;
};

const DocPreviewContext = createContext<DocPreviewContextValue | null>(null);

export function DocPreviewProvider({
  children,
  value,
}: {
  children: React.ReactNode;
  value: DocPreviewContextValue;
}) {
  return (
    <DocPreviewContext.Provider value={value}>{children}</DocPreviewContext.Provider>
  );
}

export function useDocPreview(): DocPreviewContextValue {
  const ctx = useContext(DocPreviewContext);
  if (!ctx) throw new Error("useDocPreview outside provider");
  return ctx;
}

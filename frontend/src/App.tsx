import { useState } from "react";
import { type SourceRef } from "./api";
import { Chat } from "./components/Chat";
import { SearchSnippetModal } from "./components/SearchSnippetModal";
import { MergeSourceQuestion } from "./components/MergeSourceQuestion";
import { AppShell } from "./components/app/AppShell";
import { DocFloatLayer } from "./components/app/DocFloatLayer";
import { DocPinnedPanel } from "./components/app/DocPinnedPanel";
import { DocPreviewProvider } from "./contexts/DocPreviewContext";
import { buildDocViewerHandlers } from "./hooks/app/buildDocViewerHandlers";
import { useAppEscapeKey } from "./hooks/app/useAppEscapeKey";
import { useConversationShell } from "./hooks/app/useConversationShell";
import { useDocPreviewLayout } from "./hooks/app/useDocPreviewLayout";
import { useKbFileSelection } from "./hooks/app/useKbFileSelection";
import { useMergeReviewSession } from "./hooks/app/useMergeReviewSession";

export default function App() {
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0);
  const [snippetSource, setSnippetSource] = useState<Extract<
    SourceRef,
    { type: "search" }
  > | null>(null);

  const refreshSidebar = () => setSidebarRefreshKey((k) => k + 1);
  const doc = useDocPreviewLayout(refreshSidebar);
  const selection = useKbFileSelection();
  const merge = useMergeReviewSession({
    previewPath: doc.previewPath,
    openDocPreview: doc.openDocPreview,
    closeDocPreview: doc.closeDocPreview,
    refreshKb: doc.refreshKb,
    setDocRefreshKey: doc.setDocRefreshKey,
    setSelectionMode: selection.setSelectionMode,
    clearSelection: selection.clearSelection,
  });
  const conversation = useConversationShell(
    sidebarRefreshKey,
    refreshSidebar,
    doc,
    selection,
    merge,
  );

  useAppEscapeKey(doc, selection, snippetSource, () => setSnippetSource(null));

  function handleOpenSource(src: SourceRef) {
    if (src.type === "kb") doc.openDocPreview(src.path, src.excerpt);
    else if (src.type === "web") window.open(src.url, "_blank", "noopener,noreferrer");
    else if (src.type === "search") setSnippetSource(src);
  }

  const docViewerHandlers = buildDocViewerHandlers(doc, merge, (id) => {
    conversation.setActiveConversationId(id);
    doc.requestCloseDocPreview();
  });

  return (
    <DocPreviewProvider value={doc.contextValue}>
      <AppShell
        panelFocus={Boolean(doc.panelFocus)}
        floatFocus={Boolean(doc.floatFocus)}
        hasMergeReview={merge.mergeReview !== null}
        mainFloatWide={doc.mainFloatWide}
        sidebarProps={conversation.sidebarProps}
        chat={
          <Chat
            conversationId={conversation.activeConversationId}
            onConversationCreated={(id) => {
              conversation.setActiveConversationId(id);
              refreshSidebar();
            }}
            onFirstQuestionTitle={(id, title) =>
              conversation.setTitleOverrides((prev) => ({ ...prev, [id]: title }))
            }
            onSidebarRefresh={refreshSidebar}
            onOpenSource={handleOpenSource}
          />
        }
        docFloat={
          doc.showFloat ? (
            <DocFloatLayer
              path={doc.previewPath!}
              refreshKey={doc.docRefreshKey}
              highlightText={doc.highlightText}
              docWidth={doc.docWidth}
              docFocus={doc.docFocus}
              showBackdrop={!doc.docFocus}
              onRequestClose={doc.requestCloseDocPreview}
              onPin={doc.pinDocPreview}
              {...docViewerHandlers}
            />
          ) : null
        }
        docPinned={
          doc.showPinned ? (
            <DocPinnedPanel
              path={doc.previewPath!}
              refreshKey={doc.docRefreshKey}
              highlightText={doc.highlightText}
              docWidth={doc.docWidth}
              docFocus={doc.docFocus}
              onUnpin={doc.unpinDocPreview}
              {...docViewerHandlers}
            />
          ) : null
        }
        modals={
          <>
            {merge.mergeSourceQuestion && (
              <MergeSourceQuestion
                mergeId={merge.mergeSourceQuestion.mergeId}
                newPath={merge.mergeSourceQuestion.newPath}
                sourcePaths={merge.mergeSourceQuestion.sourcePaths}
                onDone={() => {
                  if (doc.previewPath === merge.mergeSourceQuestion!.newPath) {
                    doc.setDocRefreshKey((k) => k + 1);
                  }
                  merge.setMergeSourceQuestion(null);
                  doc.refreshKb();
                }}
              />
            )}
            <SearchSnippetModal
              source={snippetSource}
              onClose={() => setSnippetSource(null)}
            />
          </>
        }
      />
    </DocPreviewProvider>
  );
}

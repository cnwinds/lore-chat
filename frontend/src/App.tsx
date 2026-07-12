import { useState } from "react";
import { type SourceRef } from "./api";
import { Chat } from "./components/Chat";
import { SearchSnippetModal } from "./components/SearchSnippetModal";
import { AppShell } from "./components/app/AppShell";
import { DocFloatLayer } from "./components/app/DocFloatLayer";
import { DocPinnedPanel } from "./components/app/DocPinnedPanel";
import { DocPreviewProvider } from "./contexts/DocPreviewContext";
import { buildDocViewerHandlers } from "./hooks/app/buildDocViewerHandlers";
import { useAppEscapeKey } from "./hooks/app/useAppEscapeKey";
import { useConversationShell } from "./hooks/app/useConversationShell";
import { useDocPreviewLayout } from "./hooks/app/useDocPreviewLayout";
import { useComposerDocState } from "./hooks/useComposerDocState";

export default function App() {
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0);
  const [snippetSource, setSnippetSource] = useState<Extract<
    SourceRef,
    { type: "search" }
  > | null>(null);

  const refreshSidebar = () => setSidebarRefreshKey((k) => k + 1);
  const doc = useDocPreviewLayout(refreshSidebar);
  const composer = useComposerDocState();

  function openDocWithComposer(
    path: string,
    excerpt?: string,
    options?: { pin?: boolean },
  ) {
    const title = path.split("/").pop() ?? path;
    if (!composer.paths.includes(path)) {
      composer.addToTray(path, title);
    }
    composer.setPrimary(path);
    doc.openDocPreview(path, excerpt, options);
  }

  function handleSelectFile(
    path: string,
    mods?: { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean },
  ) {
    const title = path.split("/").pop() ?? path;
    if (mods?.ctrlKey || mods?.metaKey || mods?.shiftKey) {
      composer.addToTray(path, title);
    } else {
      composer.replaceTray(path, title);
      openDocWithComposer(path, undefined, { pin: true });
    }
  }

  function handleTraySetPrimary(path: string) {
    composer.setPrimary(path);
    openDocWithComposer(path, undefined, { pin: true });
  }

  function handleTrayRemove(path: string) {
    const nextPrimary =
      composer.primaryPath !== path
        ? composer.primaryPath
        : (composer.items.find((i) => i.path !== path)?.path ?? null);
    composer.removeFromTray(path);
    if (doc.previewPath === path && nextPrimary === null) {
      doc.contextValue.closeDoc();
    }
  }

  const conversation = useConversationShell({
    sidebarRefreshKey,
    refreshSidebar,
    doc,
    composerPrimaryPath: composer.primaryPath,
    onSelectFile: handleSelectFile,
  });

  useAppEscapeKey(doc, snippetSource, () => setSnippetSource(null));

  function handleOpenSource(src: SourceRef) {
    if (src.type === "kb") openDocWithComposer(src.path, src.excerpt);
    else if (src.type === "web") {
      window.open(src.url, "_blank", "noopener,noreferrer");
    } else if (src.type === "search") {
      setSnippetSource(src);
    }
  }

  const docViewerHandlers = buildDocViewerHandlers(doc, (id) => {
    conversation.setActiveConversationId(id);
    doc.requestCloseDocPreview();
  });

  return (
    <DocPreviewProvider value={doc.contextValue}>
      <AppShell
        panelFocus={Boolean(doc.panelFocus)}
        floatFocus={Boolean(doc.floatFocus)}
        hasMergeReview={false}
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
            docTrayItems={composer.items}
            primaryDocPath={composer.primaryPath}
            docPaths={composer.paths}
            onTraySetPrimary={handleTraySetPrimary}
            onTrayRemove={handleTrayRemove}
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
          <SearchSnippetModal
            source={snippetSource}
            onClose={() => setSnippetSource(null)}
          />
        }
      />
    </DocPreviewProvider>
  );
}

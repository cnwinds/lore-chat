import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useChatConversation } from "../hooks/chat/useChatConversation";
import { useChatScroll } from "../hooks/chat/useChatScroll";
import { useAgentStream } from "../hooks/chat/useAgentStream";
import { createStreamOwnership } from "../hooks/chat/streamOwnership";
import { useConversationMemoryEvents } from "../hooks/chat/useConversationMemoryEvents";
import { useSendQueue } from "../hooks/chat/useSendQueue";
import { useOutboundOrchestrator } from "../hooks/chat/useOutboundOrchestrator";
import type { JumpTarget } from "../hooks/chat/useConversationJump";
import {
  planSearchJump,
  scrollToMessageHighlight,
} from "../hooks/chat/useConversationJump";
import {
  TIMELINE_AUTOFILL_MAX,
  TIMELINE_MESSAGE_TAIL_DESKTOP,
  TIMELINE_MESSAGE_TAIL_MOBILE,
  useRoleTimeline,
} from "../hooks/chat/useRoleTimeline";
import {
  getConversation,
  isMarkdownPath,
  normalizeDocContext,
  postRoomMessage,
  summarizeConversation,
  type DocContextItem,
  type IngestResult,
  type RoleSummary,
  type RoomParticipant,
  type SourceRef,
} from "../api";
import { useDocPreview } from "../contexts/DocPreviewContext";
import {
  canRetryAssistantReply,
  findPrecedingUserForRetry,
  isInjectedUserMessage,
  markToolBlockResolved,
  normalizeLoadedMessage,
} from "../utils/chatMessage";
import { nowIsoDisplay } from "../utils/displayTime";
import { newId } from "../utils/id";
import {
  readWebSearchEnabled,
  WEB_SEARCH_CHANGED_EVENT,
  writeWebSearchEnabled,
} from "../utils/webSearchPreference";
import {
  mergeGroupText,
  SEND_QUEUE_MAX,
  type SendQueueItem,
} from "../utils/sendQueue";
import { ConversationTranscriptPanel } from "./chat/ConversationTranscriptPanel";
import { ConversationComposerPanel } from "./chat/ConversationComposerPanel";
import { ArchiveConversationModal } from "./ArchiveConversationModal";
import type { DocTrayItem, PendingFile } from "../types/composer";
import { extractClipboardFiles } from "../utils/clipboard";
import { importChatAttachment } from "../utils/chatAttachmentImport";
import { useChatChainMediaCaps } from "../hooks/chat/useChatChainMediaCaps";
import {
  buildComposerMediaHints,
  validatePendingAttachments,
} from "../utils/chatAttachmentValidation";
import { suggestArchivePath } from "../utils/suggestArchivePath";
import { MobileChatHeader } from "./app/MobileChatHeader";
import { ChatRoleHeading } from "./chat/ChatRoleHeading";
import { GroupAvatar } from "./role/GroupAvatar";
import { mentionCandidatesForRoom } from "../utils/groupChatDisplay";
import { resolveMentionRoleIds } from "../utils/roleMentions";
import { MentionPicker } from "./chat/MentionPicker";
import { MENTION_PICKER_ID } from "./chat/mentionPickerIds";
import { useMentionPicker } from "../hooks/chat/useMentionPicker";

type ComposerDocItem = DocTrayItem;

const INPUT_MIN_HEIGHT = 34;
const INPUT_MAX_HEIGHT = 160;

type Props = {
  conversationId: string | null;
  roleId?: string | null;
  onConversationCreated?: (id: string) => void;
  onFirstQuestionTitle?: (id: string, title: string) => void;
  onSidebarRefresh?: () => void;
  onOpenSource?: (src: SourceRef) => void;
  onJumpToConversation?: (target: JumpTarget) => void;
  pendingJump?: JumpTarget | null;
  onJumpHandled?: () => void;
  docTrayItems?: ComposerDocItem[];
  primaryDocPath?: string | null;
  docContextItems?: DocContextItem[];
  onTraySetPrimary?: (path: string) => void;
  onTrayRemove?: (path: string) => void;
  onShareConversation?: () => void;
  mobileLayout?: boolean;
  mobileHeaderTitle?: string;
  onOpenMobileNav?: () => void;
  roles?: RoleSummary[];
  onSelectRole?: (id: string) => void;
  timelineRefreshKey?: number;
  roleConfigCollapsed?: boolean;
  onToggleRoleConfig?: () => void;
  /** 已加载会话不属于当前角色：父级应丢掉该会话 id，下次发送再新建 */
  onConversationRoleMismatch?: (conversationId: string, roleId: string) => void;
  roomMode?: "role" | "group";
  roomTitle?: string | null;
  roomAvatar?: string | null;
  roomParticipants?: RoomParticipant[];
  onRoomInterjectSent?: () => void;
  onOpenGroup?: (roomId: string) => void;
  onOpenGroupSettings?: () => void;
};

export function Chat({
  conversationId,
  roleId = null,
  onConversationCreated,
  onFirstQuestionTitle,
  onSidebarRefresh,
  onOpenSource,
  onJumpToConversation,
  pendingJump = null,
  onJumpHandled,
  docTrayItems = [],
  primaryDocPath = null,
  docContextItems = [],
  onTraySetPrimary,
  onTrayRemove,
  onShareConversation,
  mobileLayout = false,
  mobileHeaderTitle = "新对话",
  onOpenMobileNav,
  roles = [],
  onSelectRole,
  timelineRefreshKey = 0,
  roleConfigCollapsed = false,
  onToggleRoleConfig,
  onConversationRoleMismatch,
  roomMode = "role",
  roomTitle = null,
  roomAvatar = null,
  roomParticipants = [],
  onRoomInterjectSent,
  onOpenGroup,
  onOpenGroupSettings,
}: Props) {
  const { previewPath, openDoc, refreshKb } = useDocPreview();

  const [input, setInput] = useState("");
  const [caret, setCaret] = useState(0);
  const [archiving, setArchiving] = useState(false);
  const [archiveModalOpen, setArchiveModalOpen] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const {
    videoSupported: chatVideoSupported,
    maxVideos: chatMaxVideos,
    imageSupported: chatImageSupported,
    maxImages: chatMaxImages,
    videoWireData: chatVideoWireData,
  } = useChatChainMediaCaps();
  const [webEnabled, setWebEnabled] = useState(() => readWebSearchEnabled());
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mentionCandidates = useMemo(
    () =>
      mentionCandidatesForRoom({
        roomMode,
        roles,
        participants: roomParticipants,
      }),
    [roomMode, roles, roomParticipants],
  );
  const mentionPicker = useMentionPicker({
    input,
    caret,
    setInput,
    setCaret,
    textareaRef,
    candidates: mentionCandidates,
  });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const skipLoadRef = useRef<string | null>(null);
  const streamOwnership = useRef(createStreamOwnership()).current;
  const conversationIdRef = useRef(conversationId);
  const stickToBottomRef = useRef(true);
  const resumeActiveTurnRef = useRef<
    (cid: string, startedAt?: string | null) => Promise<boolean>
  >(async () => false);

  const messageTail = mobileLayout
    ? TIMELINE_MESSAGE_TAIL_MOBILE
    : TIMELINE_MESSAGE_TAIL_DESKTOP;

  const {
    msgs,
    setMsgs,
    loadingHistory,
    loadingOlderMessages,
    olderMessageCount,
    loadOlderMessages,
    summarized,
    setSummarized,
    summaryPath,
    setSummaryPath,
    respondingRoleId,
  } = useChatConversation({
    conversationId,
    roleId,
    skipLoadRef,
    streamOwnership,
    pendingJump,
    onJumpHandled,
    messageTail,
    onActiveTurn: (cid, startedAt) => {
      void resumeActiveTurnRef.current(cid, startedAt);
    },
    onRoleMismatch: onConversationRoleMismatch,
  });

  const {
    historicalSegments,
    continuityIdleHours,
    loading: loadingTimeline,
    loadingOlder,
    hasMore: timelineHasMore,
    loadOlder,
    revealAround,
  } = useRoleTimeline({
    roleId,
    tipConversationId: conversationId,
    messageLimit: messageTail,
    refreshKey: timelineRefreshKey,
    enabled: roomMode !== "group",
  });

  const loadingOlderContent = loadingOlder || loadingOlderMessages;
  const jumpedSegment = historicalSegments.find((s) => s.jumped);
  const displayHistorical = useMemo(() => {
    const tipIds = new Set(
      msgs.map((m) => m.id).filter((id): id is string => !!id),
    );
    if (!tipIds.size) return historicalSegments;
    return historicalSegments
      .map((seg) => {
        if (!seg.jumped) return seg;
        const messages = seg.messages.filter((m) => !m.id || !tipIds.has(m.id));
        return messages.length === seg.messages.length
          ? seg
          : { ...seg, messages };
      })
      .filter((seg) => !seg.jumped || seg.messages.length > 0);
  }, [historicalSegments, msgs]);
  const canLoadOlder = jumpedSegment
    ? jumpedSegment.olderMessageCount > 0
    : olderMessageCount > 0 ||
      (historicalSegments[0]?.olderMessageCount ?? 0) > 0 ||
      timelineHasMore;

  const loadOlderContent = useCallback(async () => {
    if (jumpedSegment) {
      return loadOlder();
    }
    if (olderMessageCount > 0) {
      return loadOlderMessages();
    }
    return loadOlder();
  }, [jumpedSegment, olderMessageCount, loadOlderMessages, loadOlder]);

  const revealKeyRef = useRef<string | null>(null);

  // 搜索命中：已在内存则滚过去；否则一次拉附近窗口，绝不顺着时间线翻到古代
  useEffect(() => {
    if (!pendingJump?.messageId) {
      revealKeyRef.current = null;
      return;
    }
    const key = `${pendingJump.conversationId}:${pendingJump.messageId}`;
    const decision = planSearchJump({
      pendingJump,
      msgs,
      historicalSegments: displayHistorical,
      loading: loadingTimeline || loadingHistory || loadingOlderContent,
      revealAttempted: revealKeyRef.current === key,
    });
    if (decision === "wait") return;
    if (decision === "settle") {
      onJumpHandled?.();
      return;
    }
    if (decision === "reveal") {
      revealKeyRef.current = key;
      void revealAround(pendingJump.conversationId, pendingJump.messageId);
      return;
    }
    const range =
      pendingJump.startChar !== undefined && pendingJump.endChar !== undefined
        ? { start: pendingJump.startChar, end: pendingJump.endChar }
        : undefined;
    const frame = requestAnimationFrame(() => {
      const ok = scrollToMessageHighlight(
        pendingJump.messageId!,
        range,
        pendingJump.offsetVersion,
      );
      if (ok) onJumpHandled?.();
    });
    return () => cancelAnimationFrame(frame);
  }, [
    pendingJump,
    msgs,
    displayHistorical,
    loadingTimeline,
    loadingHistory,
    loadingOlderContent,
    onJumpHandled,
    revealAround,
  ]);

  const sendQueue = useSendQueue(conversationId);

  const streamEndRef = useRef<(info: {
    failed: boolean;
    aborted: boolean;
    detached?: boolean;
    awaitingUser?: boolean;
  }) => void>(() => {});
  const injectDeferredRef = useRef<(id: string) => void>(() => {});
  const userInjectedRef = useRef<(id: string) => void>(() => {});

  const {
    streamingForView,
    reconciling,
    networkReconnectNeeded,
    liveElapsedMs,
    streamNowMs,
    streamingAssistantIdxRef,
    runAgentStream,
    resumeActiveTurn,
    retryNetworkReconcile,
    stopStreaming,
    ensureConversationId,
    resolveDocContext,
  } = useAgentStream({
    conversationId,
    roleId,
    previewPath,
    webEnabled,
    docContextItems,
    primaryDocPath,
    msgs,
    setMsgs,
    setSummarized,
    setSummaryPath,
    conversationIdRef,
    skipLoadRef,
    streamOwnership,
    stickToBottomRef,
    onConversationCreated,
    onFirstQuestionTitle,
    onSidebarRefresh,
    onKbChanged: refreshKb,
    onStreamEnd: (info) => streamEndRef.current(info),
    onInjectDeferred: (id) => injectDeferredRef.current(id),
    onUserInjected: (id) => userInjectedRef.current(id),
  });
  resumeActiveTurnRef.current = resumeActiveTurn;

  const runOutbound = useCallback(
    async (group: SendQueueItem[]) => {
      const text = mergeGroupText(group);
      const first = group[0];
      const docContext = normalizeDocContext(first.doc_context);
      const trayPaths = docContext.map((d) => d.path);
      return runAgentStream(
        text,
        text,
        {
          attachments: first.attachments?.length ? first.attachments : undefined,
          doc_context: docContext.length ? docContext : undefined,
          primary_doc: first.primary_doc ?? undefined,
        },
        {
          trayPaths,
          docContext,
          primary: first.primary_doc ?? null,
        },
        {
          webEnabled: first.webEnabled,
          reuseUserMessageId: first.reuseUserMessageId,
          replaceAssistantIndex: first.replaceAssistantIndex,
          mentions:
            roomMode === "group"
              ? resolveMentionRoleIds(text, roles)
              : undefined,
          assistantSpeaker:
            roomMode === "group"
              ? (() => {
                  const id = resolveMentionRoleIds(text, roles)[0];
                  const role = id ? roles.find((r) => r.id === id) : undefined;
                  return role
                    ? { id: role.id, name: role.name }
                    : undefined;
                })()
              : undefined,
        },
      );
    },
    [runAgentStream, roomMode, roles],
  );

  const outbound = useOutboundOrchestrator({
    sendQueue,
    streaming: streamingForView,
    streamingRef: streamOwnership.streamingRef,
    conversationIdRef,
    runOutbound,
  });
  streamEndRef.current = outbound.handleStreamEnd;
  injectDeferredRef.current = outbound.handleInjectDeferred;
  userInjectedRef.current = outbound.handleUserInjected;

  const { messagesContainerRef } = useChatScroll(
    [msgs, loadingHistory, streamingForView, displayHistorical],
    stickToBottomRef,
  );
  const { notice: memoryNotice, dismissNotice: dismissMemoryNotice } =
    useConversationMemoryEvents(conversationId);

  // 上滚接近顶部 → 续载更早段，并保持视口锚点
  useEffect(() => {
    const el = messagesContainerRef.current;
    if (!el) return;
    let busy = false;
    const onScroll = () => {
      if (busy || loadingOlderContent || loadingTimeline || !canLoadOlder) return;
      if (el.scrollTop > 80) return;
      busy = true;
      const prevHeight = el.scrollHeight;
      const prevTop = el.scrollTop;
      void loadOlderContent().then((loaded) => {
        requestAnimationFrame(() => {
          if (loaded) {
            el.scrollTop = prevTop + (el.scrollHeight - prevHeight);
          }
          busy = false;
        });
      });
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [
    messagesContainerRef,
    loadOlderContent,
    loadingOlderContent,
    loadingTimeline,
    canLoadOlder,
  ]);

  // 内容不足以溢出滚动时仍自动续载更早段（失败/无更多则停，防死循环）
  const autoFillAttemptsRef = useRef(0);
  useEffect(() => {
    autoFillAttemptsRef.current = 0;
  }, [roleId, conversationId, timelineRefreshKey]);
  useEffect(() => {
    const el = messagesContainerRef.current;
    if (!el || loadingOlderContent || loadingTimeline || !canLoadOlder) return;
    if (jumpedSegment) return;
    if (el.scrollHeight > el.clientHeight + 8) return;
    if (autoFillAttemptsRef.current >= TIMELINE_AUTOFILL_MAX) return;
    autoFillAttemptsRef.current += 1;
    void loadOlderContent();
  }, [
    jumpedSegment,
    historicalSegments,
    msgs,
    canLoadOlder,
    loadingOlderContent,
    loadingTimeline,
    loadOlderContent,
    messagesContainerRef,
  ]);

  // Sync before child effects load history so stream patches don't cross conversations.
  useLayoutEffect(() => {
    conversationIdRef.current = conversationId;
  }, [conversationId]);

  useEffect(() => {
    const onChange = (e: Event) => {
      const enabled = (e as CustomEvent<{ enabled?: boolean }>).detail?.enabled;
      setWebEnabled(
        typeof enabled === "boolean" ? enabled : readWebSearchEnabled(),
      );
    };
    window.addEventListener(WEB_SEARCH_CHANGED_EVENT, onChange);
    return () => window.removeEventListener(WEB_SEARCH_CHANGED_EVENT, onChange);
  }, []);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const next = Math.min(
      Math.max(el.scrollHeight, INPUT_MIN_HEIGHT),
      INPUT_MAX_HEIGHT,
    );
    el.style.height = `${next}px`;
    el.style.overflowY = el.scrollHeight > INPUT_MAX_HEIGHT ? "auto" : "hidden";
  }, [input]);

  function toggleWebSearch() {
    const next = !webEnabled;
    writeWebSearchEnabled(next);
    setWebEnabled(next);
  }

  async function send() {
    if (!input.trim() && pendingFiles.length === 0) return;
    const text = input.trim();
    if (!text && pendingFiles.length === 0) return;

    const filesToUpload = [...pendingFiles];
    const attachmentErr = validatePendingAttachments(filesToUpload, {
      maxVideos: chatMaxVideos,
      maxImages: chatMaxImages,
    });
    if (attachmentErr) {
      window.alert(attachmentErr);
      return;
    }
    const uploadedPaths: string[] = [];

    setInput("");
    if (filesToUpload.length > 0) {
      setPendingFiles([]);
      try {
        for (const pf of filesToUpload) {
          const rel = await importChatAttachment(pf.file);
          uploadedPaths.push(rel);
          refreshKb(rel);
        }
      } catch (err) {
        setPendingFiles(filesToUpload);
        setInput(text);
        const msg = err instanceof Error ? err.message : "上传失败";
        setMsgs((m) => [
          ...m,
          { role: "assistant", text: `错误：${msg}`, ts: nowIsoDisplay() },
        ]);
        return;
      }
    }

    const mentions =
      roomMode === "group" ? resolveMentionRoleIds(text, roles) : [];
    const mentionedRole = mentions[0]
      ? roles.find((r) => r.id === mentions[0])
      : undefined;

    if (roomMode === "group" && conversationId && mentions.length === 0) {
      try {
        await postRoomMessage(conversationId, { text, mentions: [] });
        const conv = await getConversation(conversationId);
        setMsgs(
          (conv.messages || []).map((m) =>
            normalizeLoadedMessage(m, {
              activeTurnRunning: conv.active_turn?.status === "running",
            }),
          ),
        );
        onRoomInterjectSent?.();
      } catch (err) {
        setInput(text);
        const msg = err instanceof Error ? err.message : "发送失败";
        setMsgs((m) => [
          ...m,
          { role: "assistant", text: `错误：${msg}`, ts: nowIsoDisplay() },
        ]);
      }
      return;
    }

    const ctx = resolveDocContext();
    if (
      ctx.docContext.length === 0 &&
      /[（(]*(几|两|\d+).*文档|合并|整合/.test(text)
    ) {
      setInput(text);
      window.alert(
        "请先在侧栏用 Ctrl+单击 将文件或目录加入工作托盘（顶层「技能」除外），再发送。",
      );
      return;
    }

    const shouldQueue = streamingForView || sendQueue.items.length > 0;
    if (!shouldQueue) {
      await runAgentStream(
        text,
        text,
        {
          attachments: uploadedPaths.length ? uploadedPaths : undefined,
          doc_context: ctx.docContext.length ? ctx.docContext : undefined,
          primary_doc: ctx.primary ?? undefined,
        },
        ctx,
        {
          webEnabled,
          mentions: mentions.length ? mentions : undefined,
          assistantSpeaker: mentionedRole
            ? { id: mentionedRole.id, name: mentionedRole.name }
            : undefined,
        },
      );
      return;
    }

    if (!conversationId) {
      try {
        await ensureConversationId();
      } catch (err) {
        setInput(text);
        const msg = err instanceof Error ? err.message : "创建对话失败";
        setMsgs((m) => [
          ...m,
          { role: "assistant", text: `错误：${msg}`, ts: nowIsoDisplay() },
        ]);
        return;
      }
    }

    const newItem: SendQueueItem = {
      id: newId(),
      text,
      timing: "defer",
      mergeWithNext: false,
      doc_context: ctx.docContext.length ? ctx.docContext : undefined,
      primary_doc: ctx.primary,
      attachments: uploadedPaths.length ? uploadedPaths : undefined,
      webEnabled,
      locked: false,
      error: null,
    };
    if (outbound.itemsRef.current.length >= SEND_QUEUE_MAX) {
      window.alert(`发送队列最多 ${SEND_QUEUE_MAX} 条`);
      setInput(text);
      return;
    }
    outbound.enqueueAndKick(newItem);
  }

  function handleStop() {
    stopStreaming();
    outbound.handleStop();
  }

  function handleContinue() {
    outbound.handleContinue();
  }

  function handleRetry() {
    outbound.handleRetry();
  }

  function handleSkipFailed() {
    outbound.handleSkipFailed();
  }

  async function handleRetryAssistantReply(assistantSourceIndex: number) {
    if (streamOwnership.streamingRef.current) return;
    let liveMsgs = msgs;
    let user = findPrecedingUserForRetry(liveMsgs, assistantSourceIndex);
    if (!user) return;
    const text = (user.text || "").trim();
    const attachments = user.attachments ?? [];
    if (!text && attachments.length === 0) return;

    let assistantIdx = assistantSourceIndex;
    let reuseId = user.id;
    if (!reuseId && conversationId) {
      try {
        const conv = await getConversation(conversationId);
        if (conversationIdRef.current !== conversationId) return;
        liveMsgs = conv.messages.map((m) =>
          normalizeLoadedMessage({
            ...m,
            injected: isInjectedUserMessage(m),
          }),
        );
        setMsgs(liveMsgs);
        for (let i = liveMsgs.length - 1; i >= 0; i--) {
          const m = liveMsgs[i];
          if (m.role !== "assistant" || !canRetryAssistantReply(m)) continue;
          const u = findPrecedingUserForRetry(liveMsgs, i);
          if (
            u?.id &&
            (u.text || "").trim() === text &&
            JSON.stringify(u.attachments ?? []) === JSON.stringify(attachments)
          ) {
            user = u;
            reuseId = u.id;
            assistantIdx = i;
            break;
          }
        }
      } catch {
        /* keep local state */
      }
    }
    if (!reuseId) {
      window.alert("无法定位原提问，请刷新后再试");
      return;
    }

    const docContext = normalizeDocContext(user.doc_context);
    const docCtx = {
      trayPaths: docContext.map((d) => d.path),
      docContext,
      primary: user.primary_doc ?? null,
    };
    const userMeta = {
      attachments: attachments.length ? attachments : undefined,
      doc_context: docContext.length ? docContext : undefined,
      primary_doc: user.primary_doc ?? undefined,
    };
    const replyWeb =
      typeof user.web_enabled === "boolean" ? user.web_enabled : webEnabled;

    const shouldQueue = streamingForView || sendQueue.items.length > 0;
    if (!shouldQueue) {
      void runAgentStream(text, text, userMeta, docCtx, {
        webEnabled: replyWeb,
        reuseUserMessageId: reuseId,
        replaceAssistantIndex: assistantIdx,
      });
      return;
    }

    const newItem: SendQueueItem = {
      id: newId(),
      text,
      timing: "defer",
      mergeWithNext: false,
      doc_context: userMeta.doc_context,
      primary_doc: user.primary_doc ?? null,
      attachments: userMeta.attachments,
      webEnabled: replyWeb,
      reuseUserMessageId: reuseId,
      replaceAssistantIndex: assistantIdx,
      locked: false,
      error: null,
    };
    if (outbound.itemsRef.current.length >= SEND_QUEUE_MAX) {
      window.alert(`发送队列最多 ${SEND_QUEUE_MAX} 条`);
      return;
    }
    outbound.enqueueAndKick(newItem);
  }

  function openArchiveModal() {
    if (!conversationId || streamingForView || archiving) return;
    if (!msgs.some((m) => m.role === "user")) return;
    setArchiveModalOpen(true);
  }

  async function performArchive(directory: string, filename: string) {
    if (!conversationId || streamingForView || archiving) return;
    const targetCid = conversationId;
    setArchiving(true);
    try {
      const result = await summarizeConversation(targetCid, { directory, filename });
      setArchiveModalOpen(false);
      if (conversationIdRef.current !== targetCid) {
        onSidebarRefresh?.();
        if (result.rel_path) refreshKb(result.rel_path);
        return;
      }
      const text =
        result.status === "saved" && result.rel_path
          ? `已把本次会话归档为文档：${result.rel_path}`
          : result.message || "归档完成";
      setMsgs((m) => [
        ...m,
        { role: "assistant", text, ts: nowIsoDisplay() },
      ]);
      if (result.rel_path) {
        setSummarized(true);
        setSummaryPath(result.rel_path);
        refreshKb(result.rel_path);
        openDoc(result.rel_path, undefined, { pin: true });
      }
      onSidebarRefresh?.();
    } catch (err) {
      if (conversationIdRef.current !== targetCid) {
        onSidebarRefresh?.();
        return;
      }
      const msg = err instanceof Error ? err.message : "归档失败";
      setMsgs((m) => [
        ...m,
        { role: "assistant", text: `错误：${msg}`, ts: nowIsoDisplay() },
      ]);
    } finally {
      setArchiving(false);
    }
  }

  const firstUserText =
    msgs.find((m) => m.role === "user")?.text?.trim() ?? "";
  const archiveDefaults = suggestArchivePath(summaryPath, firstUserText);

  function handleQuestionResolved(
    blockId: string,
    result: IngestResult,
    choiceLabel: string,
  ) {
    setMsgs((prev) => markToolBlockResolved(prev, blockId, choiceLabel));
    refreshKb(result.rel_path ?? undefined);

    if (result.status === "continue" && result.continue_prompt) {
      // Answering unpauses; the follow-up stream will auto-flush on done
      // unless it asks another question.
      outbound.pausedRef.current = false;
      sendQueue.setPaused(false);
      if (streamingForView || sendQueue.items.length > 0) {
        sendQueue.enqueue({
          text: result.continue_prompt,
          timing: "defer",
          webEnabled,
        });
        if (!streamingForView) void outbound.flushQueue();
      } else {
        void runAgentStream(result.continue_prompt, choiceLabel, undefined, undefined, {
          webEnabled,
        });
      }
      return;
    }
    // Resume deferred queue after the user answered.
    outbound.unpauseAndFlush();
    if (result.status === "saved" && result.message) {
      setMsgs((m) => [
        ...m,
        {
          role: "assistant",
          text: result.message,
          ts: nowIsoDisplay(),
        },
      ]);
      if (result.rel_path) {
        openDoc(result.rel_path, undefined, { pin: true });
      }
      return;
    }
    if (result.status === "acknowledged") {
      setMsgs((m) => [
        ...m,
        {
          role: "assistant",
          text: result.message,
          ts: nowIsoDisplay(),
        },
      ]);
    }
  }

  function addPendingFiles(files: File[]) {
    if (!files.length) return;
    const next = files.map((f) => ({
      id: `${Date.now()}-${f.name}-${newId()}`,
      file: f,
      name: f.name,
      size: f.size,
    }));
    const combined = [...pendingFiles, ...next];
    const attachmentErr = validatePendingAttachments(combined, {
      maxVideos: chatMaxVideos,
      maxImages: chatMaxImages,
    });
    if (attachmentErr) {
      window.alert(attachmentErr);
      return;
    }
    setPendingFiles(combined);
  }

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const list = e.target.files;
    if (!list?.length) return;
    addPendingFiles(Array.from(list));
    e.target.value = "";
  }

  function removePendingFile(id: string) {
    setPendingFiles((prev) => prev.filter((f) => f.id !== id));
  }

  function onInputPaste(e: React.ClipboardEvent<HTMLTextAreaElement>) {
    const files = extractClipboardFiles(e.clipboardData);
    if (!files.length) return;
    e.preventDefault();
    addPendingFiles(files);
  }

  function onInputKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (mentionPicker.handleKeyDown(e)) return;
    if (e.key !== "Enter") return;
    if (e.shiftKey) return;
    if (e.nativeEvent.isComposing) return;
    e.preventDefault();
    void send();
  }

  function handleOpenSource(src: SourceRef) {
    if (src.type === "conversation") {
      onJumpToConversation?.({
        conversationId: src.cid,
        ...(src.message_id ? { messageId: src.message_id } : {}),
        startChar: src.start_char,
        endChar: src.end_char,
        offsetVersion: src.offset_version,
      });
      return;
    }
    // 非 Markdown（含 SVG）交给 shell：灯箱预览 / 下载，勿当文档打开
    if (src.type === "kb" && src.path && !isMarkdownPath(src.path)) {
      onOpenSource?.(src);
      return;
    }
    if (src.type === "kb" && src.path) {
      openDoc(src.path, src.excerpt, { pin: true });
      return;
    }
    if (onOpenSource) {
      onOpenSource(src);
    } else if (src.type === "web" || src.type === "search") {
      window.open(src.url, "_blank", "noopener,noreferrer");
    }
  }

  function handleOpenConversation(target: {
    conversationId: string;
    messageId?: string;
  }) {
    onJumpToConversation?.({
      conversationId: target.conversationId,
      ...(target.messageId ? { messageId: target.messageId } : {}),
    });
  }

  const composerMediaHints = useMemo(
    () =>
      buildComposerMediaHints(pendingFiles, {
        videoSupported: chatVideoSupported,
        maxVideos: chatMaxVideos,
        imageSupported: chatImageSupported,
        maxImages: chatMaxImages,
        videoWireData: chatVideoWireData,
      }),
    [
      pendingFiles,
      chatVideoSupported,
      chatMaxVideos,
      chatImageSupported,
      chatMaxImages,
      chatVideoWireData,
    ],
  );

  const activeRole = roles.find((r) => r.id === roleId) ?? null;
  const headerTitle =
    roomMode === "group"
      ? roomTitle || "群聊"
      : activeRole?.name || mobileHeaderTitle || "对话";
  return (
    <div className={`chat-panel${mobileLayout ? " chat-panel--mobile" : ""}`}>
      {mobileLayout && onOpenMobileNav && (
        <MobileChatHeader
          title={headerTitle}
          onOpenNav={onOpenMobileNav}
          onShare={onShareConversation}
          roles={roles}
          activeRoleId={roleId}
          onSelectRole={roomMode === "group" ? undefined : onSelectRole}
          roomMode={roomMode}
          roomAvatar={roomAvatar}
          roomParticipants={roomParticipants}
        />
      )}
      {!mobileLayout && (
        <header className="chat-desktop-header">
          <h1 className="chat-desktop-header-title">
            {roomMode === "group" ? (
              <span className="chat-role-heading">
                <GroupAvatar
                  name={headerTitle}
                  seed={conversationId || headerTitle}
                  avatar={roomAvatar}
                  members={roomParticipants}
                  size={22}
                />
                <span className="chat-role-heading-name">{headerTitle}</span>
              </span>
            ) : (
              <ChatRoleHeading
                name={headerTitle}
                roleId={activeRole?.id || roleId}
                avatar={activeRole?.avatar}
              />
            )}
          </h1>
          {roomMode === "group" && onOpenGroupSettings ? (
            <div className="chat-desktop-header-actions">
              <button
                type="button"
                className="chat-desktop-header-btn"
                onClick={onOpenGroupSettings}
                title="群设置"
                aria-label="群设置"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.8" />
                  <path
                    d="M12 4v2M12 18v2M4 12h2M18 12h2M6.3 6.3l1.4 1.4M16.3 16.3l1.4 1.4M6.3 17.7l1.4-1.4M16.3 7.7l1.4-1.4"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                  />
                </svg>
              </button>
            </div>
          ) : roleConfigCollapsed && onToggleRoleConfig ? (
            <div className="chat-desktop-header-actions">
              <button
                type="button"
                className="chat-desktop-header-btn"
                onClick={onToggleRoleConfig}
                title="展开角色设置"
                aria-label="展开角色设置"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <path
                    d="M15 6l-6 6 6 6M10 6l-6 6 6 6"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </div>
          ) : null}
        </header>
      )}
      <ConversationTranscriptPanel
        msgs={msgs}
        historicalSegments={displayHistorical}
        continuityIdleHours={continuityIdleHours}
        timelineHasMore={canLoadOlder}
        loadingOlder={loadingOlderContent}
        loadingHistory={loadingHistory}
        streaming={streamingForView}
        reconciling={reconciling}
        networkReconnectNeeded={networkReconnectNeeded}
        onNetworkReconnect={() => {
          void retryNetworkReconcile();
        }}
        liveElapsedMs={liveElapsedMs}
        streamNowMs={streamNowMs}
        streamingAssistantIdxRef={streamingAssistantIdxRef}
        messagesContainerRef={messagesContainerRef}
        messagesEndRef={messagesEndRef}
        previewPath={previewPath}
        conversationId={conversationId}
        onOpenSource={handleOpenSource}
        onOpenConversation={handleOpenConversation}
        onQuestionResolved={handleQuestionResolved}
        onRetryReply={handleRetryAssistantReply}
        outlineLayout={mobileLayout ? "sheet" : "rail"}
        roles={roles}
        onRoomInterjectSent={onRoomInterjectSent}
        onOpenGroup={onOpenGroup}
        roomMode={roomMode}
        respondingRoleId={respondingRoleId}
        memoryNotice={memoryNotice}
        onDismissMemoryNotice={dismissMemoryNotice}
      />
      <ConversationComposerPanel
        sendQueueItems={sendQueue.items}
        sendQueuePaused={sendQueue.paused}
        onContinue={handleContinue}
        onRetry={handleRetry}
        onSkipFailed={handleSkipFailed}
        onUpdateQueueText={(id, text) => sendQueue.updateItem(id, { text })}
        onSetQueueTiming={sendQueue.setItemTiming}
        onToggleQueueMerge={(id) => {
          const item = sendQueue.items.find((x) => x.id === id);
          if (!item) return;
          const idx = sendQueue.items.findIndex((x) => x.id === id);
          const nextItem = sendQueue.items[idx + 1];
          const merge = !item.mergeWithNext;
          if (merge && nextItem && nextItem.timing !== item.timing) {
            sendQueue.setItemTiming(nextItem.id, item.timing);
          }
          sendQueue.updateItem(id, { mergeWithNext: merge });
        }}
        onRemoveQueueItem={sendQueue.removeItem}
        onMoveQueueItem={sendQueue.moveItem}
        onSetAllQueueTiming={sendQueue.setAllTiming}
        onSetAllQueueMerge={sendQueue.setAllMerge}
        onClearQueue={sendQueue.clear}
        docTrayItems={docTrayItems}
        primaryDocPath={primaryDocPath}
        pendingFiles={pendingFiles}
        composerMediaHints={composerMediaHints}
        onTraySetPrimary={onTraySetPrimary ?? (() => {})}
        onTrayRemove={onTrayRemove ?? (() => {})}
        onRemovePendingFile={removePendingFile}
        input={input}
        onInputChange={(value) => {
          setInput(value);
          setCaret(textareaRef.current?.selectionStart ?? value.length);
        }}
        onCaretSync={() => {
          setCaret(textareaRef.current?.selectionStart ?? input.length);
        }}
        mentionSlot={
          mentionPicker.open ? (
            <MentionPicker
              roles={mentionPicker.hits}
              query={mentionPicker.mention?.query || ""}
              selectedIndex={mentionPicker.selectedIndex}
              onHover={mentionPicker.setSelectedIndex}
              onPick={mentionPicker.apply}
            />
          ) : null
        }
        mentionOpen={mentionPicker.open}
        mentionListId={MENTION_PICKER_ID}
        mentionActiveId={mentionPicker.activeOptionId}
        onInputKeyDown={onInputKeyDown}
        onInputPaste={onInputPaste}
        textareaRef={textareaRef}
        webEnabled={webEnabled}
        onToggleWeb={toggleWebSearch}
        streaming={streamingForView}
        canSend={!!input.trim() || pendingFiles.length > 0}
        archiving={archiving}
        conversationId={conversationId}
        summarized={summarized}
        summaryPath={summaryPath}
        canArchive={msgs.some((m) => m.role === "user")}
        onArchive={openArchiveModal}
        onOpenSummary={(path) => openDoc(path, undefined, { pin: true })}
        onAttachClick={() => fileInputRef.current?.click()}
        onSend={send}
        onStop={handleStop}
        fileInputRef={fileInputRef}
        onFileChange={onFile}
        onShare={onShareConversation}
      />
      <ArchiveConversationModal
        open={archiveModalOpen}
        initialDirectory={archiveDefaults.directory}
        initialFilename={archiveDefaults.filename}
        submitting={archiving}
        onClose={() => !archiving && setArchiveModalOpen(false)}
        onConfirm={(directory, filename) => void performArchive(directory, filename)}
      />
    </div>
  );
}

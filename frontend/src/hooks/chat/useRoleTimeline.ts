import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getConversation,
  getConversationMessages,
  getRoleTimeline,
  type ChatMessage,
  type RoleTimelineSegment,
} from "../../api";
import {
  isInjectedUserMessage,
  normalizeLoadedMessage,
} from "../../utils/chatMessage";

/** 首屏不拉历史段（只要 tip）；上滚每次续 1 段 */
export const TIMELINE_FIRST_PAGE_SIZE = 0;
export const TIMELINE_PAGE_SIZE = 1;
export const TIMELINE_MESSAGE_TAIL_DESKTOP = 12;
export const TIMELINE_MESSAGE_TAIL_MOBILE = 8;
/** 内容撑不满一屏时自动续载的次数上限，避免短气泡把整条时间线拉齐 */
export const TIMELINE_AUTOFILL_MAX = 4;
/** 搜索跳转：锚点前后各这么多条，禁止为定位去拉全量 */
export const SEARCH_JUMP_RADIUS = 16;

function normalizeSegmentMessages(
  messages: ChatMessage[] | undefined,
  activeTurnRunning: boolean,
): ChatMessage[] {
  return (messages || []).map((m) =>
    normalizeLoadedMessage(
      {
        ...m,
        injected: isInjectedUserMessage(m),
      },
      { activeTurnRunning },
    ),
  );
}

export type TimelineSegmentView = {
  conversationId: string;
  roleId?: string;
  title: string;
  createdAt: string;
  messages: ChatMessage[];
  isTip: boolean;
  olderMessageCount: number;
  newerMessageCount?: number;
  /** 搜索定位插入的附近窗口；可与当前 tip 同会话并存 */
  jumped?: boolean;
  kind?: string;
  peerRoleId?: string | null;
};

function toView(
  seg: RoleTimelineSegment,
  tipId: string | null,
  roleId: string,
): TimelineSegmentView | null {
  const msgs = normalizeSegmentMessages(
    seg.messages,
    seg.active_turn?.status === "running",
  );
  const isTip = !!tipId && seg.id === tipId;
  if (!isTip && msgs.length === 0) return null;
  if (isTip) return null; // tip 消息由 useChatConversation 维护
  const isRoom = seg.kind === "peer_dm" || seg.kind === "group";
  const segRole = seg.role_id || roleId;
  if (!isRoom && segRole && segRole !== roleId) return null;
  return {
    conversationId: seg.id,
    roleId: segRole,
    title: seg.title,
    createdAt: seg.created_at,
    messages: msgs,
    isTip: false,
    olderMessageCount: seg.older_message_count ?? 0,
    kind: seg.kind,
    peerRoleId: seg.peer_role_id,
  };
}

type Options = {
  roleId: string | null;
  tipConversationId: string | null;
  /** 每段只取尾部若干条；手机更少 */
  messageLimit?: number;
  /** 新话题等强制重置近端窗口 */
  refreshKey?: number;
};

/**
 * 角色时间线：首屏不拉历史段；上滚先补当前最旧段更早消息，再续更早段。
 */
export function useRoleTimeline({
  roleId,
  tipConversationId,
  messageLimit = TIMELINE_MESSAGE_TAIL_DESKTOP,
  refreshKey = 0,
}: Options) {
  const [segments, setSegments] = useState<TimelineSegmentView[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [continuityIdleHours, setContinuityIdleHours] = useState(6);
  const genRef = useRef(0);
  const roleRef = useRef(roleId);
  roleRef.current = roleId;
  const tipRef = useRef(tipConversationId);
  tipRef.current = tipConversationId;
  const tipMetaRef = useRef<{ createdAt: string; id: string } | null>(null);
  const messageLimitRef = useRef(messageLimit);
  messageLimitRef.current = messageLimit;

  const rememberTipMeta = (tl: {
    tip_conversation_id: string;
    segments: RoleTimelineSegment[];
  }) => {
    const serverTip = tl.tip_conversation_id;
    const localTip = tipRef.current;
    const tipId =
      localTip &&
      (localTip === serverTip || tl.segments.some((s) => s.id === localTip))
        ? localTip
        : serverTip;
    const tipSeg =
      tl.segments.find((s) => s.id === tipId) ||
      tl.segments.find((s) => s.id === serverTip);
    if (tipSeg) {
      tipMetaRef.current = { createdAt: tipSeg.created_at, id: tipSeg.id };
      return;
    }
    if (tipMetaRef.current?.id !== tipId) {
      tipMetaRef.current = null;
    }
  };

  const resetAndLoadRecent = useCallback(async () => {
    // 先丢掉上一角色的段和 tip 游标，避免切到「通用」时用别人的会话当 before
    tipMetaRef.current = null;
    setSegments([]);
    setHasMore(false);
    if (!roleId) {
      return;
    }
    const gen = ++genRef.current;
    setLoading(true);
    try {
      const tl = await getRoleTimeline(roleId, {
        includeMessages: false,
        limit: TIMELINE_FIRST_PAGE_SIZE,
      });
      if (gen !== genRef.current || roleRef.current !== roleId) return;
      rememberTipMeta(tl);
      setHasMore(!!tl.has_more);
      setContinuityIdleHours(tl.continuity_idle_hours ?? 6);
    } catch {
      if (gen === genRef.current) {
        setHasMore(false);
      }
    } finally {
      if (gen === genRef.current) setLoading(false);
    }
  }, [roleId]);

  useEffect(() => {
    void resetAndLoadRecent();
  }, [resetAndLoadRecent, refreshKey, tipConversationId]);

  const loadOlder = useCallback(async () => {
    if (!roleId || loadingOlder || loading) return false;

    const jumped = segments.find((s) => s.jumped && s.roleId === roleId);
    const oldest = jumped ?? segments.find((s) => s.roleId === roleId) ?? null;
    if (oldest?.olderMessageCount && oldest.messages[0]?.id) {
      const gen = genRef.current;
      setLoadingOlder(true);
      try {
        const page = await getConversationMessages(oldest.conversationId, {
          beforeId: oldest.messages[0].id,
          limit: messageLimitRef.current,
        });
        if (gen !== genRef.current || roleRef.current !== roleId) return false;
        setSegments((prev) =>
          prev.map((s) => {
            if (
              s.conversationId !== oldest.conversationId ||
              !!s.jumped !== !!oldest.jumped
            ) {
              return s;
            }
            const seen = new Set(
              s.messages.map((m) => m.id).filter((id): id is string => !!id),
            );
            const prepend = normalizeSegmentMessages(page.messages, false).filter(
              (m) => !m.id || !seen.has(m.id),
            );
            return {
              ...s,
              messages: [...prepend, ...s.messages],
              olderMessageCount: page.older_message_count,
            };
          }),
        );
        return true;
      } catch {
        return false;
      } finally {
        if (gen === genRef.current) setLoadingOlder(false);
      }
    }

    // 搜索窗口耗尽后停住：不要为补齐定位再去走整条角色时间线
    if (oldest?.jumped) return false;

    if (!hasMore) return false;

    const gen = genRef.current;
    setLoadingOlder(true);
    try {
      const before = oldest
        ? { beforeCreatedAt: oldest.createdAt, beforeId: oldest.conversationId }
        : tipMetaRef.current
          ? {
              beforeCreatedAt: tipMetaRef.current.createdAt,
              beforeId: tipMetaRef.current.id,
            }
          : {};
      const tl = await getRoleTimeline(roleId, {
        limit: TIMELINE_PAGE_SIZE,
        messageLimit: messageLimitRef.current,
        ...before,
      });
      if (gen !== genRef.current || roleRef.current !== roleId) return false;
      rememberTipMeta(tl);
      const tipId = tipRef.current || tl.tip_conversation_id;
      const older = tl.segments
        .map((s) => toView(s, tipId, roleId))
        .filter((v): v is TimelineSegmentView => !!v);
      if (older.length === 0) {
        setHasMore(false);
        return false;
      }
      setSegments((prev) => {
        const kept = prev.filter((p) => p.roleId === roleId);
        const seen = new Set(kept.map((p) => p.conversationId));
        return [
          ...older.filter((o) => !seen.has(o.conversationId)),
          ...kept,
        ];
      });
      setHasMore(!!tl.has_more);
      return true;
    } catch {
      if (gen === genRef.current && roleRef.current === roleId) {
        setHasMore(false);
      }
      return false;
    } finally {
      if (gen === genRef.current) {
        setLoadingOlder(false);
      }
    }
  }, [roleId, loadingOlder, loading, hasMore, segments]);

  const revealAround = useCallback(
    async (conversationId: string, messageId: string) => {
      if (!roleId) return false;
      const gen = genRef.current;
      setLoadingOlder(true);
      try {
        const conv = await getConversation(conversationId, {
          aroundId: messageId,
          radius: SEARCH_JUMP_RADIUS,
        });
        if (gen !== genRef.current || roleRef.current !== roleId) return false;
        if (conv.role_id && conv.role_id !== roleId) return false;
        const segment: TimelineSegmentView = {
          conversationId,
          roleId: conv.role_id || roleId,
          title: conv.title,
          createdAt: conv.created_at,
          messages: normalizeSegmentMessages(conv.messages, false),
          isTip: false,
          olderMessageCount: conv.older_message_count ?? 0,
          newerMessageCount: conv.newer_message_count ?? 0,
          jumped: true,
        };
        setSegments([segment]);
        return segment.messages.some((m) => m.id === messageId);
      } catch {
        return false;
      } finally {
        if (gen === genRef.current) setLoadingOlder(false);
      }
    },
    [roleId],
  );

  const historicalSegments = useMemo(
    () =>
      segments.filter(
        (s) =>
          (s.jumped || s.conversationId !== tipConversationId) &&
          (!roleId || s.roleId === roleId),
      ),
    [segments, tipConversationId, roleId],
  );

  return {
    historicalSegments,
    continuityIdleHours,
    loading,
    loadingOlder,
    hasMore,
    loadOlder,
    revealAround,
    reload: resetAndLoadRecent,
  };
}

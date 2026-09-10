import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  getRoleTimeline,
  type ChatMessage,
  type RoleTimelineSegment,
} from "../../api";
import {
  isInjectedUserMessage,
  normalizeLoadedMessage,
} from "../../utils/chatMessage";

/** 首屏 / 每次上滚加载的段数（有消息的历史段；tip 另算） */
export const TIMELINE_PAGE_SIZE = 5;

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
  title: string;
  createdAt: string;
  messages: ChatMessage[];
  isTip: boolean;
};

function toView(
  seg: RoleTimelineSegment,
  tipId: string | null,
): TimelineSegmentView | null {
  const msgs = normalizeSegmentMessages(
    seg.messages,
    seg.active_turn?.status === "running",
  );
  const isTip = !!tipId && seg.id === tipId;
  if (!isTip && msgs.length === 0) return null;
  if (isTip) return null; // tip 消息由 useChatConversation 维护
  return {
    conversationId: seg.id,
    title: seg.title,
    createdAt: seg.created_at,
    messages: msgs,
    isTip: false,
  };
}

type Options = {
  roleId: string | null;
  tipConversationId: string | null;
  /** 新话题等强制重置近端窗口 */
  refreshKey?: number;
};

/**
 * 角色时间线：默认只拉最近若干段；上滚调用 loadOlder 续取。
 */
export function useRoleTimeline({
  roleId,
  tipConversationId,
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

  const resetAndLoadRecent = useCallback(async () => {
    if (!roleId) {
      setSegments([]);
      setHasMore(false);
      return;
    }
    const gen = ++genRef.current;
    setLoading(true);
    try {
      const tl = await getRoleTimeline(roleId, { limit: TIMELINE_PAGE_SIZE });
      if (gen !== genRef.current || roleRef.current !== roleId) return;
      const tipId = tipRef.current || tl.tip_conversation_id;
      const views = tl.segments
        .map((s) => toView(s, tipId))
        .filter((v): v is TimelineSegmentView => !!v);
      setSegments(views);
      setHasMore(!!tl.has_more);
      setContinuityIdleHours(tl.continuity_idle_hours ?? 6);
    } catch {
      if (gen === genRef.current) {
        setSegments([]);
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
    if (!roleId || loadingOlder || loading || !hasMore || segments.length === 0) {
      return false;
    }
    const oldest = segments[0];
    const gen = genRef.current;
    setLoadingOlder(true);
    try {
      const tl = await getRoleTimeline(roleId, {
        limit: TIMELINE_PAGE_SIZE,
        beforeCreatedAt: oldest.createdAt,
        beforeId: oldest.conversationId,
      });
      if (gen !== genRef.current || roleRef.current !== roleId) return false;
      const tipId = tipRef.current || tl.tip_conversation_id;
      const older = tl.segments
        .map((s) => toView(s, tipId))
        .filter((v): v is TimelineSegmentView => !!v);
      if (older.length === 0) {
        setHasMore(false);
        return false;
      }
      setSegments((prev) => {
        const seen = new Set(prev.map((p) => p.conversationId));
        return [
          ...older.filter((o) => !seen.has(o.conversationId)),
          ...prev,
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

  const historicalSegments = useMemo(
    () => segments.filter((s) => s.conversationId !== tipConversationId),
    [segments, tipConversationId],
  );

  return {
    historicalSegments,
    continuityIdleHours,
    loading,
    loadingOlder,
    hasMore,
    loadOlder,
    reload: resetAndLoadRecent,
  };
}

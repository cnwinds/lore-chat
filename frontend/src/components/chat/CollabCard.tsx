import { useEffect, useState } from "react";
import {
  getRoomStatus,
  type GroupAssignmentStatus,
  type IngestResult,
  type Question,
  type TimelineBlock,
} from "../../api";
import type { ConversationLinkTarget } from "../../utils/conversationLinks";
import { CONVERSATION_CID_RE } from "../../utils/conversationLinks";
import { PendingQuestion } from "../PendingQuestion";
import { sanitizeCollabPreview } from "../../utils/groupChatDisplay";

const STATE_LABEL: Record<string, string> = {
  queued: "排队中",
  working: "工作中",
  awaiting_user: "等你确认",
  done: "已回执",
  idle: "已送达",
  failed: "失败",
  started: "工作中",
  posted: "已送达",
  mixed: "部分开始",
};

const ASSIGNMENT_LABEL: Record<string, string> = {
  open: "待开始",
  working: "进行中",
  overdue: "已超时",
};

type ToolBlock = Extract<TimelineBlock, { type: "tool" }>;

type Props = {
  block: ToolBlock;
  conversationId?: string | null;
  onOpenConversation?: (target: ConversationLinkTarget) => void;
  onQuestionResolved?: (
    blockId: string,
    result: IngestResult,
    choiceLabel: string,
  ) => void;
};

export function roomIdFromCollabBlock(block: ToolBlock): string | null {
  if (block.room_id && CONVERSATION_CID_RE.test(block.room_id)) {
    return block.room_id;
  }
  const m = (block.summary || "").match(/conversation:\/\/([a-f0-9]{12})/i);
  return m?.[1] ?? null;
}

function initialState(block: ToolBlock): string {
  if (block.error) return "failed";
  if (block.wake_status === "queued") return "queued";
  if (block.wake_status === "started") return "working";
  if (block.wake_status === "posted") return "idle";
  return "done";
}

function assignmentLive(rows: GroupAssignmentStatus[]): boolean {
  return rows.some(
    (a) => a.status === "open" || a.status === "working" || a.status === "overdue",
  );
}

export function CollabCard({
  block,
  conversationId,
  onOpenConversation,
  onQuestionResolved,
}: Props) {
  const roomId = roomIdFromCollabBlock(block);
  const [state, setState] = useState(initialState(block));
  const [preview, setPreview] = useState(
    sanitizeCollabPreview(block.summary || ""),
  );
  const [pending, setPending] = useState<Question[]>([]);
  const [assignments, setAssignments] = useState<GroupAssignmentStatus[]>([]);
  const live =
    state === "queued" ||
    state === "working" ||
    state === "awaiting_user" ||
    assignmentLive(assignments);

  useEffect(() => {
    if (!roomId) return;
    let cancelled = false;
    async function poll() {
      try {
        const st = await getRoomStatus(roomId!);
        if (cancelled) return;
        setState(st.state || initialState(block));
        if (st.preview) setPreview(sanitizeCollabPreview(st.preview));
        setPending(st.pending_questions || []);
        setAssignments(st.assignments || []);
      } catch {
        /* 房间尚未可读时保持工具结果 */
      }
    }
    void poll();
    const t = live ? window.setInterval(() => void poll(), 2500) : 0;
    return () => {
      cancelled = true;
      if (t) window.clearInterval(t);
    };
  }, [roomId, block, state, live]);

  const target =
    block.target_role_name ||
    block.targets?.map((t) => t.name).join("、") ||
    "其他角色";
  const label = STATE_LABEL[state] || state;

  return (
    <div
      className={`timeline-collab-card${live ? " timeline-collab-card--live" : ""}`}
      data-collab-state={state}
    >
      <div className="timeline-collab-head">
        <div className="timeline-collab-title">协作 · {target}</div>
        <span className="timeline-collab-state">{label}</span>
      </div>
      {preview ? <div className="timeline-collab-preview">{preview}</div> : null}
      {assignments.length > 0 ? (
        <ul className="timeline-collab-assignments">
          {assignments.map((row) => {
            const name = row.assignee_name || row.assignee_role_id || "角色";
            const asgLabel = ASSIGNMENT_LABEL[row.status] || row.status;
            return (
              <li
                key={row.id}
                className={`timeline-collab-assignment${
                  row.status === "overdue"
                    ? " timeline-collab-assignment--overdue"
                    : ""
                }`}
              >
                {name} · {asgLabel}
              </li>
            );
          })}
        </ul>
      ) : null}
      <div className="timeline-collab-actions">
        {roomId && onOpenConversation ? (
          <button
            type="button"
            className="source-link"
            onClick={() => onOpenConversation({ conversationId: roomId })}
          >
            查看协作
          </button>
        ) : null}
      </div>
      {pending.map((q) => (
        <div key={q.id} className="timeline-collab-pending">
          <PendingQuestion
            question={q}
            conversationId={roomId || conversationId}
            onResolved={(result, choiceLabel) =>
              onQuestionResolved?.(block.id, result, choiceLabel)
            }
          />
        </div>
      ))}
    </div>
  );
}

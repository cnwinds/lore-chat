import { GroupAvatar } from "../role/GroupAvatar";
import type { RoomParticipant } from "../../types/chat";

type Props = {
  roomId: string;
  title: string;
  excerpt?: string;
  status?: string;
  avatar?: string | null;
  members?: RoomParticipant[];
  onOpen?: (roomId: string) => void;
};

const STATUS_LABEL: Record<string, string> = {
  working: "思考中",
  done: "已回复",
};

export function GroupParticipationCard({
  roomId,
  title,
  excerpt,
  status,
  avatar,
  members,
  onOpen,
}: Props) {
  const label = STATUS_LABEL[status || ""] || "在群里发言";
  return (
    <button
      type="button"
      className="group-participation-card"
      onClick={() => onOpen?.(roomId)}
    >
      <GroupAvatar
        name={title}
        seed={roomId}
        avatar={avatar}
        members={members}
        size={40}
      />
      <div className="group-participation-card-body">
        <div className="group-participation-card-top">
          <span className="group-participation-card-title">{title}</span>
          <span className="group-participation-card-status">{label}</span>
        </div>
        <div className="group-participation-card-excerpt">
          {excerpt || "打开群聊查看完整对话"}
        </div>
      </div>
    </button>
  );
}

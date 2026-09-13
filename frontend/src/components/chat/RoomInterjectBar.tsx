import { useState } from "react";
import { postRoomMessage } from "../../api";
import { resolveMentionRoleIds } from "../../utils/roleMentions";

type RoleOpt = { id: string; name: string };

type Props = {
  roomId: string;
  roles: RoleOpt[];
  kind?: string;
  onSent?: () => void;
};

export function RoomInterjectBar({ roomId, roles, kind, onSent }: Props) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hint =
    kind === "group"
      ? "插话到群聊，@角色 才会唤醒对方"
      : "插话到协作房间，默认唤醒上一应者";

  async function submit() {
    const body = text.trim();
    if (!body || busy) return;
    setBusy(true);
    setError(null);
    try {
      await postRoomMessage(roomId, {
        text: body,
        mentions: resolveMentionRoleIds(body, roles),
      });
      setText("");
      onSent?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "发送失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="room-interject">
      <input
        className="room-interject-input"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={hint}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            void submit();
          }
        }}
        disabled={busy}
      />
      <button
        type="button"
        className="btn-primary room-interject-send"
        disabled={busy || !text.trim()}
        onClick={() => void submit()}
      >
        插话
      </button>
      {error ? <div className="room-interject-error">{error}</div> : null}
    </div>
  );
}

from __future__ import annotations

from dataclasses import dataclass

from app.engine.rooms.schema import (
    ACTOR_ROLE,
    ACTOR_SYSTEM,
    ACTOR_USER,
    OWNER_ACTOR_ID,
)


@dataclass(frozen=True)
class Actor:
    kind: str
    id: str


OWNER = Actor(kind=ACTOR_USER, id=OWNER_ACTOR_ID)
SYSTEM = Actor(kind=ACTOR_SYSTEM, id="system")


def format_peer_message(
    *,
    from_name: str,
    from_role_id: str,
    text: str,
) -> str:
    name = (from_name or "").strip() or from_role_id
    body = (text or "").strip()
    return (
        f'<peer_message from="{name}" role_id="{from_role_id}">\n'
        f"{body}\n"
        f"</peer_message>"
    )


@dataclass
class InboundStimulus:
    text: str
    speaker: Actor
    causation_id: str | None = None
    hop: int = 0
    inbound_message_id: str | None = None
    responding_role_id: str | None = None
    speaker_name: str | None = None
    extra_system: str | None = None

    @classmethod
    def owner(cls, text: str) -> InboundStimulus:
        return cls(text=text, speaker=OWNER)

    def is_owner(self) -> bool:
        return self.speaker.kind == ACTOR_USER

    def llm_user_text(self) -> str:
        if self.speaker.kind == ACTOR_SYSTEM:
            body = (self.text or "").strip()
            return f"[系统通知]\n{body}" if body else "[系统通知]"
        if self.speaker.kind != ACTOR_ROLE:
            return self.text
        return format_peer_message(
            from_name=self.speaker_name or self.speaker.id,
            from_role_id=self.speaker.id,
            text=self.text,
        )

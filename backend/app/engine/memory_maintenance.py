from __future__ import annotations

from app.engine.conversations import ConversationStore
from app.engine.memory.decay import DecayConfig, decay_target_status, utc_now
from app.engine.memory.store import MemoryStore
from app.logging_config import get_logger


class MemoryMaintenanceJob:
    def __init__(
        self,
        store: MemoryStore,
        conversations: ConversationStore | None = None,
        *,
        config: DecayConfig | None = None,
    ):
        self.store = store
        self.conversations = conversations
        self.config = config or DecayConfig()

    def run(self) -> dict:
        now = utc_now()
        changed = 0
        events: list[dict] = []
        for fact in self.store.list_active_facts():
            new_status = decay_target_status(fact, now=now, config=self.config)
            if not new_status or new_status == fact.get("status"):
                continue
            old_status = fact["status"]
            self.store.set_status(fact["id"], new_status)
            changed += 1
            payload = {
                "type": "memory_decayed",
                "fact_id": fact["id"],
                "old_status": old_status,
                "new_status": new_status,
                "statement": fact.get("statement", ""),
            }
            events.append(payload)
            if self.conversations:
                cid = self._latest_conversation_for_fact(fact["id"])
                if cid:
                    self.conversations.append_system_event(cid, "memory_decayed", payload)
        if changed:
            get_logger("memory_maintenance").info("memory decay applied count=%s", changed)
        return {"changed": changed, "events": events}

    def _latest_conversation_for_fact(self, fact_id: str) -> str | None:
        evidence = self.store.list_evidence(fact_id)
        if not evidence:
            return None
        return evidence[-1]["conversation_id"]

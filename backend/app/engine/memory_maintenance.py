from __future__ import annotations

from app.engine.conversations import ConversationStore
from app.engine.memory.card_growth import CardGrowthLog
from app.engine.memory.cards import OWNER_SCOPE
from app.engine.memory.decay import DecayConfig, decay_target_status, utc_now
from app.engine.memory.store import MemoryStore
from app.logging_config import get_logger


def _fade_growth_action(old_status: str, new_status: str) -> str | None:
    if new_status == "stale":
        return "expired"
    if new_status == "rejected":
        return "dropped"
    if old_status == "confirmed" and new_status == "candidate":
        return "demoted"
    return None


class MemoryMaintenanceJob:
    def __init__(
        self,
        store: MemoryStore,
        conversations: ConversationStore | None = None,
        *,
        config: DecayConfig | None = None,
        growth: CardGrowthLog | None = None,
    ):
        self.store = store
        self.conversations = conversations
        self.config = config or DecayConfig()
        self.growth = growth

    def run(self) -> dict:
        now = utc_now()
        changed = 0
        events: list[dict] = []
        growth_items: list[dict] = []
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
            action = _fade_growth_action(old_status, new_status)
            if action:
                growth_items.append(
                    {
                        "action": action,
                        "card_id": fact["id"],
                        "kind": fact.get("category") or "",
                        "statement": fact.get("statement") or "",
                        "external": False,
                        "status": new_status,
                    }
                )
            if self.conversations:
                cid = self._latest_conversation_for_fact(fact["id"])
                if cid:
                    self.conversations.system_events.append(
                        cid, "memory_decayed", payload
                    )
        if growth_items and self.growth is not None:
            self.growth.append(OWNER_SCOPE, "faded", growth_items)
        if changed:
            get_logger("memory_maintenance").info("memory decay applied count=%s", changed)
        return {"changed": changed, "events": events}

    def _latest_conversation_for_fact(self, fact_id: str) -> str | None:
        evidence = self.store.list_evidence(fact_id)
        if not evidence:
            return None
        return evidence[-1]["conversation_id"]

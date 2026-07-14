from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.engine.memory.extractor import RuleBasedMemoryExtractor
from app.engine.memory.models import MemoryCandidate
from app.engine.memory.policy import (
    initial_status,
    infer_sensitivity,
    origin_wins_conflict,
    quote_hash_for,
    should_promote,
    slot_for_candidate,
    validate_evidence,
)
from app.engine.memory.store import MemoryStore
from app.engine.secrets import scan_secrets


@dataclass
class ObserveResult:
    ok: bool
    confirmed_count: int = 0
    candidate_count: int = 0
    rejected_count: int = 0
    error: str | None = None


class MemoryObserver:
    def __init__(self, store: MemoryStore, *, extractor=None):
        self.store = store
        self.extractor = extractor or RuleBasedMemoryExtractor()

    def observe_message(
        self,
        text: str,
        *,
        conversation_id: str,
        message_id: str,
        context_messages: list[dict] | None = None,
    ) -> ObserveResult:
        if scan_secrets(text):
            return ObserveResult(ok=True, rejected_count=0)
        extracted = self.extractor.extract(text, context_messages=context_messages or [])
        confirmed = 0
        candidates = 0
        rejected = 0
        for cand in extracted.candidates:
            if not validate_evidence(text, cand):
                rejected += 1
                continue
            out = self._apply_candidate(
                cand,
                text=text,
                conversation_id=conversation_id,
                message_id=message_id,
            )
            if out == "confirmed":
                confirmed += 1
            elif out == "candidate":
                candidates += 1
            else:
                rejected += 1
        return ObserveResult(
            ok=True,
            confirmed_count=confirmed,
            candidate_count=candidates,
            rejected_count=rejected,
        )

    def _apply_candidate(
        self,
        cand: MemoryCandidate,
        *,
        text: str,
        conversation_id: str,
        message_id: str,
    ) -> str:
        sensitivity = infer_sensitivity(cand.statement)
        status = initial_status(cand, sensitivity=sensitivity)
        if status == "rejected":
            return "rejected"
        slot, vhash = slot_for_candidate(cand)
        if self.store.has_tombstone(slot_key=slot, normalized_value_hash=vhash):
            return "rejected"

        existing = self.store.find_by_slot_and_hash(slot, vhash)
        if existing and existing["status"] in ("forgotten", "superseded", "rejected"):
            return "rejected"

        self._resolve_slot_conflicts(cand, slot=slot, vhash=vhash)

        if existing and existing["status"] == "candidate":
            evidence_n = self.store.count_evidence(existing["id"]) + 1
            merged_conf = min(1.0, max(float(existing["confidence"]), cand.confidence) + 0.1 * evidence_n)
            fact = self.store.upsert_fact(
                slot_key=slot,
                category=cand.category,
                statement=cand.statement,
                normalized_value_hash=vhash,
                origin=cand.origin,
                confidence=merged_conf,
                sensitivity=sensitivity,
                status="candidate",
            )
        elif existing and existing["status"] == "confirmed":
            fact = existing
        else:
            fact = self.store.upsert_fact(
                slot_key=slot,
                category=cand.category,
                statement=cand.statement,
                normalized_value_hash=vhash,
                origin=cand.origin,
                confidence=cand.confidence,
                sensitivity=sensitivity,
                status=status,
            )

        qh = quote_hash_for(text, cand.start_char, cand.end_char)
        self.store.add_evidence(
            fact_id=fact["id"],
            conversation_id=conversation_id,
            message_id=message_id,
            start_char=cand.start_char,
            end_char=cand.end_char,
            quote_hash=qh,
        )

        if fact["status"] == "candidate" and should_promote(
            fact,
            distinct_conversations=self.store.count_distinct_conversation_evidence(fact["id"]),
            evidence_count=self.store.count_evidence(fact["id"]),
        ):
            fact = self.store.upsert_fact(
                slot_key=slot,
                category=cand.category,
                statement=cand.statement,
                normalized_value_hash=vhash,
                origin=cand.origin,
                confidence=float(fact["confidence"]),
                sensitivity=sensitivity,
                status="confirmed",
            )
            return "confirmed"

        return fact["status"]

    def _resolve_slot_conflicts(
        self, cand: MemoryCandidate, *, slot: str, vhash: str
    ) -> None:
        for old in self.store.find_confirmed_by_slot(slot):
            if old["normalized_value_hash"] == vhash:
                continue
            if cand.origin == "inferred" and old["origin"] == "inferred":
                continue
            if origin_wins_conflict(cand.origin, old["origin"]) or (
                cand.origin == old["origin"] and cand.origin == "direct"
            ):
                self.store.mark_superseded(old["id"])

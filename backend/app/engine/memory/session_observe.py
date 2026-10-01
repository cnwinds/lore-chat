"""会话定稿观察：dirty / idle / extract / resolve / CAS 收进一个 deep module。"""

from __future__ import annotations

from app.engine.conversation.outbox import SESSION_OBSERVE_IMMEDIATE
from app.engine.background.purpose import llm_call_subject
from app.engine.conversations import ConversationStore
from app.engine.memory.service import MemoryService
from app.engine.memory.session_extractor import SessionMemoryExtractor
from app.logging_config import get_logger

_KIND_SESSION_OBSERVE = "session_observe_memory"
_SOFT_REJECT = frozenset({"tombstoned", "secret_rejected", "rejected", "inactive"})
_log = get_logger("memory.session_observe")


class SessionMemoryObserve:
    """给定 conversation_id，跑完一次 session_observe（对外小 interface）。"""

    def __init__(
        self,
        conversations: ConversationStore,
        memory_service: MemoryService,
        *,
        extractor: SessionMemoryExtractor | None = None,
        cards=None,
        card_extractor=None,
        idle_hours: float = 24.0,
    ):
        self.conversations = conversations
        self.schedule = conversations.memory_schedule
        self.memory_service = memory_service
        # 无 LLM 抽取器时跳过落库，保留 dirty 待下次（不回退启发式）
        self.extractor = extractor
        self.cards = cards
        self.card_extractor = card_extractor
        self.idle_hours = idle_hours
        # 与 MemoryService 共用同一 Resolver（写不变式 locality）
        self._resolver = memory_service.resolver

    def mark_dirty(self, conversation_id: str, *, at: str | None = None) -> None:
        self.schedule.mark_dirty(conversation_id, at=at)

    def enqueue(
        self, conversation_id: str, *, immediate: bool = False
    ) -> bool:
        return self.schedule.enqueue_session_observe(
            conversation_id, immediate=immediate
        )

    def mark_dirty_and_enqueue(
        self,
        conversation_ids: list[str],
        *,
        mark_dirty: bool = True,
        immediate: bool = False,
    ) -> int:
        """批量标 dirty 并入队（backfill / 维护入口）。"""
        return self.schedule.batch_mark_dirty_and_enqueue(
            conversation_ids,
            mark_dirty=mark_dirty,
            immediate=immediate,
        )

    def schedule_idle(self, *, limit: int = 20) -> int:
        n = 0
        for row in self.schedule.list_idle_dirty(
            idle_hours=self.idle_hours, limit=limit
        ):
            if self.enqueue(row["id"]):
                n += 1
        return n

    def cancel_legacy_jobs(self) -> int:
        return self.schedule.cancel_legacy_observe_memory()

    def process_session_job(self, job: dict) -> None:
        """兼容旧名 → run_job。"""
        self.run_job(job)

    def run_job(self, job: dict) -> None:
        """消费一条 outbox job（保留 job 形以兼容 claim_outbox）。"""
        job_id = job["id"]
        source = job.get("source_message_id") or ""
        cid = source.removeprefix("conv:") if source.startswith("conv:") else source
        try:
            if not cid:
                self.conversations.complete_outbox(job_id)
                return
            immediate = (job.get("turn_id") or "") == SESSION_OBSERVE_IMMEDIATE
            if not immediate and not self.schedule.is_extract_idle(
                cid, idle_hours=self.idle_hours
            ):
                self._complete_and_requeue_immediate(job_id, cid)
                return
            started_last_user_at = self.schedule.get_last_user_message_at(cid)
            conv_kind = self.conversations.get_conversation_kind(cid)
            from app.engine.rooms.schema import KIND_GROUP, KIND_PEER_DM

            if conv_kind in (KIND_PEER_DM, KIND_GROUP):
                self._run_room_job(
                    job_id,
                    cid,
                    conv_kind,
                    started_last_user_at=started_last_user_at,
                    immediate=immediate,
                )
                return

            turns = self.conversations.list_dialogue_turns(cid)
            if not any(role == "user" and t.strip() for role, t in turns):
                self.schedule.clear_dirty(
                    cid, expected_last_user_message_at=started_last_user_at
                )
                self._complete_and_requeue_immediate(job_id, cid)
                return

            if self.cards:
                owner_lens, card_lens = self.cards.lenses_for(cid)
            else:
                owner_lens, card_lens = True, None

            if not owner_lens and not card_lens:
                self.schedule.clear_dirty(
                    cid, expected_last_user_message_at=started_last_user_at
                )
                self._complete_and_requeue_immediate(job_id, cid)
                return

            lenses_ready = True
            if owner_lens and self.extractor is None:
                _log.info(
                    "session_observe 跳过主人镜头：未配置 LLM 抽取器 cid=%s",
                    cid,
                )
                lenses_ready = False
            if card_lens and self.card_extractor is None:
                _log.info(
                    "session_observe 跳过角色卡镜头：未配置抽取器 cid=%s",
                    cid,
                )
                lenses_ready = False

            hard_failures = 0
            memory_confirmed_landed = False

            if owner_lens and self.extractor is not None:
                confirmed = [
                    {
                        "slot_key": f["slot_key"],
                        "statement": f["statement"],
                        "category": f.get("category"),
                    }
                    for f in self.memory_service.store.list_confirmed()
                ]
                with llm_call_subject(conversation_id=cid, scope=None):
                    actions = self.extractor.extract(turns, confirmed_summary=confirmed)
                if self.cards:
                    outs = self.cards.learn_owner(actions, conversation_id=cid)
                else:
                    outs = [
                        self._resolver.apply(action, conversation_id=cid)
                        for action in actions
                    ]
                for out in outs:
                    if not out.get("ok"):
                        if out.get("error") not in _SOFT_REJECT:
                            hard_failures += 1
                        continue
                    fact = out.get("fact") or {}
                    if fact.get("status") == "confirmed":
                        memory_confirmed_landed = True

                if memory_confirmed_landed:
                    self.conversations.system_events.append(
                        cid,
                        "memory_updated",
                        {
                            "type": "memory_updated",
                            "conversation_id": cid,
                        },
                    )

            if card_lens and self.card_extractor is not None:
                scope = card_lens.scope
                card_store = self.cards.store(scope)
                existing = [
                    {
                        "slot_key": f["slot_key"],
                        "statement": f["statement"],
                        "category": f.get("category"),
                    }
                    for f in card_store.list_confirmed() + card_store.list_candidates()
                ]
                owner_summary = [
                    f["statement"] for f in self.memory_service.store.list_confirmed()
                ]
                with llm_call_subject(conversation_id=cid, scope=scope):
                    card_actions = self.card_extractor.extract(
                        turns,
                        lens=card_lens,
                        existing_cards=existing,
                        owner_summary=owner_summary,
                    )
                cards_confirmed_landed = False
                outs = self.cards.learn(scope, card_actions, conversation_id=cid)
                for out in outs:
                    if not out.get("ok"):
                        if out.get("error") not in _SOFT_REJECT:
                            hard_failures += 1
                        continue
                    fact = out.get("fact") or {}
                    if fact.get("status") == "confirmed":
                        cards_confirmed_landed = True

                if cards_confirmed_landed:
                    self.conversations.system_events.append(
                        cid,
                        "cards_updated",
                        {
                            "type": "cards_updated",
                            "conversation_id": cid,
                            "scope": scope,
                        },
                    )

            if hard_failures == 0 and lenses_ready:
                self.schedule.clear_dirty(
                    cid, expected_last_user_message_at=started_last_user_at
                )
            self._complete_and_requeue_immediate(job_id, cid)
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "session_observe_memory 失败 job_id=%s cid=%s err=%s",
                job_id,
                cid,
                exc,
                exc_info=True,
            )
            self.conversations.fail_outbox(job_id, str(exc), backoff=1.0)
            if cid and self.schedule.consume_immediate_pending(cid):
                self.enqueue(cid, immediate=True)

    def drain(self, max_jobs: int = 20) -> int:
        self.cancel_legacy_jobs()
        self.schedule_idle(limit=max_jobs)
        done = 0
        while done < max_jobs:
            jobs = self.conversations.claim_outbox(
                kind=_KIND_SESSION_OBSERVE,
                limit=min(10, max_jobs - done),
                lease_seconds=120,
            )
            if not jobs:
                break
            for job in jobs:
                self.process_session_job(job)
                done += 1
        return done

    def schedule_idle_sessions(self, *, limit: int = 20) -> int:
        """兼容旧 MemoryWorker 名。"""
        return self.schedule_idle(limit=limit)

    def cancel_legacy_observe_jobs(self) -> int:
        """兼容旧 MemoryWorker 名。"""
        return self.cancel_legacy_jobs()

    def _complete_and_requeue_immediate(self, job_id: str, cid: str) -> None:
        self.conversations.complete_outbox(job_id)
        if cid and self.schedule.consume_immediate_pending(cid):
            self.enqueue(cid, immediate=True)

    def _run_room_job(
        self,
        job_id: str,
        cid: str,
        conv_kind: str,
        *,
        started_last_user_at: str | None,
        immediate: bool,
    ) -> None:
        from app.engine.memory.constants import (
            ROOM_CONTEXT_MESSAGES,
            ROOM_WINDOW_MAX_MESSAGES,
        )
        from app.engine.memory.room_observe import (
            build_room_dialogue,
            direct_lens_for_role,
            owner_turns_from_window,
            role_name_map,
            select_room_role_ids,
        )

        cursor = self.schedule.get_cursor_seq(cid)
        window = self.conversations.list_room_window(
            cid,
            after_seq=cursor,
            limit=ROOM_WINDOW_MAX_MESSAGES,
            context=ROOM_CONTEXT_MESSAGES,
        )

        if not window.lines:
            if window.end_seq is not None:
                self.schedule.advance_cursor_seq(cid, window.end_seq)
            self.schedule.clear_dirty(
                cid, expected_last_user_message_at=started_last_user_at
            )
            self._complete_and_requeue_immediate(job_id, cid)
            return

        owner_spoke = any(ln.speaker_kind == "user" for ln in window.lines)
        role_ids = select_room_role_ids(window, self.cards) if self.cards else []

        lenses_ready = True
        if owner_spoke and self.extractor is None:
            _log.info(
                "session_observe 跳过主人镜头：未配置 LLM 抽取器 cid=%s",
                cid,
            )
            lenses_ready = False
        if role_ids and self.card_extractor is None:
            _log.info(
                "session_observe 跳过角色卡镜头：未配置抽取器 cid=%s",
                cid,
            )
            lenses_ready = False

        hard_failures = 0
        memory_confirmed_landed = False

        if owner_spoke and self.extractor is not None:
            confirmed = [
                {
                    "slot_key": f["slot_key"],
                    "statement": f["statement"],
                    "category": f.get("category"),
                }
                for f in self.memory_service.store.list_confirmed()
            ]
            turns = owner_turns_from_window(window.lines)
            with llm_call_subject(conversation_id=cid, scope=None):
                actions = self.extractor.extract(turns, confirmed_summary=confirmed)
            if self.cards:
                outs = self.cards.learn_owner(actions, conversation_id=cid)
            else:
                outs = [
                    self._resolver.apply(action, conversation_id=cid)
                    for action in actions
                ]
            for out in outs:
                if not out.get("ok"):
                    if out.get("error") not in _SOFT_REJECT:
                        hard_failures += 1
                    continue
                fact = out.get("fact") or {}
                if fact.get("status") == "confirmed":
                    memory_confirmed_landed = True
            if memory_confirmed_landed:
                self.conversations.system_events.append(
                    cid,
                    "memory_updated",
                    {
                        "type": "memory_updated",
                        "conversation_id": cid,
                    },
                )

        role_names = role_name_map(
            self.cards,
            {
                rid
                for ln in window.lines + window.context
                if ln.speaker_kind == "role"
                for rid in [(ln.speaker_id or "").strip()]
                if rid
            },
        ) if self.cards else {}

        title = self.conversations.get_title(cid) or ""

        if self.card_extractor is not None and self.cards:
            for role_id in role_ids:
                lens = direct_lens_for_role(self.cards, role_id)
                if lens is None:
                    continue
                card_store = self.cards.store(lens.scope)
                existing = [
                    {
                        "slot_key": f["slot_key"],
                        "statement": f["statement"],
                        "category": f.get("category"),
                    }
                    for f in card_store.list_confirmed() + card_store.list_candidates()
                ]
                owner_summary = [
                    f["statement"] for f in self.memory_service.store.list_confirmed()
                ]
                room = build_room_dialogue(
                    kind=conv_kind,
                    title=title,
                    window=window,
                    role_id=role_id,
                    role_names=role_names,
                )
                with llm_call_subject(conversation_id=cid, scope=lens.scope):
                    card_actions = self.card_extractor.extract_room(
                        room,
                        lens=lens,
                        existing_cards=existing,
                        owner_summary=owner_summary,
                    )
                cards_confirmed_landed = False
                outs = self.cards.learn(lens.scope, card_actions, conversation_id=cid)
                for out in outs:
                    if not out.get("ok"):
                        if out.get("error") not in _SOFT_REJECT:
                            hard_failures += 1
                        continue
                    fact = out.get("fact") or {}
                    if fact.get("status") == "confirmed":
                        cards_confirmed_landed = True
                if cards_confirmed_landed:
                    self.conversations.system_events.append(
                        cid,
                        "cards_updated",
                        {
                            "type": "cards_updated",
                            "conversation_id": cid,
                            "scope": lens.scope,
                        },
                    )

        if hard_failures == 0 and lenses_ready and window.end_seq is not None:
            self.schedule.advance_cursor_seq(cid, window.end_seq)
            if window.has_more:
                self.schedule.request_immediate(cid)
            else:
                self.schedule.clear_dirty(
                    cid, expected_last_user_message_at=started_last_user_at
                )
        self._complete_and_requeue_immediate(job_id, cid)


# 兼容旧名
MemoryWorker = SessionMemoryObserve

"""角色知识卡分区索引：同步、检索与注入。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.engine.agent.message_builder import build_agent_messages
from app.engine.agent.prompts import (
    build_system_prompt,
    current_time_block,
    wrap_turn_cards,
)
from app.engine.conversations import ConversationStore
from app.engine.intent import _strip_user_injections
from app.engine.memory.card_consolidation import LLMCardConsolidator
from app.engine.memory.card_index import (
    TURN_CARDS_LIMIT,
    CardIndex,
    CardRetrievalTuning,
    card_partition,
)
from app.engine.memory.cards import KnowledgeCards, persona_scope, role_scope
from app.engine.memory.resolver import SlotAction
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.engine.roles import RoleStore
from app.index.partitioned import IndexItem, SearchIndex
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer
from tests.test_knowledge_cards import _FakeChannelInstances


@dataclass
class FakeEmbedder:
    model: str = "test-model"
    dim: int = 8
    delay: float = 0.0
    text_vectors: dict[str, list[float]] = field(default_factory=dict)
    call_count: int = 0

    def embed(self, texts: list[str]):
        from app.index.partitioned.embedder import EmbedBatch

        self.call_count += 1
        if self.delay:
            time.sleep(self.delay)
        default = [0.0, 1.0] + [0.0] * (self.dim - 2)
        vectors = [list(self.text_vectors.get(t, default)) for t in texts]
        return EmbedBatch(vectors=vectors, model=self.model)


def _cards(tmp_path, *, max_chars: int = 2000) -> tuple[KnowledgeCards, RoleStore]:
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    writer = make_writer(repo, tmp_path)
    owner_store = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    owner = MemoryService(owner_store, repo, knowledge_writer=writer)
    roles = RoleStore(tmp_path / "roles")
    conv = ConversationStore(tmp_path / "conversations")
    cards = KnowledgeCards(
        tmp_path / "memory.db",
        owner=owner,
        roles=roles,
        conversations=conv,
        channel_instances=_FakeChannelInstances(),
        max_chars=max_chars,
    )
    return cards, roles


def _wire_index(
    cards: KnowledgeCards,
    tmp_path,
    embedder: FakeEmbedder | None = None,
    *,
    tuning: CardRetrievalTuning | None = None,
) -> tuple[CardIndex, SearchIndex]:
    idx_dir = tmp_path / "card_idx"
    search = SearchIndex(
        idx_dir / "partitioned.db",
        idx_dir / "vec",
        embedder,
    )
    card_index = CardIndex(search, cards, tuning or CardRetrievalTuning())
    cards.index = card_index
    return card_index, search


def _seed(
    st: MemoryStore,
    *,
    card_id: str,
    statement: str,
    kind: str = "domain",
    origin: str = "direct",
    updated_at: str = "2026-09-29T10:00:00+00:00",
    status: str = "confirmed",
) -> None:
    st.upsert_fact(
        slot_key=f"{kind}.{card_id}",
        category=kind,
        statement=statement,
        normalized_value_hash=f"h-{card_id}",
        origin=origin,
        status=status,
        fact_id=card_id,
    )
    with st._connect() as conn:
        conn.execute(
            "UPDATE memory_facts SET updated_at = ? WHERE id = ?",
            (updated_at, card_id),
        )
        conn.commit()


def _sync_scope(cards: KnowledgeCards, scope: str) -> None:
    with cards.scope_lock(scope):
        cards._sync_index_locked(scope)


def _unit_vec(i: int, dim: int = 8) -> list[float]:
    v = [0.0] * dim
    v[i % dim] = 1.0
    return v


def test_learn_then_turn_cards_lexical(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    _wire_index(cards, tmp_path, FakeEmbedder())
    cards.learn(
        scope,
        [
            SlotAction(
                action="new",
                statement="先查违约条款再看付款",
                category="domain",
                origin="direct",
            )
        ],
        conversation_id="c1",
    )
    assert "违约" in cards.turn_cards(scope, "违约", exclude_ids=set())
    assert "违约条款" in cards.turn_cards(
        scope, "这份合同里的违约金怎么约定", exclude_ids=set()
    )


def test_source_of_truth_after_forget(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    card_index, _ = _wire_index(cards, tmp_path, FakeEmbedder())
    st = cards.store(scope)
    _seed(st, card_id="gone", statement="独有词Alpha归档流程")
    _sync_scope(cards, scope)

    saved = cards.index
    cards.index = None
    cards.forget(scope, "gone")
    cards.index = saved

    assert "独有词Alpha" not in cards.turn_cards(scope, "独有词Alpha", exclude_ids=set())


def test_fade_then_restore(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    _wire_index(cards, tmp_path, FakeEmbedder())
    st = cards.store(scope)
    _seed(st, card_id="f1", statement="淡出独有词Beta")
    _sync_scope(cards, scope)

    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=200)).isoformat()
    with st._connect() as conn:
        conn.execute(
            "UPDATE memory_facts SET last_seen_at=?, updated_at=? WHERE id=?",
            (old, old, "f1"),
        )
        conn.commit()
    cards._fade_scope(scope, now=now)
    assert "淡出独有词Beta" not in cards.turn_cards(
        scope, "独有词Beta", exclude_ids=set()
    )

    cards.restore(scope, "f1")
    assert "淡出独有词Beta" in cards.turn_cards(scope, "独有词Beta", exclude_ids=set())


def test_edit_renders_store_not_stale_index_text(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    _wire_index(cards, tmp_path, FakeEmbedder())
    st = cards.store(scope)
    _seed(st, card_id="e1", statement="归档前先查违约条款")
    _sync_scope(cards, scope)

    with patch.object(cards, "_sync_index_locked"):
        cards.edit(scope, "e1", "归档前先查新目录结构")

    out = cards.turn_cards(scope, "违约", exclude_ids=set())
    assert "新目录结构" in out
    assert "违约条款" not in out


def test_channel_scope_isolation(tmp_path):
    cards, roles = _cards(tmp_path)
    visible = roles.create(name="通道前台", system_prompt="")
    persona = roles.create_persona(name="客服人设", system_prompt="客服")
    pscope = persona_scope(persona["id"])
    rscope = role_scope(visible["id"])
    _wire_index(cards, tmp_path, FakeEmbedder())
    _seed(cards.store(pscope), card_id="p1", statement="人设域内独有词Omega规则")
    _seed(cards.store(rscope), card_id="r1", statement="左栏独有词Psi规则")
    _sync_scope(cards, pscope)
    _sync_scope(cards, rscope)

    inst_id = "inst-iso"
    cards.channel_instances.put(
        {"id": inst_id, "persona_id": persona["id"], "include_owner_memory": False}
    )
    cid = cards.conversations.create(
        role_id=visible["id"],
        origin="api",
        channel_instance_id=inst_id,
    )
    ch_inj = cards.injection_for(
        conversation_id=cid, role_id=visible["id"], query="独有词Omega"
    )
    assert "独有词Omega规则" in ch_inj.turn_cards
    assert "独有词Psi规则" not in ch_inj.turn_cards
    # 左栏 scope 检索不跨到 persona 分区
    assert "独有词Psi规则" in cards.turn_cards(
        rscope, "独有词Psi", exclude_ids=set()
    )
    assert "独有词Omega规则" not in cards.turn_cards(
        rscope, "独有词Psi", exclude_ids=set()
    )


def test_exclude_all_confirmed_skips_embedder(tmp_path):
    cards, roles = _cards(tmp_path, max_chars=500)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    emb = FakeEmbedder()
    _wire_index(cards, tmp_path, emb)
    st = cards.store(scope)
    _seed(st, card_id="only", statement="归档前先查目录结构")
    _sync_scope(cards, scope)
    _, core_ids = cards.render_with_ids(scope)
    assert core_ids == {"only"}
    emb.call_count = 0
    assert cards.turn_cards(scope, "查目录", exclude_ids=core_ids) == ""
    assert emb.call_count == 0


def test_common_term_only_no_injection(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    # 查询与卡文向量正交，避免语义 lane 误放行
    emb = FakeEmbedder(text_vectors={"主人": _unit_vec(0)})
    _wire_index(
        cards,
        tmp_path,
        emb,
        tuning=CardRetrievalTuning(min_vector_score=0.55),
    )
    st = cards.store(scope)
    for i in range(4):
        _seed(st, card_id=f"m{i}", statement=f"主人偏好简洁说明{i}")
    _sync_scope(cards, scope)
    cards.index.index.embed_pending()
    assert cards.turn_cards(scope, "主人", exclude_ids=set()) == ""


def test_semantic_vector_gate(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    good = _unit_vec(0)
    bad = _unit_vec(1)
    card_text = "先查甲方盖章流程"
    emb = FakeEmbedder(
        text_vectors={
            "合同违约": good,
            card_text: good,
        }
    )
    _wire_index(
        cards,
        tmp_path,
        emb,
        tuning=CardRetrievalTuning(min_vector_score=0.55),
    )
    st = cards.store(scope)
    _seed(st, card_id="sem", statement=card_text)
    _sync_scope(cards, scope)
    cards.index.index.embed_pending()

    hit = cards.turn_cards(scope, "合同违约", exclude_ids=set())
    assert card_text in hit

    miss_emb = FakeEmbedder(text_vectors={"合同违约": bad, card_text: good})
    cards.index.index.embedder = miss_emb
    cards.index.index.on_embedder_changed()
    res = cards.index.index.search(
        "合同违约", partitions=[card_partition(scope)], lanes=("vec",)
    )
    assert res.vector_status == "ok"
    assert res.hits and res.hits[0].vector_score < 0.55
    assert cards.turn_cards(scope, "合同违约", exclude_ids=set()) == ""


def test_vector_timeout_lexical_still_works(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    emb = FakeEmbedder(delay=1.0)
    tuning = CardRetrievalTuning(vector_timeout_s=0.2, min_vector_score=0.55)
    _wire_index(cards, tmp_path, emb, tuning=tuning)
    st = cards.store(scope)
    _seed(st, card_id="t1", statement="尾卡独有词Zeta说明")
    _sync_scope(cards, scope)
    t0 = time.monotonic()
    out = cards.turn_cards(scope, "尾卡独有词Zeta", exclude_ids=set())
    elapsed = time.monotonic() - t0
    assert "尾卡独有词Zeta说明" in out
    assert elapsed < 0.6


def test_purge_scope_drops_partition(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    card_index, _ = _wire_index(cards, tmp_path, FakeEmbedder())
    _seed(cards.store(scope), card_id="x", statement="待清空")
    _sync_scope(cards, scope)
    assert card_partition(scope) in card_index.index.partitions("cards")
    cards.purge_scope(scope)
    assert card_partition(scope) not in card_index.index.partitions("cards")


def test_sync_all_drops_orphan_partition(tmp_path):
    cards, roles = _cards(tmp_path)
    roles.create(name="R", system_prompt="")
    card_index, search = _wire_index(cards, tmp_path, FakeEmbedder())
    orphan = card_partition("role:orphan")
    search.sync_partition(orphan, [IndexItem("1", "孤儿卡")])
    assert orphan in search.partitions("cards")
    stats = card_index.sync_all()
    assert orphan not in search.partitions("cards")
    assert stats["dropped_partitions"] >= 1


def test_consolidation_sync_removes_merged_card(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="整理", system_prompt="")
    scope = role_scope(role["id"])
    _wire_index(cards, tmp_path, FakeEmbedder())
    st = cards.store(scope)
    _seed(st, card_id="a", statement="经验甲独有词Delta", kind="lesson")
    _seed(
        st,
        card_id="b",
        statement="经验乙独有词Delta",
        kind="lesson",
        updated_at="2026-09-28T00:00:00+00:00",
    )
    _sync_scope(cards, scope)
    from app.engine.memory.cards import CardLens

    lens = CardLens(scope, "direct", role["name"], "")
    class FakeLLM:
        def chat(self, messages, **_kw):
            return json.dumps(
                {
                    "ops": [
                        {
                            "op": "merge",
                            "ids": ["c1", "c2"],
                            "kind": "lesson",
                            "statement": "合并后独有词Delta正文",
                        }
                    ]
                },
                ensure_ascii=False,
            )

    cards.consolidator = LLMCardConsolidator(FakeLLM(), cards)
    cards.consolidator.run(scope, lens)
    with cards.scope_lock(scope):
        cards._sync_index_locked(scope)

    assert "经验甲独有词Delta" not in cards.turn_cards(
        scope, "独有词Delta", exclude_ids=set()
    )
    assert "合并后独有词Delta正文" in cards.turn_cards(
        scope, "独有词Delta", exclude_ids=set()
    )


def test_recall_uses_index_with_query(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    _wire_index(cards, tmp_path, FakeEmbedder())
    st = cards.store(scope)
    _seed(
        st,
        card_id="old",
        statement="旧卡",
        updated_at="2026-09-01T00:00:00+00:00",
    )
    _seed(
        st,
        card_id="hit",
        statement="召回独有词Epsilon",
        updated_at="2026-09-29T00:00:00+00:00",
    )
    _sync_scope(cards, scope)
    rows = cards.recall(scope, "独有词Epsilon", limit=5)
    assert len(rows) == 1
    assert rows[0]["statement"] == "召回独有词Epsilon"
    assert "kind" in rows[0]
    assert "external" in rows[0]
    assert "updated_at" in rows[0]


def test_recall_empty_query_by_updated_at(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    _wire_index(cards, tmp_path, FakeEmbedder())
    st = cards.store(scope)
    _seed(st, card_id="a", statement="A", updated_at="2026-09-01T00:00:00+00:00")
    _seed(st, card_id="b", statement="B", updated_at="2026-09-29T00:00:00+00:00")
    _sync_scope(cards, scope)
    rows = cards.recall(scope, "", limit=1)
    assert rows[0]["statement"] == "B"


def test_turn_cards_respects_limit(tmp_path):
    cards, roles = _cards(tmp_path, max_chars=10)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    _wire_index(cards, tmp_path, FakeEmbedder())
    st = cards.store(scope)
    for i in range(6):
        _seed(
            st,
            card_id=f"z{i}",
            statement=f"专有词Alpha{i} 说明",
            updated_at=f"2026-09-{10 + i:02d}T00:00:00+00:00",
        )
    _sync_scope(cards, scope)
    out = cards.turn_cards(
        scope, " ".join(f"Alpha{i}" for i in range(6)), exclude_ids=set()
    )
    assert out.count("- ") == TURN_CARDS_LIMIT


def test_turn_cards_empty_when_core_fits_all(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    _wire_index(cards, tmp_path, FakeEmbedder())
    _seed(cards.store(scope), card_id="c1", statement="归档前先查目录结构")
    _sync_scope(cards, scope)
    inj = cards.injection_for(conversation_id=None, role_id=role["id"], query="查目录")
    assert inj.turn_cards == ""


def test_turn_cards_surfaces_truncated_card(tmp_path):
    cards, roles = _cards(tmp_path, max_chars=28)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    _wire_index(cards, tmp_path, FakeEmbedder())
    st = cards.store(scope)
    for i in range(4):
        _seed(
            st,
            card_id=f"d{i}",
            statement=f"短条目{i}",
            updated_at=f"2026-09-{10 + i:02d}T00:00:00+00:00",
        )
    _seed(
        st,
        card_id="tail",
        statement="尾卡独有词Zeta说明",
        kind="lesson",
        updated_at="2026-09-29T00:00:00+00:00",
    )
    _sync_scope(cards, scope)
    core, core_ids = cards.render_with_ids(scope)
    assert "尾卡独有词Zeta说明" not in core
    inj = cards.injection_for(
        conversation_id=None, role_id=role["id"], query="尾卡独有词Zeta"
    )
    assert "尾卡独有词Zeta说明" in inj.turn_cards
    assert inj.turn_cards.count("- ") == 1


def test_turn_cards_external_suffix(tmp_path):
    cards, roles = _cards(tmp_path, max_chars=10)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    _wire_index(cards, tmp_path, FakeEmbedder())
    _seed(
        cards.store(scope),
        card_id="ext",
        statement="访客常问退款流程",
        origin="external",
    )
    _sync_scope(cards, scope)
    inj = cards.injection_for(conversation_id=None, role_id=role["id"], query="退款流程")
    assert "（外部来源）" in inj.turn_cards


def test_message_builder_turn_cards_prefix_order():
    turn_body = "- 尾卡独有词说明"
    messages = build_agent_messages(
        "用户原文",
        mode="default",
        web_enabled=False,
        system_layer_text="",
        user_memory="",
        turn_cards=turn_body,
        history=None,
        active_doc_path=None,
        active_doc_paths=None,
        primary_doc_path=None,
    )
    user = messages[-1]["content"]
    assert user.startswith("【当前时间】")
    assert "\n\n【相关知识卡】\n" in user
    assert user.endswith("用户原文")


def test_system_prompt_unchanged_without_turn_cards(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="你是助手")
    scope = role_scope(role["id"])
    _wire_index(cards, tmp_path, FakeEmbedder())
    _seed(cards.store(scope), card_id="c1", statement="先查目录")
    _sync_scope(cards, scope)
    inj_no = cards.injection_for(conversation_id=None, role_id=role["id"])
    inj_q = cards.injection_for(
        conversation_id=None, role_id=role["id"], query="查目录"
    )
    assert inj_no.role_cards == inj_q.role_cards
    prompt_a = build_system_prompt(
        "default", "", user_memory=inj_no.owner_memory, role_cards=inj_no.role_cards
    )
    prompt_b = build_system_prompt(
        "default", "", user_memory=inj_q.owner_memory, role_cards=inj_q.role_cards
    )
    assert prompt_a == prompt_b


def test_strip_user_injections_three_cases():
    raw = "真实用户句"
    time_only = f"{current_time_block()}\n\n{raw}"
    turn_block = wrap_turn_cards("- 相关经验")
    both = f"{current_time_block()}\n\n{turn_block}\n\n{raw}"
    assert _strip_user_injections(both) == raw
    assert _strip_user_injections(time_only) == raw
    assert _strip_user_injections(raw) == raw


def test_render_with_ids_matches_render(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    _wire_index(cards, tmp_path, FakeEmbedder())
    st = cards.store(scope)
    _seed(st, card_id="c1", statement="经验一")
    _seed(st, card_id="c2", statement="外部事实", origin="external")
    _sync_scope(cards, scope)
    assert cards.render(scope) == cards.render_with_ids(scope)[0]

"""主人记忆超出字数预算时，按本轮原话补回相关事实。"""

from __future__ import annotations

import time

from app.engine.agent.message_builder import build_agent_messages
from app.engine.agent.prompt_parts import PARTS_KEY, category_for_kind
from app.engine.agent.prompts import build_system_prompt
from app.engine.memory.owner_index import OwnerMemoryIndex, OwnerRetrievalTuning
from app.engine.memory.renderer import MemoryRenderer
from app.index.partitioned import SearchIndex
from tests.test_card_index import FakeEmbedder, _unit_vec
from tests.test_knowledge_cards import _cards

CORE = "核心里也写了独有词Zeta"
OVERFLOW_OLD = "预算外独有词Zeta说明"
OVERFLOW_NEW = "预算外独有词Zeta说明（现行）"
IRREL = "周末常去爬山"
CAND = "候选独有词Zeta待印证"
FORGOT = "已遗忘独有词Zeta旧事"
QUERY = "独有词Zeta"


def _wire(cards, tmp_path, embedder, tuning=None):
    idx_dir = tmp_path / "owner_idx"
    search = SearchIndex(idx_dir / "partitioned.db", idx_dir / "vec", embedder)
    index = OwnerMemoryIndex(
        search,
        cards.owner.store,
        tuning or OwnerRetrievalTuning(),
    )
    cards.owner.owner_index = index
    cards.owner_index = index
    cards.owner.store.on_mutated = index.sync
    return index, search


def _seed(
    store,
    *,
    fact_id: str,
    statement: str,
    origin: str = "inferred",
    category: str = "preference",
    confidence: float = 0.5,
    status: str = "confirmed",
) -> None:
    store.upsert_fact(
        slot_key=f"{category}.{fact_id}",
        category=category,
        statement=statement,
        normalized_value_hash=f"h-{fact_id}",
        origin=origin,
        status=status,
        confidence=confidence,
        fact_id=fact_id,
    )


def _fit_only(service, fact_ids: set[str]) -> None:
    facts = [f for f in service.store.list_confirmed() if f["id"] in fact_ids]
    body, ids = MemoryRenderer(max_chars=10**9).render_with_ids(facts)
    assert ids == fact_ids
    service.memory_max_chars = len(body)


def test_fits_all_skips_retrieval(tmp_path):
    cards, roles, owner = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    index, _search = _wire(cards, tmp_path, FakeEmbedder())
    _seed(
        owner.store,
        fact_id="core",
        statement="核心偏好先给结论",
        origin="manual",
        confidence=1.0,
    )
    seen: list[str] = []
    real = index.search_turn

    def wrapped(query, **kwargs):
        seen.append(query)
        return real(query, **kwargs)

    index.search_turn = wrapped  # type: ignore[method-assign]
    text, ids = owner.render_context_with_ids()
    assert ids == {"core"}
    assert text == owner.render_context()
    assert "<!-- memory:" not in text

    inj = cards.injection_for(
        conversation_id=None, role_id=role["id"], query="核心偏好"
    )
    assert seen == []
    assert "核心偏好先给结论" in inj.owner_memory
    assert inj.turn_memory == ""
    assert "<!-- memory:" not in inj.owner_memory


def test_overflow_retrieves_relevant_and_skips_core_and_stale(tmp_path):
    cards, roles, owner = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    good = _unit_vec(0)
    bad = _unit_vec(1)
    emb = FakeEmbedder(
        text_vectors={
            QUERY: good,
            CORE: good,
            OVERFLOW_OLD: good,
            CAND: good,
            FORGOT: good,
            IRREL: bad,
        }
    )
    index, search = _wire(
        cards, tmp_path, emb, tuning=OwnerRetrievalTuning(min_vector_score=0.55)
    )
    _seed(
        owner.store,
        fact_id="core",
        statement=CORE,
        origin="manual",
        confidence=1.0,
    )
    _seed(owner.store, fact_id="overflow", statement=OVERFLOW_OLD, confidence=0.4)
    _seed(owner.store, fact_id="irrel", statement=IRREL, confidence=0.3)
    _seed(owner.store, fact_id="cand", statement=CAND, confidence=0.2)
    _seed(owner.store, fact_id="forgot", statement=FORGOT, confidence=0.1)
    index.sync()
    search.embed_pending()

    with owner.store._connect() as conn:
        conn.execute(
            "UPDATE memory_facts SET statement = ? WHERE id = ?",
            (OVERFLOW_NEW, "overflow"),
        )
        conn.execute(
            "UPDATE memory_facts SET status = 'candidate' WHERE id = ?",
            ("cand",),
        )
        conn.execute(
            "UPDATE memory_facts SET status = 'forgotten' WHERE id = ?",
            ("forgot",),
        )
        conn.commit()

    _fit_only(owner, {"core"})
    text, included = owner.render_context_with_ids()
    assert included == {"core"}
    assert OVERFLOW_NEW not in text
    assert IRREL not in text

    inj = cards.injection_for(
        conversation_id=None, role_id=role["id"], query=QUERY
    )
    assert CORE in inj.owner_memory
    assert CORE not in inj.turn_memory
    assert "（现行）" in inj.turn_memory
    assert IRREL not in inj.turn_memory
    assert CAND not in inj.turn_memory
    assert FORGOT not in inj.turn_memory
    assert CAND not in inj.owner_memory
    assert FORGOT not in inj.owner_memory
    assert "<!-- memory:" not in inj.owner_memory
    assert inj.turn_memory.count("- ") == 1


def test_overflow_without_index_keeps_core(tmp_path):
    cards, roles, owner = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    _seed(
        owner.store,
        fact_id="core",
        statement="核心甲",
        origin="manual",
        confidence=1.0,
    )
    _seed(owner.store, fact_id="extra", statement="放不下的乙", confidence=0.2)
    _fit_only(owner, {"core"})
    inj = cards.injection_for(
        conversation_id=None, role_id=role["id"], query="放不下的乙"
    )
    assert "核心甲" in inj.owner_memory
    assert inj.turn_memory == ""


def test_turn_memory_respects_limit(tmp_path):
    cards, roles, owner = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    _wire(cards, tmp_path, FakeEmbedder())
    for i in range(6):
        _seed(
            owner.store,
            fact_id=f"z{i}",
            statement=f"专有词Alpha{i} 说明",
            confidence=0.5,
        )
    owner.memory_max_chars = 1
    _text, ids = owner.render_context_with_ids()
    assert ids == set()
    inj = cards.injection_for(
        conversation_id=None,
        role_id=role["id"],
        query=" ".join(f"Alpha{i}" for i in range(6)),
    )
    assert inj.turn_memory.count("- ") == 5


def test_vector_timeout_falls_back_to_rare_term(tmp_path):
    cards, roles, owner = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    emb = FakeEmbedder(delay=1.0)
    _wire(
        cards,
        tmp_path,
        emb,
        tuning=OwnerRetrievalTuning(vector_timeout_s=0.2, min_vector_score=0.55),
    )
    _seed(
        owner.store,
        fact_id="core",
        statement="核心甲",
        origin="manual",
        confidence=1.0,
    )
    _seed(owner.store, fact_id="tail", statement="尾卡独有词Zeta说明", confidence=0.4)
    _seed(owner.store, fact_id="other", statement="另一件普通的事", confidence=0.3)
    _fit_only(owner, {"core"})
    t0 = time.monotonic()
    inj = cards.injection_for(
        conversation_id=None, role_id=role["id"], query="尾卡独有词Zeta"
    )
    elapsed = time.monotonic() - t0
    assert "尾卡独有词Zeta说明" in inj.turn_memory
    assert "另一件普通的事" not in inj.turn_memory
    assert "核心甲" in inj.owner_memory
    assert elapsed < 0.6


def test_index_failure_leaves_turn_empty(tmp_path):
    cards, roles, owner = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    _index, search = _wire(cards, tmp_path, FakeEmbedder())
    _seed(
        owner.store,
        fact_id="core",
        statement="核心甲",
        origin="manual",
        confidence=1.0,
    )
    _seed(owner.store, fact_id="tail", statement="预算外独有词Zeta说明", confidence=0.4)
    _fit_only(owner, {"core"})

    def boom(*_args, **_kwargs):
        raise RuntimeError("index down")

    search.search = boom  # type: ignore[method-assign]
    inj = cards.injection_for(
        conversation_id=None, role_id=role["id"], query="独有词Zeta"
    )
    assert "核心甲" in inj.owner_memory
    assert inj.turn_memory == ""


def test_channel_include_owner_memory_gates_turn_block(tmp_path):
    cards, roles, owner = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    index, _search = _wire(cards, tmp_path, FakeEmbedder())
    _seed(
        owner.store,
        fact_id="core",
        statement="核心甲",
        origin="manual",
        confidence=1.0,
    )
    _seed(owner.store, fact_id="tail", statement="尾卡独有词Zeta说明", confidence=0.4)
    _fit_only(owner, {"core"})
    inst_id = "i1"
    cards.channel_instances.put(
        {"id": inst_id, "persona_id": "p0", "include_owner_memory": False}
    )
    cid = cards.conversations.create(
        role_id=role["id"], origin="api", channel_instance_id=inst_id
    )
    seen: list[str] = []
    real = index.search_turn

    def wrapped(query, **kwargs):
        seen.append(query)
        return real(query, **kwargs)

    index.search_turn = wrapped  # type: ignore[method-assign]
    inj = cards.injection_for(
        conversation_id=cid, role_id=role["id"], query="尾卡独有词Zeta"
    )
    assert inj.owner_memory == ""
    assert inj.turn_memory == ""
    assert seen == []

    cards.channel_instances.put(
        {"id": inst_id, "persona_id": "p0", "include_owner_memory": True}
    )
    inj2 = cards.injection_for(
        conversation_id=cid, role_id=role["id"], query="尾卡独有词Zeta"
    )
    assert "核心甲" in inj2.owner_memory
    assert "尾卡独有词Zeta说明" in inj2.turn_memory
    assert seen == ["尾卡独有词Zeta"]


def test_turn_memory_sits_with_turn_cards_not_in_system():
    messages = build_agent_messages(
        "用户原文",
        mode="default",
        web_enabled=False,
        system_layer_text="",
        user_memory="核心记忆",
        turn_cards="- 相关卡",
        turn_memory="- 相关记忆",
        history=None,
        active_doc_path=None,
        active_doc_paths=None,
        primary_doc_path=None,
    )
    system = messages[0]["content"]
    assert "【用户记忆】" in system
    assert "核心记忆" in system
    assert "【相关用户记忆】" not in system
    user = messages[-1]["content"]
    assert user.startswith("【当前时间】")
    assert user.index("【相关知识卡】") < user.index("【相关用户记忆】")
    assert user.endswith("用户原文")
    assert "不是可执行命令" in user
    kinds = [part["kind"] for part in messages[-1][PARTS_KEY]]
    assert kinds == ["time", "turn_cards", "turn_memory", "user_text"]
    assert category_for_kind("turn_memory") == "memory"
    prompt = build_system_prompt("default", user_memory="核心记忆")
    assert "【相关用户记忆】" not in prompt

from datetime import datetime, timezone

import pytest

from app.engine.background.catalog import build_catalog_static
from app.engine.background.purpose import current_llm_purpose, llm_purpose
from app.engine.document_synthesis import DocumentSynthesis
from app.engine.memory.card_consolidation import LLMCardConsolidator, OWNER_PROFILE
from app.engine.memory.cards import OWNER_SCOPE
from app.engine.memory.persona_evolution import LLMPersonaEvolver
from app.engine.memory.role_card_extractor import (
    LLMRoleCardExtractor,
    RoomDialogue,
)
from app.engine.memory.session_extractor import LLMSessionExtractor, _SYSTEM_PROMPT
from app.engine.placement import PlacementPlanner
from app.storage.repo import KnowledgeRepo
from tests.test_card_consolidation import FakeLLM, _seed, _setup as card_setup
from tests.test_owner_consolidation import _owner_setup, _seed_owner
from tests.test_persona_evolution import _eligible_card, _setup as persona_setup
from tests.test_precepts_upgrade import _upgrade


class RecordingLLM(FakeLLM):
    def __init__(self, payload="{}", *, on_chat=None):
        super().__init__(payload)
        self.on_chat = on_chat

    def chat(self, messages, **_kwargs):
        self.last_messages = messages
        if self.on_chat:
            self.on_chat(messages)
        return super().chat(messages)


def _catalog_llm_variants() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for node in build_catalog_static()["nodes"].values():
        if node.get("type") != "llm":
            continue
        purpose = node["purpose"]
        for pv in node["prompts"]:
            out.append((purpose, pv["id"]))
    return sorted(out)


def _node_system(purpose: str, variant: str = "default") -> str:
    node = build_catalog_static()["nodes"][purpose]
    for pv in node["prompts"]:
        if pv["id"] == variant:
            return pv["system"]
    raise KeyError((purpose, variant))


def _runtime_variant(catalog_variant: str) -> str | None:
    return None if catalog_variant == "default" else catalog_variant


def _run_memory_owner_extract(_tmp_path, llm):
    LLMSessionExtractor(llm).extract(
        [("user", "我长期做教育科技产品。")],
        confirmed_summary=[],
    )


def _run_cards_extract_dm(_tmp_path, llm):
    cards, _, _scope, lens = card_setup(_tmp_path)
    LLMRoleCardExtractor(llm).extract(
        [("user", "以后这类合同先查违约条款。")],
        lens=lens,
        existing_cards=[],
        owner_summary=[],
    )


def _run_cards_extract_room(_tmp_path, llm):
    cards, _, _scope, lens = card_setup(_tmp_path)
    room = RoomDialogue(
        kind="group",
        title="协作",
        peer_names=["同伴"],
        context=[],
        lines=[("本角色", "以后这类合同先查违约条款。")],
    )
    LLMRoleCardExtractor(llm).extract_room(
        room, lens=lens, existing_cards=[], owner_summary=[]
    )


def _run_memory_owner_consolidate(tmp_path, llm):
    cards, owner, _roles = _owner_setup(tmp_path)
    st = owner.store
    _seed_owner(st, fact_id="oa", statement="主人记忆甲内容")
    _seed_owner(st, fact_id="ob", statement="主人记忆乙内容", vhash="hob")
    cards.owner_consolidator = LLMCardConsolidator(llm, cards, profile=OWNER_PROFILE)
    cards.owner_consolidator.run(OWNER_SCOPE, None)


def _run_cards_consolidate(tmp_path, llm):
    cards, _, scope, lens = card_setup(tmp_path)
    st = cards.store(scope)
    _seed(st, fact_id="c1", statement="卡一内容足够长", kind="lesson")
    _seed(st, fact_id="c2", statement="卡二内容足够长", vhash="hc", kind="lesson")
    cards.consolidator = LLMCardConsolidator(llm, cards)
    cards.consolidator.run(scope, lens)


def _run_persona_evolve(tmp_path, llm):
    cards, _roles, scope, lens, _evolver = persona_setup(tmp_path)
    st = cards.store(scope)
    _eligible_card(st, cards, scope)
    cards.evolver = LLMPersonaEvolver(llm, cards)
    cards.evolver.run(scope, lens)


def _run_docs_archive_whole(_tmp_path, llm):
    DocumentSynthesis(llm).archive_transcript(
        "简短会话", system_rules="{《戒律》与会话总结规约}"
    )


def _run_docs_archive_segment(_tmp_path, llm):
    DocumentSynthesis(llm).archive_segment(
        "（片段正文）",
        "{《戒律》规约}",
        {"first_message_id": "m1", "last_message_id": "m9"},
    )


def _run_docs_archive_merge_segments(_tmp_path, llm):
    DocumentSynthesis(llm).merge_archive_segments(
        ["段摘要一", "段摘要二"], "{规约}"
    )


def _run_docs_reorganize(_tmp_path, llm):
    DocumentSynthesis(llm).reorganize_existing(
        "（已有正文）", "（新内容）", "示例标题"
    )


def _run_docs_merge(_tmp_path, llm):
    DocumentSynthesis(llm).merge_documents(
        [("路径/a.md", "正文 A")], "合并要求示例"
    )


def _run_docs_placement_understand(_tmp_path, llm):
    repo = KnowledgeRepo(_tmp_path / "kb", protected_dirs=("系统",))
    planner = PlacementPlanner(repo, object(), llm)
    planner.understand("待归位正文示例")


def _run_docs_placement_decide(_tmp_path, llm):
    repo = KnowledgeRepo(_tmp_path / "kb2", protected_dirs=("系统",))
    planner = PlacementPlanner(repo, object(), llm)
    planner.decide("正文", "摘要", [])


def _run_precepts_resolve(tmp_path, llm):
    _repo, _writer, _layer, up = _upgrade(tmp_path, llm=llm)
    pending = {
        "marked": "《戒律》全文占位",
        "conflicts": [{"base": "旧官方块", "ours": "本地块", "theirs": "新官方块"}],
        "proposed": "足够长的待确认合并稿正文占位" * 3,
        "ours": "本地稿占位",
    }
    up._resolve_with_llm(pending)


LLM_CONTRACT_CASES: list[tuple[str, str, str, object]] = [
    ("memory.owner_extract", "default", '{"items":[]}', _run_memory_owner_extract),
    ("cards.extract", "dm", '{"items":[]}', _run_cards_extract_dm),
    ("cards.extract", "room", '{"items":[]}', _run_cards_extract_room),
    ("memory.owner_consolidate", "default", {"ops": []}, _run_memory_owner_consolidate),
    ("cards.consolidate", "default", {"ops": []}, _run_cards_consolidate),
    ("persona.evolve", "default", {"edits": [], "proposals": []}, _run_persona_evolve),
    ("docs.archive", "whole", "# ok\n", _run_docs_archive_whole),
    ("docs.archive", "segment", "# ok\n", _run_docs_archive_segment),
    ("docs.archive", "merge_segments", "# ok\n", _run_docs_archive_merge_segments),
    ("docs.reorganize", "default", "# ok\n", _run_docs_reorganize),
    ("docs.merge", "default", "# ok\n", _run_docs_merge),
    ("docs.placement", "understand", "一句话摘要", _run_docs_placement_understand),
    (
        "docs.placement",
        "decide",
        '{"action":"new","rel_path":"未分类/x.md","title":"t","category":"","tags":[],"ambiguous":false,"reason":""}',
        _run_docs_placement_decide,
    ),
    (
        "precepts.resolve",
        "default",
        "合并后的戒律正文足够长且无冲突标记" * 4,
        _run_precepts_resolve,
    ),
]


@pytest.mark.parametrize(
    "purpose,variant,payload,runner",
    LLM_CONTRACT_CASES,
    ids=[f"{p}-{v}" for p, v, _, _ in LLM_CONTRACT_CASES],
)
def test_llm_system_matches_catalog(tmp_path, purpose, variant, payload, runner):
    seen: dict = {}

    def on_chat(messages):
        seen["purpose"] = current_llm_purpose()
        seen["system"] = messages[0]["content"]

    llm = RecordingLLM(payload, on_chat=on_chat)
    runner(tmp_path, llm)

    assert seen["purpose"] is not None
    assert seen["purpose"].purpose == purpose
    assert seen["purpose"].variant == _runtime_variant(variant)
    assert seen["system"] == _node_system(purpose, variant)


def test_llm_contract_cases_cover_catalog():
    expected = set(_catalog_llm_variants())
    actual = {(p, v) for p, v, _, _ in LLM_CONTRACT_CASES}
    assert actual == expected


def test_session_extract_system_catalog():
    assert _node_system("memory.owner_extract", "default") == _SYSTEM_PROMPT


def test_usage_purpose_column(tmp_path):
    from app.engine.usage.recorder import UsageRecorder
    from app.engine.usage.store import UsageStore

    store = UsageStore(tmp_path / "usage.db")
    rec = UsageRecorder(store)
    with llm_purpose("memory.owner_extract"):
        rec.record(model="m", kind="chat", role="utility", tokens_known=False)
    cols = {r[1] for r in store.conn.execute("PRAGMA table_info(usage_events)")}
    assert "purpose" in cols
    row = store.conn.execute(
        "SELECT purpose FROM usage_events LIMIT 1"
    ).fetchone()
    assert row["purpose"] == "memory.owner_extract"
    store.close()


def test_memory_subgraph_apply_settings(tmp_path):
    from app.config import Settings
    from app.deps_memory import build_memory_subgraph
    from app.engine.conversations import ConversationStore
    from app.engine.memory.service import MemoryService
    from app.engine.memory.store import MemoryStore
    from app.engine.roles import RoleStore
    from tests.helpers import make_writer

    kb = tmp_path / "knowledge"
    repo = KnowledgeRepo(kb, protected_dirs=("系统",))
    writer = make_writer(repo, tmp_path)
    ms = MemoryService(
        MemoryStore(tmp_path / "memory.db", owner_key="ws"), repo, knowledge_writer=writer
    )
    conv = ConversationStore(tmp_path / "conv")
    roles = RoleStore(tmp_path / "roles")
    settings = Settings(kb_path=kb, memory_session_idle_hours=6.0, memory_decay_stale_days=30)
    subgraph = build_memory_subgraph(
        settings,
        repo,
        FakeLLM("{}"),
        conv,
        memory_service=ms,
        roles=roles,
        channel_instances=None,
    )
    assert subgraph.worker.idle_hours == 6.0
    settings2 = settings.model_copy(
        update={"memory_session_idle_hours": 12.0, "memory_decay_stale_days": 45}
    )
    subgraph.apply_settings(settings2)
    assert subgraph.worker.idle_hours == 12.0
    assert subgraph.maintenance.config.stale_days_goal_project == 45


def test_maintain_pause_consolidation_still_evolve(tmp_path):
    cards, _roles, scope, lens, evolver = persona_setup(tmp_path)
    st = cards.store(scope)
    _eligible_card(st, cards, scope)
    _seed(st, fact_id="c2", statement="卡一内容足够长", kind="lesson")
    _seed(st, fact_id="c3", statement="卡二内容足够长", vhash="hc", kind="lesson")
    consolidate_calls = {"n": 0}
    evolve_calls = {"n": 0}

    class SpyConsolidator(LLMCardConsolidator):
        def run(self, *args, **kwargs):
            consolidate_calls["n"] += 1
            return {"ops_proposed": 0, "ops_applied": 0, "dropped": []}

    class SpyEvolver(LLMPersonaEvolver):
        def run(self, s, l):
            evolve_calls["n"] += 1
            return evolver.run(s, l)

    cards.consolidator = SpyConsolidator(FakeLLM({"ops": []}), cards)
    cards.owner_consolidator = LLMCardConsolidator(
        FakeLLM({"ops": []}), cards, profile=OWNER_PROFILE
    )
    cards.evolver = SpyEvolver(FakeLLM({"edits": [], "proposals": []}), cards)
    now = datetime.now(timezone.utc)
    out = cards.maintain(now=now, paused=frozenset({"consolidation"}))
    assert out["consolidated_scopes"] == 0
    assert consolidate_calls["n"] == 0
    assert out["evolved_scopes"] == 1
    assert evolve_calls["n"] == 1


def test_maintain_pause_evolution_still_consolidate(tmp_path):
    cards, owner, _roles = _owner_setup(tmp_path)
    st_owner = owner.store
    _seed_owner(st_owner, fact_id="oa", statement="主人记忆甲内容")
    _seed_owner(st_owner, fact_id="ob", statement="主人记忆乙内容", vhash="hob")
    cards, _roles, scope, lens = card_setup(tmp_path)
    st = cards.store(scope)
    _eligible_card(st, cards, scope)
    _seed(st, fact_id="c2", statement="卡一内容足够长", kind="lesson")
    _seed(st, fact_id="c3", statement="卡二内容足够长", vhash="hc", kind="lesson")
    evolve_calls = {"n": 0}

    class SpyEvolver(LLMPersonaEvolver):
        def run(self, *args, **kwargs):
            evolve_calls["n"] += 1
            return {"skipped": "should not run"}

    cards.consolidator = LLMCardConsolidator(FakeLLM({"ops": []}), cards)
    cards.owner_consolidator = LLMCardConsolidator(
        FakeLLM({"ops": []}), cards, profile=OWNER_PROFILE
    )
    cards.evolver = SpyEvolver(FakeLLM({"edits": [], "proposals": []}), cards)
    now = datetime.now(timezone.utc)
    out = cards.maintain(now=now, paused=frozenset({"persona_evolution"}))
    assert out["consolidated_scopes"] >= 2
    assert out["evolved_scopes"] == 0
    assert evolve_calls["n"] == 0


def test_drain_derivation_session_observe_pause(client, monkeypatch):
    from app.main import _drain_derivation

    app = client.app
    container = app.state.container
    memory_calls = {"n": 0}
    embed_calls = {"n": 0}

    def memory_drain(_batch):
        memory_calls["n"] += 1
        return 0

    def embed_pending(_batch):
        embed_calls["n"] += 1
        return 0

    monkeypatch.setattr(container.memory_worker, "drain", memory_drain)
    monkeypatch.setattr(container.derivation_worker, "drain", lambda _b: 0)
    monkeypatch.setattr(container.search_index, "embed_pending", embed_pending)

    container.settings = container.settings.model_copy(
        update={"background_paused": ["session_observe"]}
    )
    paused_result = _drain_derivation(app)
    assert paused_result["session_observe"] == "paused"
    assert memory_calls["n"] == 0
    assert embed_calls["n"] == 1

    container.settings = container.settings.model_copy(update={"background_paused": []})
    active_result = _drain_derivation(app)
    assert active_result["session_observe"] == 0
    assert memory_calls["n"] == 1
    assert embed_calls["n"] == 2

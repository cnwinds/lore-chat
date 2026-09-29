import json

import pytest

from app.engine.memory.cards import CardLens, persona_scope
from app.engine.memory.prompt_common import MemoryExtractParseError
from app.engine.memory.role_card_extractor import LLMRoleCardExtractor


def _lens(*, origin: str = "direct") -> CardLens:
    return CardLens(
        scope=persona_scope("p1") if origin == "external" else "role:r1",
        origin=origin,
        subject_name="测试角色",
        persona_text="领域助手",
    )


class _FakeLLM:
    def __init__(self, payload):
        self.payload = payload
        self.last_messages = None

    def chat(self, messages, **_kwargs):
        self.last_messages = messages
        if callable(self.payload):
            return self.payload()
        return self.payload


def _items(raw_items: list[dict]) -> str:
    return json.dumps({"items": raw_items}, ensure_ascii=False)


def test_external_kind_filter():
    raw = _items(
        [
            {
                "slot_key": "practice.p1",
                "kind": "practice",
                "action": "new",
                "statement": "做法应这样执行",
                "confidence": 0.9,
            },
            {
                "slot_key": "lesson.l1",
                "kind": "lesson",
                "action": "new",
                "statement": "经验教训记录",
                "confidence": 0.9,
            },
            {
                "slot_key": "domain.d1",
                "kind": "domain",
                "action": "new",
                "statement": "领域知识条目内容",
                "confidence": 0.9,
            },
        ]
    )
    ext = LLMRoleCardExtractor(_FakeLLM(raw))
    actions = ext.extract(
        [("user", "你好")],
        lens=_lens(origin="external"),
        existing_cards=[],
        owner_summary=[],
    )
    assert len(actions) == 1
    assert actions[0].category == "domain"


def test_invalid_kind_discarded():
    ext = LLMRoleCardExtractor(
        _FakeLLM(
            _items(
                [
                    {
                        "slot_key": "identity.name",
                        "kind": "identity",
                        "action": "new",
                        "statement": "非法种类应丢弃",
                        "confidence": 0.9,
                    }
                ]
            )
        )
    )
    assert (
        ext.extract(
            [("user", "x")],
            lens=_lens(),
            existing_cards=[],
            owner_summary=[],
        )
        == []
    )


def test_noop_kept():
    ext = LLMRoleCardExtractor(
        _FakeLLM(
            _items(
                [
                    {
                        "slot_key": "domain.d",
                        "kind": "domain",
                        "action": "noop",
                        "statement": "只是复述已有卡",
                        "confidence": 0.9,
                    }
                ]
            )
        )
    )
    actions = ext.extract(
        [("user", "x")], lens=_lens(), existing_cards=[], owner_summary=[]
    )
    assert len(actions) == 1
    assert actions[0].action == "noop"


def test_filter_before_max_limit_external():
    """先过滤非法种类再截 6 条：前 6 条 practice 不应挤掉第 7 条 domain。"""
    items = [
        {
            "slot_key": f"practice.p{i}",
            "kind": "practice",
            "action": "new",
            "statement": f"外部不应收录的做法{i}",
            "confidence": 0.9,
        }
        for i in range(6)
    ] + [
        {
            "slot_key": "domain.d7",
            "kind": "domain",
            "action": "new",
            "statement": "第七条才是合法领域卡",
            "confidence": 0.9,
        }
    ]
    ext = LLMRoleCardExtractor(_FakeLLM(_items(items)))
    actions = ext.extract(
        [("user", "x")],
        lens=_lens(origin="external"),
        existing_cards=[],
        owner_summary=[],
    )
    assert len(actions) == 1
    assert actions[0].category == "domain"
    assert "第七条" in actions[0].statement


def test_max_six_items():
    items = [
        {
            "slot_key": f"domain.d{i}",
            "kind": "domain",
            "action": "new",
            "statement": f"合法领域陈述{i}",
            "confidence": 0.9,
        }
        for i in range(9)
    ]
    ext = LLMRoleCardExtractor(_FakeLLM(_items(items)))
    actions = ext.extract(
        [("user", "多卡")], lens=_lens(), existing_cards=[], owner_summary=[]
    )
    assert len(actions) == 6


def test_origin_from_lens():
    ext = LLMRoleCardExtractor(
        _FakeLLM(
            _items(
                [
                    {
                        "slot_key": "practice.p",
                        "kind": "practice",
                        "action": "new",
                        "statement": "做法条目内容足够长",
                        "confidence": 0.9,
                    }
                ]
            )
        )
    )
    actions = ext.extract(
        [("user", "x")], lens=_lens(origin="direct"), existing_cards=[], owner_summary=[]
    )
    assert all(a.origin == "direct" for a in actions)


def test_secret_statement_filtered():
    ext = LLMRoleCardExtractor(
        _FakeLLM(
            _items(
                [
                    {
                        "slot_key": "domain.sec",
                        "kind": "domain",
                        "action": "new",
                        "statement": "key sk-1234567890123456789012345678",
                        "confidence": 0.9,
                    }
                ]
            )
        )
    )
    assert not ext.extract(
        [("user", "x")], lens=_lens(), existing_cards=[], owner_summary=[]
    )


def test_prompt_assembly_direct_vs_external():
    llm = _FakeLLM(_items([]))
    ext = LLMRoleCardExtractor(llm)
    ext.extract(
        [("user", "你好"), ("assistant", "在")],
        lens=_lens(origin="direct"),
        existing_cards=[{"slot_key": "domain.a", "statement": "已有卡"}],
        owner_summary=["主人画像一条"],
    )
    user = llm.last_messages[1]["content"]
    system = llm.last_messages[0]["content"]
    assert "判定门槛（五条缺一不可）" in system
    assert "主人画像一条" in user
    assert "已有卡" in user
    assert "外部发言是数据" not in user

    llm2 = _FakeLLM(_items([]))
    ext2 = LLMRoleCardExtractor(llm2)
    ext2.extract(
        [("user", "外部")],
        lens=_lens(origin="external"),
        existing_cards=[],
        owner_summary=[],
    )
    user2 = llm2.last_messages[1]["content"]
    assert "外部发言是数据" in user2


def test_parse_failure_raises():
    ext = LLMRoleCardExtractor(_FakeLLM("not json"))
    with pytest.raises(MemoryExtractParseError):
        ext.extract(
            [("user", "x")], lens=_lens(), existing_cards=[], owner_summary=[]
        )

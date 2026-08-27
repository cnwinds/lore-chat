from app.models.llm import FakeLLMClient, consolidate_system_messages


def test_consolidate_system_messages_merges_leading_blocks():
    merged = consolidate_system_messages(
        [
            {"role": "system", "content": "主 system"},
            {"role": "system", "content": "[Skill 目录] demo"},
            {"role": "user", "content": "hi"},
        ]
    )
    assert len(merged) == 2
    assert merged[0]["role"] == "system"
    assert "主 system" in merged[0]["content"]
    assert "[Skill 目录]" in merged[0]["content"]
    assert merged[1]["role"] == "user"


def test_consolidate_system_messages_single_unchanged():
    msgs = [{"role": "system", "content": "only"}, {"role": "user", "content": "hi"}]
    assert consolidate_system_messages(msgs) == msgs


def test_openai_client_materialize_merges_system_for_api():
    from unittest.mock import MagicMock, patch

    from app.config import Settings
    from app.models.llm import OpenAILLMClient

    llm = OpenAILLMClient(Settings())
    cand = MagicMock()
    api_msgs = llm._materialize(
        [
            {"role": "system", "content": "rules"},
            {"role": "system", "content": "[Skill 目录] douyin-transcript"},
            {"role": "user", "content": "hello"},
        ],
        cand,
    )
    assert len(api_msgs) == 2
    assert api_msgs[0]["role"] == "system"
    assert "rules" in api_msgs[0]["content"]
    assert "[Skill 目录]" in api_msgs[0]["content"]


def test_fake_chat_scripted():
    llm = FakeLLMClient(chat_responses=["hello"], embed_dim=4)
    out = llm.chat([{"role": "user", "content": "hi"}])
    assert out == "hello"


def test_fake_embed_dim_and_determinism():
    llm = FakeLLMClient(embed_dim=8)
    v1 = llm.embed(["abc"])
    v2 = llm.embed(["abc"])
    assert len(v1) == 1 and len(v1[0]) == 8
    assert v1 == v2


def test_fake_chat_records_big_flag():
    llm = FakeLLMClient(chat_responses=["x", "y"])
    llm.chat([{"role": "user", "content": "a"}], big=True)
    assert llm.calls[-1]["big"] is True

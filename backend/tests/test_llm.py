from app.models.llm import FakeLLMClient


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

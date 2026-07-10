from app.engine.intent import classify_intent
from app.models.llm import FakeLLMClient


def test_classify_recall_by_heuristic():
    llm = FakeLLMClient(chat_responses=["remember"])
    assert classify_intent("windows终端怎么设置utf8编码", llm) == "recall"


def test_is_question_only():
    from app.engine.intent import is_question_only

    assert is_question_only("windows终端怎么设置utf8编码")
    assert not is_question_only("kubectl get pods 列出所有 pod")
    assert not is_question_only("记录如下配置：\n```powershell\nchcp 65001\n```")


def test_classify_remember_long_content():
    llm = FakeLLMClient(chat_responses=["remember"])
    text = "记录如下配置：\n```powershell\nchcp 65001\n```\n" * 5
    assert classify_intent(text, llm) == "remember"


def test_classify_uses_llm_for_ambiguous_short_text():
    llm = FakeLLMClient(chat_responses=["recall"])
    assert classify_intent("docker ps", llm) == "recall"

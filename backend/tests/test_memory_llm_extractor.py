import json

from app.engine.memory.llm_extractor import (
    LLMMemoryExtractor,
    locate_statement_span,
)
from app.engine.memory.policy import is_template_like
from app.models.llm import FakeLLMClient


def test_locate_statement_span():
    text = "我偏好简洁回答，谢谢"
    assert locate_statement_span(text, "我偏好简洁回答") == (0, 7)


def test_template_like_rejects_fill_in():
    assert is_template_like("我是一个______(职业)")
    assert not is_template_like("我是后端工程师")


def test_llm_extractor_parses_and_validates_quote():
    payload = json.dumps(
        {
            "candidates": [
                {
                    "statement": "我偏好简洁回答",
                    "category": "preference",
                    "origin": "direct",
                    "confidence": 0.95,
                }
            ]
        }
    )
    llm = FakeLLMClient(chat_responses=[payload])
    ext = LLMMemoryExtractor(llm)
    text = "我偏好简洁回答，谢谢"
    out = ext.extract(text)
    assert len(out.candidates) == 1
    assert out.candidates[0].statement == "我偏好简洁回答"


def test_llm_extractor_skips_template_from_model():
    payload = json.dumps(
        {
            "candidates": [
                {
                    "statement": "我是一个______(职业)",
                    "category": "identity",
                    "origin": "direct",
                    "confidence": 0.9,
                }
            ]
        }
    )
    llm = FakeLLMClient(chat_responses=[payload])
    out = LLMMemoryExtractor(llm).extract("我是一个______(职业)")
    assert out.candidates == []


def test_llm_extractor_rejects_hallucinated_evidence():
    payload = json.dumps(
        {
            "candidates": [
                {
                    "statement": "用户喜欢咖啡",
                    "evidence": "用户喜欢咖啡",
                    "category": "preference",
                    "origin": "inferred",
                    "confidence": 0.7,
                }
            ]
        }
    )
    llm = FakeLLMClient(chat_responses=[payload])
    out = LLMMemoryExtractor(llm).extract("我其实更爱茶")
    assert out.candidates == []


def test_llm_extractor_accepts_rewritten_statement_with_evidence():
    user = (
        "1 我是一名软件工程师，主要致力于游戏服务器的高并发，可伸缩架构的设计和开发。"
        "具备较强的线上问题的分析定位和解决能力。"
    )
    rewritten = (
        "我是一名软件工程师，主要致力于游戏服务器的高并发、可伸缩架构设计与开发，"
        "并具备较强的线上问题分析与定位能力。"
    )
    evidence = (
        "我是一名软件工程师，主要致力于游戏服务器的高并发，可伸缩架构的设计和开发。"
        "具备较强的线上问题的分析定位和解决能力。"
    )
    payload = json.dumps(
        {
            "candidates": [
                {
                    "statement": rewritten,
                    "evidence": evidence,
                    "category": "identity",
                    "origin": "direct",
                    "confidence": 0.95,
                }
            ]
        }
    )
    llm = FakeLLMClient(chat_responses=[payload])
    out = LLMMemoryExtractor(llm).extract(user)
    assert len(out.candidates) == 1
    assert out.candidates[0].statement == rewritten
    assert out.candidates[0].statement not in user
    assert out.candidates[0].rewritten is True


def test_llm_extractor_rejects_rewrite_with_unrelated_evidence():
    payload = json.dumps(
        {
            "candidates": [
                {
                    "statement": "用户喜欢咖啡",
                    "evidence": "我其实更爱茶",
                    "category": "preference",
                    "origin": "inferred",
                    "confidence": 0.7,
                }
            ]
        }
    )
    llm = FakeLLMClient(chat_responses=[payload])
    out = LLMMemoryExtractor(llm).extract("我其实更爱茶")
    assert out.candidates == []


def test_llm_extractor_rejects_template_evidence():
    payload = json.dumps(
        {
            "candidates": [
                {
                    "statement": "我是后端工程师",
                    "evidence": "我是一个______(职业)",
                    "category": "identity",
                    "origin": "direct",
                    "confidence": 0.9,
                }
            ]
        }
    )
    llm = FakeLLMClient(chat_responses=[payload])
    out = LLMMemoryExtractor(llm).extract("我是一个______(职业)")
    assert out.candidates == []

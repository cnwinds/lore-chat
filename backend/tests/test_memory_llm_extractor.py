import json

from app.engine.memory.llm_extractor import (
    LLMMemoryExtractor,
    is_template_like,
    locate_statement_span,
)
from app.engine.memory.policy import validate_evidence
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
    assert validate_evidence(text, out.candidates[0])


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


def test_llm_extractor_rejects_non_substring():
    payload = json.dumps(
        {
            "candidates": [
                {
                    "statement": "用户喜欢咖啡",
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

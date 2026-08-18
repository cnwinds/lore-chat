from app.demo.redact import redact_secrets_for_guest


def test_top_level_keys_fully_masked():
    out = redact_secrets_for_guest({"openai_api_key": "sk***cdef", "big_model": "gpt-4o"})
    assert out["openai_api_key"] == "***"
    assert out["big_model"] == "gpt-4o"


def test_nested_chain_keys_fully_masked():
    out = redact_secrets_for_guest(
        {
            "chat_models": [{"id": "a", "model": "gpt-4o", "api_key": "sk***wxyz"}],
            "search_providers": [{"provider": "tavily", "api_key": "tv***1234"}],
            "image_providers": [{"provider": "x", "api_key": "im***5678"}],
        }
    )
    assert out["chat_models"][0]["api_key"] == "***"
    assert out["chat_models"][0]["model"] == "gpt-4o"
    assert out["search_providers"][0]["api_key"] == "***"
    assert out["image_providers"][0]["api_key"] == "***"


def test_none_key_stays_none():
    out = redact_secrets_for_guest({"small_api_key": None})
    assert out["small_api_key"] is None


def test_input_is_not_mutated():
    src = {"openai_api_key": "sk***cdef"}
    redact_secrets_for_guest(src)
    assert src["openai_api_key"] == "sk***cdef"

import pytest

from app.engine.doc_context import (
    DocContextValidationError,
    normalize_doc_context_items,
    parse_doc_context_for_api,
    split_doc_context,
)


def test_normalize_legacy_strings():
    items = normalize_doc_context_items(["a.md", "b.md"])
    assert items == [
        {"path": "a.md", "kind": "document"},
        {"path": "b.md", "kind": "document"},
    ]


def test_split_doc_context():
    items = [
        {"path": "doc.md", "kind": "document"},
        {"path": "skill/foo", "kind": "skill_root"},
    ]
    docs, skills = split_doc_context(items)
    assert docs == ["doc.md"]
    assert skills == ["skill/foo"]


def test_parse_api_rejects_string_item():
    with pytest.raises(DocContextValidationError):
        parse_doc_context_for_api(["x.md"])


def test_parse_api_rejects_invalid_kind():
    with pytest.raises(DocContextValidationError):
        parse_doc_context_for_api([{"path": "x", "kind": "skill_single"}])

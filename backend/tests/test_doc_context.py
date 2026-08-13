import pytest

from app.engine.doc_context import (
    DocContextValidationError,
    doc_context_paths,
    normalize_doc_context_items,
    parse_doc_context_for_api,
)


def test_normalize_legacy_strings():
    items = normalize_doc_context_items(["a.md", "b.md"])
    assert items == [
        {"path": "a.md", "kind": "document"},
        {"path": "b.md", "kind": "document"},
    ]


def test_normalize_legacy_skill_root_to_document():
    items = normalize_doc_context_items(
        [{"path": "技能/foo", "kind": "skill_root"}]
    )
    assert items == [{"path": "技能/foo", "kind": "document"}]


def test_doc_context_paths():
    assert doc_context_paths(
        [
            {"path": "doc.md", "kind": "document"},
            {"path": "技能/foo", "kind": "document"},
        ]
    ) == ["doc.md", "技能/foo"]


def test_parse_api_rejects_string_item():
    with pytest.raises(DocContextValidationError):
        parse_doc_context_for_api(["x.md"])


def test_parse_api_rejects_invalid_kind():
    with pytest.raises(DocContextValidationError):
        parse_doc_context_for_api([{"path": "x", "kind": "skill_single"}])


def test_parse_api_coerces_skill_root():
    items = parse_doc_context_for_api(
        [{"path": "技能/foo", "kind": "skill_root"}]
    )
    assert items == [{"path": "技能/foo", "kind": "document"}]

import pytest

from app.index.partitioned.tokenize import index_terms, query_terms


@pytest.mark.parametrize(
    "text,expected",
    [
        ("先查违约条款", ["先查", "查违", "违约", "约条", "条款"]),
        ("我", ["我"]),
        ("GPT-4o 模型", ["gpt", "4o", "模型"]),
        ("ＧＰＴ", ["gpt"]),
        ("用Python写", ["用", "python", "写"]),
        (
            "超过25MB，切片后成功",
            ["超过", "25mb", "切片", "片后", "后成", "成功"],
        ),
        ("a_b", ["a", "b"]),
        ("", []),
        ("，。！", []),
    ],
)
def test_index_terms_table(text, expected):
    assert index_terms(text) == expected


def test_query_terms_dedup_preserves_order():
    text = "违约 违约 条款"
    assert index_terms(text).count("违约") >= 2
    qt = query_terms(text)
    assert qt.count("违约") == 1
    assert qt.index("违约") < qt.index("条款")


def test_query_terms_same_kernel_as_index():
    text = "先查违约条款"
    assert query_terms(text) == list(dict.fromkeys(index_terms(text)))

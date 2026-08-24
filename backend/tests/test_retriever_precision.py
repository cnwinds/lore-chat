from app.engine.retriever import Retriever
from app.index.conversation_fts import ConversationFTS
from app.index.conversation_vector import ConversationVector
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.message_chunk import MessageChunk
from app.index.revision import IndexRevision
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient


def _build(tmp_path, *, llm=None):
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    cfts = ConversationFTS(tmp_path / "conversation_fts.db")
    cvec = ConversationVector(tmp_path / "conv_vec")
    rev = IndexRevision(tmp_path / "revision.txt")
    llm = llm or FakeLLMClient(chat_responses=[], embed_dim=8)
    idx = Indexer(vi, fi, llm)
    retr = Retriever(
        vi,
        fi,
        llm,
        min_score=0.0,
        conversation_fts=cfts,
        conversation_vector=cvec,
        index_revision=rev,
        kb_first_throttle=True,
    )
    return idx, retr, cfts, cvec, llm


def test_media_grant_query_filters_url_noise_conversation(tmp_path):
    idx, retr, cfts, _cvec, _llm = _build(tmp_path)
    idx.reindex_doc(
        "技术/media-grant.md",
        "Media Grant 提供不透明 capability URL，供上游无登录拉取媒体。",
    )
    cfts.upsert_message_chunks(
        conversation_id="caddy-session",
        message_id="m1",
        role="assistant",
        ts="2026-08-01T10:00:00",
        conversation_title="Caddy 反代配置",
        chunks=[
            MessageChunk(
                0,
                0,
                80,
                "在 Caddyfile 里配置反代，注意 URL 路径与 401 鉴权放行 /api/media/grant。",
            )
        ],
    )

    page = retr.search("Media Grant 不透明 capability URL", k=5, scope="all")

    assert page.match_strength == "strong"
    kb_hits = [h for h in page.hits if not h.source.startswith("conv:")]
    conv_hits = [h for h in page.hits if h.source.startswith("conv:")]
    assert kb_hits
    assert not conv_hits


def test_chinese_multi_keyword_still_recalls(tmp_path):
    idx, retr, _cfts, _cvec, _llm = _build(tmp_path)
    idx.reindex_doc(
        "运营/教培机构合作会谈材料.md",
        "面向教培机构的合作会谈材料，强调数据本地部署。",
    )

    page = retr.search("产品介绍 教培机构 合作", k=5, scope="knowledge")

    assert page.match_strength == "strong"
    assert any("教培机构" in h.chunk for h in page.hits)


def test_weak_only_returns_empty_with_weak_strength(tmp_path):
    _idx, retr, cfts, _cvec, _llm = _build(tmp_path)
    cfts.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="t",
        conversation_title="杂谈",
        chunks=[MessageChunk(0, 0, 20, "今天天气不错，顺便提到了 URL 这个词。")],
    )

    page = retr.search("Media Grant 不透明 capability URL", k=5, scope="conversations")

    assert page.hits == []
    assert page.match_strength in ("weak", "none")

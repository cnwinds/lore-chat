from __future__ import annotations

from dataclasses import dataclass

from app.index.vector import VectorIndex
from app.index.fulltext import FullTextIndex
from app.index.types import Hit
from app.logging_config import get_logger
from app.models.llm import LLMClient

_ATTACH_MARKER = "/attachments/"

# 向量余弦相似度下限；低于此视为无关（小库中否则会把全部文档都当最近邻返回）
MIN_VECTOR_SCORE = 0.45


@dataclass
class Answer:
    text: str
    sources: list[str]
    attachments: list[str]


class Retriever:
    def __init__(
        self,
        vector: VectorIndex,
        fulltext: FullTextIndex,
        llm: LLMClient,
        *,
        excluded_prefixes: tuple[str, ...] = (),
        min_score: float = MIN_VECTOR_SCORE,
    ):
        self.vector = vector
        self.fulltext = fulltext
        self.llm = llm
        # 命中来源以这些前缀开头的结果直接剔除（如系统控制层「系统/」，不参与检索）
        self.excluded_prefixes = tuple(excluded_prefixes)
        self.min_score = min_score

    def _excluded(self, source: str) -> bool:
        norm = (source or "").replace("\\", "/").lstrip("/")
        return any(norm.startswith(p) for p in self.excluded_prefixes)

    def search(self, query: str, k: int = 5) -> list[Hit]:
        ft_hits = self.fulltext.query(query, k=k)
        vec_hits: list[Hit] = []
        try:
            q_emb = self.llm.embed([query])[0]
            vec_hits = [
                h for h in self.vector.query(q_emb, k=k) if h.score >= self.min_score
            ]
        except Exception:
            # Chroma/SQLite 跨线程或元数据异常时，全文检索仍可兜底
            get_logger("retriever").warning("向量检索失败，回退全文", exc_info=True)
            vec_hits = []
        # 按 doc_id 去重，保留每个 doc 的最高分片段
        best: dict[str, Hit] = {}
        for h in vec_hits + ft_hits:
            if self._excluded(h.source):
                continue
            cur = best.get(h.doc_id)
            if cur is None or h.score > cur.score:
                best[h.doc_id] = h
        merged = sorted(best.values(), key=lambda h: h.score, reverse=True)
        return merged[:k]

    def answer(self, query: str, k: int = 5) -> Answer:
        hits = self.search(query, k=k)
        if not hits:
            return Answer(text="我没有找到相关内容。", sources=[], attachments=[])
        context = "\n\n".join(f"[来源: {h.source}]\n{h.chunk}" for h in hits)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是知识库助手。只依据提供的资料回答；资料中没有就明确说没有，不要编造。"
                    "回答简洁，并在末尾不必重复来源（系统会单独展示）。"
                ),
            },
            {"role": "user", "content": f"资料：\n{context}\n\n问题：{query}"},
        ]
        text = self.llm.chat(messages, big=True)
        sources = list(dict.fromkeys(h.source for h in hits))
        attachments = [s for s in sources if _ATTACH_MARKER in s]
        return Answer(text=text, sources=sources, attachments=attachments)

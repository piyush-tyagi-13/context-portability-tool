from __future__ import annotations
from dataclasses import dataclass

from ctxkit.core.indexer.embedding_engine import EmbeddingEngine


@dataclass
class SummaryEmbeddings:
    full: list[float]
    sentences: list[tuple[str, list[float]]]   # (sentence_text, embedding)


class SummaryEmbedder:
    def __init__(self, engine: EmbeddingEngine) -> None:
        self._engine = engine

    def embed(self, summary: str) -> SummaryEmbeddings:
        full_emb = self._engine.embed_query(summary)
        sentences = _split_sentences(summary)
        sent_embs = self._engine.embed_texts(sentences) if sentences else []
        return SummaryEmbeddings(
            full=full_emb,
            sentences=list(zip(sentences, sent_embs)),
        )


def _split_sentences(text: str) -> list[str]:
    import re
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if len(s.strip().split()) >= 5]

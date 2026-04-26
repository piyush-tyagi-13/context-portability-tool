from __future__ import annotations
from langchain_core.documents import Document

from mdcore.store.vector_store import VectorStore
from mdcore.core.indexer.embedding_engine import EmbeddingEngine
from mdcore.config.models import IndexerConfig
from mdcore.utils.logging import get_logger

log = get_logger("indexer.writer")

# ChromaDB only supports these primitive types in metadata
_PRIMITIVE = (str, int, float, bool)


def _sanitize_metadata(meta: dict) -> dict:
    """Strip any non-primitive metadata fields (e.g. nested dicts) before upsert."""
    return {
        k: v for k, v in meta.items()
        if isinstance(v, _PRIMITIVE)
    }


class IndexWriter:
    def __init__(self, store: VectorStore, engine: EmbeddingEngine, cfg: IndexerConfig) -> None:
        self._store = store
        self._engine = engine
        self._batch_size = cfg.batch_size

    def write(self, chunks: list[Document], source_file: str) -> None:
        # Delete all existing chunks for this file first
        self._store.delete(source_file)

        # Sanitize metadata so ChromaDB doesn't reject nested dicts/lists
        clean_chunks = [
            Document(page_content=c.page_content, metadata=_sanitize_metadata(c.metadata))
            for c in chunks
        ]

        texts = [c.page_content for c in clean_chunks]
        embeddings: list[list[float]] = []

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i:i + self._batch_size]
            embeddings.extend(self._engine.embed_texts(batch))

        self._store.upsert(clean_chunks, embeddings)
        log.info("Indexed %d chunks for %s", len(chunks), source_file)

from __future__ import annotations
from langchain_core.documents import Document

from mdcore.store.vector_store import VectorStore
from mdcore.core.indexer.embedding_engine import EmbeddingEngine
from mdcore.config.models import RetrieverConfig
from mdcore.utils.logging import get_logger

log = get_logger("retriever.searcher")


class VectorSearcher:
    def __init__(self, store: VectorStore, engine: EmbeddingEngine, cfg: RetrieverConfig) -> None:
        self._store = store
        self._engine = engine
        self._cfg = cfg

    def search(self, query: str, candidate_sources: set[str] | None = None) -> list[Document]:
        query_emb = self._engine.embed_query(query)
        threshold = self._cfg.similarity_threshold

        # Phase 1 — broad vector search, filter to keyword candidates
        k = self._cfg.top_k * 2 if candidate_sources else self._cfg.top_k
        results = self._store.search(query_emb, k=k)

        if candidate_sources:
            results = [d for d in results if d.metadata.get("source_file") in candidate_sources]
            results = results[: self._cfg.top_k]

        filtered = [d for d in results if d.metadata.get("_similarity", 0) >= threshold]

        # Phase 2 — keyword-rescue: for candidate files that got zero chunks in
        # phase 1 (semantic mismatch — e.g. "emigration" query vs visa/sponsorship
        # content), do a targeted search at a relaxed threshold.
        # This ensures keyword-strong matches always get representation.
        if candidate_sources:
            represented = {d.metadata.get("source_file") for d in filtered}
            missing = candidate_sources - represented
            if missing:
                rescue_threshold = threshold * 0.75
                rescue_results = self._store.search_in_sources(query_emb, missing, k=self._cfg.top_k)
                rescued = [
                    d for d in rescue_results
                    if d.metadata.get("_similarity", 0) >= rescue_threshold
                ]
                if rescued:
                    log.debug(
                        "VectorSearcher phase-2 rescued %d chunks from %d files (threshold %.2f)",
                        len(rescued), len(missing), rescue_threshold,
                    )
                filtered.extend(rescued)

        log.debug("VectorSearcher: %d chunks pass threshold for '%s'", len(filtered), query)
        return filtered

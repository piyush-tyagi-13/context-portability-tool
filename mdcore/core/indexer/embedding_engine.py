from __future__ import annotations
import hashlib
import pickle
from pathlib import Path

from langchain_core.embeddings import Embeddings

from mdcore.config.models import EmbeddingsConfig
from mdcore.config.loader import expand_path
from mdcore.utils.logging import get_logger

log = get_logger("indexer.embeddings")

# nomic-embed-text: 8192 token context.
# Code-heavy content tokenizes at ~2.5–3 chars/token (vs ~4 for prose), so the
# practical char limit is much lower than (8192 × 4). Measured failures at ~22k chars.
# 6000 chars ≈ 1500–2400 tokens — well within limit for any content type.
# The full chunk text is still stored in ChromaDB; only the embedding is truncated.
_MAX_EMBED_CHARS = 6_000


def _truncate(text: str) -> str:
    if len(text) <= _MAX_EMBED_CHARS:
        return text
    log.warning("Chunk truncated for embedding (%d → %d chars)", len(text), _MAX_EMBED_CHARS)
    return text[:_MAX_EMBED_CHARS]


def _build_embeddings(cfg: EmbeddingsConfig) -> Embeddings:
    if cfg.backend == "ollama":
        from langchain_ollama import OllamaEmbeddings
        return OllamaEmbeddings(model=cfg.local_model)
    elif cfg.backend == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(model_name=cfg.local_model)
    elif cfg.backend == "openai":
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model=cfg.api_model, api_key=cfg.api_key)
    elif cfg.backend == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        return GoogleGenerativeAIEmbeddings(model=cfg.api_model, google_api_key=cfg.api_key)
    raise ValueError(f"Unknown embeddings backend: {cfg.backend}")


class EmbeddingEngine:
    def __init__(self, cfg: EmbeddingsConfig) -> None:
        self._cfg = cfg
        self._model = _build_embeddings(cfg)
        self._cache: dict[str, list[float]] = {}
        self._cache_path: Path | None = None
        if cfg.cache_embeddings:
            self._cache_path = expand_path(cfg.cache_path) / "embed_cache.pkl"
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_cache()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        safe_texts = [_truncate(t) for t in texts]

        if not self._cfg.cache_embeddings:
            return self._model.embed_documents(safe_texts)

        results: list[list[float]] = [None] * len(safe_texts)  # type: ignore
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, text in enumerate(safe_texts):
            key = self._hash(text)
            if key in self._cache:
                results[i] = self._cache[key]
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        if uncached_texts:
            new_embeddings = self._model.embed_documents(uncached_texts)
            for i, idx in enumerate(uncached_indices):
                key = self._hash(safe_texts[idx])
                self._cache[key] = new_embeddings[i]
                results[idx] = new_embeddings[i]
            self._save_cache()

        return results

    def embed_query(self, text: str) -> list[float]:
        return self._model.embed_query(_truncate(text))

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def _load_cache(self) -> None:
        if self._cache_path and self._cache_path.exists():
            try:
                with open(self._cache_path, "rb") as f:
                    self._cache = pickle.load(f)
                log.debug("Loaded %d cached embeddings", len(self._cache))
            except Exception:
                self._cache = {}

    def _save_cache(self) -> None:
        if self._cache_path:
            with open(self._cache_path, "wb") as f:
                pickle.dump(self._cache, f)

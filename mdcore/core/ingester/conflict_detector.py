from __future__ import annotations
import re
from dataclasses import dataclass

from mdcore.core.indexer.embedding_engine import EmbeddingEngine
from mdcore.config.models import IngesterConfig
from mdcore.utils.logging import get_logger

log = get_logger("ingester.conflict")


@dataclass
class ConflictPair:
    existing_sentence: str
    incoming_sentence: str
    similarity: float


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return (dot / (na * nb)) if na and nb else 0.0


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip().split()) >= 5]


class ConflictDetector:
    def __init__(self, engine: EmbeddingEngine, cfg: IngesterConfig) -> None:
        self._engine = engine
        self._cfg = cfg

    def detect(self, existing_text: str, incoming_text: str) -> list[ConflictPair]:
        if not self._cfg.conflict_detection:
            return []
        existing_sents = _split_sentences(existing_text)
        incoming_sents = _split_sentences(incoming_text)
        if not existing_sents or not incoming_sents:
            return []

        existing_embs = self._engine.embed_texts(existing_sents)
        incoming_embs = self._engine.embed_texts(incoming_sents)

        conflicts: list[ConflictPair] = []
        for i_text, i_emb in zip(incoming_sents, incoming_embs):
            for e_text, e_emb in zip(existing_sents, existing_embs):
                sim = _cosine_sim(i_emb, e_emb)
                if self._cfg.conflict_similarity_min <= sim <= self._cfg.conflict_similarity_max:
                    conflicts.append(ConflictPair(
                        existing_sentence=e_text,
                        incoming_sentence=i_text,
                        similarity=sim,
                    ))

        log.debug("ConflictDetector: %d potential conflicts", len(conflicts))
        return conflicts[:10]  # Cap to avoid overwhelming the proposal

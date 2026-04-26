from __future__ import annotations
import re
from dataclasses import dataclass

from langchain_core.documents import Document

from ctxkit.store.vector_store import VectorStore
from ctxkit.llm.llm_layer import LLMLayer, ClassificationResult
from ctxkit.config.models import IngesterConfig
from ctxkit.utils.logging import get_logger

log = get_logger("ingester.classify")


def _is_self_contained(text: str) -> bool:
    """Return True if the document looks like a standalone artefact.

    Heuristic: has 2+ H2 headings AND (a markdown table OR an ordered/unordered list
    with 3+ items). Such documents cover a distinct topic in full and should not be
    blindly appended to an existing file just because of topical similarity.
    """
    h2_count = len(re.findall(r"^#{1,2}\s+\S", text, re.MULTILINE))
    has_table = bool(re.search(r"^\|.+\|", text, re.MULTILINE))
    list_items = re.findall(r"^[\*\-\d]+[\.\)]\s+\S", text, re.MULTILINE)
    return h2_count >= 2 and (has_table or len(list_items) >= 3)


@dataclass
class ClassificationDecision:
    action: str            # "update" | "new"
    target_file: str | None
    confidence: float
    reasoning: str
    used_llm: bool
    top_scores: dict[str, float] = None  # file → similarity, top-k results


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class ClassificationEngine:
    def __init__(self, store: VectorStore, llm: LLMLayer, cfg: IngesterConfig) -> None:
        self._store = store
        self._llm = llm
        self._cfg = cfg

    def classify(self, summary_embedding: list[float], summary_text: str) -> ClassificationDecision:
        file_embeddings = self._store.file_embeddings()
        if not file_embeddings:
            return ClassificationDecision(action="new", target_file=None, confidence=1.0,
                                          reasoning="Empty index — all ingestions are new files.",
                                          used_llm=False, top_scores={})

        scores = {
            sf: _cosine_sim(summary_embedding, emb)
            for sf, emb in file_embeddings.items()
        }
        # Keep top-10 scores for folder routing downstream
        top_scores = dict(sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10])

        top_file = max(scores, key=lambda k: scores[k])
        top_score = scores[top_file]

        log.info("Classification top match: %s (%.3f)", top_file, top_score)

        if top_score > self._cfg.similarity_threshold_high and not _is_self_contained(summary_text):
            return ClassificationDecision(
                action="update", target_file=top_file,
                confidence=top_score, reasoning="Clear update match (above high threshold).",
                used_llm=False, top_scores=top_scores,
            )

        if top_score < self._cfg.similarity_threshold_low:
            return ClassificationDecision(
                action="new", target_file=None,
                confidence=1.0 - top_score, reasoning="Clear new file (below low threshold).",
                used_llm=False, top_scores=top_scores,
            )

        # Ambiguous — call LLM
        top_n = sorted(scores.items(), key=lambda x: x[1], reverse=True)[: self._cfg.max_candidates_for_llm]
        all_meta = self._store.all_metadata()
        candidates: list[Document] = []
        for sf, _ in top_n:
            snippet = next((m.get("source_file", "") for m in all_meta if m.get("source_file") == sf), sf)
            candidates.append(Document(page_content=snippet, metadata={"source_file": sf}))

        result: ClassificationResult = self._llm.classify(summary_text, candidates)
        return ClassificationDecision(
            action=result.action,
            target_file=result.target_file,
            confidence=result.confidence,
            reasoning=result.reasoning,
            used_llm=True,
            top_scores=top_scores,
        )

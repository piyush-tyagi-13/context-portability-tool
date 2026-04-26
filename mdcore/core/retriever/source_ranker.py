from __future__ import annotations
from mdcore.core.retriever.chunk_stitcher import StitchedPassage
from mdcore.utils.logging import get_logger

log = get_logger("retriever.ranker")


def rank_sources(
    passages_by_source: dict[str, list[StitchedPassage]],
) -> list[tuple[str, list[StitchedPassage]]]:
    """Return sources sorted by aggregate (mean) similarity score descending."""
    scored: list[tuple[float, str, list[StitchedPassage]]] = []
    for sf, passages in passages_by_source.items():
        agg = sum(p.avg_similarity for p in passages) / max(len(passages), 1)
        scored.append((agg, sf, passages))
    scored.sort(key=lambda x: x[0], reverse=True)
    log.debug("SourceRanker: top source = %s (%.3f)", scored[0][1] if scored else "none", scored[0][0] if scored else 0)
    return [(sf, passages) for _, sf, passages in scored]

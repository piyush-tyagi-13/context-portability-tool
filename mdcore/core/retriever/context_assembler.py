from __future__ import annotations
from dataclasses import dataclass

from mdcore.core.retriever.chunk_stitcher import StitchedPassage
from mdcore.config.models import RetrieverConfig
from mdcore.utils.logging import get_logger

log = get_logger("retriever.assembler")


@dataclass
class AssembledContext:
    query: str
    primary: list[tuple[str, list[StitchedPassage]]]   # (source_file, passages)
    signpost: list[tuple[str, list[str]]]               # (source_file, breadcrumbs)
    total_words: int
    source_count: int


def assemble(
    query: str,
    ranked: list[tuple[str, list[StitchedPassage]]],
    cfg: RetrieverConfig,
) -> AssembledContext:
    budget = cfg.context_block_max_words
    remaining = budget
    primary: list[tuple[str, list[StitchedPassage]]] = []
    signpost: list[tuple[str, list[str]]] = []

    for source_file, passages in ranked:
        # Cap passages per source
        capped = passages[: cfg.max_chunks_per_source]
        total_wc = sum(p.word_count for p in capped)

        if total_wc <= remaining:
            primary.append((source_file, capped))
            remaining -= total_wc
        elif remaining > 100:
            # Truncate to fit remaining budget
            truncated: list[StitchedPassage] = []
            for p in capped:
                if p.word_count <= remaining:
                    truncated.append(p)
                    remaining -= p.word_count
                else:
                    words = p.text.split()
                    trunc_text = " ".join(words[:remaining]) + " ..."
                    truncated.append(StitchedPassage(
                        source_file=p.source_file,
                        text=trunc_text,
                        breadcrumbs=p.breadcrumbs,
                        chunk_indices=p.chunk_indices,
                        word_count=remaining,
                        avg_similarity=p.avg_similarity,
                    ))
                    remaining = 0
                    break
            if truncated:
                primary.append((source_file, truncated))
            all_bc = [bc for p in capped for bc in p.breadcrumbs]
            if len(signpost) < cfg.signpost_max_items:
                signpost.append((source_file, all_bc))
            remaining = 0
        else:
            if len(signpost) < cfg.signpost_max_items:
                all_bc = [bc for p in passages for bc in p.breadcrumbs]
                signpost.append((source_file, all_bc))

    total_words = budget - remaining
    log.debug("Assembled %d words from %d sources; signpost=%d", total_words, len(primary), len(signpost))
    return AssembledContext(
        query=query,
        primary=primary,
        signpost=signpost,
        total_words=total_words,
        source_count=len(primary),
    )

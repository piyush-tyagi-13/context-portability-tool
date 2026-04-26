from __future__ import annotations
from dataclasses import dataclass, field

from langchain_core.documents import Document

from mdcore.config.models import RetrieverConfig
from mdcore.utils.file_utils import word_count
from mdcore.utils.logging import get_logger

log = get_logger("retriever.stitcher")


@dataclass
class StitchedPassage:
    source_file: str
    text: str
    breadcrumbs: list[str]
    chunk_indices: list[int]
    word_count: int
    avg_similarity: float


def stitch(
    source_file: str,
    chunks: list[Document],
    cfg: RetrieverConfig,
) -> list[StitchedPassage]:
    """Stitch adjacent/near-adjacent chunks within a single source into passages."""
    if not chunks:
        return []

    # Index all chunks by their chunk_index for gap-filling
    by_index = {c.metadata.get("chunk_index", i): c for i, c in enumerate(chunks)}
    retrieved_indices = sorted(by_index.keys())

    passages: list[StitchedPassage] = []
    used: set[int] = set()

    for idx in retrieved_indices:
        if idx in used:
            continue
        group_indices = [idx]
        used.add(idx)

        # Extend group by near-adjacent indices (up to stitch_distance gap)
        probe = idx + 1
        while True:
            gap = probe - group_indices[-1]
            if gap > cfg.stitch_distance:
                break
            if probe in retrieved_indices and probe not in used:
                group_indices.append(probe)
                used.add(probe)
                probe += 1
            elif probe not in retrieved_indices:
                # Fill gap chunk if it gets us to a retrieved index within distance
                next_retrieved = next((i for i in retrieved_indices if i > probe and i not in used), None)
                if next_retrieved is not None and (next_retrieved - group_indices[-1]) <= cfg.stitch_distance:
                    for fill in range(probe, next_retrieved + 1):
                        group_indices.append(fill)
                        used.add(fill)
                    probe = next_retrieved + 1
                else:
                    break
            else:
                break

            if len(group_indices) >= cfg.max_chunks_per_source + 2:
                break

        # Fetch actual chunks for group (may include gap chunks from store if available)
        passage_chunks = [by_index[i] for i in sorted(group_indices) if i in by_index]
        text = "\n\n".join(c.page_content for c in passage_chunks)
        wc = word_count(text)

        # If over stitch_max_words, truncate
        if wc > cfg.stitch_max_words:
            words = text.split()
            text = " ".join(words[: cfg.stitch_max_words]) + " ..."
            wc = cfg.stitch_max_words

        breadcrumbs = list(dict.fromkeys(
            c.metadata.get("heading_breadcrumb", "") for c in passage_chunks if c.metadata.get("heading_breadcrumb")
        ))
        similarities = [c.metadata.get("_similarity", 0.0) for c in passage_chunks]
        avg_sim = sum(similarities) / max(len(similarities), 1)

        passages.append(StitchedPassage(
            source_file=source_file,
            text=text,
            breadcrumbs=breadcrumbs,
            chunk_indices=sorted(group_indices),
            word_count=wc,
            avg_similarity=avg_sim,
        ))

    log.debug("ChunkStitcher: %s → %d passages", source_file, len(passages))
    return passages

from __future__ import annotations
from langchain_core.documents import Document

from ctxkit.utils.logging import get_logger

log = get_logger("retriever.grouper")


def group_by_source(chunks: list[Document]) -> dict[str, list[Document]]:
    """Group chunks by source_file, sorted by chunk_index within each source."""
    groups: dict[str, list[Document]] = {}
    for chunk in chunks:
        sf = chunk.metadata.get("source_file", "unknown")
        groups.setdefault(sf, []).append(chunk)
    for sf in groups:
        groups[sf].sort(key=lambda d: d.metadata.get("chunk_index", 0))
    log.debug("ChunkGrouper: %d sources", len(groups))
    return groups

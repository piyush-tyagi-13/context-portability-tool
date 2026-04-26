from __future__ import annotations
from pathlib import Path

from mdcore.utils.logging import get_logger

log = get_logger("writer.trigger")


class IndexTrigger:
    """Triggers a single-file reindex after a write operation."""

    def __init__(self, indexer_factory) -> None:
        # Accepts a callable that returns (loader, splitter, writer, manifest) tuple
        self._factory = indexer_factory

    def reindex(self, path: Path) -> None:
        loader, splitter, writer, manifest = self._factory()
        doc = loader.load(path)
        chunks = splitter.split(doc)
        source_file = doc.metadata.get("source_file", str(path))
        writer.write(chunks, source_file)
        manifest.update(path)
        log.info("Reindexed: %s", source_file)

from __future__ import annotations
import re
from datetime import datetime, timezone

from langchain_core.documents import Document

from mdcore.config.models import IndexerConfig
from mdcore.utils.file_utils import word_count
from mdcore.utils.logging import get_logger

log = get_logger("indexer.splitter")

_TABLE_RE = re.compile(r"(\|.+\|\n?)+", re.MULTILINE)
_CODE_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)


class TextSplitter:
    def __init__(self, cfg: IndexerConfig) -> None:
        self._cfg = cfg

    def split(self, doc: Document) -> list[Document]:
        content = doc.page_content
        if self._cfg.heading_aware_splitting:
            sections = self._split_by_headings(content)
        else:
            sections = [("", content)]

        chunks: list[tuple[str, str]] = []
        for breadcrumb, text in sections:
            text = text.strip()
            if not text:
                continue
            wc = word_count(text)
            if wc < self._cfg.min_word_count:
                if chunks:
                    prev_bc, prev_text = chunks[-1]
                    chunks[-1] = (prev_bc, prev_text + "\n\n" + text)
                    continue
            if wc > self._cfg.max_chunk_words:
                sub = self._split_by_tokens(text, breadcrumb)
                chunks.extend(sub)
            else:
                chunks.append((breadcrumb, text))

        now = datetime.now(timezone.utc).isoformat()
        total = len(chunks)
        result: list[Document] = []
        for idx, (breadcrumb, text) in enumerate(chunks):
            is_table = bool(_TABLE_RE.search(text))
            is_code = bool(_CODE_RE.search(text))
            meta = {
                **doc.metadata,
                "heading_breadcrumb": breadcrumb,
                "chunk_index": idx,
                "chunk_total": total,
                "word_count": word_count(text),
                "is_table": is_table,
                "is_code": is_code,
                "last_indexed": now,
            }
            result.append(Document(page_content=text, metadata=meta))
        log.debug("Split %s into %d chunks", doc.metadata.get("source_file"), total)
        return result

    def _split_by_headings(self, content: str) -> list[tuple[str, str]]:
        """Split on configured heading levels, returning (breadcrumb, text) pairs."""
        levels = self._cfg.heading_levels
        pattern = "^(#{" + str(min(levels)) + "," + str(max(levels)) + r"})\s+(.+)$"
        heading_re = re.compile(pattern, re.MULTILINE)

        sections: list[tuple[str, str]] = []
        heading_stack: list[tuple[int, str]] = []  # (level, title)
        last_end = 0

        for m in heading_re.finditer(content):
            # Flush previous section
            text = content[last_end:m.start()].strip()
            if text:
                bc = self._breadcrumb(heading_stack)
                sections.append((bc, text))

            level = len(m.group(1))
            title = m.group(2).strip()
            # Maintain heading stack
            heading_stack = [(l, t) for l, t in heading_stack if l < level]
            heading_stack.append((level, title))
            last_end = m.end()

        # Remaining text after last heading
        tail = content[last_end:].strip()
        if tail:
            sections.append((self._breadcrumb(heading_stack), tail))

        # If nothing was split, return the whole content
        if not sections:
            sections = [("", content)]
        return sections

    def _breadcrumb(self, stack: list[tuple[int, str]]) -> str:
        return " > ".join(t for _, t in stack)

    def _split_by_tokens(self, text: str, breadcrumb: str) -> list[tuple[str, str]]:
        """Simple word-count-based split with overlap, preserving tables and code blocks."""
        if self._cfg.preserve_tables and _TABLE_RE.search(text):
            return [(breadcrumb, text)]
        if self._cfg.preserve_code_blocks and _CODE_RE.search(text):
            return [(breadcrumb, text)]

        words = text.split()
        size = self._cfg.chunk_size  # treat chunk_size as word count for simplicity
        overlap = self._cfg.chunk_overlap
        chunks = []
        start = 0
        while start < len(words):
            end = min(start + size, len(words))
            chunk_text = " ".join(words[start:end])
            chunks.append((breadcrumb, chunk_text))
            if end == len(words):
                break
            start += size - overlap
        return chunks

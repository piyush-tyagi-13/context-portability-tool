from __future__ import annotations
from pathlib import Path

import frontmatter
from langchain_core.documents import Document

from ctxkit.config.models import VaultConfig
from ctxkit.utils.file_utils import vault_relative_path, folder_path_from_relative
from ctxkit.utils.logging import get_logger

log = get_logger("indexer.loader")


class DocumentLoader:
    def __init__(self, vault_cfg: VaultConfig) -> None:
        self._vault_path = Path(vault_cfg.path).expanduser()

    def load(self, path: Path) -> Document:
        raw = path.read_text(encoding="utf-8", errors="ignore")
        try:
            post = frontmatter.loads(raw)
            content = post.content
            fm = dict(post.metadata)
        except Exception:
            content = raw
            fm = {}

        rel = vault_relative_path(path, self._vault_path)
        folder = folder_path_from_relative(rel)

        metadata = {
            "source_file": rel,
            "folder_path": folder,
            "filename": path.name,
            "frontmatter": fm,
        }
        log.debug("Loaded: %s", rel)
        return Document(page_content=content, metadata=metadata)

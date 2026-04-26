from __future__ import annotations
from datetime import date
from pathlib import Path

import frontmatter

from ctxkit.config.models import FrontmatterConfig
from ctxkit.utils.logging import get_logger

log = get_logger("writer.frontmatter")


class FrontmatterInjector:
    def __init__(self, cfg: FrontmatterConfig) -> None:
        self._cfg = cfg

    def inject(self, path: Path, updates: dict) -> str:
        """Return updated file content string with merged frontmatter."""
        raw = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        try:
            post = frontmatter.loads(raw)
        except Exception:
            post = frontmatter.loads("")
            post.content = raw

        for field in self._cfg.fields:
            if field not in updates:
                continue
            if field == "tags":
                existing = list(post.metadata.get("tags", []))
                new_tags = updates["tags"]
                merged = list(dict.fromkeys(existing + new_tags))
                post.metadata["tags"] = merged[: self._cfg.tag_max_count]
            elif field == "related":
                existing = list(post.metadata.get("related", []))
                new_related = updates["related"]
                merged = list(dict.fromkeys(existing + new_related))
                post.metadata["related"] = merged[: self._cfg.related_max_count]
            elif field == "updated":
                post.metadata["updated"] = updates.get("updated", str(date.today()))
            else:
                post.metadata[field] = updates[field]

        result = frontmatter.dumps(post)
        log.debug("Frontmatter injected for %s", path.name)
        return result

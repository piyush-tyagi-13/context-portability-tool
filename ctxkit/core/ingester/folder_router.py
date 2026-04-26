from __future__ import annotations
from pathlib import Path

from ctxkit.config.models import IngesterConfig, VaultConfig
from ctxkit.core.vault_map import VaultMap
from ctxkit.utils.logging import get_logger

log = get_logger("ingester.folder_router")


class FolderRouter:
    def __init__(self, vault_cfg: VaultConfig, cfg: IngesterConfig) -> None:
        self._vault_path = Path(vault_cfg.path).expanduser()
        self._confidence_threshold = cfg.folder_routing_confidence
        self._vault_map = VaultMap(self._vault_path)

    def route(self, summary: str) -> tuple[str, float]:
        """Return (suggested_folder, confidence).

        Scoring strategy:
          1. For each folder, build a search corpus = folder name tokens
             + description tokens (if available). Description tokens are
             weighted 3× to dominate over bare folder-name matching.
          2. Score = overlap(summary_terms, corpus) / len(corpus_unique_terms)
          3. Return best match and its score.
        """
        terms = set(summary.lower().split())
        folders = self._get_folders()
        descriptions = self._vault_map.folder_descriptions()

        if not folders:
            return ("", 0.0)

        best_folder = ""
        best_score = 0.0

        for folder in folders:
            # Folder name tokens
            name_tokens = set(folder.lower().replace("/", " ").replace("-", " ").split())

            # Description tokens (weighted 3x by repeating them)
            desc = descriptions.get(folder, "")
            desc_tokens = set(desc.lower().split()) if desc else set()

            corpus = name_tokens | desc_tokens
            # Weighted overlap: desc token matches count 3x
            name_overlap = len(terms & name_tokens)
            desc_overlap = len(terms & desc_tokens) * 3
            total_overlap = name_overlap + desc_overlap
            score = total_overlap / max(len(corpus), 1)

            if score > best_score:
                best_score = score
                best_folder = folder

        # If best match has a description, confidence is higher
        if best_folder and best_folder in descriptions:
            best_score = min(best_score * 1.2, 1.0)

        log.debug("FolderRouter: '%s' (%.2f)", best_folder, best_score)
        return (best_folder, best_score)

    def needs_confirmation(self, confidence: float) -> bool:
        return confidence < self._confidence_threshold

    def _get_folders(self) -> list[str]:
        folders = []
        for p in self._vault_path.rglob("*"):
            if p.is_dir():
                try:
                    rel = str(p.relative_to(self._vault_path))
                    if not any(part.startswith(".") for part in rel.split("/")):
                        folders.append(rel)
                except ValueError:
                    pass
        return folders

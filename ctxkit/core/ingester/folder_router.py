from __future__ import annotations
from pathlib import Path

from ctxkit.config.models import IngesterConfig, VaultConfig
from ctxkit.utils.logging import get_logger

log = get_logger("ingester.folder_router")


class FolderRouter:
    def __init__(self, vault_cfg: VaultConfig, cfg: IngesterConfig) -> None:
        self._vault_path = Path(vault_cfg.path).expanduser()
        self._confidence_threshold = cfg.folder_routing_confidence

    def route(self, summary: str) -> tuple[str, float]:
        """Return (suggested_folder, confidence)."""
        terms = set(summary.lower().split())
        folders = self._get_folders()
        if not folders:
            return ("", 0.0)

        best_folder = ""
        best_score = 0.0
        for folder in folders:
            folder_terms = set(folder.lower().replace("/", " ").replace("-", " ").split())
            overlap = len(terms & folder_terms)
            score = overlap / max(len(folder_terms), 1)
            if score > best_score:
                best_score = score
                best_folder = folder

        log.debug("FolderRouter: '%s' (%.2f)", best_folder, best_score)
        return (best_folder, best_score)

    def needs_confirmation(self, confidence: float) -> bool:
        return confidence < self._confidence_threshold

    def _get_folders(self) -> list[str]:
        folders = []
        for p in self._vault_path.rglob("*"):
            if p.is_dir():
                try:
                    folders.append(str(p.relative_to(self._vault_path)))
                except ValueError:
                    pass
        return folders

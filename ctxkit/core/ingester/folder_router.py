from __future__ import annotations
from pathlib import Path

from ctxkit.config.models import IngesterConfig, VaultConfig
from ctxkit.core.vault_map import VaultMap
from ctxkit.llm.llm_layer import LLMLayer, FolderRoutingResult
from ctxkit.utils.logging import get_logger

log = get_logger("ingester.folder_router")


class FolderRouter:
    def __init__(self, vault_cfg: VaultConfig, cfg: IngesterConfig, llm: LLMLayer) -> None:
        self._vault_path = Path(vault_cfg.path).expanduser()
        self._confidence_threshold = cfg.folder_routing_confidence
        self._vault_map = VaultMap(self._vault_path)
        self._llm = llm

    def route(self, document: str) -> tuple[str, float]:
        """Return (suggested_folder, confidence) using LLM routing."""
        folders = self._get_folders()
        if not folders:
            return ("", 0.0)

        descriptions = self._vault_map.folder_descriptions()
        result: FolderRoutingResult = self._llm.route_folder(document, folders, descriptions)
        log.info("FolderRouter LLM: '%s' (%.2f) — %s", result.folder, result.confidence, result.reasoning)
        return (result.folder, result.confidence)

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
        return sorted(folders)

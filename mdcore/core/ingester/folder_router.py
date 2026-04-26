from __future__ import annotations
from pathlib import Path

from langchain_core.documents import Document

from mdcore.config.models import IngesterConfig, VaultConfig
from mdcore.core.vault_map import VaultMap
from mdcore.llm.llm_layer import LLMLayer, FolderRoutingResult
from mdcore.utils.logging import get_logger

log = get_logger("ingester.folder_router")

# If the best semantic match is below this threshold the top-k files
# are too dissimilar to reliably derive candidate folders from —
# fall back to passing the full folder list to LLM.
_SEMANTIC_FALLBACK_THRESHOLD = 0.60


class FolderRouter:
    def __init__(self, vault_cfg: VaultConfig, cfg: IngesterConfig, llm: LLMLayer) -> None:
        self._vault_path = Path(vault_cfg.path).expanduser()
        self._confidence_threshold = cfg.folder_routing_confidence
        self._vault_map = VaultMap(self._vault_path)
        self._llm = llm

    def route(self, document: str, top_scores: dict[str, float] | None = None) -> tuple[str, float]:
        """Return (suggested_folder, confidence).

        Two-stage strategy:
          1. Derive candidate folders from top-k semantic matches already
             computed during classification (zero extra API calls).
          2. LLM picks the best folder from those candidates + optional
             vault map descriptions as context.

        Fallback: if max similarity is below _SEMANTIC_FALLBACK_THRESHOLD
        (doc is novel, no close matches), pass the full folder list to LLM.
        """
        descriptions = self._vault_map.folder_descriptions()
        all_folders = self._get_folders()

        if not all_folders:
            return ("", 0.0)

        # Stage 1 — derive candidate folders from top-k semantic matches
        candidate_folders: list[str] = []
        max_sim = 0.0

        if top_scores:
            max_sim = max(top_scores.values())
            if max_sim >= _SEMANTIC_FALLBACK_THRESHOLD:
                candidate_folders = self._extract_candidate_folders(top_scores, all_folders)
                log.info(
                    "FolderRouter: semantic candidates %s (max_sim=%.2f)",
                    candidate_folders, max_sim,
                )

        if not candidate_folders:
            # Fallback — use full folder list
            candidate_folders = all_folders
            log.info("FolderRouter: falling back to full folder list (%d folders)", len(all_folders))

        # Stage 2 — LLM picks from candidates
        result: FolderRoutingResult = self._llm.route_folder(document, candidate_folders, descriptions)

        # Validate result is in all_folders (LLM might pick from candidate subset
        # but we want to ensure it's a real vault path)
        if result.folder not in all_folders:
            log.warning("LLM returned unknown folder '%s', falling back to full list", result.folder)
            result = self._llm.route_folder(document, all_folders, descriptions)

        log.info("FolderRouter result: '%s' (%.2f) — %s", result.folder, result.confidence, result.reasoning)
        return (result.folder, result.confidence)

    def needs_confirmation(self, confidence: float) -> bool:
        return confidence < self._confidence_threshold

    def _extract_candidate_folders(
        self, top_scores: dict[str, float], all_folders: list[str]
    ) -> list[str]:
        """Derive unique parent folders from top-k matching files.

        For each top file, walk up its path to find the deepest folder
        that exists in the vault folder list.
        """
        seen: dict[str, float] = {}  # folder → best similarity score
        for file_path, sim in top_scores.items():
            p = Path(file_path)
            # Try most-specific to least-specific folder
            for parent in [str(p.parent)] + [str(p.parents[i]) for i in range(1, len(p.parents))]:
                if parent in all_folders:
                    if parent not in seen or sim > seen[parent]:
                        seen[parent] = sim
                    break  # use most specific match

        if not seen:
            return all_folders

        # Sort by descending similarity, return top 5
        return [f for f, _ in sorted(seen.items(), key=lambda x: x[1], reverse=True)[:5]]

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
